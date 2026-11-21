"""Two prompt versions on the golden set, through /ask: how often each one abstains.

    python3 scripts/prompt_compare.py bench/results/<date>_prompt-versions     # standard library only; needs the stack up

One /ask call per golden question and prompt version (temperature 0, fixed seed). A call that already has an answer
in answers.jsonl is skipped and a failed one is tried again, so an interrupted run is resumed by the same command.

  abstention_acc    share of the unanswerable questions where the reply starts with NOT_IN_CONTEXT (higher is better)
  false_abstention  share of the answerable questions where it does (lower is better)

Names and definitions are rag-golden-eval's (rge/harness.py, generation_metrics). A failed call has no abstention
verdict: summarize() keeps it in the denominator and counts it under `failed` (tests/test_prompt_compare.py).
--against <other run folder> also prints how many calls the two runs share and how many of those got the same answer.
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "vendor" / "rag-golden-eval" / "data" / "golden_set_v1.jsonl"


def read(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["id"], r["version"]): r for r in rows}


def ask(app: str, question: str, version: str) -> dict:
    req = urllib.request.Request(f"{app}/ask", json.dumps({"question": question, "prompt_version": version}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return {"status": r.status, **json.load(r)}
    except urllib.error.HTTPError as e:
        return {"status": e.code}


def summarize(rows: list[dict], versions: list[str]) -> dict:
    out = {}
    for v in versions:
        mine = [r for r in rows if r["version"] == v]
        una = [r for r in mine if r["type"] == "unanswerable"]
        ans = [r for r in mine if r["type"] != "unanswerable"]
        out[v] = {"unanswerable": len(una), "abstained_unanswerable": sum(bool(r.get("abstained")) for r in una),
                  "answerable": len(ans), "abstained_answerable": sum(bool(r.get("abstained")) for r in ans),
                  "failed": sum(r["status"] != 200 for r in mine)}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--app", default="http://localhost:8000")
    p.add_argument("--versions", nargs="+", default=["v1", "v2"])
    p.add_argument("--every", type=int, default=1, help="take every Nth golden question (a repeat run on a subset)")
    p.add_argument("--against", type=Path, help="another run folder to compare answers with")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / "answers.jsonl"
    done = read(path)
    questions = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()][::a.every]
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for n, q in enumerate(questions, 1):
            for v in a.versions:  # versions alternate, so an interrupted run holds both for the same questions
                if done.get((q["id"], v), {}).get("status") == 200:  # a failed call is tried again
                    continue
                r = ask(a.app, q["question"], v)
                row = {"id": q["id"], "type": q["type"], "version": v, "status": r["status"],
                       "abstained": r.get("abstained"), "answer": r.get("answer"),
                       "generate_seconds": r.get("generate_seconds")}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                done[(q["id"], v)] = row
            print(f"{n}/{len(questions)}", flush=True)
    summary = summarize(list(done.values()), a.versions)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("| prompt | abstention_acc (unanswerable) | false_abstention (answerable) | failed |")
    print("|---|---|---|---|")
    for v, s in summary.items():
        print(f"| {v} | {s['abstained_unanswerable']}/{s['unanswerable']} = "
              f"{s['abstained_unanswerable'] / max(s['unanswerable'], 1):.3f} | "
              f"{s['abstained_answerable']}/{s['answerable']} = "
              f"{s['abstained_answerable'] / max(s['answerable'], 1):.3f} | {s['failed']} |")
    if a.against:
        other = read(a.against / "answers.jsonl")
        shared = [k for k in done if k in other and done[k]["status"] == other[k]["status"] == 200]
        same = sum(done[k]["answer"] == other[k]["answer"] for k in shared)
        flips = sum(done[k]["abstained"] != other[k]["abstained"] for k in shared)
        print(f"against {a.against.name}: {len(shared)} calls in both runs, {same} with the same answer, "
              f"{flips} with a different abstention verdict")


if __name__ == "__main__":
    main()
