"""Table and figure for one benchmark run: python bench/summarize.py bench/results/<run>

Reads the c<concurrency>_r<repeat>.json files that `vllm bench serve --save-result` wrote, prints a markdown table
(median of the repeats, with their min and max) and writes figure.png next to them.
"""
import json
import re
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

METRICS = ("output_throughput", "median_ttft_ms", "p95_ttft_ms")
SURFACE, INK, MUTED, BLUE, ORANGE = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"


def load(run_dir):
    """{concurrency: {metric: [one value per repeat]}}; a run with a failed request is an error."""
    runs = {}
    for path in sorted(run_dir.glob("c*_r*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result["failed"] or result["completed"] != result["num_prompts"]:
            raise SystemExit(f"{path.name}: {result['completed']}/{result['num_prompts']} completed, "
                             f"{result['failed']} failed")
        concurrency = int(re.match(r"c(\d+)_r", path.name).group(1))
        if result["max_concurrency"] != concurrency:
            raise SystemExit(f"{path.name}: file name says {concurrency}, result says {result['max_concurrency']}")
        for metric in METRICS:
            runs.setdefault(concurrency, {}).setdefault(metric, []).append(result[metric])
    if not runs:
        raise SystemExit(f"no c*_r*.json under {run_dir}")
    return dict(sorted(runs.items()))


def cell(values, digits):
    return f"{statistics.median(values):.{digits}f} ({min(values):.{digits}f} to {max(values):.{digits}f})"


def table(runs):
    repeats = {len(m["output_throughput"]) for m in runs.values()}
    lines = [f"Median of {'/'.join(map(str, sorted(repeats)))} repeats, with the lowest and highest repeat in brackets.",
             "",
             "| concurrency | output tokens/s | TTFT p50 (ms) | TTFT p95 (ms) |",
             "|---|---|---|---|"]
    for concurrency, m in runs.items():
        lines.append(f"| {concurrency} | {cell(m['output_throughput'], 0)} | {cell(m['median_ttft_ms'], 0)} "
                     f"| {cell(m['p95_ttft_ms'], 0)} |")
    return "\n".join(lines)


def draw(ax, runs, metric, colour, label):
    xs = list(runs)
    values = [runs[c][metric] for c in xs]
    medians = [statistics.median(v) for v in values]
    ax.vlines(xs, [min(v) for v in values], [max(v) for v in values], color=colour, linewidth=1)
    ax.plot(xs, medians, color=colour, linewidth=2, marker="o", markersize=6, markeredgecolor=SURFACE,
            markeredgewidth=1.5, label=label)
    ax.annotate(f"{medians[-1]:.0f}", (xs[-1], medians[-1]), xytext=(8, 0), textcoords="offset points",
                va="center", color=INK, fontsize=9)


def figure(runs, out):
    plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": MUTED, "axes.edgecolor": "#d9d8d2",
                         "xtick.color": MUTED, "ytick.color": MUTED})
    fig, (left, right) = plt.subplots(1, 2, figsize=(9.5, 3.8), facecolor=SURFACE)
    draw(left, runs, "output_throughput", BLUE, None)
    left.set_title("Output tokens per second", loc="left", fontsize=11)
    draw(right, runs, "median_ttft_ms", BLUE, "p50")
    draw(right, runs, "p95_ttft_ms", ORANGE, "p95")
    right.set_title("Time to first token (ms)", loc="left", fontsize=11)
    right.legend(frameon=False, loc="upper left")
    for ax in (left, right):
        ax.set_facecolor(SURFACE)
        ax.set_xscale("log", base=2)
        ax.set_xticks(list(runs), [str(c) for c in runs])
        ax.minorticks_off()
        ax.set_xlim(min(runs) / 1.4, max(runs) * 1.7)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("concurrent requests")
        ax.grid(axis="y", color="#e9e8e3", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)


if __name__ == "__main__":
    run_dir = Path(sys.argv[1])
    runs = load(run_dir)
    print(table(runs))
    figure(runs, run_dir / "figure.png")
