import json
import os
import sys
import time
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai not installed.")
    sys.exit(1)

EXAMS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exams.json")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable not set.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_syllabus(exam_name, exam_desc):
    prompt = f"""
    You are an expert educational consultant.
    I need the official syllabus for the following Indian exam: {exam_name} ({exam_desc}).
    
    Using Google Search, find:
    1. A short, concise summary of the syllabus topics (e.g., 'General Aptitude, Engineering Math, Core Subject'). Keep it under 200 words.
    2. A direct URL to the official syllabus PDF, OR if a direct PDF is absolutely not available, the official web page where the syllabus can be found.

    Return ONLY a valid JSON object with exactly two keys:
    - "syllabus_summary": "Your string summary here"
    - "syllabus_link": "https://..."
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_mime_type="application/json"
            )
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Error fetching {exam_name}: {e}")
        return None

def main():
    with open(EXAMS_JSON_PATH, "r", encoding="utf-8") as f:
        exams = json.load(f)
        
    updated = False
    for i, exam in enumerate(exams):
        if "syllabus_link" not in exam or "syllabus_summary" not in exam:
            print(f"[{i+1}/{len(exams)}] Fetching syllabus for {exam['name']}...")
            result = fetch_syllabus(exam['name'], exam.get('desc', ''))
            if result:
                exam['syllabus_summary'] = result.get('syllabus_summary', '')
                exam['syllabus_link'] = result.get('syllabus_link', '')
                updated = True
                
                # Save incrementally
                with open(EXAMS_JSON_PATH, "w", encoding="utf-8") as f:
                    json.dump(exams, f, indent=2)
            
            time.sleep(4) # Rate limit
            
    if updated:
        print("Syllabi populated successfully.")
    else:
        print("No exams needed updating.")

if __name__ == "__main__":
    main()
