"""Thin command-line adapter for the personalization API."""

import argparse
from pathlib import Path
import sys

from .core import Options, WatermarkError, personalize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add a customer watermark/header and apply AES-256 PDF permission controls."
    )
    parser.add_argument("input", nargs="?", type=Path, help="Original, unencrypted static PDF")
    parser.add_argument("--interactive", action="store_true", help="Prompt for a customer and use portable template/output defaults")
    parser.add_argument("--customer", help="Customer name for the diagonal watermark")
    parser.add_argument("--output", type=Path, help="New PDF filename; must not exist")
    parser.add_argument("--header", help="Header text (default: Prepared exclusively for CUSTOMER)")
    parser.add_argument("--opacity", type=float, default=0.16, help="Watermark opacity, 0.05-0.4 (default: 0.16)")
    parser.add_argument("--font", type=Path, help="TrueType font with glyphs for the supplied text")
    parser.add_argument("--qpdf-path", type=Path, help="Override the bundled/system qpdf executable")
    parser.add_argument("--owner-password-file", type=Path,
                        help="Read owner password from a UTF-8 file; otherwise generate and discard a random password")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.3")
    args = parser.parse_args(argv)
    if not args.interactive and (args.input is None or args.customer is None or args.output is None):
        parser.error("input, --customer and --output are required unless --interactive is used")
    try:
        if args.interactive:
            from .interactive import collect_inputs
            args.input, args.output, args.customer = collect_inputs(args.input, args.output, args.customer)
        owner = None
        if args.owner_password_file:
            # Remove a single conventional file-ending newline, not password spaces.
            try:
                owner = args.owner_password_file.read_text(encoding="utf-8").removesuffix("\n")
            except (OSError, UnicodeError) as exc:
                raise WatermarkError("Could not read the owner password file as UTF-8.") from exc
        result = personalize(args.input, args.output, Options(
            customer=args.customer, header=args.header, opacity=args.opacity,
            font=args.font, qpdf_path=args.qpdf_path, owner_password=owner,
        ))
    except (WatermarkError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, WatermarkError) else "Could not read or write a file; check the configured paths and permissions."
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except EOFError:
        print("Cancelled: input closed.", file=sys.stderr)
        return 130
    print(f"Created {result.output} ({result.pages} pages). AES-256 and PDF permissions verified.")
    return 0
