"""Independent native inspection of actual browser-generated PDFs."""

from pathlib import Path
import json

import pikepdf
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "tmp" / "web-tests"
manifest = json.loads((FOLDER / "manifest.json").read_text())
keys = []
for item in manifest:
    output = Path(item["output"])
    with pikepdf.open(item["source"]) as original, pikepdf.open(output, password="") as pdf:
        assert pdf.is_encrypted and pdf.encryption.R == 6 and pdf.encryption.bits == 256
        assert str(pdf.trailer.Encrypt.CF.StdCF.CFM) == "/AESV3"
        assert pdf.allow.accessibility and not pdf.owner_password_matched
        assert not any((pdf.allow.extract, pdf.allow.print_lowres, pdf.allow.print_highres,
            pdf.allow.modify_annotation, pdf.allow.modify_assembly, pdf.allow.modify_form, pdf.allow.modify_other))
        assert len(pdf.pages) == len(original.pages)
        for source_page, page in zip(original.pages, pdf.pages):
            source_page.flatten_rotation()
            expected = list(map(float, source_page.cropbox))
            expected[3] += 36
            assert all(abs(float(actual) - expected_value) < 0.01 for actual, expected_value in zip(page.cropbox, expected))
            assert page.rotation == 0
            assert len(page.obj.get('/Annots', [])) == len(source_page.obj.get('/Annots', []))
            assert any(abs(float(state.get('/ca', 1)) - item['opacity']) < 0.000001
                       for state in page.Resources.get('/ExtGState', {}).values()), 'Watermark opacity differs from selection'
        if '/Title' in original.docinfo:
            assert str(original.docinfo.Title) == str(pdf.docinfo.Title)
        keys.append(bytes(pdf.encryption.encryption_key))
    reader = PdfReader(output)
    source_reader = PdfReader(item['source'])
    for source_page, page in zip(source_reader.pages, reader.pages):
        text = page.extract_text()
        assert ''.join(source_page.extract_text().split()) in ''.join(text.split()), output.name
        for expected in (item['customer'], item['header'], 'Under NDA', 'Not for redistribution'):
            assert expected in text, (output.name, expected)
        if item.get('expectedFontSize') is not None:
            sizes = []
            def inspect_text(text, cm, tm, font, size):
                if text.strip() == item['customer']:
                    sizes.append(size)
            page.extract_text(visitor_text=inspect_text)
            assert sizes and all(abs(size - item['expectedFontSize']) < 0.01 for size in sizes), (output.name, sizes)
    if 'external-template' not in output.name:
        assert 'Searchable original browser-test content' in reader.pages[0].extract_text()
    print(f"PASS independent inspection: {output.name}, {len(reader.pages)} pages")
assert len(keys) == len(set(keys)), 'Repeated browser runs reused an encryption key'
print(f"PASS all {len(keys)} outputs have distinct 256-bit encryption keys")
