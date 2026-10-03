"""Download an ONNX export of ProsusAI/finbert into ``models/finbert/``.

Usage (from backend/): ``uv run python scripts/download_finbert.py [--dest DIR]``.

Source repo: ``Xenova/finbert`` (declares ``base_model: ProsusAI/finbert``; its config.json
labels are positive/negative/neutral). The int8-quantized file is preferred because it is ~4x
smaller than the fp32 export; we fall back to fp32 if the quantized file ever disappears.

Supply chain: the download is pinned to one commit (``REVISION``) and every file must match its
recorded sha256, so a changed or compromised upstream repo fails the build instead of shipping.
To upgrade, pick a new commit (``HfApi().model_info(REPO_ID).sha``), re-check the labels, and
update ``REVISION`` and ``SHA256`` together.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "Xenova/finbert"
REVISION = "8f269abebfdd9009d7d9b5e96af7e5c6bfe50b20"  # commit of 2025-06-30
SHA256 = {
    "config.json": "3629c9707884176d61af8452d8779ee167169db85d81e2183afe939a88c483b8",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "onnx/model_quantized.onnx": "56cd19c7068ca5670c326816845bb7d7edda508b68a228697a1460d0e821ce76",
    "onnx/model.onnx": "4a8d58ba2f8d74c7fca30fdb49fbbe367b64760104b64e8623e896a007229a6e",
}
# Preference order: smallest first.
ONNX_CANDIDATES = ("onnx/model_quantized.onnx", "onnx/model.onnx")
EXPECTED_LABELS = {"positive", "negative", "neutral"}
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "models" / "finbert"


class ChecksumError(RuntimeError):
    """A downloaded file does not match its pinned sha256."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(filename: str) -> Path:
    """Download one file at the pinned revision and refuse it unless its sha256 matches."""
    path = Path(hf_hub_download(repo_id=REPO_ID, filename=filename, revision=REVISION))
    actual = _sha256(path)
    if actual != SHA256[filename]:
        msg = f"{filename}: sha256 {actual} does not match the pinned {SHA256[filename]}"
        raise ChecksumError(msg)
    return path


def _fetch_onnx() -> tuple[str, Path]:
    last_error: Exception | None = None
    for candidate in ONNX_CANDIDATES:
        try:
            return candidate, _fetch(candidate)
        except ChecksumError:
            raise  # tampering is not a reason to try the next file
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
