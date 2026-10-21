"""Package the built static site and an optional local-preview bundle."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def main():
    source = WEB / "dist"
    if not (source / "index.html").is_file():
        raise SystemExit("Build the browser variant first: cd web, npm ci, npm run build")
    version = json.loads((WEB / "package.json").read_text())["version"]
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    static = output / f"pdf-watermark-web-{version}-static.zip"
    preview = output / f"pdf-watermark-web-{version}-preview.zip"
    files = sorted(path for path in source.rglob("*") if path.is_file())
    if any(path.suffix.lower() == ".pdf" for path in files):
        raise SystemExit("Refusing to package a website containing PDF documents.")
    with zipfile.ZipFile(static, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(source))
    prefix = Path("pdf-watermark-web")
    with zipfile.ZipFile(preview, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, prefix / "dist" / path.relative_to(source))
        for name in ("Preview.command", "serve.py", "README.md", "DEPLOY.md", "gitlab-pages.yml"):
            bundle.write(WEB / name, prefix / name)
        bundle.writestr(str(prefix / "START-HERE.txt"),
            "PDF WATERMARK - LOCAL BROWSER PREVIEW\n\n"
            "1. Extract the entire folder.\n"
            "2. On Mac, double-click Preview.command.\n"
            "   Or run: python3 serve.py (Windows: py serve.py).\n"
            "3. Open http://127.0.0.1:4173/ in a current Chrome or Edge browser.\n"
            "4. Choose your local PDF template and enter the customer name.\n"
            "5. Generate and download the protected copy.\n\n"
            "The local server only serves static files. PDFs are processed in\n"
            "your browser, not uploaded. Stop the server with Ctrl+C.\n"
            "Use --port 4175 if port 4173 is occupied.\n\n"
            "For GitLab Pages, publish only the contents of dist/.\n"
            "Python is not needed when the site is hosted.\n")
    for archive in (static, preview):
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
        print(archive)


if __name__ == "__main__":
    main()
