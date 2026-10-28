"""
Phase 3 - AI-written summary.

Takes the verified facts from insights.py (explain_week) and asks an LLM
to turn them into a short, readable paragraph. The LLM is NEVER given the
raw data or asked to calculate anything - only the numbers we already
computed and checked in Phase 1/2.

"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

from kpis import build_weekly_table, DATA_PATH
from insights import flag_weeks, explain_week

load_dotenv()  # reads the .env file and loads GEMINI_API_KEY into the environment

MODEL_NAME = "gemini-3.5-flash-lite"  # Google keeps this alias pointed at its current supported Flash model

SYSTEM_PROMPT = """You are a business analyst writing a short weekly summary for a category manager.

STRICT RULES:
- Use ONLY the numbers given to you in the facts below. Do not calculate, estimate, or invent any number.
- Do not mention any category, percentage, or figure that is not present in the facts.
- If a value is null, do not mention that metric at all.
- Write 3-4 sentences in plain, professional English. No headings, no bullet points.
- Tone: neutral and factual. Do not use hype words like "amazing" or "incredible".

Structure to follow:
1. Headline: how revenue moved this week (use wow_pct and vs_avg4_pct).
2. Whether this week is unusual or within the normal range (use 'flagged').
3. What drove the change, if a driver is given (use top_driver_category and top_driver_pct_of_total_change).
4. One closing sentence: either a watch-out (if flagged) or a one-line "steady week" note (if not).
"""


def build_facts(kpis, df, week_start):
    """Wrap explain_week()'s output as the exact JSON the LLM is allowed to see."""
    facts = explain_week(kpis, df, week_start)
    # Dates and numpy types don't serialize cleanly - force everything to plain Python types.
    return json.loads(json.dumps(facts, default=str))


def generate_summary(facts, model_name=MODEL_NAME, max_retries=3):
    """Send ONLY the facts dict to the LLM and return its written summary.

    Gemini occasionally returns a 503 'model overloaded' error that has
    nothing to do with our code - it clears up if we just wait and retry.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    user_prompt = f"Facts for this week (JSON):\n{json.dumps(facts, indent=2)}\n\nWrite the summary."

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config={"system_instruction": SYSTEM_PROMPT},
            )
            return response.text.strip()
        except genai_errors.ServerError:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt  # 2s, 4s, 8s
            print(f"  Gemini busy (attempt {attempt}/{max_retries}), retrying in {wait}s...")
            time.sleep(wait)
        except genai_errors.ClientError as e:
            if e.code == 429 and attempt < max_retries:
                wait = 20  # free tier quota resets fast; a flat 20s is simplest and safe
                print(f"  Rate limit hit (attempt {attempt}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: GEMINI_API_KEY not found. Check your .env file.")
        sys.exit(1)

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_PATH
    kpis, df = build_weekly_table(path)
    kpis = flag_weeks(kpis)

    latest = kpis.index[-1]
    facts = build_facts(kpis, df, latest)

    print("Facts sent to the LLM:")
    print(json.dumps(facts, indent=2))

    print("\nGenerated summary:\n")
    summary_text = generate_summary(facts)
    print(summary_text)