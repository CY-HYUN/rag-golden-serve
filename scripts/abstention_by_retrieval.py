"""Split the false abstentions of each prompt version by whether retrieval brought the gold evidence into the top 5.

    PYTHONPATH=src:vendor/rag-golden-eval uv run python scripts/abstention_by_retrieval.py bench/results/<date>_prompt-versions

An abstention on an answerable question whose evidence never reached the model is the right call for the model, and a
retrieval failure for the pipeline; only abstentions with the evidence in front of the model are the prompt's fault.
"""
import json
import sys
from pathlib import Path

from rge.common import chunks, hits, load_golden

from rag_golden_serve.app import retrieve


def main() -> None:
    run = Path(sys.argv[1])
    rows = {(r["id"], r["version"]): r for r in map(json.loads, (run / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    cs = chunks()
    answerable = [q for q in load_golden() if q.type != "unanswerable"]
    found = {q.id: any(hits(cs[i], ev) for i in retrieve(q.question) for ev in q.evidence) for q in answerable}
    assert sum(found.values()) == 91, sum(found.values())  # the retrieval gate's baseline: same function, same count
    print("| prompt | false abstentions, evidence in the top 5 | false abstentions, evidence not retrieved |")
    print("|---|---|---|")
    for v in ("v1", "v2"):
        inside = sum(rows[(q.id, v)]["abstained"] is True for q in answerable if found[q.id])
        outside = sum(rows[(q.id, v)]["abstained"] is True for q in answerable if not found[q.id])
        print(f"| {v} | {inside}/{sum(found.values())} | {outside}/{len(answerable) - sum(found.values())} |")


if __name__ == "__main__":
    main()
