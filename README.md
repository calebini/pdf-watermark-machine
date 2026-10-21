# PDF Watermark

**[Open the browser utility](https://calebini.github.io/pdf-watermark-machine/)**
— PDFs and customer names are processed in your browser, without uploads.

A local CLI for adding a customer's name and a header to an existing PDF, then
applying qpdf AES-256 encryption and PDF permission controls. No network calls
are made during processing. A reusable Python API leaves room for a later UI.

A separate **browser-only distribution** now lives in [`web/`](web/README.md).
It produces the same watermark/header and PDF permissions using browser-local
JavaScript and qpdf WebAssembly. Its built static files are in `web/dist/` for
local testing and static hosting. The GitHub Pages workflow publishes this
variant; an alternative GitLab Pages configuration is also included. See
[`web/DEPLOY.md`](web/DEPLOY.md) for deployment and maintenance instructions.

## Use a portable build

On macOS, extract the entire folder, put your template PDF in
`working/template/`, and double-click **Personalize.command**. Enter the customer
name; a timestamped customer PDF is written to `working/output/`. Press Return to
close the Terminal window when finished. If multiple templates exist, choose one
from the numbered list. On Windows the equivalent launcher is `Personalize.cmd`.
The package does not contain a template; supply your own.

Optional environment overrides:

| Variable | Meaning | Default |
| --- | --- | --- |
| `PDF_WATERMARK_TEMPLATE` | Path to a specific template PDF | Single PDF in `working/template/`, or a numbered choice |
| `PDF_WATERMARK_OUTPUT_DIR` | Folder for generated copies | `working/output/` |

Defaults are beside the launcher, not Terminal's current directory. Relative
environment paths are also resolved against that folder. Home-directory `~`
and environment variable references in those paths are expanded. From Terminal:

```sh
PDF_WATERMARK_TEMPLATE="$HOME/Documents/template.pdf" \
PDF_WATERMARK_OUTPUT_DIR="$HOME/Documents/Customer Copies" \
./Personalize.command
```

Variables exported in a Terminal session apply when launching from that session;
double-clicking in Finder does not inherit that Terminal's exports. The folder
defaults work with Finder without any configuration. You can also invoke
`./pdf-watermark --interactive` directly. Explicit input, `--output` and
`--customer` arguments override the corresponding interactive defaults.

The output folder is created if needed. Filenames contain a sanitized customer
name and local timestamp, including microseconds; existing files are never
overwritten. Errors are displayed and the launcher waits before closing.

Extract the entire distribution folder and keep its contents together. From
PowerShell on Windows:

```powershell
.\pdf-watermark.exe whitepaper.pdf --customer "Example Corporation" --output customer.pdf
```

From Terminal on macOS:

```sh
./pdf-watermark whitepaper.pdf --customer "Example Corporation" --output customer.pdf
```

Use `--header "Confidential - Example Corporation"` to override the default
`Prepared exclusively for CUSTOMER`. A 36-point header band is added ABOVE
each visible page, so the original content is not covered by the header.
The same header line includes `Under NDA` aligned left and
`Not for redistribution` aligned right. The customer header stays centered on
the page; all three texts shrink together when necessary to avoid overlap.
Remove any existing copies of those labels from your original template.
The diagonal customer watermark is translucent page content, not an annotation.
The page becomes 36 points taller. The watermark opacity defaults to 0.16 and
can be adjusted with `--opacity` (0.05-0.4).

An embedded Bitstream Vera font supports common Latin customer names. Missing
glyphs are rejected instead of silently printing boxes. Use `--font path/to/font.ttf`
with a suitable licensed TrueType font for other scripts. Complex script shaping
and right-to-left layout have not been validated.

## Security behavior

| Capability | Permission |
| --- | --- |
| Open | Empty user password; no authentication prompt |
| General text/image extraction | Denied |
| Printing, including low resolution | Denied |
| Editing, annotations, forms, page assembly | Denied |
| Accessibility extraction | Allowed |
| Search | Original text retained |
| Selection | Reader-dependent |

qpdf uses AES-256 with revision 6 and generates a fresh random encryption key for
each output PDF. The tool also generates a separate random 256-bit owner secret
for each output, with an empty user password. Neither is hardcoded. Supplying an
owner password file overrides only the owner password, not the random encryption
key. The owner secret is never logged or placed in subprocess arguments;
qpdf receives arguments over standard input. By default the secret is discarded.
If you need an owner password for later administrative use, store one in a UTF-8
file and pass `--owner-password-file path/to/secret.txt`. Keep it separate from
customer deliveries. Only the generated PDF goes to the customer.

The output is checked with `qpdf --check`, reopened without a password to verify
encryption, permissions and page count, and reopened with the owner password to
verify owner access before publication. Source files are never overwritten;
existing output files are refused. Temporary plaintext PDFs are removed on
normal completion and handled errors. A forced process termination or system
crash can leave a `.pdf-watermark-*` temporary directory beside the intended output.
Temporary-file deletion is not a secure erase guarantee.

PDF permissions are enforced by cooperative reader software. They do not stop
screenshots, OCR, restriction removal by other tools, or determined watermark
removal. Keeping accessibility permission does not remediate an inaccessible
source PDF. Added decorative text is marked as a PDF artifact.

## Supported input

Static, unencrypted PDFs, including mixed page sizes, cropped pages and page
rotations. Empty form dictionaries left by PDF exporters are accepted when there
are no fields, XFA forms or widget annotations. Links and document metadata are
preserved. Password-protected inputs,
interactive forms, signed/certified documents, custom UserUnit scaling and pages
smaller than 144 PDF points in either dimension are rejected. Use an unsigned,
static source. This prototype does not perform full PDF/UA accessibility validation.

## Develop

Python 3.13 or newer and qpdf 11.7 or newer are development prerequisites:

```sh
python3 -m venv .venv
# macOS
source .venv/bin/activate
# Windows instead: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pdf-watermark --help
python -m pytest
```

Install qpdf through your package manager, stage it under `vendor/qpdf/qpdf`
(`qpdf.exe` on Windows), or pass `--qpdf-path`. Packaged distributions include it.
Tests invoke real qpdf and use pypdf as an independent extraction check. Test
rotation/crop geometry, exact permission settings, owner access, original content,
metadata and links, invalid inputs, secret redaction, failure cleanup and refusal
to overwrite files. Readers can still select/copy differently; manually check the
actual source document in your approved Windows/macOS PDF readers before a release.

Generate a synthetic two-page demo (portrait and landscape):

```sh
python scripts/make_demo.py
pdf-watermark output/pdf/demo-original.pdf --customer "Example Corporation" --output output/pdf/demo-customer.pdf
```

## Build a portable distribution

For a Windows x64 build, use Windows with 64-bit Python 3.13 or newer installed:

```powershell
py -3.13 scripts/build_windows.py
```

This creates a project-local build environment, downloads the pinned official
qpdf 12.4.2 Windows runtime, verifies its SHA-256 checksum, runs the test suite,
and builds the application with `Personalize.cmd` and empty working folders.
It then extracts the ZIP into a path with spaces and exercises the launcher
from another directory with Python and qpdf absent from PATH. It checks the
generated PDF's content, AES-256 encryption and permissions. The final ZIP and
checksum are in `dist/`. No templates or customer documents are packaged.
Internet access is required on the build machine; end users need no Python or
qpdf installation. The resulting preview is unsigned.

The same build is available as the manually dispatched **Windows portable
package** GitHub Actions workflow in `.github/workflows/windows.yml`. Once this
project is in a GitHub repository, run that workflow and download its artifact.
No Windows executable has been validated until that native build and smoke
check actually complete; running tests on macOS does not validate a Windows ZIP.

Build on the target OS/architecture. Place a complete qpdf runtime in
`vendor/qpdf/`, including required DLLs/dylibs (libraries may be in `lib/`).
Use redistributable dependencies, not links to a developer's Homebrew installation.

```sh
python scripts/build.py
```

The resulting `dist/pdf-watermark/` folder contains the executable, Python,
fonts and PDF dependencies, plus qpdf and its runtime libraries. Users need no
Python, package manager, qpdf installation, internet connection or admin rights
for portable use, subject to enterprise application policy. They need read access
to the source, write access to the output directory, and space for temporary PDFs.
Zip the whole folder; preserve executable permissions and symlinks on macOS.
The build script copies available dependency notices into `THIRD-PARTY-LICENSES`;
stage qpdf's `LICENSE.txt` beside its executable. Review notices for any additional
native dependencies in your selected qpdf distribution before releasing it.

Separate builds are needed for Windows x64, macOS arm64, and optionally macOS
x64. Minimum OS versions depend on the selected Python/native-library wheels
and must be established through release testing. The first local build is a
development preview; it is not a signed/notarized production distribution.

Before external distribution: test on clean target machines without Python or
Homebrew, sign Windows binaries, sign and notarize the macOS distribution, and
exercise the intended PDF readers. Building/signing Windows artifacts requires
a Windows build environment. Release signing credentials are not included.
