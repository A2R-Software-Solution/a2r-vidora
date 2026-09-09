"""Fail deployment before upload if the offline model bundle is missing."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2"
required = ["model.safetensors", "modules.json", "config.json", "tokenizer.json",
            "tokenizer_config.json", "1_Pooling/config.json"]
missing = [name for name in required if not (root / name).is_file()]
if missing:
    raise SystemExit("Missing model files; run functions/scripts/prepare_model.py: " + ", ".join(missing))
manifest = json.loads(Path(__file__).with_name("model_manifest.json").read_text())
for name, expected in manifest["sha256"].items():
    with (root / name).open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual != expected:
        raise SystemExit(f"Model integrity check failed: {name}")
print("Offline model bundle and SHA-256 integrity verified.")
