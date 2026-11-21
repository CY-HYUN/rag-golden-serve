"""The alert drill of stage 2: healthy traffic, then the model server is stopped, then it comes back.

    python3 scripts/alert_drill.py bench/results/<date>_alert-drill       # standard library only; needs the compose stack up

Phase 1 sends golden-set questions to /ask one after another for --healthy-minutes (the CPU sets the pace).
Phase 2 stops the model server and keeps asking, at least --interval seconds apart, until the alert fires.
Phase 3 starts the model server again and keeps asking until the alert is inactive. The alert also goes inactive
by itself once the last failure leaves the 1-minute window, so the request file is what shows that answers came back.
Each request goes to requests.jsonl and each change of the alert's state (polled once a second) to alert_states.jsonl,
both with a UTC time. Exit code 1 if the alert was not inactive throughout phase 1, no request was answered in phase 1, or the alert
never fired in phase 2.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "vendor" / "rag-golden-eval" / "data" / "golden_set_v1.jsonl"
ALERT = "AskErrorRatioHigh"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def alert_state(prometheus: str) -> str:
    with urllib.request.urlopen(f"{prometheus}/api/v1/rules?type=alert", timeout=5) as r:
        rules = [rule for g in json.load(r)["data"]["groups"] for rule in g["rules"] if rule["name"] == ALERT]
    return rules[0]["state"]  # inactive, pending or firing


def ask(app: str, question: str) -> tuple[int, float]:
    req = urllib.request.Request(f"{app}/ask", json.dumps({"question": question}).encode(),
                                 {"Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except OSError:  # the service itself is unreachable: logged as status 0, the traffic goes on
        status = 0
    return status, time.perf_counter() - t


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--app", default="http://localhost:8000")
    p.add_argument("--prometheus", default="http://localhost:9090")
    p.add_argument("--healthy-minutes", type=float, default=10)
    p.add_argument("--interval", type=float, default=5, help="least seconds between the starts of two requests")
    p.add_argument("--give-up-minutes", type=float, default=5, help="how long phases 2 and 3 may wait for the alert")
    a = p.parse_args()
    if (a.out / "requests.jsonl").exists():  # a finished run is a record: never written over
        sys.exit(f"{a.out} already holds a run; give a new folder or move the old one")
    a.out.mkdir(parents=True, exist_ok=True)
    questions = [json.loads(line)["question"] for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    requests_log = (a.out / "requests.jsonl").open("w", encoding="utf-8", newline="\n")
    states_log = (a.out / "alert_states.jsonl").open("w", encoding="utf-8", newline="\n")
    phase, stop, seen, answered = ["healthy"], threading.Event(), [], {}

    def watch():  # one line per change of state, polled every second
        last = None
        while not stop.is_set():
            s = alert_state(a.prometheus)
            if s != last:
                seen.append((phase[0], s))
                states_log.write(json.dumps({"time": now(), "phase": phase[0], "state": s}) + "\n")
                states_log.flush()
                print(f"{now()} alert {s} (phase {phase[0]})", flush=True)
                last = s
            stop.wait(1)

    def traffic():
        n = 0
        while not stop.is_set():
            started = time.monotonic()
            status, seconds = ask(a.app, questions[n % len(questions)])
            requests_log.write(json.dumps({"time": now(), "phase": phase[0], "n": n, "status": status,
                                           "seconds": round(seconds, 3)}) + "\n")
            requests_log.flush()
            n += 1
            answered[phase[0]] = answered.get(phase[0], 0) + (status == 200)
            stop.wait(max(0.0, a.interval - (time.monotonic() - started)))

    def compose(*args):
        subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True)
        states_log.write(json.dumps({"time": now(), "phase": phase[0], "action": "docker compose " + " ".join(args)}) + "\n")
        states_log.flush()
        print(f"{now()} docker compose {' '.join(args)}", flush=True)

    def wait_for(state: str) -> bool:
        deadline = time.monotonic() + a.give_up_minutes * 60
        while time.monotonic() < deadline:
            if seen and seen[-1] == (phase[0], state):
                return True
            time.sleep(1)
        return False

    threads = [threading.Thread(target=watch, daemon=True), threading.Thread(target=traffic, daemon=True)]
    for t in threads:
        t.start()
    time.sleep(a.healthy_minutes * 60)
    phase[0] = "model-stopped"
    compose("stop", "model")
    fired = wait_for("firing")
    phase[0] = "model-restarted"
    compose("start", "model")
    recovered = wait_for("inactive")
    stop.set()
    for t in threads:
        t.join(timeout=310)
    quiet = [s for ph, s in seen if ph == "healthy"] == ["inactive"]
    print(f"inactive throughout the healthy phase: {quiet} ({answered.get('healthy', 0)} requests answered) | "
          f"fired after the stop: {fired} | inactive again: {recovered} "
          f"({answered.get('model-restarted', 0)} requests answered after the restart)")
    return 0 if quiet and fired and answered.get("healthy") else 1


if __name__ == "__main__":
    sys.exit(main())
