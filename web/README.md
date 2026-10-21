# PDF Watermark — browser distribution

Live site: **https://calebini.github.io/pdf-watermark-machine/**

This is a local-first static variant of the desktop utility. Choose a PDF,
enter a customer name, generate, then download. There is no application server,
upload endpoint, analytics, external CDN, account service, or browser storage.
All dependencies, fonts, the worker and WebAssembly module are served by the
same static host. Documents and customer names are processed in a dedicated
browser worker. The worker is terminated after success, error or cancellation;
the download URL is revoked when inputs change or the page is closed.

## Try locally

The already-built site is in `web/dist/`. On macOS, double-click
`web/Preview.command`, or from the project root run:

```sh
python3 web/serve.py
```

Open **http://127.0.0.1:4173/**. Stop the server with Ctrl+C. Use
`--port 4175` if the default port is occupied. Python only serves static files;
it does not process PDFs. Opening `index.html` with `file://` is not supported
because browsers restrict workers and WebAssembly loading from local files.

Select your cleaned, unsigned, unencrypted PDF template. The template is never
copied into the website or sent to the static server. The original is unchanged.
Your browser's Download action saves the protected PDF; browser download settings
determine its destination folder. No source documents or customer PDFs are included
in the distribution.

## Behavior and limits

- Three-part header: `Under NDA`, a centered customer header, and
  `Not for redistribution`, on every page.
- Default center: `Prepared exclusively for CUSTOMER`; optional custom text.
- A 36-point band is added above each visible page; source content is not covered.
- Translucent diagonal customer watermark, adjustable from 5% to 40% opacity.
- Watermark font size adjustable from 12 to 96 points (default 48). Long names
  shrink to fit each page. Both size and opacity update the illustration live
  and apply to the downloaded PDF; the header size remains automatic.
- Original text, links, metadata and document structure retained; no rasterization.
- Embedded Bitstream Vera supports common Latin names, including accented text.
  Missing glyphs produce an error; optionally choose a suitable TrueType font.
- PDF limit: 50 MiB. Custom font limit: 10 MiB. Available browser memory can impose
  a lower practical limit. Complex-script shaping and full PDF/UA compliance have
  not been validated; the app does not add missing accessibility tags.
- Mixed page sizes, crop offsets and rotations supported. Empty form dictionaries
  accepted. Real form fields/widgets, XFA, signatures, usage-rights permissions,
  encrypted inputs, custom UserUnit scaling and very small pages are rejected.

The small document illustration is a live text mockup, not a preview of your
selected file. Review the downloaded PDF before sharing.

## Security settings and validation

qpdf 12.2.0 compiled to WebAssembly writes AES-256 with revision 6, an empty user
password and a fresh random owner password for each PDF. Both our owner password
generation and the WASM runtime's random device use browser
`crypto.getRandomValues`; processing fails if secure randomness is unavailable.
qpdf generates its own random encryption key. There is no hardcoded owner secret
and none is retained for later retrieval. A client-side utility cannot keep its
code or in-memory values secret from the person operating that browser.

| Capability | Output permission |
| --- | --- |
| Open without password | Allowed |
| Copy text / extract graphics | Denied |
| Print at any resolution | Denied |
| Edit, annotate, assemble pages, fill forms | Denied |
| Accessibility extraction | Allowed |
| Search | Original text retained |
| Text selection | Reader-dependent |

Before exposing a download, the worker runs qpdf's syntax check and inspects
its JSON report for AESv3, 256 bits, R=6, the exact permissions, accessibility,
page count, opening with the empty user password, and owner access. Failure
does not expose a download. Error diagnostics from the native engine are kept
out of the browser console because they can contain secret arguments.

These are PDF reader-enforced permissions, as in the desktop variant. They do
not stop screenshots, OCR, copying by libraries that ignore permissions, or
determined watermark removal. Web hosting does not strengthen those restrictions.
Local processing avoids document uploads; it does not guarantee secure erasure
from browser memory, the browser's download history, or the user's disk.

## Build

Use a current supported Node.js version compatible with Vite (Node 24 recommended):

```sh
cd web
npm ci
npm test
npm run build
```

Dependencies are pinned in `package.json` and `package-lock.json`.
From the project root, `python3 scripts/package_web.py` produces a static ZIP
for hosting and a separate local-preview ZIP with the helper, plus SHA-256 files.
`@neslinesli93/qpdf-wasm` 0.3.0 contains qpdf 12.2.0. Its conditional Node-only
`fs`, `path` and `crypto` imports produce Vite externalization notices; the browser
branch uses WebAssembly, its memory filesystem and browser cryptography instead.
No cross-origin isolation, SharedArrayBuffer, or custom server headers are
required. The build supplies a restrictive CSP in the page itself and relative
asset paths for a project subdirectory on GitHub or GitLab Pages. Serve over HTTPS in production
and use the default `.wasm` MIME type `application/wasm`.

The source, build inputs and third-party notices stay in this folder; publish
only `dist/`. Review upstream dependency updates before replacing the pinned
WASM binary. The compiled module's source and build instructions are linked in
`third-party/README.md` and the generated software notices.

## Test the actual browser-generated PDFs

From the project root, with the desktop development dependencies installed:

```sh
.venv/bin/python web/tests/make_fixtures.py
```

Serve the built site, then in another Terminal:

```sh
cd web
npx playwright install chromium
node tests/browser.mjs
cd ..
.venv/bin/python web/tests/verify_outputs.py
```

On Windows use `.venv\Scripts\python.exe` for the Python commands. You can set
`PDF_WATERMARK_BROWSER_PATH` to an already installed Chromium/Chrome/Edge executable,
`PDF_WATERMARK_TEST_URL` to another local URL, and `PDF_WATERMARK_TEST_TEMPLATE` to a local
template PDF for an additional full-template test. PDFs, screenshots and test reports
are written only to the root project's ignored `tmp/web-tests/` folder.

The suite generates actual encrypted downloads in the browser; exercises repeated
jobs, recovery after errors, missing glyphs, long headers, forms, signatures,
encryption rejection, rotations, crop offsets, cancellation and mobile layout;
and checks that all application requests are same-origin static GETs, with no
PDF requests or browser storage. The Python verifier independently checks
encryption, permission flags, text, metadata, links, page geometry, page count
and unique encryption keys. Root `pytest` tests for the desktop variant remain
separate.

## GitHub Pages

The workflow in `.github/workflows/pages.yml` builds the browser utility and
publishes only `web/dist/`. Pages is enabled with GitHub Actions as the source.
See [DEPLOY.md](DEPLOY.md) for deployment and maintenance instructions. No
template or customer PDF is hosted; document processing stays in the browser.

## GitLab Pages alternative

The root `.gitlab-ci.yml` includes `web/gitlab-pages.yml`. On the default branch,
it installs the pinned dependencies, runs the unit checks, builds and publishes
only `web/dist/`. See [DEPLOY.md](DEPLOY.md) for project setup, access control,
runner requirements and the first-deployment checks. The GitLab alternative
has not been deployed.

If moving this folder into its own repository root, use `gitlab-pages.yml` as
`.gitlab-ci.yml`, remove `cd web` and change both publish/artifact paths from
`web/dist` to `dist`.

Alternatively, publish the contents of the prebuilt static ZIP directly with
your existing Pages pipeline. It needs no Node.js or Python at runtime.

Configure Pages access control for the intended internal audience: repository
privacy and website access should be checked separately. Keep templates and
generated documents out of the Pages artifacts. The site has no built-in login;
authentication, if required, belongs to the GitLab Pages hosting layer.
