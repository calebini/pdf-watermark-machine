import { personalize } from './processor.js';

self.onmessage = async ({ data }) => {
  try {
    const result = await personalize(data.input, data.options, data.font,
      message => self.postMessage({ type: 'progress', message }));
    self.postMessage({ type: 'complete', pages: result.pages, security: result.security,
      bytes: result.bytes.buffer }, [result.bytes.buffer]);
  } catch (error) {
    self.postMessage({ type: 'error', message: error.message || 'The PDF could not be processed.' });
  }
};
