"""
Phase 1 - KPI engine for the automated weekly report.

Turns the raw Amazon orders file into one row per complete week (Mon-Sun)
with the KPIs, week-over-week change, and comparison against the
previous 4-week average.

"""
import sys
from pathlib import Path

import pandas as pd

DATA_PATH = Path("data/Amazon_Data_Set_2023_-_2024.xlsx")
OUTPUT_PATH = Path("outputs/weekly_kpis.csv")
LOST_STATUSES = ["Cancelled", "Returned"]
KPI_COLS = ["net_revenue", "orders", "aov", "lost_rate", "avg_discount"]


def load_orders(path=DATA_PATH):
    """Read the raw file and add the helper columns every KPI needs."""
    df = pd.read_excel(path)
    df["OrderDate"] = pd.to_datetime(df["OrderDate"])
    df["gross"] = df["Quantity"] * df["UnitPrice"]
    df["net"] = df["gross"] * (1 - df["Discount"])
    df["is_lost"] = df["OrderStatus"].isin(LOST_STATUSES)
    # Weeks run Monday-Sunday; week_start is the Monday.
    df["week_start"] = df["OrderDate"].dt.to_period("W-SUN").dt.start_time
    return df


def weekly_kpis(df):
    """One row per week with the core KPIs."""
    valid = df[~df["is_lost"]]
    all_g = df.groupby("week_start")
    ok_g = valid.groupby("week_start")

    out = pd.DataFrame(
        {
            "orders": all_g["OrderID"].count(),
            "valid_orders": ok_g["OrderID"].count(),
            "lost_orders": all_g["is_lost"].sum(),
            "net_revenue": ok_g["net"].sum(),
            "avg_discount": all_g["Discount"].mean(),
        }
    )
    out["aov"] = out["net_revenue"] / out["valid_orders"]
    out["lost_rate"] = out["lost_orders"] / out["orders"]
    return out


def top_by_dimension(df, dim):
    """Top value of `dim` (e.g. Category, Country) by net revenue each week, plus its share."""
    rev = (
        df[~df["is_lost"]]
        .groupby(["week_start", dim])["net"]
        .sum()
        .reset_index()
    )
    rev["share"] = rev["net"] / rev.groupby("week_start")["net"].transform("sum")
    top = rev.loc[rev.groupby("week_start")["net"].idxmax()].set_index("week_start")
    name = dim.lower()
    return top[[dim, "share"]].rename(
        columns={dim: f"top_{name}", "share": f"top_{name}_share"}
    )


def add_comparisons(kpis, cols=KPI_COLS):
    """Week-over-week % change and gap vs the PREVIOUS 4-week average."""
    for c in cols:
        kpis[f"{c}_wow_pct"] = kpis[c].pct_change() * 100
        # shift(1) so the average uses the 4 weeks BEFORE this one, not including it
        kpis[f"{c}_avg4"] = kpis[c].rolling(4).mean().shift(1)
        kpis[f"{c}_vs_avg4_pct"] = (kpis[c] / kpis[f"{c}_avg4"] - 1) * 100
    return kpis


def keep_complete_weeks(kpis, df):
    """Drop partial weeks at the start/end of the data (a partial week looks like a fake crash)."""
    first, last = df["OrderDate"].min(), df["OrderDate"].max()
    week_end = kpis.index + pd.Timedelta(days=6)
    mask = (kpis.index >= first) & (week_end <= last)
    return kpis[mask]


def build_weekly_table(path=DATA_PATH):
    df = load_orders(path)
    kpis = weekly_kpis(df)
    kpis = kpis.join(top_by_dimension(df, "Category"))
    kpis = keep_complete_weeks(kpis, df)
    kpis = add_comparisons(kpis)
    return kpis, df


def verify_week(df, week_start):
    """Manual cross-check: recompute one week's revenue with a plain row loop."""
    week_start = pd.Timestamp(week_start)
    week_end = week_start + pd.Timedelta(days=6)
    total, n_orders = 0.0, 0
    for _, r in df.iterrows():
        if week_start <= r["OrderDate"] <= week_end:
            n_orders += 1
            if r["OrderStatus"] not in LOST_STATUSES:
                total += r["Quantity"] * r["UnitPrice"] * (1 - r["Discount"])
    return round(total, 2), n_orders


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_PATH
    kpis, df = build_weekly_table(path)

    print(f"{len(kpis)} complete weeks: {kpis.index.min().date()} to {kpis.index.max().date()}\n")

    last = kpis.iloc[-1]
    print(f"Latest week starting {kpis.index[-1].date()}:")
    print(f"  Net revenue : {last.net_revenue:,.0f}  ({last.net_revenue_wow_pct:+.1f}% WoW, "
          f"{last.net_revenue_vs_avg4_pct:+.1f}% vs 4-wk avg)")
    print(f"  Orders      : {last.orders:.0f}  ({last.orders_wow_pct:+.1f}% WoW)")
    print(f"  AOV         : {last.aov:,.2f}  ({last.aov_wow_pct:+.1f}% WoW)")
    print(f"  Lost rate   : {last.lost_rate:.1%}")
    print(f"  Top category: {last.top_category} ({last.top_category_share:.1%} of revenue)")

    # Manual verification of the latest week
    check_rev, check_orders = verify_week(df, kpis.index[-1])
    ok = abs(check_rev - last.net_revenue) < 0.01 and check_orders == last.orders
    print(f"\nManual check for that week: revenue {check_rev:,.2f}, orders {check_orders} -> "
          f"{'MATCH' if ok else 'MISMATCH'}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    kpis.to_csv(OUTPUT_PATH)
    print(f"\nSaved weekly table to {OUTPUT_PATH}")