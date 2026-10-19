"""Compose a PDF, encrypt with qpdf, and verify before publishing."""

from __future__ import annotations

import hashlib
import io
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass

import pikepdf
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

LEFT_HEADER = "Under NDA"
RIGHT_HEADER = "Not for redistribution"


class WatermarkError(Exception):
    """An actionable processing or validation error."""


@dataclass(frozen=True)
class Options:
    customer: str
    header: str | None = None
    opacity: float = 0.16
    font: Path | None = None
    qpdf_path: Path | None = None
    owner_password: str | None = None


@dataclass(frozen=True)
class Result:
    output: Path
    pages: int


def _single_line(value: str, label: str) -> str:
    value = value.strip()
    if not value or len(value) > 300 or any(
        unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        for char in value
    ):
        raise WatermarkError(f"{label} must be a single line of 1-300 printable characters.")
    return value


def find_qpdf(explicit: Path | None = None) -> Path:
    """Prefer packaged qpdf; never require users to configure PATH."""
    executable = "qpdf.exe" if os.name == "nt" else "qpdf"
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
    else:
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        bundled = root / "vendor" / "qpdf" / executable
        candidate = bundled if bundled.is_file() else Path(shutil.which(executable) or "")
    if not candidate.is_file():
        raise WatermarkError("qpdf was not found. Use --qpdf-path or a distribution with bundled qpdf.")
    return candidate.resolve()


def _run_qpdf(executable: Path, args: list[str]) -> None:
    # qpdf @- reads one argument per line.
    # Keeping every argument on stdin also handles spaces without shell quoting.
    if any("\n" in arg or "\r" in arg for arg in args):
        raise WatermarkError("qpdf arguments cannot contain line breaks.")
    try:
        result = subprocess.run(
            [str(executable), "@-"], input="\n".join(args) + "\n",
            text=True, encoding="utf-8", capture_output=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WatermarkError("Could not run qpdf; check its dependencies and executable permissions.") from exc
    if result.returncode != 0:
        # Do not echo qpdf diagnostics: they could contain secret arguments.
        raise WatermarkError(f"qpdf reported an error or warning (exit {result.returncode}); no output published.")


def _load_font(path: Path | None, texts: tuple[str, ...]) -> str:
    font_path = path or Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    try:
        font_id = "Customer-" + hashlib.sha256(font_path.read_bytes()).hexdigest()[:16]
        if font_id not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_id, str(font_path)))
        supported = pdfmetrics.getFont(font_id).face.charToGlyph
        missing = sorted({c for text in texts for c in text if not supported.get(ord(c))})
        if missing:
            raise WatermarkError(
                "The font does not support these characters: " + " ".join(missing)
                + ". Supply a suitable TrueType font with --font."
            )
        return font_id
    except (OSError, ValueError, reportlab.pdfbase.ttfonts.TTFError) as exc:
        raise WatermarkError("Could not load the TrueType font; check --font.") from exc


def _font_size(text: str, font: str, width: float, preferred: float, minimum: float) -> float:
    size = min(preferred, width / pdfmetrics.stringWidth(text, font, 1))
    if size < minimum:
        raise WatermarkError("Customer/header text is too long for this page; use shorter text.")
    return size


def _overlay(width: float, height: float, customer: str, header: str,
             font: str, opacity: float) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height + 36), pageCompression=1)
    # Decorative content should not enter a screen reader's reading order.
    c._code.append("/Artifact BMC")
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, height, width, 36, fill=1, stroke=0)
    c.setFillColorRGB(0.15, 0.19, 0.24)
    # Reserve equal space on both sides so the center remains page-centered.
    # Scale the entire line together when needed, without overlapping labels.
    margin, gap = 24, 12
    side_units = max(pdfmetrics.stringWidth(text, font, 1)
                     for text in (LEFT_HEADER, RIGHT_HEADER))
    header_units = pdfmetrics.stringWidth(header, font, 1)
    header_size = min(9, (width - 2 * margin - 2 * gap) / (header_units + 2 * side_units))
    if header_size < 6:
        raise WatermarkError("Header text is too long to fit beside the NDA labels; use a shorter header.")
    c.setFont(font, header_size)
    baseline = height + 14
    c.drawString(margin, baseline, LEFT_HEADER)
    c.drawCentredString(width / 2, baseline, header)
    c.drawRightString(width - margin, baseline, RIGHT_HEADER)
    c.setStrokeColorRGB(0.8, 0.83, 0.86)
    c.setLineWidth(0.5)
    c.line(0, height + 0.5, width, height + 0.5)
    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(35)
    c.setFillAlpha(opacity)
    c.setFillColorRGB(0.15, 0.19, 0.24)
    # Bound the rotated text horizontally AND vertically, including its height.
    angle = math.radians(35)
    available = min((width - 48) / math.cos(angle), (height - 80) / math.sin(angle))
    size = _font_size(customer, font, available, 48, 10)
    c.setFont(font, size)
    c.drawCentredString(0, -size / 3, customer)
    c.restoreState()
    c._code.append("EMC")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def _check_static_input(pdf: pikepdf.Pdf) -> None:
    # Some exporters leave empty AcroForm/Perms containers in static documents.
    # Container presence alone is not evidence of fields or a signature.
    if pdf.Root.get("/Perms"):
        raise WatermarkError("The PDF has certification or usage-rights permissions; use an unsigned static original.")
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Dictionary) and obj.get("/Type") in (
            pikepdf.Name.Sig, pikepdf.Name("/DocTimeStamp")
        ):
            raise WatermarkError("The PDF contains a digital signature; use an unsigned original.")
    form = pdf.Root.get("/AcroForm")
    if form is not None:
        if not isinstance(form, pikepdf.Dictionary):
            raise WatermarkError("The PDF has an invalid form dictionary; use a valid static original.")
        fields = form.get("/Fields", pikepdf.Array())
        if not isinstance(fields, pikepdf.Array):
            raise WatermarkError("The PDF has an invalid form field list; use a valid static original.")
        if fields or form.get("/XFA"):
            raise WatermarkError("The PDF contains interactive form fields; use a static original.")
    for page in pdf.pages:
        if any(annotation.get("/Subtype") == pikepdf.Name.Widget
               for annotation in page.obj.get("/Annots", [])):
            raise WatermarkError("The PDF contains interactive form widgets; use a static original.")


def _stamp(source: Path, destination: Path, customer: str, header: str,
           font: str, opacity: float) -> int:
    with pikepdf.open(source) as pdf:
        if pdf.is_encrypted:
            raise WatermarkError("Use the unencrypted original PDF as input.")
        _check_static_input(pdf)
        if not pdf.pages:
            raise WatermarkError("The input PDF has no pages.")
        for page in pdf.pages:
            if float(page.obj.get("/UserUnit", 1)) != 1:
                raise WatermarkError("Pages with custom UserUnit scaling are not supported yet.")
            page.flatten_rotation()
            left, bottom, right, top = map(float, page.cropbox)
            width, height = right - left, top - bottom
            if not all(math.isfinite(n) for n in (left, bottom, right, top)) or min(width, height) < 144:
                raise WatermarkError("The input has an invalid or unusually small page size.")
            # Add space above the visible page instead of covering source content.
            media = list(map(float, page.mediabox))
            page.mediabox = pikepdf.Array([
                min(media[0], left), min(media[1], bottom),
                max(media[2], right), max(media[3], top + 36),
            ])
            page.cropbox = pikepdf.Array([left, bottom, right, top + 36])
            # Keep print-production boundaries consistent with the expanded page.
            for box in ("/TrimBox", "/BleedBox", "/ArtBox"):
                if box in page.obj:
                    del page.obj[box]
            with pikepdf.open(_overlay(width, height, customer, header, font, opacity)) as overlay:
                page.add_overlay(overlay.pages[0], pikepdf.Rectangle(left, bottom, right, top + 36))
        count = len(pdf.pages)
        pdf.save(destination)
        return count


def _verify(path: Path, page_count: int, owner: str) -> None:
    with pikepdf.open(path, password="") as pdf:
        if not pdf.is_encrypted or pdf.encryption.R != 6 or pdf.encryption.bits != 256:
            raise WatermarkError("Output did not pass AES-256 verification.")
        encryption = pdf.trailer.Encrypt
        if str(encryption.CF.StdCF.CFM) != "/AESV3":
            raise WatermarkError("Output encryption is not AES-256.")
        permissions = pdf.allow
        denied = (permissions.extract, permissions.print_lowres, permissions.print_highres,
                  permissions.modify_annotation, permissions.modify_assembly,
                  permissions.modify_form, permissions.modify_other)
        if any(denied) or not permissions.accessibility or len(pdf.pages) != page_count:
            raise WatermarkError("Output did not pass permission/page-count verification.")
        if pdf.owner_password_matched:
            raise WatermarkError("Output unexpectedly opens as owner with an empty password.")
    with pikepdf.open(path, password=owner) as pdf:
        if not pdf.owner_password_matched:
            raise WatermarkError("Output owner password verification failed.")


def _publish(staged: Path, target: Path) -> None:
    try:
        os.link(staged, target)  # Atomic no-clobber publication on APFS/NTFS.
    except FileExistsError:
        raise WatermarkError("Output already exists; choose another output filename.") from None
    except OSError:
        # Filesystems without hard-link support still get exclusive creation.
        try:
            with target.open("xb") as output:
                try:
                    with staged.open("rb") as source:
                        shutil.copyfileobj(source, output)
                except BaseException:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise
        except FileExistsError:
            raise WatermarkError("Output already exists; choose another output filename.") from None


def personalize(source: Path, output: Path, options: Options) -> Result:
    """Personalize a static unencrypted PDF; never overwrite source or output.

    A random owner password is discarded unless supplied through Options.
    No networking, shell invocation, or persistent plaintext intermediates.
    """
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if source == output:
        raise WatermarkError("Input and output must be different files.")
    if not source.is_file():
        raise WatermarkError("Input PDF does not exist.")
    if output.exists():
        raise WatermarkError("Output already exists; choose another output filename.")
    if not output.parent.is_dir():
        raise WatermarkError("The output directory does not exist.")
    customer = _single_line(options.customer, "Customer name")
    header = _single_line(options.header if options.header is not None else
                          f"Prepared exclusively for {customer}", "Header")
    if not math.isfinite(options.opacity) or not 0.05 <= options.opacity <= 0.4:
        raise WatermarkError("Watermark opacity must be between 0.05 and 0.4.")
    owner = options.owner_password if options.owner_password is not None else secrets.token_urlsafe(32)
    if not owner or len(owner.encode("utf-8")) > 127 or any(c in owner for c in "\r\n\x00"):
        raise WatermarkError("Owner password must contain 1-127 UTF-8 bytes without line breaks or NUL.")
    executable = find_qpdf(options.qpdf_path)
    font = _load_font(options.font, (customer, header, LEFT_HEADER, RIGHT_HEADER))
    try:
        # Under output.parent so publication can use a same-filesystem hard link.
        with tempfile.TemporaryDirectory(prefix=".pdf-watermark-", dir=output.parent) as work:
            stamped = Path(work) / "stamped.pdf"
            encrypted = Path(work) / "encrypted.pdf"
            count = _stamp(source, stamped, customer, header, font, options.opacity)
            _run_qpdf(executable, ["--encrypt", "--user-password=",
                                  f"--owner-password={owner}", "--bits=256", "--print=none",
                                  "--modify=none", "--extract=n", "--accessibility=y",
                                  "--", str(stamped), str(encrypted)])
            _run_qpdf(executable, ["--check", str(encrypted)])
            _verify(encrypted, count, owner)
            _publish(encrypted, output)
    except pikepdf.PasswordError as exc:
        raise WatermarkError("Input requires a password; use the unencrypted original PDF.") from exc
    except pikepdf.PdfError as exc:
        raise WatermarkError("The PDF could not be processed; check that the input is a valid PDF.") from exc
    except OSError as exc:
        raise WatermarkError("Could not read or write a file; check paths, permissions, and free space.") from exc
    return Result(output=output, pages=count)
