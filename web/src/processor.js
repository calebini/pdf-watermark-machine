import createQpdf from '@neslinesli93/qpdf-wasm';
import wasmURL from '@neslinesli93/qpdf-wasm/dist/qpdf.wasm?url';
import fontkit from '@pdf-lib/fontkit';
import { PDFDocument, PDFName, PDFDict, PDFArray, PDFOperator, degrees, rgb } from 'pdf-lib';
import { LEFT_HEADER, RIGHT_HEADER, MAX_FILE_BYTES, validateOptions, assertSecurityReport } from './policy.js';

function run(qpdf, args) {
  let code;
  try { code = qpdf.callMain([...args]); }
  catch { throw new Error('The PDF engine could not process this document. Use a valid, unencrypted static original.'); }
  if (code !== 0) {
    throw new Error('The PDF engine reported an error or warning. Use a valid, unencrypted static original.');
  }
}

function report(qpdf, source, path, owner) {
  const args = [source, '--json-output', '--json-key=encrypt', '--json-key=pages',
    '--json-object=trailer', '--json-stream-data=none'];
  if (owner) args.push(`--password=${owner}`);
  args.push(path);
  run(qpdf, args);
  return JSON.parse(new TextDecoder().decode(qpdf.FS.readFile(path)));
}

function staticInput(doc) {
  const perms = doc.catalog.lookupMaybe(PDFName.of('Perms'), PDFDict);
  if (perms?.size()) throw new Error('This PDF has certification or usage-rights permissions. Use an unsigned original.');
  for (const [, value] of doc.context.enumerateIndirectObjects()) {
    if (value instanceof PDFDict) {
      const type = value.get(PDFName.of('Type'))?.toString();
      if (type === '/Sig' || type === '/DocTimeStamp') throw new Error('This PDF contains a digital signature. Use an unsigned original.');
    }
  }
  const form = doc.catalog.lookupMaybe(PDFName.of('AcroForm'), PDFDict);
  if (form) {
    const fields = form.lookupMaybe(PDFName.of('Fields'), PDFArray);
    if (fields?.size() || form.has(PDFName.of('XFA'))) throw new Error('Interactive forms are not supported. Use a static original.');
  }
  for (const page of doc.getPages()) {
    const annotations = page.node.lookupMaybe(PDFName.of('Annots'), PDFArray);
    for (let index = 0; index < (annotations?.size() ?? 0); index++) {
      if (annotations.lookup(index, PDFDict).get(PDFName.of('Subtype'))?.toString() === '/Widget') {
        throw new Error('Interactive form widgets are not supported. Use a static original.');
      }
    }
  }
}

function drawPage(page, font, { customer, header, opacity }) {
  const unit = page.node.get(PDFName.of('UserUnit'));
  if (unit && Number(unit.toString()) !== 1) throw new Error('Custom page scaling (UserUnit) is not supported.');
  const { x, y, width, height } = page.getCropBox();
  if (![x, y, width, height].every(Number.isFinite) || Math.min(width, height) < 144) {
    throw new Error('This PDF has an invalid or unusually small page size.');
  }
  const media = page.getMediaBox();
  const left = Math.min(media.x, x), bottom = Math.min(media.y, y);
  page.setMediaBox(left, bottom, Math.max(media.x + media.width, x + width) - left,
    Math.max(media.y + media.height, y + height + 36) - bottom);
  page.setCropBox(x, y, width, height + 36);
  for (const box of ['TrimBox', 'BleedBox', 'ArtBox']) page.node.delete(PDFName.of(box));
  const textWidth = text => font.widthOfTextAtSize(text, 1);
  const side = Math.max(textWidth(LEFT_HEADER), textWidth(RIGHT_HEADER));
  const headerSize = Math.min(9, (width - 72) / (textWidth(header) + 2 * side));
  if (headerSize < 6) throw new Error('The header is too long to fit beside the NDA labels. Use a shorter header.');
  const angle = 35 * Math.PI / 180;
  const available = Math.min((width - 48) / Math.cos(angle), (height - 80) / Math.sin(angle));
  const watermarkSize = Math.min(48, available / textWidth(customer));
  if (watermarkSize < 10) throw new Error('The customer name is too long for this page. Use a shorter name.');
  const ink = rgb(0.15, 0.19, 0.24);
  page.pushOperators(PDFOperator.of('BMC', [PDFName.of('Artifact')]));
  page.drawRectangle({ x, y: y + height, width, height: 36, color: rgb(1, 1, 1) });
  const baseline = y + height + 14;
  const common = { y: baseline, size: headerSize, font, color: ink };
  page.drawText(LEFT_HEADER, { ...common, x: x + 24 });
  page.drawText(header, { ...common, x: x + (width - textWidth(header) * headerSize) / 2 });
  page.drawText(RIGHT_HEADER, { ...common, x: x + width - 24 - textWidth(RIGHT_HEADER) * headerSize });
  page.drawLine({ start: { x, y: y + height + 0.5 }, end: { x: x + width, y: y + height + 0.5 },
    thickness: 0.5, color: rgb(0.8, 0.83, 0.86) });
  const textLength = textWidth(customer) * watermarkSize;
  // Match the desktop's rotated, centered baseline without transforming the source page.
  page.drawText(customer, {
    x: x + width / 2 - textLength / 2 * Math.cos(angle) + watermarkSize / 3 * Math.sin(angle),
    y: y + height / 2 - textLength / 2 * Math.sin(angle) - watermarkSize / 3 * Math.cos(angle),
    size: watermarkSize, font, rotate: degrees(35), color: ink, opacity,
  });
  page.pushOperators(PDFOperator.of('EMC'));
}

export async function personalize(input, options, fontBytes, progress = () => {}) {
  const settings = validateOptions(options);
  if (!(input instanceof ArrayBuffer) || !input.byteLength || input.byteLength > MAX_FILE_BYTES) {
    throw new Error('Choose a non-empty PDF smaller than 50 MB.');
  }
  if (!globalThis.crypto?.getRandomValues) throw new Error('This browser cannot provide secure randomness.');
  progress('Checking the template…');
  // The WASM runtime binds output handlers when instantiated. Keep its diagnostics
  // private to this worker: qpdf errors can contain paths or password arguments.
  const savedLog = console.log, savedError = console.error;
  let qpdf;
  try {
    console.log = () => {};
    console.error = () => {};
    qpdf = await createQpdf({ locateFile: () => wasmURL, noInitialRun: true });
  } finally { console.log = savedLog; console.error = savedError; }
  const files = ['/input.pdf', '/input.json', '/normalized.pdf', '/stamped.pdf', '/encrypted.pdf', '/verify.json', '/owner.json'];
  try {
    qpdf.FS.writeFile('/input.pdf', new Uint8Array(input));
    const original = report(qpdf, '/input.pdf', '/input.json');
    if (original.encrypt.encrypted) throw new Error('Use the unencrypted original PDF as input.');
    if (!original.pages.length) throw new Error('The template PDF has no pages.');
    run(qpdf, ['/input.pdf', '--flatten-rotation', '/normalized.pdf']);
    const doc = await PDFDocument.load(qpdf.FS.readFile('/normalized.pdf'), { updateMetadata: false });
    staticInput(doc);
    doc.registerFontkit(fontkit);
    const font = await doc.embedFont(fontBytes, { subset: true });
    const characters = new Set(font.getCharacterSet());
    const missing = [...new Set([...settings.customer + settings.header + LEFT_HEADER + RIGHT_HEADER])]
      .filter(char => !characters.has(char.codePointAt(0)));
    if (missing.length) throw new Error(`The font is missing these characters: ${missing.join(' ')}. Choose a suitable TrueType font.`);
    const pages = doc.getPages();
    if (pages.length !== original.pages.length) throw new Error('The PDF page count changed during preparation. No download was created.');
    pages.forEach((page, index) => {
      progress(`Personalizing page ${index + 1} of ${pages.length}…`);
      drawPage(page, font, settings);
    });
    qpdf.FS.writeFile('/stamped.pdf', await doc.save());
    progress('Applying encryption and permissions…');
    const secret = crypto.getRandomValues(new Uint8Array(32));
    const owner = [...secret].map(byte => byte.toString(16).padStart(2, '0')).join('');
    secret.fill(0);
    run(qpdf, ['--encrypt', '--user-password=', `--owner-password=${owner}`, '--bits=256',
      '--print=none', '--modify=none', '--extract=n', '--accessibility=y', '--', '/stamped.pdf', '/encrypted.pdf']);
    progress('Verifying the protected PDF…');
    run(qpdf, ['--check', '/encrypted.pdf']);
    const verified = report(qpdf, '/encrypted.pdf', '/verify.json');
    assertSecurityReport(verified, pages.length);
    assertSecurityReport(report(qpdf, '/encrypted.pdf', '/owner.json', owner), pages.length, true);
    return { bytes: qpdf.FS.readFile('/encrypted.pdf').slice(), pages: pages.length,
      security: { bits: verified.encrypt.parameters.bits, revision: verified.encrypt.parameters.R } };
  } finally {
    for (const path of files) {
      try { qpdf.FS.unlink(path); } catch { /* File may not exist after an error. */ }
    }
  }
}
