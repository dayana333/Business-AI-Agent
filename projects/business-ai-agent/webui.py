"""One-page market research UI (stdlib only): python3 webui.py 8000

Open https://kitan-a.com/frp/s12/proxy/8000/ while it runs.
"""

import argparse
import datetime as dt
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from TOOLS import collect, insights, market_data, recommend, reviews  # noqa: E402

PAGE = ROOT / "index.html"


def analyze(query):
    query = (query or "").strip()[:120]
    if not query:
        raise ValueError("Введите название товара")
    rows, statuses = collect.collect(query)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    data_path = ROOT / "data" / f"search_{collect.slug(query)}.csv"
    collect.write_csv(rows, data_path)
    collect.write_status(ROOT / "data" / "collection_status.json", query, statuses, rows)
    if not rows:
        return {
            "ok": False,
            "query": query,
            "statuses": statuses,
            "message": "Kaspi returned no data. The report is not built and nothing is invented.",
            "stamp": stamp,
        }

    raw_coverage = {
        name: len([r for r in rows if r.get("marketplace") == name])
        for name in ("kaspi",)
    }
    picks = recommend.recommend(rows, query)
    relevant = picks.pop("relevant_rows", rows)
    if picks["status"] in ("no_relevant", "insufficient_relevant", "insufficient_data", "insufficient_quality", "insufficient_distinct"):
        message = picks.get("reason", "No suitable products were found.")
        examples = []
        for e in picks.get("filtered_examples", [])[:3]:
            if not e.get("title"):
                continue
            price = e.get("price_kzt")
            label = f"{price:,.0f} KZT".replace(",", " ") if price else "price unknown"
            examples.append(f"{e['title']} ({label})")
        if examples:
            message += " Excluded examples: " + "; ".join(examples) + "."
        return {
            "ok": False,
            "query": query,
            "stamp": stamp,
            "statuses": statuses,
            "coverage": raw_coverage,
            "raw_coverage": raw_coverage,
            "picks": picks,
            "message": message,
        }

    collect.write_csv(relevant, data_path)
    facts = market_data.summarise(relevant, str(data_path.relative_to(ROOT)))
    per_market = {}
    for name in ("kaspi",):
        subset = [r for r in relevant if r.get("marketplace") == name]
        if subset:
            per_market[name] = recommend.recommend(subset)
    coverage = {
        name: len([r for r in relevant if r.get("marketplace") == name])
        for name in ("kaspi",)
    }
    review_data = reviews.collect_for_picks(picks, pages=4)
    reviews.attach_to_picks(picks, review_data)
    picks = reviews.apply_original_gate(picks)
    if picks.get("status") == "no_likely_original":
        return {
            "ok": False,
            "query": query,
            "stamp": stamp,
            "statuses": statuses,
            "coverage": coverage,
            "raw_coverage": raw_coverage,
            "picks": picks,
            "message": picks.get("reason", "No likely-original Kaspi pick was found."),
        }
    report = insights.build(relevant, facts, picks, statuses, coverage, query, review_data=review_data)

    return {
        "ok": True,
        "query": query,
        "stamp": stamp,
        "statuses": statuses,
        "facts": facts,
        "picks": picks,
        "per_market": per_market,
        "coverage": coverage,
        "raw_coverage": raw_coverage,
        "filtered_out": picks.get("filtered_out", 0),
        "review_analysis": review_data,
        "report": report,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if not PAGE.exists():
                self._send(500, "index.html missing", "text/plain; charset=utf-8")
                return
            self._send(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/analyze":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            try:
                result = analyze(query)
            except ValueError as exc:
                self._send(400, str(exc), "text/plain; charset=utf-8")
            except Exception as exc:
                self._send(500, f"{type(exc).__name__}: {exc}", "text/plain; charset=utf-8")
            else:
                self._send(200, json.dumps(result, ensure_ascii=False))
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}/  (stop with Ctrl+C)")
    server.serve_forever()


if __name__ == "__main__":
    main()
