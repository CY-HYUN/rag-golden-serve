# The service image: the app, the pinned rag-golden-eval code and corpus, and only the packages /ask needs.
# rag-golden-eval's own dependency list is not installed: its embedding rungs would pull a multi-gigabyte torch.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
COPY vendor/rag-golden-eval/rge vendor/rag-golden-eval/rge
COPY vendor/rag-golden-eval/data/corpus.jsonl.gz vendor/rag-golden-eval/data/corpus.jsonl.gz
COPY src src
# the stub model server CI deploys next to the service (deploy/helm/values-ci.yaml)
COPY tests/fake_model.py tests/fake_model.py
# the commit the image was built from; /healthz reports it, so a rollout or a rollback can be seen from outside
ARG GIT_SHA=dev
ENV APP_VERSION=$GIT_SHA
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/src:/app/vendor/rag-golden-eval PYTHONUNBUFFERED=1
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "rag_golden_serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
