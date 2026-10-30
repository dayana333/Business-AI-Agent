#!/usr/bin/env python3
"""Check that SKILLS/market_analysis.md points at real files and that the
market_data tool can be found and executed the way the skill documents."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / "SKILLS" / "market_analysis.md"
SAMPLE = "data/sample_marketplace_data.csv"

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main():
    skill = SKILL.read_text(encoding="utf-8")

    refs = sorted(set(re.findall(r"[A-Za-z0-9_./-]+\.(?:py|csv|md)", skill)))
    check("skill mentions the tool file", "TOOLS/market_data.py" in refs, str(refs))
    missing = [r for r in refs if not (ROOT / r).exists()]
    check(
        "every file path in the skill exists",
        not missing,
        "missing: " + ", ".join(missing) if missing else f"{len(refs)} paths",
    )

    sys.path.insert(0, str(ROOT))
    from TOOLS import TOOLS, market_data

    spec_name = market_data.TOOL_SPEC["function"]["name"]
    check("tool name in TOOL_SPEC", spec_name == "market_data_summary", spec_name)
    check("tool is registered", TOOLS.get("market_data_summary") is market_data)
    check("skill uses the registered name", f"`{spec_name}`" in skill)
    check(
        "skill forbids invented numbers",
        "never estimate" in skill.lower() and "must actually run" in skill.lower(),
    )

    facts = market_data.summary(SAMPLE, product="Redmi Buds 6")
    check("documented Python call runs", facts["rows_analysed"] == 8, f"{facts['rows_analysed']} rows")
    check(
        "one Kaspi source has no cross-marketplace gaps",
        facts["cross_marketplace"] == [],
        str(facts["cross_marketplace"]),
    )

    proc = subprocess.run(
        [sys.executable, "TOOLS/market_data.py", SAMPLE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    check("documented shell command exits 0", proc.returncode == 0, proc.stderr[-300:])
    try:
        cli = json.loads(proc.stdout)
        check("shell command prints JSON", cli["rows_analysed"] == 8)
    except json.JSONDecodeError:
        check("shell command prints JSON", False, proc.stdout[:200])

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
