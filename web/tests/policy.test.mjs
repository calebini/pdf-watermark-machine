import { test } from 'node:test';
import assert from 'node:assert/strict';
import { singleLine, validateOptions, outputFilename, assertSecurityReport } from '../src/policy.js';

test('customer and header validation', () => {
  assert.equal(singleLine('  Müller & Co.  '), 'Müller & Co.');
  for (const invalid of ['', 'a\nb', 'a\0b', 'a'.repeat(301)]) assert.throws(() => singleLine(invalid));
  assert.equal(validateOptions({ customer: 'Acme' }).header, 'Prepared exclusively for Acme');
  for (const opacity of [NaN, 0, 0.41]) assert.throws(() => validateOptions({ customer: 'Acme', opacity }));
});

test('safe generated filename', () => {
  assert.match(outputFilename('Müller / .. & Co.', new Date('2026-10-21T08:00:00Z')), /^Customer_Copy_Muller-Co_2026-10-21T08-00-00-000Z\.pdf$/);
  assert.match(outputFilename('客户'), /^Customer_Copy_customer_/);
});

function validReport() {
  return { pages: [{}, {}], encrypt: { encrypted: true, ownerpasswordmatched: false,
    parameters: { R: 6, bits: 256, method: 'AESv3', streammethod: 'AESv3', stringmethod: 'AESv3', filemethod: 'AESv3' },
    capabilities: { accessibility: true, extract: false, modify: false, modifyannotations: false,
      modifyassembly: false, modifyforms: false, modifyother: false, printhigh: false, printlow: false } } };
}

test('security verification rejects permissive, weaker, or incomplete output', () => {
  assert.doesNotThrow(() => assertSecurityReport(validReport(), 2));
  for (const field of ['extract', 'modify', 'modifyannotations', 'modifyassembly', 'modifyforms', 'modifyother', 'printhigh', 'printlow']) {
    const report = validReport(); report.encrypt.capabilities[field] = true;
    assert.throws(() => assertSecurityReport(report, 2));
  }
  for (const field of ['R', 'bits', 'filemethod']) {
    const report = validReport(); delete report.encrypt.parameters[field];
    assert.throws(() => assertSecurityReport(report, 2));
  }
  const report = validReport(); report.encrypt.capabilities.accessibility = false;
  assert.throws(() => assertSecurityReport(report, 2));
  assert.throws(() => assertSecurityReport(validReport(), 3));
  assert.throws(() => assertSecurityReport(validReport(), 2, true));
});
