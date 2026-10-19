"""Resolve portable defaults and collect the few inputs a person needs."""

from datetime import datetime
import os
from pathlib import Path
import re
import sys
import unicodedata

from .core import WatermarkError, _single_line


def application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _environment_path(name: str, base: Path) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    path = Path(os.path.expandvars(value)).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _choose_template(base: Path) -> Path:
    folder = base / "working" / "template"
    candidates = sorted((path for path in folder.iterdir()
                         if path.is_file() and path.suffix.lower() == ".pdf"),
                        key=lambda path: path.name.casefold()) if folder.is_dir() else []
    if not candidates:
        raise WatermarkError(
            f"No template PDF found. Put a PDF in {folder}, or set PDF_WATERMARK_TEMPLATE to its full path."
        )
    if len(candidates) == 1:
        return candidates[0]
    print("Available templates:")
    for index, path in enumerate(candidates, 1):
        print(f"  {index}. {path.name}")
    while True:
        choice = input(f"Choose template [1-{len(candidates)}]: ").strip()
        if choice.isascii() and choice.isdecimal() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        print(f"Enter a number from 1 to {len(candidates)}.")


def output_filename(customer: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", customer).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-")[:80].rstrip("-") or "customer"
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S_%f")
    return f"Customer_Copy_{slug}_{timestamp}.pdf"


def collect_inputs(source: Path | None, output: Path | None,
                   customer: str | None) -> tuple[Path, Path, str]:
    base = application_directory()
    print("PDF Watermark - Customer Copy\n")
    source = source or _environment_path("PDF_WATERMARK_TEMPLATE", base) or _choose_template(base)
    source = source.expanduser().resolve()
    if not source.is_file():
        raise WatermarkError(f"Template PDF does not exist: {source}")
    folder = (output.expanduser().resolve().parent if output else
              _environment_path("PDF_WATERMARK_OUTPUT_DIR", base) or base / "working" / "output")
    print(f"Template: {source}")
    print(f"Output:   {folder}\n")
    if customer is None:
        while True:
            try:
                customer = _single_line(input("Customer name: "), "Customer name")
                break
            except WatermarkError as exc:
                print(str(exc))
    else:
        customer = _single_line(customer, "Customer name")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WatermarkError(f"Could not create the output folder: {folder}") from exc
    output = output.expanduser().resolve() if output else folder / output_filename(customer)
    print("\nProcessing...")
    return source, output, customer
