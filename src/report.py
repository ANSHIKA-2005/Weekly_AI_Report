"""
Phase 5 - Build the final HTML report.

Pulls everything together into one shareable file:
  - a revenue trend chart (last 12 weeks)
  - the verified KPI numbers for the latest week
  - the AI-written summary (already validated by validate.py's logic)

"""
import base64
import io
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

import matplotlib
matplotlib.use("Agg")  
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from kpis import build_weekly_table, DATA_PATH
from insights import flag_weeks, explain_week
from summary import build_facts, generate_summary

OUTPUT_DIR = Path("outputs")
CHART_WEEKS = 12  # how many recent weeks to show in the trend chart


COLOR_NAVY = "#17324D"
COLOR_SLATE = "#5B6770"
COLOR_BLUE = "#2563EB"
COLOR_GREEN = "#16794A"
COLOR_RED = "#B3261E"
COLOR_GRAY_LINE = "#9CA3AF"
COLOR_SUMMARY_BG = "#F3F6FA"


def make_chart(kpis, latest_week, n_weeks=CHART_WEEKS):
    """Build a simple revenue trend chart and return it as a base64 PNG string."""
    recent = kpis.tail(n_weeks)

    fig, ax = plt.subplots(figsize=(8, 3))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.plot(recent.index, recent["net_revenue"], color=COLOR_BLUE, linewidth=2, zorder=3)
    ax.axhline(recent["net_revenue"].mean(), color=COLOR_GRAY_LINE, linestyle="--", linewidth=1,
               label=f"{n_weeks}-week average", zorder=2)

    # Highlight the latest week's point in red
    ax.scatter([latest_week], [kpis.loc[latest_week, "net_revenue"]],
               color=COLOR_RED, zorder=5, s=70, edgecolors="white", linewidths=1.5)

    ax.set_title(f"Net revenue - last {n_weeks} weeks", color=COLOR_NAVY, fontsize=11, loc="left")
    ax.tick_params(colors=COLOR_SLATE, labelsize=9)

    pad = pd.Timedelta(days=3)
    ax.set_xlim(recent.index.min() - pad, recent.index.max() + pad)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.autofmt_xdate(rotation=45)
    legend = ax.legend(loc="upper left", fontsize=8, frameon=False)
    for text in legend.get_texts():
        text.set_color(COLOR_SLATE)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(COLOR_GRAY_LINE)
    ax.grid(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _signed_color(value):
    """Dark green for positive, dark red for negative - used for WoW/avg figures."""
    return COLOR_GREEN if value >= 0 else COLOR_RED


TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report_template.html"


def render_html(facts, summary_text, chart_b64):
    """Load the HTML template and fill in the facts, AI summary, and chart.

    Keeping the HTML/CSS in its own file (templates/report_template.html)
    instead of as a big string inside this script makes both easier to
    read and edit independently.
    """
    status_text = (
        f'Unusual &ndash; {facts["flag_direction"]}' if facts["flagged"] else "Normal range"
    )
    status_color = COLOR_RED if facts["flagged"] else COLOR_SLATE

    driver_line = ""
    if facts.get("top_driver_category"):
        driver_line = (
            f'<p class="kpi-sub">Top driver: <strong>{facts["top_driver_category"]}</strong> '
            f'({facts["top_driver_pct_of_total_change"]:+.0f}% of the total change)</p>'
        )

    replacements = {
        "{{WEEK_START}}": str(facts["week_start"]),
        "{{GENERATED_TIME}}": f"{datetime.now(IST):%d %b %Y, %H:%M}",
        "{{NET_REVENUE}}": f"{facts['net_revenue']:,.0f}",
        "{{WOW_PCT}}": f"{facts['wow_pct']:+.1f}%",
        "{{WOW_COLOR}}": _signed_color(facts["wow_pct"]),
        "{{AVG_PCT}}": f"{facts['vs_avg4_pct']:+.1f}%",
        "{{AVG_COLOR}}": _signed_color(facts["vs_avg4_pct"]),
        "{{STATUS_TEXT}}": status_text,
        "{{STATUS_COLOR}}": status_color,
        "{{DRIVER_LINE}}": driver_line,
        "{{CHART_B64}}": chart_b64,
        "{{SUMMARY_TEXT}}": summary_text,
        "{{COLOR_NAVY}}": COLOR_NAVY,
        "{{COLOR_SLATE}}": COLOR_SLATE,
        "{{COLOR_SUMMARY_BG}}": COLOR_SUMMARY_BG,
    }

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html


if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        from dotenv import load_dotenv
        load_dotenv()
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: GEMINI_API_KEY not found. Check your .env file.")
        sys.exit(1)

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_PATH
    kpis, df = build_weekly_table(path)
    kpis = flag_weeks(kpis)

    latest = kpis.index[-1]
    facts = build_facts(kpis, df, latest)
    print("Generating summary...")
    summary_text = generate_summary(facts)

    print("Building chart...")
    chart_b64 = make_chart(kpis, latest)

    html = render_html(facts, summary_text, chart_b64)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"report_{facts['week_start']}.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"\nSaved report to {out_path}")
    print("Open it in any browser to view.")