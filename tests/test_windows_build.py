"""Archive staging checks that run before a native Windows build is available."""

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_windows.py"
    spec = spec_from_file_location("windows_builder", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_download_checksum_is_required(builder, tmp_path):
    archive = tmp_path / "download.zip"
    archive.write_bytes(b"unverified download")
    target = tmp_path / "runtime"
    with pytest.raises(RuntimeError, match="checksum"):
        builder.stage_qpdf(archive, target)
    assert not target.exists()


def test_windows_runtime_staging_is_limited_to_expected_binaries(builder, tmp_path):
    archive = tmp_path / "release.zip"
    prefix = f"qpdf-{builder.QPDF_VERSION}-msvc64/bin/"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("qpdf.exe", "qpdf30.dll", "vcruntime140.dll", "fix-qdf.exe", "../escape.dll"):
            bundle.writestr(prefix + name, b"synthetic fixture")
    builder.QPDF_SHA256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    target = tmp_path / "runtime"
    builder.stage_qpdf(archive, target)
    assert {path.name for path in target.iterdir()} == {"qpdf.exe", "qpdf30.dll", "vcruntime140.dll"}
    assert not (tmp_path / "escape.dll").exists()


def test_missing_runtime_is_rejected(builder, tmp_path):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    builder.QPDF_SHA256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="expected Windows runtime"):
        builder.stage_qpdf(archive, tmp_path / "runtime")
