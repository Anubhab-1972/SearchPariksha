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
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai")
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

def load_exams():
    """Load the current exams database from JSON file."""
    with open(EXAMS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_exams(exams):
    """Save the updated exams database to JSON file."""
    with open(EXAMS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(exams, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {len(exams)} exams to {EXAMS_JSON_PATH}")

def query_gemini_for_exam(exam_name, exam_desc):
    """
    Ask Gemini AI (with Google Search grounding) for the latest
    notification/registration dates for a specific exam.
    """
    today = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""Today is {today}. I need the latest official status for the Indian competitive exam: "{exam_name}" ({exam_desc}).

Search the internet and tell me:
1. Is registration (the initial application to SIT for the exam) currently OPEN? Carefully compare today's date ({today}) against the official start and end dates for online applications. If today's date falls on or between those dates, registration is OPEN. If yes, what is the EXACT LAST DATE (deadline) to apply?
   (NOTE: Ignore post-exam processes like counselling, seat allotment, or admission forms. We only care about applying to TAKE the exam.)
2. If registration hasn't started yet for the upcoming exam, when is the registration expected to open?
3. If registration to take the exam is CLOSED but the exam hasn't happened yet, what is the EXACT EXAM DATE?
4. If the exam is completely over for this cycle, search for when the registration opened THIS year, and add one year to predict when registration will open NEXT year.

CRITICAL: Respond with ONLY a single short status string (max 80 characters) that a student would find useful. DO NOT write full sentences (e.g. never write "The exam cycle is over..."). Just output the status string matching one of these exact formats:
- If open, prioritize the deadline: "Registration Open! Last Date: Sep 28, 2026"
- If registration hasn't started yet, prioritize when it starts: "Expected Registration: September 2026"
- If registration ended but exam is upcoming, prioritize the exam date: "Registration ended! Exam Date: July 15, 2026"
- If exam is completely over, predict next year's registration: "Expected Registration: August 2027"

Do NOT include any explanation or extra text. Just the status string."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a strict data extraction bot. NEVER output full sentences. ONLY output the exact short status string formats requested.",
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,  # Zero temperature for strictest factual accuracy
            ),
        )
        
        result = response.text.strip()
        # Clean up the response - remove quotes if Gemini wraps them
        result = result.strip('"').strip("'").strip("`")
        
        # Basic sanity check: response should not be too long or empty
        if len(result) > 120:
            result = result[:120]
        if len(result) < 5:
            return None
            
        return result
        
    except Exception as e:
        print(f"  [ERROR] Gemini API error for {exam_name}: {e}")
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
    print("\n[GATE] Querying Gemini for GATE exam dates...")
    gate_result = query_gemini_for_exam(
        "GATE (Graduate Aptitude Test in Engineering)",
        "Common notification for all GATE papers - registration and exam dates"
    )
    if gate_result:
        print(f"  [GATE] AI says: {gate_result}")
        for exam in gate_exams:
            exam["dateStr"] = gate_result
            exam["hasExactDate"] = has_exact_date(gate_result)
            cal = extract_cal_date(gate_result)
            if cal:
                exam["calDate"] = cal
        updated_count += len(gate_exams)
    else:
        print("  [GATE] No update - keeping existing data")
    
    time.sleep(2)  # Rate limiting
    
    # --- Update non-GATE exams individually ---
    for exam in non_gate_exams:
        print(f"\n[{exam['id']}] Querying Gemini for {exam['name']}...")
        
        result = query_gemini_for_exam(exam["name"], exam["desc"])
        
        if result:
            print(f"  [{exam['id']}] AI says: {result}")
            exam["dateStr"] = result
            exam["hasExactDate"] = has_exact_date(result)
            cal = extract_cal_date(result)
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
