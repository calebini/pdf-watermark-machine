"""Build a portable folder on the target OS with a staged qpdf distribution."""

import argparse
from importlib.metadata import distribution
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import sysconfig

import reportlab

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpdf-directory", type=Path, default=ROOT / "vendor" / "qpdf",
                        help="Folder containing qpdf[.exe] and its runtime libraries")
    args = parser.parse_args()
    vendor = args.qpdf_directory.resolve()
    name = "qpdf.exe" if os.name == "nt" else "qpdf"
    executable = vendor / name
    if not executable.is_file():
        parser.error(f"Stage a complete qpdf distribution in {vendor} first.")
    subprocess.run([str(executable), "--version"], check=True)
    font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
               "--name", "pdf-watermark", "--paths", str(ROOT / "src"),
               "--add-data", f"{font}{os.pathsep}reportlab/fonts",
               "--exclude-module", "numpy",
               "--exclude-module", "pytest", "--exclude-module", "psutil",
               "--distpath", str(ROOT / "dist"),
               "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build")]
    command += ["--add-binary", f"{executable}{os.pathsep}vendor/qpdf"]
    for library in sorted(vendor.rglob("*")):
        if library.is_file() and library.suffix.lower() in (".dll", ".dylib"):
            destination = Path("vendor/qpdf") / library.parent.relative_to(vendor)
            command += ["--add-binary", f"{library}{os.pathsep}{destination.as_posix()}"]
    command.append(str(ROOT / "scripts" / "run_cli.py"))
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "tmp" / "pyinstaller-cache"))
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    output = ROOT / "dist" / "pdf-watermark"
    shutil.copy2(ROOT / "README.md", output / "README.md")
    launcher_name = "Personalize.cmd" if os.name == "nt" else "Personalize.command"
    launcher = output / launcher_name
    shutil.copy2(ROOT / "scripts" / launcher_name, launcher)
    if os.name != "nt":
        launcher.chmod(0o755)
    for folder in ("template", "output"):
        (output / "working" / folder).mkdir(parents=True, exist_ok=True)
    (output / "working" / "template" / "PUT-TEMPLATE-HERE.txt").write_text(
        "Place your original template PDF in this folder.\n"
        "The launcher selects it automatically when there is one PDF.\n"
        "With multiple PDFs, it offers a numbered choice.\n", encoding="utf-8",
    )
    notices = output / "THIRD-PARTY-LICENSES"
    notices.mkdir(exist_ok=True)
    for name in ("pikepdf", "reportlab", "pillow", "lxml", "charset-normalizer", "packaging", "pyinstaller"):
        package = distribution(name)
        for file in package.files or []:
            if any(term in str(file).lower() for term in ("license", "copying")):
                source = Path(package.locate_file(file))
                if source.is_file():
                    target = notices / name / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for candidate in (Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
                      Path(sys.base_prefix) / "LICENSE.txt"):
        if candidate.is_file():
            shutil.copy2(candidate, notices / "Python-LICENSE.txt")
            break
    qpdf_license = vendor / "LICENSE.txt"
    if qpdf_license.is_file():
        shutil.copy2(qpdf_license, notices / "qpdf-LICENSE.txt")
    (output / "BUILD-INFO.txt").write_text(
        ("Development preview; not release-signed.\n" if os.name == "nt" else
         "Development preview; not release-signed or notarized.\n") +
        f"Build system: {platform.platform()}\nPython: {platform.python_version()}\n"
        f"Minimum OS compatibility requires clean-machine testing.\n",
        encoding="utf-8",
    )
    print(f"Portable build: {output}")


if __name__ == "__main__":
    main()
