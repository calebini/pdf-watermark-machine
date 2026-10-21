export const LEFT_HEADER = 'Under NDA';
export const RIGHT_HEADER = 'Not for redistribution';
export const MAX_FILE_BYTES = 50 * 1024 * 1024;

export function singleLine(value, label = 'Customer name') {
  const text = String(value ?? '').trim();
  if (!text || [...text].length > 300 || /[\p{C}\u2028\u2029]/u.test(text)) {
    throw new Error(`${label} must be one line of 1–300 printable characters.`);
  }
  return text;
}

export function validateOptions(options) {
  const customer = singleLine(options.customer);
  const header = singleLine(options.header ?? `Prepared exclusively for ${customer}`, 'Header');
  const opacity = Number(options.opacity ?? 0.16);
  if (!Number.isFinite(opacity) || opacity < 0.05 || opacity > 0.4) {
    throw new Error('Watermark opacity must be between 5% and 40%.');
  }
  const watermarkFontSize = Number(options.watermarkFontSize ?? 48);
  if (!Number.isFinite(watermarkFontSize) || watermarkFontSize < 12 || watermarkFontSize > 96) {
    throw new Error('Watermark font size must be between 12 and 96 points.');
  }
  return { customer, header, opacity, watermarkFontSize };
}

export function fitWatermarkSize(textWidthAtOne, width, height, requestedSize) {
  const angle = 35 * Math.PI / 180;
  const available = Math.min((width - 48) / Math.cos(angle), (height - 80) / Math.sin(angle));
  return Math.min(requestedSize, available / textWidthAtOne);
}

export function outputFilename(customer, now = new Date()) {
  const slug = customer.normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80).replace(/-$/, '') || 'customer';
  const stamp = now.toISOString().replace(/[:.]/g, '-');
  return `Customer_Copy_${slug}_${stamp}.pdf`;
}

export function assertSecurityReport(report, expectedPages, owner = false) {
  const encryption = report.encrypt;
  const parameters = encryption?.parameters;
  const capabilities = encryption?.capabilities;
  if (!encryption?.encrypted || parameters?.R !== 6 || parameters?.bits !== 256 ||
      ['method', 'streammethod', 'stringmethod', 'filemethod'].some(key => parameters[key] !== 'AESv3')) {
    throw new Error('The output did not pass AES-256 verification. No download was created.');
  }
  const denied = ['extract', 'modify', 'modifyannotations', 'modifyassembly', 'modifyforms',
    'modifyother', 'printhigh', 'printlow'];
  if (denied.some(key => capabilities?.[key] !== false) || capabilities?.accessibility !== true ||
      encryption.ownerpasswordmatched !== owner || report.pages?.length !== expectedPages) {
    throw new Error('The output did not pass permission verification. No download was created.');
  }
}
