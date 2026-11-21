"""POST /ask: BM25 retrieval over the rag-golden-eval corpus, then one call to an OpenAI-compatible model server.

    PYTHONPATH=src:vendor/rag-golden-eval uv run uvicorn rag_golden_serve.app:app --port 8000

The retriever, the passage format, the generator prompt and the abstention marker come from rag-golden-eval (a git
submodule at a pinned commit), so what the golden set measured offline is what this service runs.
"""
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from rge import retrieve as rge_retrieve
from rge.common import TOP_K_GEN, chunks
from rge.harness import ABSTAIN, GEN_SYSTEM, abstained, passages

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8001/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-0.5b-instruct")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "120"))
MAX_ANSWER_TOKENS = 128  # the prompt asks for one to three sentences

# v1 is rag-golden-eval's generator prompt, unchanged. v2 changes one thing: the abstention rule comes first and is
# tied to the passages. docs/stage2-observability.md compares the two on the golden set.
PROMPTS = {
    "v1": GEN_SYSTEM,
    "v2": ("You answer questions about recent machine-learning research papers from the context passages you are "
           f"given. First decide whether the passages contain the answer. If they do not, reply with exactly {ABSTAIN} "
           "and nothing else. If they do, answer in one to three sentences using only the passages."),
}
# Langfuse prompt management holds both texts under one name; scripts/langfuse_prompts.py creates them and fails when
# a label resolves to another version or text. The generate span carries the pair, so each answer links to its prompt.
LANGFUSE_PROMPT_NAME = "rag-golden-serve-answer"
LANGFUSE_PROMPT_VERSIONS = {"v1": 1, "v2": 2}
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v1")
if PROMPT_VERSION not in PROMPTS:  # a bad setting stops the start-up instead of failing every request later
    raise RuntimeError(f"PROMPT_VERSION={PROMPT_VERSION!r}, expected one of {sorted(PROMPTS)}")

REQUESTS = Counter("rag_requests_total", "Requests to /ask that passed validation, by HTTP status", ["status"])
for _status in ("200", "500", "502"):
    REQUESTS.labels(_status)  # exported at 0 from the start, so rate() also sees the first one of each
STAGE_SECONDS = Histogram("rag_stage_seconds", "Seconds spent in one pipeline stage of /ask", ["stage"],
                          # fine steps where the two stages land on a laptop CPU: retrieval near 1 ms, generation near 30 s
                          buckets=(.0005, .001, .0025, .005, .01, .05, .25, 1, 2.5, 5, 10, 15, 20, 25, 30, 35, 40, 60, 120))
tracer = trace.get_tracer("rag_golden_serve")
client = httpx.Client(timeout=LLM_TIMEOUT_S)  # tests replace this with a mock transport


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    prompt_version: Literal["v1", "v2"] | None = Field(None, description="defaults to the PROMPT_VERSION variable")


class Source(BaseModel):
    chunk_id: str
    paper_id: str


class AskResponse(BaseModel):
    answer: str
    abstained: bool = Field(..., description=f"the model replied {ABSTAIN}")
    prompt_version: str
    sources: list[Source]
    retrieve_seconds: float
    generate_seconds: float


def retrieve(question: str, k: int = TOP_K_GEN) -> list[int]:
    """Chunk indexes, best first. The one retrieval path: /ask and the retrieval gate both call this."""
    return rge_retrieve.bm25(question, k)


def generate(question: str, ids: list[int], system: str) -> str:
    r = client.post(f"{LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {},
                    json={"model": LLM_MODEL, "max_tokens": MAX_ANSWER_TOKENS, "temperature": 0, "seed": 0,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": f"{passages(ids)}\n\nQuestion: {question}"}]})
    r.raise_for_status()
    body = r.json()
    answer = body["choices"][0]["message"]["content"]
    if not isinstance(answer, str):
        raise TypeError("content is not a string")
    usage = body.get("usage") or {}  # token counts explain the latency: prompt length dominates on a CPU
    span = trace.get_current_span()
    span.set_attribute("gen_ai.usage.input_tokens", usage.get("prompt_tokens", 0))
    span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))
    return answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    retrieve("warm up")  # builds the BM25 index before the first request, so readiness means "index in memory"
    yield


app = FastAPI(title="rag-golden-serve", version="0.1.0", lifespan=lifespan)
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):  # tracing is off unless a collector is named
    provider = TracerProvider()  # service.name comes from OTEL_SERVICE_NAME
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics", exclude_spans=["receive", "send"])


@app.get("/healthz")
async def healthz() -> dict:  # async: answered on the event loop, so slow /ask calls cannot starve the probes
    """Liveness and readiness. It does not call the model server: when that is down /ask answers 502, the error-rate
    alert fires, and the pod stays in rotation so the failure remains visible."""
    return {"status": "ok", "chunks": len(chunks()), "version": os.environ.get("APP_VERSION", "dev")}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    status = 500  # anything not handled below is counted as a 500
    version = req.prompt_version or PROMPT_VERSION
    try:
        t0 = time.perf_counter()
        with tracer.start_as_current_span("retrieve") as span:
            ids = retrieve(req.question)
            span.set_attribute("rag.chunk_ids", [chunks()[i]["id"] for i in ids])
        t1 = time.perf_counter()
        STAGE_SECONDS.labels("retrieve").observe(t1 - t0)
        with tracer.start_as_current_span("generate") as span:
            span.set_attribute("gen_ai.request.model", LLM_MODEL)
            span.set_attribute("rag.prompt_version", version)
            span.set_attribute("langfuse.observation.type", "generation")  # Langfuse links prompts to generations only
            span.set_attribute("langfuse.observation.prompt.name", LANGFUSE_PROMPT_NAME)
            span.set_attribute("langfuse.observation.prompt.version", LANGFUSE_PROMPT_VERSIONS[version])
            span.set_attribute("input.value", req.question)
            try:
                answer = generate(req.question, ids, PROMPTS[version])
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
                # the model server is down, slow, or sent something that is not a chat completion;
                # leaving the span through the raise below records the exception and marks the span as an error
                status = 502
                raise HTTPException(status_code=502, detail=f"model server: {type(e).__name__}") from e
            t2 = time.perf_counter()
            STAGE_SECONDS.labels("generate").observe(t2 - t1)  # answered calls only: a fast failure is not a latency
            span.set_attribute("output.value", answer)
            span.set_attribute("rag.abstained", abstained(answer))
        status = 200
        cs = chunks()
        return AskResponse(answer=answer, abstained=abstained(answer), prompt_version=version,
                           sources=[Source(chunk_id=cs[i]["id"], paper_id=cs[i]["paper_id"]) for i in ids],
                           retrieve_seconds=t1 - t0, generate_seconds=t2 - t1)
    finally:
        REQUESTS.labels(str(status)).inc()
