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
1. Is registration currently OPEN? If yes, what is the last date to apply?
2. If registration is CLOSED, when did it close?
3. When is/was the exam date for the current cycle?
4. Is the current cycle completed? If so, when is the next cycle's notification expected?

IMPORTANT: Respond with ONLY a single short status string (max 80 characters) that a student would find useful. Examples of good responses:
- "Registration Open! Last Date: Sep 15, 2026"
- "Completed for 2026. Next Notification Expected: August 2027"
- "Registration ends June 19, 2026. Next Cycle Expected: Nov/Dec"
- "Next Notification Expected: April 2027"
- "Exam on Feb 1-2, 2027. Registration closes Oct 15"

Do NOT include any explanation. Just the status string."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,  # Low temperature for factual accuracy
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
    """
    Check if the date string contains a specific calendar date
    that can be added to Google Calendar.
    """
    # Look for patterns like "June 19, 2026" or "Sep 15" or specific dates
    import re
    # Match patterns with month + day + year
    date_patterns = [
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}',
        r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, date_str, re.IGNORECASE)
        if match:
            return True
    return False

def extract_cal_date(date_str):
    """Try to extract a YYYY-MM-DD calendar date from the string."""
    import re
    
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    # Try "Month Day, Year" format
    match = re.search(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2}),?\s+(\d{4})',
        date_str, re.IGNORECASE
    )
    if match:
        month = month_map[match.group(1)[:3].lower()]
        day = match.group(2).zfill(2)
        year = match.group(3)
        return f"{year}-{month}-{day}"
    
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
            if exam["hasExactDate"]:
                cal = extract_cal_date(gate_result)
                if cal:
                    exam["calDate"] = cal
            elif "calDate" in exam:
                del exam["calDate"]
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
            if exam["hasExactDate"]:
                cal = extract_cal_date(result)
                if cal:
                    exam["calDate"] = cal
            elif "calDate" in exam:
                del exam["calDate"]
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
