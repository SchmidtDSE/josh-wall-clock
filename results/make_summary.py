"""Regenerate results/summary.csv from results/all_results.csv.

Aggregates the raw per-host data points into one row per configuration
(implementation x model x threaded): count, mean/min/max/stddev wall seconds,
and mean user seconds.

Usage: python3 results/make_summary.py [all_results.csv] [summary.csv]
"""

import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "all_results.csv")
DST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "summary.csv")

groups = {}
with open(SRC, newline="") as handle:
    for row in csv.DictReader(handle):
        key = (row["implementation"], row["model"], row["threaded"])
        groups.setdefault(key, []).append(
            (float(row["wallSeconds"]), float(row["userSeconds"]))
        )

headers = [
    "implementation",
    "model",
    "threaded",
    "n",
    "mean_wall_s",
    "min_wall_s",
    "max_wall_s",
    "stddev_wall_s",
    "mean_user_s",
]

with open(DST, "w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(headers)
    for impl, model, threaded in sorted(groups):
        walls = [w for w, _ in groups[(impl, model, threaded)]]
        users = [u for _, u in groups[(impl, model, threaded)]]
        writer.writerow([
            impl,
            model,
            threaded,
            len(walls),
            f"{statistics.mean(walls):.1f}",
            f"{min(walls):.1f}",
            f"{max(walls):.1f}",
            f"{statistics.pstdev(walls):.1f}",
            f"{statistics.mean(users):.1f}",
        ])

print("wrote", DST)
