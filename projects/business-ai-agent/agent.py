#!/usr/bin/env python3
"""Business AI Agent v1: market analysis from a marketplace CSV.

Run:
    python3 agent.py market --product "Redmi Buds 6"
    python3 agent.py market --data data/marketplace_data.csv
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

from TOOLS import TOOLS, collect, insights, market_data, recommend, recommend, reviews

ROOT = Path(__file__).resolve().parent
API = os.environ.get("FRP_API", "http://127.0.0.1:19040/v1")
SKILLS = {"market": "SKILLS/market_analysis.md"}
TOOL_NAME = market_data.TOOL_SPEC["function"]["name"]


def read_model_id():
    if os.environ.get("FRP_MODEL"):
        return os.environ["FRP_MODEL"]
    r = requests.get(API + "/models", timeout=15)
    if not r.ok:
        sys.exit("Cannot list models:\n" + r.text[:500])
    return r.json()["data"][0]["id"]


def post(messages, tools=None, tool_choice=None, max_tokens=4000):
    payload = {
        "model": read_model_id(),
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    r = requests.post(API + "/chat/completions", json=payload, timeout=240)
    if not r.ok:
        sys.exit("Model error:\n" + r.text[:800])
    choice = r.json()["choices"][0]
    return choice["message"], choice.get("finish_reason")


def build_system(skill_path):
    agent = (ROOT / "AGENT.md").read_text(encoding="utf-8")
    skill = (ROOT / skill_path).read_text(encoding="utf-8")
    return (
        agent
        + "\n\nVersion 1 rule: section 13 wins over every earlier instruction about "
        "connectors. You have no live marketplace access; use only tool output.\n\n"
        + "--- SKILL ---\n\n"
        + skill
        + f"\n\nYou must call the tool `{TOOL_NAME}` before writing the report, using "
        "the data path given in the user message.\n"
    )


def execute_tool(tool_call):
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"].get("arguments") or "{}")
    print(f"tool call: {name}({json.dumps(args, ensure_ascii=False)})")
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    module = TOOLS[name]
    if hasattr(module, "summary"):
        facts = module.summary(
            args.get("path") or "data/sample_marketplace_data.csv",
            args.get("product") or None,
        )
        facts["recommendations"] = recommend.recommend(
            facts["offers"], args.get("product") or None
        )
        return facts
    return module.search(args["query"])


def run_market(args):
    data_path = args.data
    if not Path(data_path).exists():
        sys.exit(
            f"Data file not found: {data_path}\n"
            "Copy data/sample_marketplace_data.csv to data/marketplace_data.csv "
            "or pass --data."
        )
    product = args.product
    request = (
        f'Analyse the market for "{product}" with the numbers from the tool and write '
        "the Function 1 report in the skill's output format."
        if product
        else "Analyse this market data and write the Function 1 report in the skill's "
        "output format."
    )
    request += (
        "\n\nThree recommendations were computed in code by TOOLS/recommend.py and are "
        "inside the tool output under `recommendations`. Present exactly those three "
        "products (budget, mid-range, premium) with: price, rating, review count, why "
        "selected, advantages, possible disadvantages, value for money. Do not replace "
        "them with cheaper or different products. Review text was not collected: compare "
        "ratings and review counts only, and say so."
        f"\nData path for the tool: {data_path}"
        + (f"\nProduct filter: {product}" if product else "")
        + "\nEnglish, markdown tables, prices in tenge."
    )

    messages = [
        {"role": "system", "content": build_system(SKILLS["market"])},
        {"role": "user", "content": request},
    ]

    forced = {"type": "function", "function": {"name": TOOL_NAME}}
    first, _ = post(
        messages, tools=[market_data.TOOL_SPEC], tool_choice=forced, max_tokens=300
    )
    calls = first.get("tool_calls") or []
    if not calls:
        sys.exit("The model did not call the data tool, so no report was written.")

    messages.append(
        {
            "role": "assistant",
            "content": first.get("content"),
            "tool_calls": calls,
        }
    )

    facts = None
    for call in calls:
        try:
            result = execute_tool(call)
            facts = result
            body = result
        except Exception as exc:  # report the real error to the model
            body = {"error": f"{type(exc).__name__}: {exc}"}
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(body, ensure_ascii=False)[:60000],
            }
        )

    final, finish = post(
        messages, tools=[market_data.TOOL_SPEC], tool_choice="auto", max_tokens=6000
    )
    report = (final.get("content") or "").strip()
    if finish == "length":
        print("warning: model hit the token limit; the report is cut short", file=sys.stderr)
        report += "\n\n_Note: the report was cut at the model token limit._"
    if not report:
        sys.exit("Model returned an empty report.")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    out = ROOT / "reports" / f"market_{stamp}.md"
    head = [f"# Market analysis — {product or 'all rows'}", ""]
    head.append(f"- Source file: `{data_path}`")
    if facts:
        head.append(f"- Rows analysed: {facts['rows_analysed']}")
        head.append(f"- Marketplaces: {', '.join(facts['marketplaces'])}")
        head.append(
            f"- Missing: {', '.join(facts['missing_marketplaces']) or 'none'}"
        )
        if facts["sample_data"]:
            head.append("- **Demo data — the numbers are fake.**")
    else:
        head.append("- Tool failed — see the report body.")
    head.append("")
    text = "\n".join(head) + report + "\n\n## Collected review evidence\n\n" + "\n".join(
        f"- {line}" for line in review_lines
    ) + "\n"
    out.write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"Saved: {out}")


def run_analyze(query):
    """One command: search Kaspi, analyse, rank, write the report."""
    rows, statuses = collect.collect(query)
    lines = [collect.status_line(name, statuses[name]) for name in ("kaspi",)]
    print("\n".join(lines))
    if not rows:
        sys.exit("\nNo data collected, so no report was written. Nothing is invented.")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    data_path = ROOT / "data" / f"search_{collect.slug(query)}.csv"
    collect.write_csv(rows, data_path)
    collect.write_status(ROOT / "data" / "collection_status.json", query, statuses, rows)
    recs = recommend.recommend(rows, query)
    relevant = recs.pop("relevant_rows", rows)
    if recs["status"] in ("no_relevant", "insufficient_relevant", "insufficient_data", "insufficient_quality", "insufficient_distinct"):
        sys.exit(
            "\nNo suitable products to rank. " + recs.get("reason", "")
            + " Nothing is invented."
        )
    collect.write_csv(relevant, data_path)
    facts = market_data.summarise(relevant, str(data_path.relative_to(ROOT)))
    per_market = {}
    for name in ("kaspi",):
        subset = [r for r in relevant if r.get("marketplace") == name]
        if subset:
            per_market[name] = recommend.recommend(subset)
    review_data = reviews.collect_for_picks(recs, pages=4)
    reviews.attach_to_picks(recs, review_data)
    review_lines = insights._review_section(review_data, statuses)

    request = f"""Product query: "{query}"

Write the improved Function 1 report from the tool outputs below.

Required structure:
1. Market overview: rows, Kaspi offers, min/median/mean/max price, mean rating.
2. Competitor table with source links, price, rating, review count.
3. Three recommended options exactly as ranked by the recommendation tool: Best budget, Best mid-range (middle price band), Best premium (top 20% by price).
   For each option: why it was selected, price, rating, reviews, main advantages, possible disadvantages, value for money.
   Never swap in a cheaper product just because it is cheaper. If Kaspi has no data, say "no usable data" and why; do not invent offers.
4. Comparison of the three: what differs in quality evidence and price, who each option suits.
5. Customer feedback: use the collected review-text evidence below. State how many reviews were read
   for each product, the most frequent positive and negative themes with counts/shares when shown, and
   short real examples. Do not invent review text, themes or frequencies. If a product's review status
   is not ok, say which page was checked and what could not be verified.
6. Limitations: sample size, one source (Kaspi), no seller costs, no sales data.

Rules: every number must come from the tool outputs. Separate measured facts from hypotheses.
If a tier has data quality problems (few reviews, no rating), say so.
Prices in tenge.

TOOL OUTPUT — collection status:
{json.dumps(statuses, ensure_ascii=False, indent=1)}

TOOL OUTPUT — market statistics:
{json.dumps(facts, ensure_ascii=False, indent=1)}

TOOL OUTPUT — recommendations across all collected rows (already ranked by code):
{json.dumps(recs, ensure_ascii=False, indent=1)}

TOOL OUTPUT — recommendations for Kaspi:
{json.dumps(per_market, ensure_ascii=False, indent=1)}

TOOL OUTPUT — review text analysis (real visible reviews; sample only):
{json.dumps(review_data, ensure_ascii=False, indent=1)}
"""
    messages = [
        {"role": "system", "content": build_system(SKILLS["market"])
         + "\nThe orchestrator already ran the collection and recommendation tools; "
           "their real outputs are in the user message. Do not call tools again."},
        {"role": "user", "content": request},
    ]
    final, finish = post(messages, max_tokens=6000)
    report = (final.get("content") or "").strip()
    if finish == "length":
        print("warning: model hit the token limit; the report is cut short", file=sys.stderr)
        report += "\n\n_Note: the report was cut at the model token limit._"
    if not report:
        sys.exit("Model returned an empty report.")

    out = ROOT / "reports" / f"analysis_{collect.slug(query)}_{stamp}.md"
    head = [
        f"# Market analysis and 3 recommendations — {query}",
        "",
        f"- Data file: `{data_path.relative_to(ROOT)}`",
        f"- Rows analysed: {facts['rows_analysed']}",
        "- Marketplace status: " + "; ".join(
            f"{name} {collect.availability(statuses[name].get('status', ''))}" for name in ("kaspi",)
        ),
        "- " + "; ".join(lines),
        "",
    ]
    text = "\n".join(head) + report + "\n\n## Collected review evidence\n\n" + "\n".join(
        f"- {line}" for line in review_lines
    ) + "\n"
    out.write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"Saved: {out}")


def main():
    argv = sys.argv[1:]
    commands = {"market", "analyze"}
    if argv and not argv[0].startswith("-") and argv[0] not in commands:
        argv = ["analyze"] + argv

    parser = argparse.ArgumentParser(description="Business AI Agent v1")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("market", help="Function 1 on an existing CSV")
    p.add_argument("--data", default="data/marketplace_data.csv")
    p.add_argument("--product", default=None)
    a = sub.add_parser("analyze", help="Search now and write the 3-option report")
    a.add_argument("query")
    args = parser.parse_args(argv)

    if args.command == "market":
        run_market(args)
    else:
        run_analyze(args.query)


if __name__ == "__main__":
    main()
