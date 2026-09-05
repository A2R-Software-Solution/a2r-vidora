"""Operator tooling: python -m app.governance.aims_cli check|export|fingerprint."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os

from app.governance.aims import application_digest, canonical_digest, readiness, verify_evidence
from app.governance.aims_models import AIMS
from app.governance.runtime import Policy
from app.governance.inventory import MODEL_INVENTORY


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check Vidora AIMS release criteria (not ISO certification).")
    parser.add_argument("command", choices=["check", "export", "fingerprint"])
    parser.add_argument("--aims", type=Path, default=Path(os.environ.get("AI_AIMS_PATH", str(Path(__file__).with_name("aims.json")))))
    parser.add_argument("--policy", type=Path, default=Path(os.environ.get("AI_POLICY_PATH", str(Path(__file__).with_name("policy.json")))))
    parser.add_argument("--release-id", default=os.environ.get("AI_RELEASE_ID", ""))
    parser.add_argument("--retention-hours", type=int, default=None)
    parser.add_argument("--region", default=os.environ.get("AI_DEPLOYMENT_REGION", ""))
    parser.add_argument("--output", type=Path, help="Optional JSON report destination, created exclusively")
    args = parser.parse_args(argv)
    try:
        policy = Policy.model_validate_json(args.policy.read_text())
        policy_hash = canonical_digest(policy)
        app_hash = application_digest()
        report = {"policy_sha256": policy_hash, "application_sha256": app_hash}
        if args.command != "fingerprint":
            aims = AIMS.model_validate_json(args.aims.read_text())
            hours = args.retention_hours
            if hours is None:
                hours = int(os.environ.get("VIDEO_RETENTION_HOURS", "0"))
            blockers = readiness(aims, policy_digest=policy_hash, app_digest=app_hash,
                release_id=args.release_id, retention_hours=hours, languages=policy.evaluated_languages)
            blockers.extend(verify_evidence(aims, args.aims.parent))
            if policy.operations != MODEL_INVENTORY:
                blockers.append("policy:model_inventory_mismatch")
            if not policy.approved or policy.owner == "unassigned":
                blockers.append("policy:approval_missing")
            if not args.region or args.region not in policy.deployment_regions:
                blockers.append("policy:region_not_approved")
            report.update({"framework": "ISO/IEC 42001:2023 supporting controls",
                "assessed_at": datetime.now(timezone.utc).isoformat(),
                "aims_sha256": canonical_digest(aims), "aims_version": aims.version,
                "release_id": aims.release.id, "ready": not blockers,
                "blockers": sorted(set(blockers)),
                "record_counts": {name: len(getattr(aims, name)) for name in
                    ("controls", "risks", "reviews", "objectives", "findings", "evidence")}})
            if args.command == "export":
                # No names, risk descriptions, incident narratives, or artifact contents.
                report["evidence_inventory"] = {key: item.sha256 for key, item in aims.evidence.items()}
        text = json.dumps(report, indent=2) + "\n"
        if args.output:
            # Never overwrite an earlier audit record accidentally.
            with args.output.open("x") as output:
                output.write(text)
        else:
            print(text, end="")
        return 0 if report.get("ready", True) else 1
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"ready": False, "error": "Invalid configuration, unreadable records, or output already exists."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
