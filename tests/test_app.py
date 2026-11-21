"""/ask against a fake model server (httpx.MockTransport): no network, no model."""
import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from rge.harness import ABSTAIN

from rag_golden_serve import app as service

QUESTION = {"question": "Which optimizer was used to train the model?"}


def completion(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})


@pytest.fixture(scope="module")
def api():
    with TestClient(service.app) as c:  # the context manager runs the lifespan, which builds the index
        yield c


@pytest.fixture
def model(monkeypatch):
    """Install a handler as the model server; returns the list of request bodies it received."""
    seen = []

    def install(handler):
        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)
        monkeypatch.setattr(service, "client", httpx.Client(transport=httpx.MockTransport(record)))
        return seen
    return install


def count(status: str) -> float:
    return service.REQUESTS.labels(status)._value.get()


def test_answer_with_five_sources(api, model):
    seen = model(lambda request: completion("They used AdamW."))
    before = count("200")
    r = api.post("/ask", json=QUESTION)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "They used AdamW." and body["abstained"] is False and body["prompt_version"] == "v1"
    assert len(body["sources"]) == 5 and all("#" in s["chunk_id"] for s in body["sources"])
    assert count("200") == before + 1
    sent = seen[0].read().decode()
    assert "Context passages:" in sent and QUESTION["question"] in sent and service.PROMPTS["v1"] in sent


def test_abstention_marker_is_reported(api, model):
    model(lambda request: completion(ABSTAIN))
    assert api.post("/ask", json=QUESTION).json()["abstained"] is True


def test_prompt_version_reaches_the_model(api, model):
    seen = model(lambda request: completion("x"))
    api.post("/ask", json=QUESTION | {"prompt_version": "v2"})
    assert service.PROMPTS["v2"] in seen[0].read().decode()  # the whole text: v1 and v2 share their first words
    assert api.post("/ask", json=QUESTION | {"prompt_version": "v3"}).status_code == 422


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_generate_span_links_the_langfuse_prompt(api, model, monkeypatch, version):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(service, "tracer", provider.get_tracer("test"))
    model(lambda request: completion("x"))
    api.post("/ask", json=QUESTION | {"prompt_version": version})
    attrs = next(s for s in exporter.get_finished_spans() if s.name == "generate").attributes
    assert attrs["langfuse.observation.type"] == "generation"
    assert attrs["langfuse.observation.prompt.name"] == "rag-golden-serve-answer"
    assert attrs["langfuse.observation.prompt.version"] == {"v1": 1, "v2": 2}[version]
    assert set(service.LANGFUSE_PROMPT_VERSIONS) == set(service.PROMPTS)


def raise_connect_error(request):
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("handler", [
    raise_connect_error,                                           # server down
    lambda request: httpx.Response(500, text="boom"),              # server error
    lambda request: httpx.Response(200, json={"unexpected": 1}),   # not a chat completion
    lambda request: httpx.Response(200, text="not json"),
    lambda request: httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
], ids=["down", "http-500", "wrong-shape", "not-json", "null-content"])
def test_model_failure_is_a_502_and_is_counted(api, model, handler):
    model(handler)
    before = count("502")
    r = api.post("/ask", json=QUESTION)
    assert r.status_code == 502 and r.json()["detail"].startswith("model server:")
    assert count("502") == before + 1


def test_metrics_expose_both_stages(api, model):
    model(lambda request: completion("x"))
    api.post("/ask", json=QUESTION)
    text = api.get("/metrics").text
    assert 'rag_stage_seconds_count{stage="retrieve"}' in text and 'rag_stage_seconds_count{stage="generate"}' in text
    assert 'rag_requests_total{status="200"}' in text and 'rag_requests_total{status="500"}' in text


def test_failed_model_call_is_not_a_generation_latency(api, model):
    model(raise_connect_error)
    before = service.STAGE_SECONDS.labels("generate")._sum.get()
    api.post("/ask", json=QUESTION)
    assert service.STAGE_SECONDS.labels("generate")._sum.get() == before


def test_health_does_not_call_the_model(api, model):
    seen = model(raise_connect_error)
    r = api.get("/healthz")
    assert r.status_code == 200 and r.json()["chunks"] > 0 and not seen
