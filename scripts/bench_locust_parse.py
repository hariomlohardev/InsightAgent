"""BF-01 locust parser — assert p95 from locust --csv export."""

import argparse
import csv
from pathlib import Path
import json
import sys


def parse_locust(csv_path: Path, p95_ms: int = 150, expect_hit_rate: float = None):
    # locust --csv writes <prefix>_stats.csv with header Name, # reqs, # fails, Avg, Min, Max, Median, ...
    # Newer locust: columns via DictReader
    if not csv_path.exists():
        # try find stats file
        cand = list(csv_path.parent.glob(f"{csv_path.stem}*.csv"))
        # prefer *_stats.csv
        for c in cand:
            if "stats" in c.name:
                csv_path = c
                break
        else:
            if cand:
                csv_path = cand[0]
    if not csv_path.exists():
        print(f"no csv at {csv_path}", file=sys.stderr)
        sys.exit(2)
    rows = list(csv.DictReader(open(csv_path)))
    # Find Aggregated row
    agg = None
    for r in rows:
        if r.get("Name") == "Aggregated" or r.get("Name") == "Aggregated ":
            agg = r
            break
    if not agg:
        agg = rows[-1] if rows else {}
    # p95 column name variants: "95%", "p95", "95 percentile"
    p95 = None
    for k in ["95%", "p95", "95 percentile", "99%"]:
        if k in agg:
            try:
                p95 = float(agg[k])
                break
            except:
                pass
    if p95 is None:
        # try any key containing 95
        for k, v in agg.items():
            if "95" in k:
                try:
                    p95 = float(v)
                    break
                except:
                    pass
    if p95 is None:
        print(f"could not find p95 in {agg}", file=sys.stderr)
        sys.exit(2)
    # Also get hit cache if present via extra log? ignore
    ok = p95 <= p95_ms
    result = {
        "csv": str(csv_path),
        "p95_ms": p95,
        "gate_p95_ms": p95_ms,
        "pass": ok,
        "aggregated": agg,
    }
    print(json.dumps(result, indent=2))
    if not ok:
        print(f"FAIL p95 {p95:.0f}ms > gate {p95_ms}ms", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"PASS p95 {p95:.0f}ms <= {p95_ms}ms")
        sys.exit(0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, required=True)
    ap.add_argument("--p95", type=int, default=150)
    ap.add_argument("--expect-hit-rate", type=float, default=None)
    args = ap.parse_args()
    parse_locust(Path(args.csv), p95_ms=args.p95, expect_hit_rate=args.expect_hit_rate)
