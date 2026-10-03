"""The FinBERT download script pins a commit and verifies every file's sha256."""

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "download_finbert.py"


@pytest.fixture
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("download_finbert", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_hub(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes
) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    def fake_download(*, repo_id: str, filename: str, revision: str) -> str:
        calls.append({"repo_id": repo_id, "filename": filename, "revision": revision})
        path = tmp_path / filename.replace("/", "_")
        path.write_bytes(content)
        return str(path)

    monkeypatch.setattr(script, "hf_hub_download", fake_download)
    return calls


def test_revision_is_a_full_commit_hash_and_every_file_has_a_sha256(script: ModuleType) -> None:
    assert len(script.REVISION) == 40
    assert int(script.REVISION, 16) >= 0
    for filename in ("config.json", "tokenizer.json", *script.ONNX_CANDIDATES):
        assert len(script.SHA256[filename]) == 64


def test_fetch_matching_file_is_downloaded_at_the_pinned_revision(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    content = b"model bytes"
    monkeypatch.setitem(script.SHA256, "config.json", hashlib.sha256(content).hexdigest())
    calls = _fake_hub(script, monkeypatch, tmp_path, content)

    path = script._fetch("config.json")

    assert path.read_bytes() == content
    assert calls == [
        {"repo_id": script.REPO_ID, "filename": "config.json", "revision": script.REVISION}
    ]


def test_fetch_tampered_file_raises_checksum_error(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_hub(script, monkeypatch, tmp_path, b"not what we pinned")

    with pytest.raises(script.ChecksumError, match="does not match"):
        script._fetch("config.json")


def test_fetch_onnx_tampered_quantized_file_does_not_fall_back_to_fp32(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _fake_hub(script, monkeypatch, tmp_path, b"tampered")

    with pytest.raises(script.ChecksumError):
        script._fetch_onnx()

    assert [c["filename"] for c in calls] == ["onnx/model_quantized.onnx"]
