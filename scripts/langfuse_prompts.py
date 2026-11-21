"""Put the two prompt versions of /ask into Langfuse prompt management, and list what Langfuse holds.

    PYTHONPATH=src:vendor/rag-golden-eval uv run python scripts/langfuse_prompts.py          # create if missing, then list
    PYTHONPATH=src:vendor/rag-golden-eval uv run python scripts/langfuse_prompts.py --traces # also show the latest traces

Reads LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY from .env (written by scripts/langfuse_env.sh);
the keys are never printed. The prompt texts are taken from the service itself (rag_golden_serve.app.PROMPTS), so
Langfuse holds exactly what /ask sends. Version 1 is v1 (label "production", the default), version 2 is v2.
"""
import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rag_golden_serve.app import PROMPTS

ROOT = Path(__file__).resolve().parent.parent
NAME = "rag-golden-serve-answer"


def settings() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    missing = [k for k in ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if not env.get(k)]
    if missing:
        sys.exit(f".env lacks {missing}: run bash scripts/langfuse_env.sh")
    return env


def call(env: dict, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    auth = base64.b64encode(f"{env['LANGFUSE_PUBLIC_KEY']}:{env['LANGFUSE_SECRET_KEY']}".encode()).decode()
    req = urllib.request.Request(env["LANGFUSE_BASE_URL"].rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:300]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--traces", action="store_true")
    a = p.parse_args()
    env = settings()
    status, body = call(env, "GET", f"/api/public/v2/prompts/{urllib.parse.quote(NAME)}")
    if status == 404:
        for version, labels in (("v1", ["production", "v1"]), ("v2", ["v2"])):
            s, b = call(env, "POST", "/api/public/v2/prompts",
                        {"name": NAME, "type": "text", "prompt": PROMPTS[version], "labels": labels,
                         "commitMessage": f"/ask prompt {version}, from rag_golden_serve.app.PROMPTS"})
            print(f"create {version}: HTTP {s}", b.get("version", b.get("error", "")))
            if s >= 300:
                sys.exit(1)
    elif status != 200:
        sys.exit(f"GET prompt: HTTP {status} {body.get('error', '')}")
    s, listing = call(env, "GET", f"/api/public/v2/prompts?name={urllib.parse.quote(NAME)}")
    for item in listing.get("data", []):
        print("prompt", item.get("name"), "versions", item.get("versions"), "labels", item.get("labels"))
    for version, text in PROMPTS.items():
        s, b = call(env, "GET", f"/api/public/v2/prompts/{urllib.parse.quote(NAME)}?label={version}")
        print(f"label {version}: HTTP {s}, version {b.get('version')}, same text as the service: {b.get('prompt') == text}")
    if a.traces:  # /api/public/traces was removed on 2026-11-16; observations v2 is its replacement (API answer, 2026-11-21)
        since = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        s, b = call(env, "GET", f"/api/public/v2/observations?fields=core,basic&fromStartTime={since}&limit=50")
        rows = b.get("data", [])
        print(f"observations in the last hour: HTTP {s}, rows {len(rows)} {b.get('error', '')[:200]}")
        traces = {}
        for o in rows:
            traces.setdefault(o.get("traceId"), []).append(o)
        print("traces among them:", len(traces))
        for tid, obs in list(traces.items())[:2]:
            print(" ", tid, sorted((o.get("name"), o.get("type")) for o in obs))


if __name__ == "__main__":
    main()
