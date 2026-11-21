# Stage 3b: a pull request with worse retrieval cannot be merged

Run 2026-11-21 on GitHub Actions. The files behind every line below are in
[`bench/results/2026-11-21_ci-gate/`](../bench/results/2026-11-21_ci-gate/), and both pull requests are public.

## What runs

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every pull request and every push to `main`, on
`ubuntu-24.04` runners, with every action pinned to a commit hash.

| job | what it does | time on the first run |
|---|---|---|
| `lint-unit` | ruff, the unit tests against a fake model server (no network), the alert rule's unit tests with promtool | 21 s |
| `retrieval-gate` | recall@5 on the 119 answerable golden questions, through the function `/ask` calls; fails below 91/119 | 12 s |
| `kind-install` | builds the image, checks it holds no torch, creates a kind cluster, installs the chart with a stub model server, sends one `/ask` through the cluster | 80 s |

All three are required status checks on `main` (branch protection, no review requirement, not enforced on the
repository owner's own pushes).

## Result

| pull request | change | `lint-unit` | `kind-install` | `retrieval-gate` | outcome |
|---|---|---|---|---|---|
| [#1](https://github.com/CY-HYUN/rag-golden-serve/pull/1) | `/ask` keeps at most one chunk per paper, so its five sources come from five papers | pass | pass | **fail: recall@5 = 48/119 = 0.4034** (baseline 91/119 = 0.7647) | merge state `BLOCKED`; closed without merging |
| [#2](https://github.com/CY-HYUN/rag-golden-serve/pull/2) | the gate prints recall before its verdict | pass | pass | pass: 91/119 = 0.7647 | merge state `CLEAN`; merged |

The change of #1 looks like a presentation tweak, and nothing but the gate objects: the unit tests pass because five
sources still come back, and the service still installs and answers on the cluster. Recall falls because the best
evidence is often the second chunk of a paper whose first chunk is already taken.

Trying to merge #1 without administrator rights was refused:

```
X Pull request CY-HYUN/rag-golden-serve#1 is not mergeable: the base branch policy prohibits the merge.
```

## What the first red run got wrong

The first run of #1 ([run 44922034929](https://github.com/CY-HYUN/rag-golden-serve/actions/runs/44922034929)) was
red for the wrong reason. The gate asserted "exactly five chunks per question" before it
measured anything, #1 returns fewer than five for some questions, and so the log showed a failed length check and no
recall. #2 is the fix: the gate now requires at most five chunks, prints recall, then compares. After `main` was merged
into #1's branch the same pull request failed on the number (the row above).

## Checks on the numbers

- **The gate measures the service's own path.** It imports `retrieve` from `rag_golden_serve.app`, the function `/ask`
  calls, and scores it with rag-golden-eval's `retrieval_metrics`. It does not read rag-golden-eval's cached
  `results/retrieval.json`.
- **Same number locally and on the runner.** 91/119 on a Windows laptop and on `ubuntu-24.04`; 48/119 for #1 in both
  places. The library versions are pinned in `uv.lock` (bm25s 0.3.13, PyStemmer 3.1.0, numpy 2.5.3).
- **The stub is visible in the output.** The `/ask` answer in `kind-install` is the stub's fixed sentence, with five
  real chunk ids from the corpus beside it: that job tests the image, the chart and the wiring, not a model.

## Limits

- One failing and one passing pull request. Other ways of breaking retrieval were only measured locally: the BM25 top
  50 reversed gives 1/119, the query cut to its first 8 words gives 42/119.
- The baseline is a count on one frozen golden set. A change that keeps 91 hits by trading questions passes.
- The owner can still push to `main` directly and can merge with administrator rights; the rule guards pull requests.
- `kind-install` does not run the real model server, and nothing in CI measures answer quality or latency.

## Reproduce

```
uv run pytest -q -s tests/test_retrieval_gate.py        # prints recall@5 and passes on main
gh pr checks 1 --repo CY-HYUN/rag-golden-serve          # the three checks of the blocked pull request
```
