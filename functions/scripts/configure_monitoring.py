"""Configure production error email alerts without recurring health requests.

Explicit invocation makes external changes. Uptime checks are intentionally not created.
"""
import argparse
import shutil
import subprocess
import requests

PROJECT = "vidoraai-2bbce"
BASE = f"https://monitoring.googleapis.com/v3/projects/{PROJECT}"
ERROR_POLICY_TITLE = "Vidora production processing errors"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", action="append", help="Recipient email; required only for first setup")
    parser.add_argument(
        "--reuse-existing-error-policy-channels", action="store_true",
        help="Use recipients already attached to the production error policy",
    )
    args = parser.parse_args()
    if not args.email and not args.reuse_existing_error_policy_channels:
        parser.error("supply --email or --reuse-existing-error-policy-channels")
    token = subprocess.run([shutil.which("gcloud"), "auth", "print-access-token"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    def call(method, path, **kwargs):
        result = session.request(method, BASE + path, timeout=30, **kwargs)
        if not result.ok:
            raise RuntimeError(f"Monitoring HTTP {result.status_code}: {result.text[:500]}")
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
    policies = listing("/alertPolicies", "alertPolicies")
    channels = []
    if args.reuse_existing_error_policy_channels:
        error_policy = next((p for p in policies if p.get("displayName") == ERROR_POLICY_TITLE), None)
        if error_policy is None or not error_policy.get("notificationChannels"):
            raise RuntimeError("No existing error-policy recipients found; supply --email")
        channels = error_policy["notificationChannels"]
        for channel_name in channels:
            channel = next((c for c in existing if c.get("name") == channel_name), None)
            if channel is None or not channel.get("enabled", False):
                raise RuntimeError("Existing error-policy channel is missing or disabled")
            print("Channel:", channel_name, "verification:", channel.get("verificationStatus", "UNSPECIFIED"))
    for email in dict.fromkeys(args.email or []):
        channel = next((c for c in existing if c.get("type") == "email" and c.get("labels", {}).get("email_address") == email), None)
        if channel is None:
            channel = call("POST", "/notificationChannels", json={"type": "email", "displayName": "Vidora operations", "labels": {"email_address": email}, "enabled": True})
        if not channel.get("enabled", False):
            raise RuntimeError("Existing channel disabled; refusing to silently change it")
        channels.append(channel["name"])
        print("Channel:", channel["name"], "verification:", channel.get("verificationStatus", "UNSPECIFIED"))
    error_policy_body = {
        "displayName": ERROR_POLICY_TITLE, "enabled": True, "combiner": "OR",
        "notificationChannels": channels,
        "documentation": {"mimeType": "text/markdown", "content": "Inspect Cloud Run logs for api/processvideo/cleanup_expired_videos. Correlate analysis_failed by video_id; do not put transcripts or secrets in incident reports. Do not blindly resubmit paid AI work. Follow docs/AI_GOVERNANCE.md. This is an error alert, not an uptime or budget guarantee."},
        "conditions": [{"displayName": "Processing failure or server error", "conditionMatchedLog": {"filter": 'resource.type="cloud_run_revision" AND (resource.labels.service_name="api" OR resource.labels.service_name="processvideo" OR resource.labels.service_name="cleanup-expired-videos" OR resource.labels.service_name="cleanup_expired_videos") AND (severity>=ERROR OR httpRequest.status>=500 OR textPayload:"analysis_failed" OR textPayload:"unhandled_request_error")'}}],
        "alertStrategy": {"notificationRateLimit": {"period": "900s"}, "autoClose": "1800s"}
    }
    error_policy = next((p for p in policies if p.get("displayName") == ERROR_POLICY_TITLE), None)
    if error_policy:
        policy = call("PATCH", "/" + error_policy["name"].split("/", 2)[-1], json=error_policy_body)
        print("Policy updated:", policy["name"])
    else:
        policy = call("POST", "/alertPolicies", json=error_policy_body)
        print("Policy created:", policy["name"])

    print("Email receipt must still be verified by recipients.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Monitoring setup failed:", exc)
        raise SystemExit(1) from None
