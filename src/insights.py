"""
Phase 2 - Insight detection.

Takes the weekly KPI table from kpis.py and answers two questions:
  1. Is this week unusual, or just normal noise?
  2. If revenue moved, which category caused most of the move?

"""
import sys
from pathlib import Path

import pandas as pd

from kpis import build_weekly_table, DATA_PATH

FLAG_THRESHOLD_PCT = 10  # a week counts as "unusual" if it's more than this far from its 4-week average


def flag_weeks(kpis, metric="net_revenue", threshold=FLAG_THRESHOLD_PCT):
    """Mark weeks where `metric` is more than `threshold`% away from its 4-week average."""
    col = f"{metric}_vs_avg4_pct"
    kpis = kpis.copy()
    kpis["flagged"] = kpis[col].abs() > threshold
    kpis["flag_direction"] = kpis[col].apply(
        lambda x: "up" if pd.notna(x) and x > threshold
        else ("down" if pd.notna(x) and x < -threshold else "")
    )
    return kpis


def category_contribution(df, week_start, compare_to="previous"):
    """
    For one week, break the revenue change down by category.

    Returns a table: for each category, how much its revenue changed
    (in rupees) and what % of the TOTAL change that category is responsible for.

    `compare_to`: "previous" (last week) - this is the only mode used here,
    but written as a parameter so Phase 3 could ask for a 4-week-average
    comparison later without changing this function's logic.
    """
    week_start = pd.Timestamp(week_start)
    prev_start = week_start - pd.Timedelta(days=7)

    valid = df[~df["is_lost"]]
    this_week = valid[valid["week_start"] == week_start].groupby("Category")["net"].sum()
    prev_week = valid[valid["week_start"] == prev_start].groupby("Category")["net"].sum()

    combined = pd.DataFrame({"this_week": this_week, "prev_week": prev_week}).fillna(0)
    combined["change"] = combined["this_week"] - combined["prev_week"]

    total_change = combined["change"].sum()
    if total_change != 0:
        combined["pct_of_total_change"] = combined["change"] / total_change * 100
    else:
        combined["pct_of_total_change"] = 0

    return combined.sort_values("change", key=abs, ascending=False)


def explain_week(kpis, df, week_start):
    """Build a plain-language-ready summary of one week: flag status + top driver."""
    week_start = pd.Timestamp(week_start)
    row = kpis.loc[week_start]

    result = {
        "week_start": week_start.date(),
        "net_revenue": round(row["net_revenue"], 2),
        "wow_pct": round(row["net_revenue_wow_pct"], 1) if pd.notna(row["net_revenue_wow_pct"]) else None,
        "vs_avg4_pct": round(row["net_revenue_vs_avg4_pct"], 1) if pd.notna(row["net_revenue_vs_avg4_pct"]) else None,
        "flagged": bool(row["flagged"]),
        "flag_direction": row["flag_direction"],
    }

    contrib = category_contribution(df, week_start)
    if not contrib.empty:
        top_driver = contrib.iloc[0]
        result["top_driver_category"] = top_driver.name
        result["top_driver_change"] = round(top_driver["change"], 2)
        result["top_driver_pct_of_total_change"] = round(top_driver["pct_of_total_change"], 1)

    return result


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_PATH
    kpis, df = build_weekly_table(path)
    kpis = flag_weeks(kpis)

    flagged = kpis[kpis["flagged"]]
    print(f"{len(flagged)} of {len(kpis)} weeks flagged as unusual "
          f"(more than {FLAG_THRESHOLD_PCT}% from their 4-week average)\n")

    # Show the explanation for the latest week, flagged or not
    latest = kpis.index[-1]
    summary = explain_week(kpis, df, latest)
    print(f"Latest week ({summary['week_start']}):")
    print(f"  Net revenue: {summary['net_revenue']:,.0f} "
          f"({summary['wow_pct']:+.1f}% WoW, {summary['vs_avg4_pct']:+.1f}% vs 4-wk avg)")
    print(f"  Flagged: {summary['flagged']} ({summary['flag_direction'] or 'normal range'})")
    if "top_driver_category" in summary:
        print(f"  Top driver: {summary['top_driver_category']} "
              f"changed by {summary['top_driver_change']:+,.0f} "
              f"({summary['top_driver_pct_of_total_change']:+.0f}% of the total change)")

    # Show every flagged week so far, oldest first
    if len(flagged):
        print(f"\nAll flagged weeks:")
        for wk in flagged.index:
            s = explain_week(kpis, df, wk)
            driver = s.get("top_driver_category", "n/a")
            print(f"  {s['week_start']}: {s['vs_avg4_pct']:+.1f}% vs avg, top driver: {driver}")