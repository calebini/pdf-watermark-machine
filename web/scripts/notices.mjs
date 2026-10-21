import { readFile, writeFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';

const packages = ['pdf-lib', '@pdf-lib/fontkit', '@neslinesli93/qpdf-wasm', '@pdf-lib/standard-fonts', '@pdf-lib/upng', 'pako', 'tslib'];
const notices = ['PDF WATERMARK — BROWSER DISTRIBUTION\nThird-party software notices\n'];
for (const name of packages) {
  const directory = join('node_modules', name);
  const metadata = JSON.parse(await readFile(join(directory, 'package.json'), 'utf8'));
  notices.push(`\n${name} ${metadata.version}\nLicense: ${metadata.license}\nSource: ${typeof metadata.repository === 'object' ? metadata.repository.url : metadata.repository || metadata.homepage || ''}\n`);
  for (const file of await readdir(directory)) {
    if (/^(licen[sc]e|copying|notice)/i.test(file)) notices.push(await readFile(join(directory, file), 'utf8'));
  }
}
notices.push('\nQPDF is compiled into the WebAssembly module. Source and build instructions: https://github.com/neslinesli93/qpdf-wasm\nQPDF 12.2.0 source: https://github.com/qpdf/qpdf/tree/v12.2.0\n');
notices.push(await readFile('third-party/qpdf-LICENSE.txt', 'utf8'));
notices.push('\nBitstream Vera embedded font\n', await readFile('public/fonts/LICENSE.txt', 'utf8'));
await writeFile('public/THIRD-PARTY-NOTICES.txt', notices.join('\n'));
