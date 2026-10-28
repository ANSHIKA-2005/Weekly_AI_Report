# Automated Weekly KPI Report with AI-Written Summary

Turns raw e-commerce order data into a weekly business report: Verified KPIs, anomaly flagging, root-cause analysis, and an AI-written summary — validated against the source data before it ships.

**Why it matters:** Routine weekly reporting takes an analyst hours every week. This automates the full process, while treating AI strictly as a writer, never a calculator — every number it produces is checked against the data before use.

# What it does


Raw Orders → Weekly KPIs → Anomaly Detection → AI-Written Summary → Validated HTML Report


- Computes revenue, AOV, and lost-order rate for 104 weeks from 39,966 orders
- Flags any week that's more than ±10% from its own 4-week average
- Identifies which product category drove each week's change
- Gemini API writes a plain-English summary from the verified numbers only
- A validation layer independently checks every number in that summary against the source data


# Result

30/30 weeks produced a clean, validated summary with zero hallucinated numbers. The guardrail exists regardless of this result — it checks every single output, not just the ones that happen to go wrong.

# Tech stack

Python, Pandas, Google Gemini API, Matplotlib, HTML/CSS

# Limitations
- Pending/Shipped orders are counted as valid revenue — a judgment call to confirm in a real deployment
- Ran data-quality checks before analysis (e.g., product-category and location mappings); scoped product- and location-level claims accordingly
