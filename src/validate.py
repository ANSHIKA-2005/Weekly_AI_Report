"""
Phase 4 - Validation guardrail.

This is the safety net: it reads every number in the LLM's summary text
and checks it against the facts we actually sent. If the LLM invented,
miscalculated, or hallucinated a number, this catches it.

Why this matters: an LLM can round, reformat, or restate a number in many
valid ways (305998.91 -> "305,999" or "about 306,000" or "3.06 lakh").
We can't just string-match - we extract every number from the text and
check it's numerically close to SOMETHING the LLM was allowed to say.

"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from kpis import build_weekly_table, DATA_PATH
from insights import flag_weeks, explain_week
from summary import build_facts, generate_summary

load_dotenv()

DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")   # e.g. 2024-12-23 - not a "fact" number
NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")
REL_TOLERANCE = 0.01  # allow 1% rounding difference
ABS_TOLERANCE = 1.0   # allow +/-1 for small numbers (e.g. percentages rounded to whole numbers)

# Numbers that are always OK to appear (they're not "facts", they're just
# ordinary language: "a 4-week average", "week 1 of 2", etc.)
IGNORE_VALUES = {1, 2, 3, 4, 5}


def extract_numbers(text):
    """Pull every number out of a piece of text, as floats.

    Dates like "2024-12-23" are stripped first, so they don't get
    misread as three separate numbers (2024, -12, -23).
    """
    text = DATE_PATTERN.sub(" ", text)
    numbers = []
    for match in NUMBER_PATTERN.findall(text):
        cleaned = match.replace(",", "")
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
    return numbers


def allowed_numbers(facts):
    """
    Build the set of numbers the LLM was allowed to reference, including
    reasonable rounded forms (whole number, nearest 10, nearest 100, etc.)
    since the LLM may round a number when writing it in a sentence.
    """
    raw_values = []
    for key in ("net_revenue", "wow_pct", "vs_avg4_pct",
                "top_driver_change", "top_driver_pct_of_total_change"):
        v = facts.get(key)
        if v is not None:
            raw_values.append(abs(float(v)))

    expanded = set()
    for v in raw_values:
        expanded.add(v)
        expanded.add(round(v))
        expanded.add(round(v, 1))
        expanded.add(round(v, -1))   # nearest 10
        expanded.add(round(v, -2))   # nearest 100
        expanded.add(round(v, -3))   # nearest 1000
    return expanded


def is_allowed(number, allowed):
    """A number passes if it's within tolerance of something it was allowed to say."""
    n = abs(number)
    if n in IGNORE_VALUES:
        return True
    for a in allowed:
        if abs(n - a) <= max(ABS_TOLERANCE, a * REL_TOLERANCE):
            return True
    return False


def validate_summary(summary_text, facts):
    """
    Check every number in summary_text against facts.
    Returns (is_clean: bool, flagged_numbers: list of numbers that didn't match anything).
    """
    allowed = allowed_numbers(facts)
    found = extract_numbers(summary_text)
    flagged = [n for n in found if not is_allowed(n, allowed)]
    return len(flagged) == 0, flagged


def run_one_week(kpis, df, week_start, verbose=True):
    facts = build_facts(kpis, df, week_start)
    summary_text = generate_summary(facts)
    is_clean, flagged = validate_summary(summary_text, facts)

    if verbose:
        print(f"\nWeek {facts['week_start']}:")
        print(summary_text)
        if is_clean:
            print("VALIDATION: clean - every number traced back to the facts.")
        else:
            print(f"VALIDATION: FAILED - unexplained numbers: {flagged}")

    return is_clean, facts, summary_text


if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: GEMINI_API_KEY not found. Check your .env file.")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("data_path", nargs="?", default=str(DATA_PATH))
    parser.add_argument("--weeks", type=int, default=1,
                         help="How many of the most recent weeks to test (default: 1)")
    args = parser.parse_args()

    kpis, df = build_weekly_table(Path(args.data_path))
    kpis = flag_weeks(kpis)

    weeks_to_test = kpis.index[-args.weeks:]
    clean_count = 0
    # Free tier allows 5 requests/minute - pace at ~13s/call to stay safely under that.
    SECONDS_BETWEEN_CALLS = 13

    for i, wk in enumerate(weeks_to_test):
        is_clean, _, _ = run_one_week(kpis, df, wk)
        clean_count += is_clean
        if i < len(weeks_to_test) - 1:
            time.sleep(SECONDS_BETWEEN_CALLS)

    if args.weeks > 1:
        print(f"\n{'='*50}")
        print(f"Accuracy: {clean_count}/{len(weeks_to_test)} weeks clean on first try "
              f"({clean_count/len(weeks_to_test)*100:.0f}%)")