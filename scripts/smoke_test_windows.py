"""Exercise the extracted Windows launcher using only bundled runtime tools."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import zipfile

import pikepdf
from pypdf import PdfReader
from reportlab.pdfgen import canvas


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This smoke check must execute on Windows.")
    with tempfile.TemporaryDirectory(prefix="PDF Watermark Windows Test ") as folder:
        root = Path(folder)
        with zipfile.ZipFile(sys.argv[1]) as package:
            package.extractall(root)
        app = root / "pdf-watermark"
        template = app / "working" / "template" / "Sample Whitepaper.pdf"
        original = canvas.Canvas(str(template), pagesize=(595, 842))
        original.drawString(40, 400, "Original Windows smoke-test content")
        original.save()
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PYTHON", "PDF_WATERMARK_")) and key.upper() != "VIRTUAL_ENV"}
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        command = os.environ.get("COMSPEC", str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"))
        # Paths contain spaces and the working directory is outside the package.
        result = subprocess.run([command, "/d", "/c", f'call "{app / "Personalize.cmd"}"'],
                                cwd=root, env=env, input="Windows Test Customer\n\n",
                                text=True, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Packaged launcher failed:\n{result.stdout}\n{result.stderr}")
        outputs = list((app / "working" / "output").glob("*.pdf"))
        if len(outputs) != 1:
            raise RuntimeError(f"Expected one generated PDF; found {len(outputs)}.\n{result.stdout}")
        with pikepdf.open(outputs[0], password="") as pdf:
            assert pdf.is_encrypted and pdf.encryption.bits == 256 and pdf.encryption.R == 6
            assert str(pdf.trailer.Encrypt.CF.StdCF.CFM) == "/AESV3"
            assert not pdf.owner_password_matched and pdf.allow.accessibility
            assert not any((pdf.allow.extract, pdf.allow.print_lowres, pdf.allow.print_highres,
                            pdf.allow.modify_annotation, pdf.allow.modify_assembly,
                            pdf.allow.modify_form, pdf.allow.modify_other))
        text = PdfReader(outputs[0]).pages[0].extract_text()
        for expected in ("Original Windows smoke-test content", "Windows Test Customer",
                         "Under NDA", "Not for redistribution"):
            assert expected in text, f"Missing expected text: {expected}"
        print("Windows ZIP launcher, bundled qpdf, original content and permissions verified.")


if __name__ == "__main__":
    main()
