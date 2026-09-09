"""Bounded live smoke check. --analyze runs one paid analysis, never polls.

Prints status/timing only, not transcripts, secrets or provider error bodies.
"""
import argparse
from time import perf_counter
import uuid
import requests

BASE = "https://api-c4rcflddjq-uc.a.run.app"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    response = requests.post(BASE + "/videos/analyze?warmup=true", headers={"Content-Type": "text/plain"}, timeout=60)
    assert response.status_code == 200 and response.json() == {"warm": True}, "Warm-up failed"
    print("Warm-up: 200", flush=True)
    response = requests.get(BASE + "/health", timeout=30)
    assert response.status_code == 200, "Health failed"
    print("Health: 200", flush=True)
    response = requests.get(BASE + "/videos", timeout=30)
    assert response.status_code == 401, "Anonymous listing must be denied"
    print("Anonymous listing: 401", flush=True)
    if not args.analyze:
        return
    request_id = str(uuid.uuid4())
    print("Smoke video id:", request_id, flush=True)
    start = perf_counter()
    response = requests.post(BASE + "/videos/analyze", json={"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}, headers={"Idempotency-Key": request_id}, timeout=310)
    print("Analysis HTTP:", response.status_code, "seconds:", round(perf_counter()-start, 2), flush=True)
    assert response.status_code == 200, "Analysis failed; inspect correlated server logs"
    data = response.json()
    assert data["status"] == "completed", "Analysis not completed"
    response = requests.post(BASE + "/videos/analyze", json={"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}, headers={"Idempotency-Key": request_id}, timeout=30)
    assert response.status_code == 200 and response.json()["id"] == request_id, "Idempotency replay failed"
    print("Completed replay: same saved result", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Smoke failed:", type(exc).__name__, flush=True)
        raise SystemExit(1) from None
