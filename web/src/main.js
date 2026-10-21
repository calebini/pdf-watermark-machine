import { MAX_FILE_BYTES, validateOptions, outputFilename } from './policy.js';

const $ = selector => document.querySelector(selector);
const form = $('#personalize-form'), inputs = $('#inputs'), status = $('#status');
const generate = $('#generate'), cancel = $('#cancel'), result = $('#result');
let worker, downloadURL;

function clearDownload() {
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  downloadURL = undefined;
  result.hidden = true;
  $('#download').removeAttribute('href');
}
function stop() {
  worker?.terminate(); worker = undefined;
  inputs.disabled = false; generate.disabled = false; cancel.hidden = true;
}
function fail(message) {
  stop(); clearDownload(); status.textContent = message; status.className = 'error';
}
function preview() {
  const name = $('#customer').value.trim();
  $('#preview-header').textContent = $('#header').value.trim() || `Prepared exclusively for ${name || 'your customer'}`;
  $('#preview-watermark').textContent = name || 'Your customer';
  $('#opacity-label').textContent = `${$('#opacity').value}%`;
}
for (const input of form.querySelectorAll('input')) {
  input.addEventListener('input', () => { clearDownload(); status.textContent = ''; preview(); });
}
$('#template').addEventListener('change', () => {
  const file = $('#template').files[0];
  $('#file-description').textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : 'Unsigned, unencrypted PDF · Up to 50 MB';
});
cancel.addEventListener('click', () => { stop(); clearDownload(); status.className = ''; status.textContent = 'Processing cancelled. Your original file was not changed.'; });
form.addEventListener('submit', async event => {
  event.preventDefault(); clearDownload(); status.className = '';
  try {
    const file = $('#template').files[0];
    if (!file || !file.size || file.size > MAX_FILE_BYTES) throw new Error('Choose a non-empty PDF smaller than 50 MB.');
    const options = validateOptions({ customer: $('#customer').value,
      header: $('#header').value.trim() || undefined, opacity: Number($('#opacity').value) / 100 });
    inputs.disabled = true; generate.disabled = true; status.textContent = 'Reading the selected file…';
    const input = await file.arrayBuffer();
    const customFont = $('#font').files[0];
    if (customFont && (!customFont.size || customFont.size > 10 * 1024 * 1024)) {
      throw new Error('Choose a non-empty TrueType font smaller than 10 MB.');
    }
    const font = customFont ? await customFont.arrayBuffer() : await (async () => {
      const response = await fetch(new URL('fonts/Vera.ttf', document.baseURI));
      if (!response.ok) throw new Error('The bundled font could not be loaded. Refresh the page and try again.');
      return response.arrayBuffer();
    })();
    worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    cancel.hidden = false;
    worker.onmessage = ({ data }) => {
      if (data.type === 'progress') status.textContent = data.message;
      if (data.type === 'error') fail(data.message);
      if (data.type === 'complete') {
        stop(); status.textContent = '';
        downloadURL = URL.createObjectURL(new Blob([data.bytes], { type: 'application/pdf' }));
        const link = $('#download');
        link.href = downloadURL; link.download = outputFilename(options.customer);
        $('#result-description').textContent = `${data.pages} pages personalized. AES-256 encryption and PDF permissions verified.`;
        result.hidden = false; link.focus();
      }
    };
    worker.onerror = () => fail('The document engine could not start. Use a current browser with JavaScript and WebAssembly enabled.');
    worker.postMessage({ input, options, font }, [input, font]);
  } catch (error) { fail(error.message); }
});
window.addEventListener('pagehide', () => { stop(); clearDownload(); });
