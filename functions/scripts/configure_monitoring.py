"""Create/reuse email channels and one narrowly scoped production error policy.

Explicit invocation makes external changes. No runtime polling is installed.
"""
import argparse
import shutil
import subprocess
import requests

PROJECT = "vidoraai-2bbce"
BASE = f"https://monitoring.googleapis.com/v3/projects/{PROJECT}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", action="append", required=True)
    args = parser.parse_args()
    token = subprocess.run([shutil.which("gcloud"), "auth", "print-access-token"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    def call(method, path, **kwargs):
        result = session.request(method, BASE + path, timeout=30, **kwargs)
        if not result.ok:
            raise RuntimeError(f"Monitoring HTTP {result.status_code}")
        return result.json()

    def listing(path, field):
        rows, page = [], None
        while True:
            response = call("GET", path, params={"pageToken": page} if page else {})
            rows.extend(response.get(field, []))
            page = response.get("nextPageToken")
            if not page:
                return rows

    existing = listing("/notificationChannels", "notificationChannels")
    channels = []
    for email in dict.fromkeys(args.email):
        channel = next((c for c in existing if c.get("type") == "email" and c.get("labels", {}).get("email_address") == email), None)
        if channel is None:
            channel = call("POST", "/notificationChannels", json={"type": "email", "displayName": "Vidora operations", "labels": {"email_address": email}, "enabled": True})
        if not channel.get("enabled", False):
            raise RuntimeError("Existing channel disabled; refusing to silently change it")
        channels.append(channel["name"])
        print("Channel:", channel["name"], "verification:", channel.get("verificationStatus", "UNSPECIFIED"))
    title = "Vidora production processing errors"
    policies = listing("/alertPolicies", "alertPolicies")
    if any(p.get("displayName") == title for p in policies):
        print("Policy already exists; inspect before changing it.")
        return
    policy = call("POST", "/alertPolicies", json={
        "displayName": title, "enabled": True, "combiner": "OR",
        "notificationChannels": channels,
        "documentation": {"mimeType": "text/markdown", "content": "Inspect Cloud Run logs for api/processvideo/cleanup_expired_videos. Correlate analysis_failed by video_id; do not put transcripts or secrets in incident reports. Do not blindly resubmit paid AI work. Follow docs/AI_GOVERNANCE.md. This is an error alert, not an uptime or budget guarantee."},
        "conditions": [{"displayName": "Processing failure or server error", "conditionMatchedLog": {"filter": 'resource.type="cloud_run_revision" AND (resource.labels.service_name="api" OR resource.labels.service_name="processvideo" OR resource.labels.service_name="cleanup-expired-videos" OR resource.labels.service_name="cleanup_expired_videos") AND (severity>=ERROR OR httpRequest.status>=500 OR textPayload:"analysis_failed")'}}],
        "alertStrategy": {"notificationRateLimit": {"period": "900s"}, "autoClose": "1800s"}
    })
    print("Policy created:", policy["name"])
    print("Email receipt must still be verified by recipients.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Monitoring setup failed:", type(exc).__name__)
        raise SystemExit(1) from None
