# Browser runtime provenance

- `@neslinesli93/qpdf-wasm` 0.3.0, pinned with npm integrity in the lockfile:
  https://github.com/neslinesli93/qpdf-wasm
- The module reports qpdf 12.2.0. Upstream qpdf source and license:
  https://github.com/qpdf/qpdf/tree/v12.2.0
- The wrapper package declares ISC. qpdf is Apache-2.0; its license is included
  here and in the distribution notices. The upstream wrapper's Dockerfile and
  build script document the Emscripten build and dependencies.
- PDF drawing: `pdf-lib` 1.17.1 and `@pdf-lib/fontkit` 1.1.1, with their bundled
  dependencies and license notices collected by `scripts/notices.mjs`.
- Default font: Bitstream Vera from the installed ReportLab package; its
  redistribution license is included next to the font and in the notices.

The binary is consumed as a pinned upstream dependency; it is not represented as
a build of our desktop qpdf 12.4.2. Browser output is checked independently by
native qpdf/pikepdf and pypdf during local QA.
