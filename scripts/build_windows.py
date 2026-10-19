"""Run on Windows x64: python scripts/build_windows.py."""

import hashlib
from pathlib import Path
import os
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
QPDF_VERSION = "12.4.2"
QPDF_SHA256 = "db87077e683630c1217e0e8f9a20a9749d952ab676e881c3689187763a5de25d"
QPDF_URL = f"https://github.com/qpdf/qpdf/releases/download/v{QPDF_VERSION}/qpdf-{QPDF_VERSION}-msvc64.zip"


def stage_qpdf(archive: Path, target: Path) -> None:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != QPDF_SHA256:
        raise RuntimeError("qpdf archive checksum does not match the pinned official release.")
    prefix = f"qpdf-{QPDF_VERSION}-msvc64/bin/"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            name = info.filename.removeprefix(prefix)
            # Only the executable and its adjacent runtime libraries are needed.
            if "/" in name or "\\" in name or not (name == "qpdf.exe" or name.lower().endswith(".dll")):
                continue
            (target / name).write_bytes(bundle.read(info))
    if not (target / "qpdf.exe").is_file() or not (target / "qpdf30.dll").is_file():
        raise RuntimeError("qpdf archive does not contain the expected Windows runtime.")


def main() -> None:
    if os.name != "nt" or sysconfig.get_platform() != "win-amd64":
        raise SystemExit("Run this build with 64-bit x64 Python on Windows; it cannot cross-compile on macOS.")
    if sys.version_info < (3, 13):
        raise SystemExit("Python 3.13 or newer is required on the build machine.")
    os.chdir(ROOT)
    work = ROOT / "tmp" / "windows-build"
    work.mkdir(parents=True, exist_ok=True)
    environment = ROOT / ".venv-windows"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / "Scripts" / "python.exe"
    subprocess.run([str(python), "-m", "pip", "install", "-e", ".[dev]"], check=True)
    archive = work / f"qpdf-{QPDF_VERSION}-msvc64.zip"
    if not archive.exists():
        with urlopen(QPDF_URL, timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    qpdf = ROOT / "vendor" / "qpdf-windows"
    stage_qpdf(archive, qpdf)
    # The pinned pikepdf wheel includes qpdf and native dependency license texts.
    subprocess.run([str(python), "-c",
                    "from importlib.metadata import distribution; from pathlib import Path; "
                    "d=distribution('pikepdf'); "
                    "p=next(p for p in d.files if str(p).endswith('third-party-licenses/qpdf.txt')); "
                    "Path(__import__('sys').argv[1]).write_bytes(Path(d.locate_file(p)).read_bytes())",
                    str(qpdf / "LICENSE.txt")], check=True)
    env = dict(os.environ, PATH=str(qpdf) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.run([str(python), "-m", "pytest", "-q"], env=env, check=True)
    subprocess.run([str(python), "scripts/build.py", "--qpdf-directory", str(qpdf)], env=env, check=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    package = ROOT / "dist" / f"pdf-watermark-{version}-windows-x64-preview.zip"
    shutil.make_archive(str(package.with_suffix("")), "zip", root_dir=ROOT / "dist", base_dir="pdf-watermark")
    subprocess.run([str(python), "scripts/smoke_test_windows.py", str(package)], check=True)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix(".zip.sha256").write_text(f"{digest}  {package.name}\n", encoding="ascii")
    print(f"Windows ZIP built and smoke-tested: {package}")


if __name__ == "__main__":
    main()
