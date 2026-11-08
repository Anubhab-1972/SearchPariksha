"""
Automated Exam Date Updater using Google Gemini AI with Google Search Grounding.

This script:
1. Reads the current exams.json file
2. For each exam, asks Gemini AI to search the internet for the latest dates
3. Updates exams.json with the freshest information
4. Commits the changes to the GitHub repository (when run via GitHub Actions)

Usage:
  - Locally:  python update_exams.py
  - Via GitHub Actions: Runs automatically every Monday at 2:00 AM IST
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime

print(f"Python version: {sys.version}")
try:
    import google.genai as genai_check
    print(f"google-genai version: {genai_check.__version__}")
except Exception as e:
    print(f"Could not get version: {e}")

try:
    from google import genai
    from google.genai import types
    print("google-genai imported OK")
except ImportError as e:
    print(f"ERROR: google-genai package not installed: {e}")
    sys.exit(1)

# --- Configuration ---
EXAMS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exams.json")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not set.")
    print("Set it with: export GEMINI_API_KEY='your-key-here'")
    sys.exit(1)

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Model selection ---------------------------------------------------------
# Gemini model names get retired. When that happens every request returns
# 404 NOT_FOUND; the old code swallowed that, so the site quietly went stale for
# weeks while the workflow kept reporting success. We try these in order and
# stick with the first one that actually answers.
MODEL_CANDIDATES = []
_env_model = os.environ.get("GEMINI_MODEL", "").strip()
if _env_model:
    MODEL_CANDIDATES.append(_env_model)
MODEL_CANDIDATES += [
    "gemini-3.5-flash-lite",      # Primary: highest free-tier quota, low latency, structured JSON extraction
    "gemini-flash-latest",        # Google's rolling flash alias
    "gemini-3.8-flash",           # Full reasoning flash
    "gemini-3.5-flash",           # Stable 3.5 flash
    "gemini-2.5-flash",           # Fallback flash
]

_model_index = 0
stats = {
    "queries": 0,
    "failures": 0,
    "retired_models": [],
    "quota_switches": [],
    "quota_exhausted": False,
    "auth_error": False,
}


def current_model():
    return MODEL_CANDIDATES[min(_model_index, len(MODEL_CANDIDATES) - 1)]


def list_available_models():
    """Ask the API which models this key can really use, so failures explain themselves."""
    try:
        names = set()
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = (getattr(m, "supported_actions", None)
                       or getattr(m, "supported_generation_methods", None) or [])
            if name and (not actions or any("generateContent" in str(a) for a in actions)):
                names.add(name)
        return sorted(names)
    except Exception as e:
        return ["<could not list models: %s>" % e]


def load_exams():
    """Load the current exams database from JSON file."""
    with open(EXAMS_JSON_PATH, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips BOM if present
        return json.load(f)

def save_exams(exams):
    """Save the updated exams database to JSON file."""
    with open(EXAMS_JSON_PATH, "w", encoding="utf-8") as f:  # utf-8 without BOM
        json.dump(exams, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {len(exams)} exams to {EXAMS_JSON_PATH}")

def query_exam_status(exam_name, exam_desc, current_status="UPCOMING", current_datestr="", official_link=""):
    """
    Ask Gemini AI for the latest dates and status code with stage-aware rules.
    - If registration hasn't opened yet: ONLY look for registration/notification (NEVER search for admit cards).
    - If registration is live: check for deadline extensions or registration close.
    - If registration has closed: look for Admit Card, Exam Date, or Results.
    """
    global _model_index
    today = datetime.now().strftime("%B %d, %Y")
    current_year = datetime.now().year
    
    # Check if this exam is currently waiting for notification/registration to open
    is_pre_registration = (
        current_status == "UPCOMING" and 
        not any(w in (current_datestr or "").lower() for w in ["registration ended", "ended", "admit card", "results"])
    )
    
    if is_pre_registration:
        # STAGE 1: Registration has NOT opened yet (e.g. TIFR, AAI ATC, ICMR BRET, GPAT)
        # The bot MUST ONLY check whether registration/notification has opened!
        # It must NEVER search for or return Admit Card status here!
        prompt = f"""Today is {today}. I am tracking the upcoming Indian national-level competitive exam: "{exam_name}" ({exam_desc}).
Official conducting body portal: {official_link or "Official exam portal"}.
Current site status: "{current_datestr}".

The application window for the upcoming cycle ({current_year} or {current_year+1}) has NOT opened yet on our site.

STRICT VERIFICATION & ANTI-HALLUCINATION RULES:
1. STRICT EXAM IDENTITY (CRITICAL):
   - The announcement MUST be SPECIFICALLY and EXCLUSIVELY for "{exam_name}".
   - DO NOT confuse other exams conducted by the same authority!
     * NBEMS (natboard.edu.in) conducts GPAT, NEET PG, NEET MDS, DNB PDCET, FMGE, etc. A notice or application form for DNB or NEET is NOT GPAT!
     * NTA (nta.ac.in) conducts CSIR NET, UGC NET, JEE, NEET, CUET, etc. A notice for CSIR NET is NOT UGC NET or GPAT!
     * UPSC (upsc.gov.in) conducts CSE, IES/ESE, CDS, NDA, etc. A notice for CDS is NOT IES/ESE!
     * SSC (ssc.gov.in) conducts CGL, CHSL, MTS, GD, etc. A notice for GD is NOT CGL or CHSL!
   - If the conducting portal has an active registration form for a DIFFERENT examination, IGNORE IT.
2. ENTRANCE EXAM VS. COLLEGE ADMISSION / COUNSELLING:
   - DO NOT mistake state pharmacy/engineering counselling, institutional admission forms, or private college admission rounds for the national "{exam_name}" entrance exam.
3. DO NOT TRUST SPECULATIVE BLOGS:
   - Ignore speculative, estimated, or clickbait dates from coaching blogs or aggregators (e.g. Shiksha, Prepp, CollegeDunia) unless the official notification / Information Bulletin is ACTUALLY released on {official_link or 'the official portal'}.
4. NO ADMIT CARDS:
   - Admit cards CANNOT exist before registration opens. Ignore past years' articles.
5. CONSERVATIVE DEFAULT:
   - When in doubt, or if registration is merely expected/tentative, keep status_code as "UPCOMING". Only return "LIVE_REGISTRATION_OPEN" if the official application link specifically for "{exam_name}" is ACTIVE AND LIVE right now on the official conducting website.

Check official sources:
1. Has official registration / application form specifically for "{exam_name}" OPENED for the new cycle?
   -> If YES (confirmed live on official portal specifically for {exam_name}): status_code: "LIVE_REGISTRATION_OPEN", display_text: "Registration Open! Apply by [Date]"
2. If registration has NOT opened yet:
   -> status_code: "UPCOMING", display_text: "Expected Registration: [Month Year]" or "Registration starts [Date]" (if an official start date is formally scheduled).

CRITICAL: Output ONLY a JSON object with:
- 'status_code': "LIVE_REGISTRATION_OPEN" or "UPCOMING"
- 'display_text': A short string (max 80 chars)
"""
    elif current_status == "LIVE_REGISTRATION_OPEN":
        # STAGE 2: Registration is currently OPEN (e.g. GATE, CSIR NET, TIFR)
        prompt = f"""Today is {today}. The Indian competitive exam: "{exam_name}" ({exam_desc}) currently has registration open on our site ("{current_datestr}").
Official conducting body portal: {official_link or "Official exam portal"}.

STRICT RULES:
1. SPECIFIC EXAM ONLY: Ensure all checks apply strictly to "{exam_name}", NOT any other exam conducted by the same body.
2. Check if registration for "{exam_name}" is still open or has officially CLOSED:
   - If still open or deadline officially extended: -> status_code: "LIVE_REGISTRATION_OPEN", display_text: "Registration Open! Apply by [Date]"
   - If closed and Admit Card is ALREADY confirmed downloadable on official website: -> status_code: "LIVE_ADMIT_CARD", display_text: "Admit Card Released! Exam Date: [Date]"
   - If closed and waiting for exam/admit card: -> status_code: "UPCOMING", display_text: "Registration ended! Exam Date: [Date] (Admit Card to be announced)"
   - If exam has already concluded or results announced: -> status_code: "UPCOMING", display_text: "Registration ended! Opens next year (Expected: [Month Year])"

CRITICAL: Output ONLY a JSON object with 'status_code' and 'display_text'.
"""
    else:
        # STAGE 3: Registration has CLOSED (e.g. SSC CGL, IBPS PO, TIFR GS, SBI PO)
        # NOW it is appropriate to look for Admit Card, City Intimation, or Exam Date!
        prompt = f"""Today is {today}. For the Indian competitive exam: "{exam_name}" ({exam_desc}), registration has already closed.
Official conducting body portal: {official_link or "Official exam portal"}.
Current site status: "{current_datestr}".

STRICT VERIFICATION & ANTI-HALLUCINATION RULES:
1. STRICT ADMIT CARD VERIFICATION (CRITICAL):
   - The Admit Card / Hall Ticket MUST be confirmed as ACTUALLY AVAILABLE FOR DOWNLOAD on the official conducting portal: {official_link or "official portal"}.
   - DO NOT TRUST aggregator or coaching articles (Careers360, Shiksha, Adda247, Testbook, Jagran Josh, Prepp, etc.) that publish clickbait titles like "Admit Card Released" or "Hall Ticket Out" with placeholder, tentative, or past years' links!
   - If the official schedule/portal states the admit card will be released in the future (e.g., "expected mid-November", "available 2 weeks before exam", or a specific future release date), the admit card is NOT out yet! Status MUST remain "UPCOMING".
2. SPECIFIC EXAM IDENTITY ONLY:
   - Check strictly for "{exam_name}". Do NOT confuse admit cards, exam dates, or notices of other exams held by the same authority.
3. CONCLUDED EXAMS & FINAL RESULTS ARE "UPCOMING" (NEVER LIVE):
   - When an exam has already been held or its final results have been announced, that examination cycle has CONCLUDED. It is NOT a live exam!
   - Live Exams on our platform is exclusively for active registration forms and downloadable admit cards.
   - For any concluded cycle or announced results: -> status_code: "UPCOMING", display_text: "Registration ended! Opens next year (Expected: [Month Year])". NEVER return a LIVE status code for a concluded exam or final results!
4. CONSERVATIVE DEFAULT:
   - When in doubt, or while waiting for the official admit card download link to go live on the official portal, KEEP status_code as "UPCOMING" with display_text mentioning the exam date and that admit card is to be announced.

Check official sources:
1. Has the Admit Card or City Intimation slip been officially RELEASED and confirmed downloadable right now on the official portal?
   - If Admit Card is active and downloadable on official portal: -> status_code: "LIVE_ADMIT_CARD", display_text: "Admit Card Released! Exam Date: [Date]"
   - If City Intimation slip is active on official portal: -> status_code: "LIVE_CITY_INTIMATION", display_text: "City Intimation Live! Exam Date: [Date]"
2. If registration ended and waiting for exam date / admit card:
   -> status_code: "UPCOMING", display_text: "Registration ended! Exam Date: [Date] (Admit Card to be announced)" or "{current_datestr}"
3. If exam has already taken place / CONCLUDED or final results announced:
   -> status_code: "UPCOMING", display_text: "Registration ended! Opens next year (Expected: [Month Year])"

CRITICAL: Output ONLY a JSON object with 'status_code' and 'display_text'.
"""

    max_retries = 2          # tries on one model before moving to another
    max_model_hops = 3       # different models to try for a single exam
    attempt = 0
    hops = 0
    while attempt < max_retries:
        stats["queries"] += 1
        try:
            response = client.models.generate_content(
                model=current_model(),
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a strict data extraction bot. ONLY output a valid JSON object.",
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.0
                ),
            )
            text = response.text.strip()
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            print(f"  [WARN] {exam_name}: Response text did not contain valid JSON: {text[:100]}...")
            return None
        except Exception as e:
            err_msg = str(e).lower()
            is_auth_error = ("api_key" in err_msg or "401" in err_msg or "permission_denied" in err_msg or "key not valid" in err_msg)
            if is_auth_error:
                stats["auth_error"] = True

            is_missing_model = ("404" in err_msg or "not_found" in err_msg
                                or "no longer available" in err_msg
                                or "is not supported" in err_msg)
            is_rate_limit = ("429" in err_msg or "resource_exhausted" in err_msg
                             or "quota" in err_msg)

            if is_rate_limit:
                stats["quota_exhausted"] = True

            # "This model is retired" and "this model is out of quota" both mean the
            # same thing to us: it cannot serve us right now. Free-tier quota is
            # per model, so moving to the next one frequently just works.
            can_hop = (_model_index < len(MODEL_CANDIDATES) - 1) and (hops < max_model_hops)

            if is_missing_model and can_hop:
                print(f"  [MODEL] '{current_model()}' is retired -> trying '{MODEL_CANDIDATES[_model_index + 1]}'")
                stats["retired_models"].append(current_model())
                _model_index += 1
                hops += 1
                attempt = 0
                continue

            if is_rate_limit and attempt < max_retries - 1:
                attempt += 1
                wait_secs = attempt * 6
                print(f"  [RATE-LIMIT] Quota hit for {exam_name} on '{current_model()}'. Waiting {wait_secs}s ({attempt + 1}/{max_retries})...")
                time.sleep(wait_secs)
                continue

            if is_rate_limit and can_hop:
                print(f"  [MODEL] '{current_model()}' is out of quota -> trying '{MODEL_CANDIDATES[_model_index + 1]}'")
                stats["quota_switches"].append(current_model())
                _model_index += 1
                hops += 1
                attempt = 0
                continue

            if stats["failures"] == 0:
                traceback.print_exc()
            stats["failures"] += 1
            print(f"  [ERROR] Gemini API error for {exam_name} on '{current_model()}': {e}")
            return None

    stats["failures"] += 1
    print(f"  [ERROR] {exam_name}: gave up after {max_retries} attempts on '{current_model()}'")
    return None

def has_exact_date(date_str):
    import re
    # Consider it exact if it has a Day number along with the Month
    return bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}', date_str, re.IGNORECASE))

def extract_cal_date(date_str):
    """Try to extract a calendar date, fallback to 15th of the month if only month is found."""
    import re
    from datetime import datetime
    
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    current_year = datetime.now().year
    
    # Try exact date first: "Month Day, Year" or "Month Day"
    # If date range is given (e.g. "Sep 30 – Oct 30, 2026"), take the end date for calendar/archive
    matches = list(re.finditer(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})(?:,?\s+(\d{4}))?',
        date_str, re.IGNORECASE
    ))
    if matches:
        match = matches[-1]
        month = month_map[match.group(1)[:3].lower()]
        day = match.group(2).zfill(2)
        year = match.group(3)
        if not year:
            year_match = re.search(r'\b(20\d\d)\b', date_str)
            year = year_match.group(1) if year_match else str(current_year)
        return f"{year}-{month}-{day}"
        
    # Fallback: Just a month "Month Year" or "Month"
    month_matches = list(re.finditer(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*(?:\s+(\d{4}))?',
        date_str, re.IGNORECASE
    ))
    if month_matches:
        match = month_matches[-1]
        month = month_map[match.group(1)[:3].lower()]
        year = match.group(2) if match.group(2) else str(current_year)
        # Default to the 15th of the expected month
        return f"{year}-{month}-15"
    
    return None

def should_check_exam(exam):
    """
    Smart caching logic to determine if we actually need to query the API.
    """
    status = exam.get("status_code", "UPCOMING")
    cal_date_str = exam.get("calDate")
    last_checked_str = exam.get("last_checked_date")
    
    today = datetime.now()
    
    def parse_date(d_str):
        if not d_str: return None
        try:
            return datetime.strptime(d_str.split('T')[0], "%Y-%m-%d")
        except ValueError:
            return None

    cal_date = parse_date(cal_date_str)
    last_checked = parse_date(last_checked_str)

    # 0. check_from_month: annual exams that only open in a specific season.
    #    Skip entirely until that month arrives each year (e.g. DBT BITP → check_from_month=5 means skip Jan-Apr).
    check_from_month = exam.get("check_from_month")
    if check_from_month and status not in ("LIVE_REGISTRATION_OPEN", "LIVE_ADMIT_CARD", "LIVE_CITY_INTIMATION"):
        if today.month < int(check_from_month):
            return False, f"Seasonal exam — checking starts from month {check_from_month} (currently month {today.month})"

    # 1. LIVE exams with a future deadline -> SKIP
    if status in ("LIVE_REGISTRATION_OPEN", "LIVE_ADMIT_CARD", "LIVE_CITY_INTIMATION") and cal_date:
        if cal_date.date() > today.date():
            return False, f"Deadline ({cal_date_str}) is in the future"
            
    # 2. PAST exams -> CHECK WEEKLY (every 7 days)
    if status == "PAST":
        if last_checked and (today.date() - last_checked.date()).days < 7:
            days_left = 7 - (today.date() - last_checked.date()).days
            return False, f"PAST exam. Checking again in {days_left} days"

    # 2b. Registration closed with exam date > 30 days away -> CHECK EVERY 4 DAYS
    # Admit cards are released only 1-2 weeks before the exam date. Checking daily burns AI search quota.
    is_closed = any(w in (exam.get("dateStr", "")).lower() for w in ["registration ended", "ended", "opens next year"])
    if is_closed and cal_date and (cal_date.date() - today.date()).days > 30:
        if last_checked and (today.date() - last_checked.date()).days < 4:
            days_left = 4 - (today.date() - last_checked.date()).days
            return False, f"Registration closed & exam date >30 days away. Checking again in {days_left} days"
            
    # 3. UPCOMING / OTHERS -> CHECK DAILY (if not already checked today)
    if last_checked and (today.date() - last_checked.date()).days < 1:
        return False, "Already checked today"
        
    return True, "Needs update"


def update_all_exams():
    """Main function: update all exams using Gemini AI."""
    exams = load_exams()
    
    # Group GATE exams together - they all share the same notification date
    gate_exams = [e for e in exams if e["id"].startswith("gate_")]
    non_gate_exams = [e for e in exams if not e["id"].startswith("gate_")]
    
    updated_count = 0
    consecutive_quota_hits = 0
    
    # --- Update GATE exams (one query for all) ---
    if gate_exams:
        needs_check, reason = should_check_exam(gate_exams[0])
        if needs_check:
            print("\n[GATE] Querying for GATE exam dates...")
            gate_result = query_exam_status(
                "GATE (Graduate Aptitude Test in Engineering)",
                "Common notification for all GATE papers - registration and exam dates",
                current_status=gate_exams[0].get("status_code", "UPCOMING"),
                current_datestr=gate_exams[0].get("dateStr", ""),
                official_link=gate_exams[0].get("syllabus_link", "https://gate2027.iitm.ac.in/")
            )
            if gate_result and "display_text" in gate_result:
                print(f"  [GATE] AI says: {gate_result['display_text']} ({gate_result.get('status_code')})")
                for exam in gate_exams:
                    exam["dateStr"] = gate_result["display_text"]
                    exam["status_code"] = gate_result.get("status_code", "UPCOMING")
                    exam["hasExactDate"] = has_exact_date(gate_result["display_text"])
                    exam["last_checked_date"] = datetime.now().strftime("%Y-%m-%d")
                    cal = extract_cal_date(gate_result["display_text"])
                    if cal:
                        exam["calDate"] = cal
                        if exam["status_code"] in ("LIVE_REGISTRATION_OPEN", "LIVE_ADMIT_CARD", "LIVE_CITY_INTIMATION"):
                            exam["archive_after"] = cal
                updated_count += len(gate_exams)
            else:
                print("  [GATE] No update - keeping existing data")
            time.sleep(4.5)  # Rate limiting - stay safely under 15 RPM limit
        else:
            print(f"\n[GATE] Skipping check: {reason}")
    
    # --- Update non-GATE exams individually ---
    for exam in non_gate_exams:
        needs_check, reason = should_check_exam(exam)
        if needs_check:
            print(f"\n[{exam['id']}] Querying for {exam['name']}...")
            
            result = query_exam_status(
                exam["name"],
                exam["desc"],
                current_status=exam.get("status_code", "UPCOMING"),
                current_datestr=exam.get("dateStr", ""),
                official_link=exam.get("syllabus_link", "")
            )
            
            if result and "display_text" in result:
                consecutive_quota_hits = 0
                print(f"  [{exam['id']}] AI says: {result['display_text']} ({result.get('status_code')})")
                exam["dateStr"] = result["display_text"]
                exam["status_code"] = result.get("status_code", "UPCOMING")
                exam["hasExactDate"] = has_exact_date(result["display_text"])
                exam["last_checked_date"] = datetime.now().strftime("%Y-%m-%d")
                cal = extract_cal_date(result["display_text"])
                if cal:
                    exam["calDate"] = cal
                    if exam["status_code"] in ("LIVE_REGISTRATION_OPEN", "LIVE_ADMIT_CARD", "LIVE_CITY_INTIMATION"):
                        exam["archive_after"] = cal
                updated_count += 1
            else:
                print(f"  [{exam['id']}] No update - keeping existing data")
                if stats.get("quota_exhausted"):
                    consecutive_quota_hits += 1
                    if consecutive_quota_hits >= 3:
                        print("\n[QUOTA CIRCUIT BREAKER] 3 consecutive exams hit API quota/rate-limits.")
                        print("The Gemini free-tier daily quota has been reached for today.")
                        print("Stopping further queries to prevent wasted attempts. Progress so far will be saved.")
                        break
            
            time.sleep(4.5)  # Rate limiting - stay safely under 15 RPM limit
        else:
            print(f"\n[{exam['id']}] Skipping check: {reason}")
    
    # Save the updated data
    save_exams(exams)
    
    print(f"\n{'='*50}")
    print(f"UPDATE COMPLETE: {updated_count}/{len(exams)} exams updated")
    print(f"AI requests: {stats['queries']}   failures: {stats['failures']}")
    print(f"Model in use: {current_model()}")
    if stats["retired_models"]:
        print(f"Models that had been retired: {', '.join(stats['retired_models'])}")
    if stats["quota_switches"]:
        print(f"Models skipped due to quota: {', '.join(stats['quota_switches'])}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*50}")

    live_now = [e["name"] for e in exams if str(e.get("status_code", "")).startswith("LIVE_")]

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(
                    "## Exam updater\n\n"
                    f"- Exams updated: **{updated_count}/{len(exams)}**\n"
                    f"- AI requests: {stats['queries']} (failures: {stats['failures']})\n"
                    f"- Model used: `{current_model()}`\n"
                    f"- Currently live: {', '.join(live_now) if live_now else '_none_'}\n"
                )
        except Exception as e:
            print(f"[WARN] could not write step summary: {e}")

    # Write run summary for GitHub Actions
    if stats.get("quota_exhausted"):
        print("\n[NOTICE] Free-tier Gemini API quota limit reached during this run.")
        print("Remaining exams will automatically resume on the next scheduled run when quota resets.")

    # Only exit with error if there is a real authentication failure (e.g. invalid API key).
    # Normal free-tier API throttling or quota limits must NOT fail the workflow or trigger alarm emails.
    if stats.get("auth_error"):
        print("\nFATAL: Authentication error with GEMINI_API_KEY. Please verify the GitHub secret.")
        print("Models this API key can use:", ", ".join(list_available_models()))
        sys.exit(1)

    if stats["failures"] > 0:
        print(f"\n[STATUS] {stats['failures']} of {stats['queries']} queries encountered rate-limits/throttling; "
              f"{updated_count} exams updated/saved successfully.")

if __name__ == "__main__":
    print("=" * 50)
    print("EXAM DATE AUTO-UPDATER")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 50)
    update_all_exams()
