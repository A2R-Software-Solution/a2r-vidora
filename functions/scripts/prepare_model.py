"""Download only pinned inference files before deployment; runtime stays offline."""
from pathlib import Path
from huggingface_hub import snapshot_download

MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

if __name__ == "__main__":
    snapshot_download(
        repo_id="sentence-transformers/all-MiniLM-L6-v2",
        revision=MODEL_REVISION,
        local_dir=Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2",
        allow_patterns=["*.json", "vocab.txt", "model.safetensors", "1_Pooling/config.json", "README.md"],
        max_workers=1,
    )
