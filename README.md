# rag-golden-serve

The question-answering pipeline of [rag-golden-eval](https://github.com/CY-HYUN/rag-golden-eval), turned into a service
that is served, observed and deployed. The retriever and the golden set come from that repository at a pinned commit,
so the evaluation set that measured the pipeline is also the check that gates each change to the service.

Every stage ends with one measured line and the command that reproduces it. A stage with no number is not done.

## Status

**Nothing is measured yet.** Stage 0 (environment) is done and recorded in
[docs/stage0-environment.md](docs/stage0-environment.md); the table fills as stages finish.

| stage | what it shows | result | reproduce |
|---|---|---|---|
| 1. serving | an open model behind vLLM on a Colab T4: time to first token and output tokens/s at concurrency 1 to 32, three repeats | - | - |
| 2. observability | Prometheus, Grafana and OpenTelemetry on the service: latency per stage, and an alert seen both silent and firing | - | - |
| 3a. Kubernetes and Helm | a local cluster (kind): one rollout of a new version and one rollback | - | - |
| 3b. CI | the retrieval check on every pull request: a pull request with broken retrieval is blocked before merge | - | - |
| 3c. Terraform | cluster and namespace created and destroyed from code | - | - |

## Design in short

- **Service.** `POST /ask`: BM25 retrieval over the rag-golden-eval corpus, then generation through an
  OpenAI-compatible endpoint. If the model server is down, `/ask` answers 502, so the error-rate alert can see it.
- **Two environments, never mixed.** Serving numbers are measured on a GPU (Colab T4, benchmark client and server
  in the same notebook). The deployed stack runs on a laptop and talks only to a local CPU server with the same API.
- **The retrieval gate.** recall@5 on the 119 answerable questions of the golden set, computed through the same
  function `/ask` uses, must stay at or above 0.7647 (91 of 119), the BM25 value committed in rag-golden-eval's
  `results/summary.json`. BM25 is deterministic at fixed library versions, so the rule is exact.
- **Who owns what.** Terraform owns the cluster and the namespace. Helm owns the release and its rollback.
- **Out of scope.** Answer-quality scoring with a judge model, retrieval improvements, cloud deployment, GPUs on
  Kubernetes, autoscaling, a front end.

The full reasoning, the options that were rejected and the stop line of each stage are in [docs/design.md](docs/design.md).

## Layout

```
src/rag_golden_serve/   the service (stage 2)
tests/                  unit tests with a fake model, and the retrieval gate
bench/                  stage 1: the Colab notebook and its result files
observability/          Prometheus, alert rules, Grafana, OpenTelemetry Collector
deploy/helm/            the chart
deploy/terraform/       cluster and namespace
docs/                   design and the environment record
```

Paths are relative to the repository root or come from environment variables. `.env.example` lists the variables;
`.env` is never committed.

## License

MIT
