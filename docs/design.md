# Design

Written 2026-11-21, before the first line of code. One fresh reviewer with no history of the drafting read it;
all 14 of its findings were taken (3 high: how the evaluation repository is consumed, running the gate on pull
requests, gating the service's own retrieval path).

## Problem

rag-golden-eval measures a retrieval-augmented question-answering pipeline offline: a frozen golden set, scorers
written before the pipeline, a noise band from repeated runs. It says nothing about running that pipeline as a
service: how fast a served model answers under load, what an operator sees when it degrades, how a change reaches a
cluster and how a bad one is stopped or rolled back. This repository adds exactly that, one stage at a time, and
each stage must end in a number somebody else can reproduce.

## Constraints

| constraint | value |
|---|---|
| machine | one laptop: 10 cores, 40 GB RAM, no NVIDIA GPU, AVX2 but no AVX-512 |
| vLLM on CPU | Linux only; AVX-512 recommended, AVX2 "limited features" (vLLM CPU install page, read 2026-11-21) |
| money | no cloud bill and no paid model calls |
| data | the public arXiv snapshot of rag-golden-eval (CC BY 4.0) only |

## Decisions

**What is served.** Three options: (A) a question-answering service over rag-golden-eval's retriever and golden
set, (B) the verifier API of another repository, which already has a Dockerfile but calls no model, (C) a bare model
endpoint with a load test. A is chosen: a request crosses two stages (retrieve, generate), so per-stage latency
means something, and the golden set becomes the pre-deploy check.

**Where the model runs.** Serving is measured on a free Colab T4 with vLLM; the deployed stack uses a local CPU
server with the same OpenAI-compatible API. Running everything on the laptop CPU would not show the effect of
batching concurrent requests, and a managed API would give no serving evidence. The two environments are never
connected: Colab's terms forbid remote proxies, and the local stack only talks to the local server.

**How rag-golden-eval is consumed.** It is not an installable package (no build configuration; `rge/common.py`
finds its data next to the code or under `RGE_ROOT`). It comes in as a git submodule at a fixed commit, with
`RGE_ROOT` and `PYTHONPATH` pointing at it. The service image installs only bm25s, PyStemmer and pydantic at the
versions of its `uv.lock`; installing its full dependency list would pull a multi-gigabyte torch for the embedding
rungs this service does not use.

**Tracing and prompt versions.** Langfuse Cloud's free plan, because the data is public. Self-hosting needs six
services whose documented minimum memory adds up to 25.5 GiB when blob storage is self-hosted too.

**Terraform and Helm.** One release with two owners drifts: a `helm rollback` would fight the next
`terraform apply`. Terraform stops at cluster and namespace; Helm owns the release. Terraform state stays local and
out of git.

## Stages and stop lines

| stage | work | stop line |
|---|---|---|
| 0. environment | Ubuntu on WSL2 with its disk off the system drive, Docker Engine, kind, kubectl, helm, terraform, one answer from a local CPU model server | the five tool versions recorded in `docs/stage0-environment.md`; free space on the system drive before and after |
| 1. serving | Qwen2.5-0.5B-Instruct on vLLM, Colab T4; fixed input and output lengths; concurrency 1, 4, 16, 32; p50 and p95 of time to first token and output tokens/s; three repeats in one session | one table, one figure, the spread of the repeats. No tuning, no quantisation comparison |
| 2. service and observability | `/ask`; request, 5xx and per-stage latency metrics; spans per stage; one Grafana dashboard; one alert (5xx ratio above 5% for 1 minute); two prompt versions compared on abstention over the 21 unanswerable questions and false abstention over the 119 answerable ones, by string match | a dashboard screenshot; two alert records with timestamps (Normal over 10 minutes and 100 requests, Firing after the model server is stopped); the two-ratio table |
| 3a. Kubernetes and Helm | image tagged with the commit hash; kind; chart with probes, requests and limits. Readiness checks only the in-process BM25 index, built at start-up | one `helm upgrade`, one `helm rollback`; the image holds no torch; its size |
| 3b. CI | on every pull request: lint, unit tests with a fake model, the retrieval gate, install on kind inside the runner with a fake model server and one `/ask` call | one pull request with broken retrieval blocked by the required check; one green pull request |
| 3c. Terraform | cluster and namespace | one `terraform apply`, one `terraform destroy` |

Stages are independent: the repository stands after stage 1 alone. When a stop line is reached the stage is closed;
polishing is not a reason to stay.

## Verification

- **A check counts only after it has fired.** The alert and the CI gate are each recorded once silent and once
  firing. Reversing the BM25 top 50 drops recall@5 to 0.0084, so the gate can see a broken retriever.
- **The gate does not reuse cached results.** `rge.harness.retrieve_all` returns the committed
  `results/retrieval.json` whenever it exists, so the gate calls the service's retrieval function directly and scores
  it with `retrieval_metrics`.
- **Undo.** Unregister the WSL distribution; everything this project installs lives inside it.

## Not known yet

- What vLLM's "limited features" on AVX2 leaves out. Stage 0 settles it with a 30-minute trial; llama.cpp's server
  is the fallback (same API).
- Whether a free Colab session gets a T4 every time, and whether vLLM needs `--dtype half` there. The measurement
  script writes one result file per concurrency level so a cut session can resume.
