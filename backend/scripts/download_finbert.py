"""Download an ONNX export of ProsusAI/finbert into ``models/finbert/``.

Usage (from backend/): ``uv run python scripts/download_finbert.py [--dest DIR]``.

Source repo: ``Xenova/finbert`` (declares ``base_model: ProsusAI/finbert``; its config.json
labels are positive/negative/neutral). The int8-quantized file is preferred because it is ~4x
smaller than the fp32 export; we fall back to fp32 if the quantized file ever disappears.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "Xenova/finbert"
# Preference order: smallest first.
ONNX_CANDIDATES = ("onnx/model_quantized.onnx", "onnx/model.onnx")
EXPECTED_LABELS = {"positive", "negative", "neutral"}
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "models" / "finbert"


def _fetch(filename: str) -> Path:
    return Path(hf_hub_download(repo_id=REPO_ID, filename=filename))


def _fetch_onnx() -> tuple[str, Path]:
    last_error: Exception | None = None
    for candidate in ONNX_CANDIDATES:
        try:
            return candidate, _fetch(candidate)
        except Exception as exc:
            last_error = exc
    msg = f"No ONNX file found in {REPO_ID}: {last_error}"
    raise RuntimeError(msg)


def download(dest: Path) -> None:
    """Fetch model.onnx, tokenizer.json and config.json into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)

    config_src = _fetch("config.json")
    labels = set(json.loads(config_src.read_text(encoding="utf-8"))["id2label"].values())
    if labels != EXPECTED_LABELS:
        msg = f"Unexpected labels {sorted(labels)} in {REPO_ID}; refusing to install"
        raise RuntimeError(msg)

    used, onnx_src = _fetch_onnx()
    shutil.copyfile(onnx_src, dest / "model.onnx")
    shutil.copyfile(_fetch("tokenizer.json"), dest / "tokenizer.json")
    shutil.copyfile(config_src, dest / "config.json")
    (dest / "SOURCE.txt").write_text(f"{REPO_ID}/{used}\n", encoding="utf-8")
    print(f"Installed {REPO_ID}/{used} into {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    download(parser.parse_args().dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
