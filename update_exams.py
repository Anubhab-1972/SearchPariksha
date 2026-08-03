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
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
    from openai import OpenAI
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai")
    sys.exit(1)

# --- Configuration ---
EXAMS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exams.json")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MESH_API_KEY = os.environ.get("MESH_API_KEY", "")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not set.")
    print("Set it with: export GEMINI_API_KEY='your-key-here'")
    sys.exit(1)

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize the Mesh API client (OpenAI compatible)
try:
    mesh_client = OpenAI(
        api_key=MESH_API_KEY,
        base_url="https://api.meshapi.ai/v1" if MESH_API_KEY else None
    )
except Exception:
    mesh_client = None

def load_exams():
    """Load the current exams database from JSON file."""
    with open(EXAMS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_exams(exams):
    """Save the updated exams database to JSON file."""
    with open(EXAMS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(exams, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {len(exams)} exams to {EXAMS_JSON_PATH}")

def query_exam_status(exam_name, exam_desc):
    """
    Ask Gemini AI and Mesh API for consensus on the latest dates and status code.
    """
    today = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""Today is {today}. I need the latest official status for the Indian competitive exam: "{exam_name}" ({exam_desc}).

Search the internet and tell me:
1. Is registration currently OPEN?
2. If hasn't started yet, when is it expected?
3. If registration is CLOSED, check the exact EXAM DATE first.
   - If exam is in the PAST, check for RESULTS.
   - If exam is in the FUTURE, check for ADMIT CARD.

CRITICAL: You must output a JSON object with two keys:
1. 'status_code': Must be exactly one of: LIVE_REGISTRATION_OPEN, LIVE_ADMIT_CARD, LIVE_RESULTS, UPCOMING, PAST.
2. 'display_text': A short display string (max 80 chars) like "Apply by: Oct 5, 2026" or "Expected Registration: Sep 2027" or "Admit Card Released! Exam Date: Aug 15".

Do NOT include any explanation or extra text."""

    gemini_result = None
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a strict data extraction bot. ONLY output JSON.",
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "status_code": types.Schema(type=types.Type.STRING),
                        "display_text": types.Schema(type=types.Type.STRING)
                    },
                    required=["status_code", "display_text"]
                ),
            ),
        )
        gemini_result = json.loads(response.text.strip())
    except Exception as e:
        print(f"  [ERROR] Gemini API error: {e}")

    # Consensus Check with Mesh API
    mesh_result = None
    if mesh_client and MESH_API_KEY:
        try:
            mesh_res = mesh_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a strict data extraction bot. Return JSON with status_code and display_text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={ "type": "json_object" }
            )
            mesh_result = json.loads(mesh_res.choices[0].message.content.strip())
        except Exception as e:
            print(f"  [WARNING] Mesh API consensus failed: {e}")

    # Consensus Logic
    if gemini_result and mesh_result:
        if gemini_result.get("status_code") == mesh_result.get("status_code"):
            return gemini_result
        else:
            print(f"  [CONSENSUS MISMATCH] Gemini: {gemini_result.get('status_code')} vs Mesh: {mesh_result.get('status_code')}")
            # Fallback to UPCOMING for safety if they disagree
            return {"status_code": "UPCOMING", "display_text": gemini_result.get("display_text")}
    
    return gemini_result

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
    match = re.search(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})(?:,?\s+(\d{4}))?',
        date_str, re.IGNORECASE
    )
    if match:
        month = month_map[match.group(1)[:3].lower()]
        day = match.group(2).zfill(2)
        year = match.group(3) if match.group(3) else str(current_year)
        return f"{year}-{month}-{day}"
        
    # Fallback: Just a month "Month Year" or "Month"
    match = re.search(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*(?:\s+(\d{4}))?',
        date_str, re.IGNORECASE
    )
    if match:
        month = month_map[match.group(1)[:3].lower()]
        year = match.group(2) if match.group(2) else str(current_year)
        # Default to the 15th of the expected month
        return f"{year}-{month}-15"
    
    return None

def update_all_exams():
    """Main function: update all exams using Gemini AI."""
    exams = load_exams()
    
    # Group GATE exams together - they all share the same notification date
    gate_exams = [e for e in exams if e["id"].startswith("gate_")]
    non_gate_exams = [e for e in exams if not e["id"].startswith("gate_")]
    
    updated_count = 0
    
    # --- Update GATE exams (one query for all) ---
    print("\n[GATE] Querying for GATE exam dates...")
    gate_result = query_exam_status(
        "GATE (Graduate Aptitude Test in Engineering)",
        "Common notification for all GATE papers - registration and exam dates"
    )
    if gate_result and "display_text" in gate_result:
        print(f"  [GATE] AI says: {gate_result['display_text']} ({gate_result.get('status_code')})")
        for exam in gate_exams:
            exam["dateStr"] = gate_result["display_text"]
            exam["status_code"] = gate_result.get("status_code", "UPCOMING")
            exam["hasExactDate"] = has_exact_date(gate_result["display_text"])
            cal = extract_cal_date(gate_result["display_text"])
            if cal:
                exam["calDate"] = cal
        updated_count += len(gate_exams)
    else:
        print("  [GATE] No update - keeping existing data")
    
    time.sleep(2)  # Rate limiting
    
    # --- Update non-GATE exams individually ---
    for exam in non_gate_exams:
        print(f"\n[{exam['id']}] Querying for {exam['name']}...")
        
        result = query_exam_status(exam["name"], exam["desc"])
        
        if result and "display_text" in result:
            print(f"  [{exam['id']}] AI says: {result['display_text']} ({result.get('status_code')})")
            exam["dateStr"] = result["display_text"]
            exam["status_code"] = result.get("status_code", "UPCOMING")
            exam["hasExactDate"] = has_exact_date(result["display_text"])
            cal = extract_cal_date(result["display_text"])
            if cal:
                exam["calDate"] = cal
            updated_count += 1
        else:
            print(f"  [{exam['id']}] No update - keeping existing data")
        
        time.sleep(2)  # Rate limiting - be nice to Google's API
    
    # Save the updated data
    save_exams(exams)
    
    print(f"\n{'='*50}")
    print(f"UPDATE COMPLETE: {updated_count}/{len(exams)} exams updated")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*50}")

if __name__ == "__main__":
    print("=" * 50)
    print("EXAM DATE AUTO-UPDATER")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 50)
    update_all_exams()
