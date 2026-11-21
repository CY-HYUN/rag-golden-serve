"""The retrieval gate: recall@5 over the answerable golden questions, through the function /ask calls.

The baseline is the BM25 value committed in rag-golden-eval's results/summary.json (91 of 119). BM25 is deterministic
at the pinned library versions, so the rule is exact: the count may not fall.
"""
from rge.common import load_golden
from rge.harness import retrieval_metrics

from rag_golden_serve.app import retrieve

BASELINE_HITS, ANSWERABLE = 91, 119


def test_recall_at_5_does_not_fall():
    answerable = [q for q in load_golden() if q.type != "unanswerable"]
    assert len(answerable) == ANSWERABLE
    ranked = [retrieve(q.question) for q in answerable]  # the default k, as /ask calls it
    assert all(len(r) == 5 for r in ranked)
    recall = retrieval_metrics(ranked, [q.evidence for q in answerable], k_list=(5,))["recall@5"]
    hits = round(recall * ANSWERABLE)
    print(f"retrieval gate: recall@5 = {hits}/{ANSWERABLE} = {recall:.4f} (baseline {BASELINE_HITS}/{ANSWERABLE})")
    assert hits >= BASELINE_HITS, f"recall@5 fell to {hits}/{ANSWERABLE} = {recall:.4f}"
