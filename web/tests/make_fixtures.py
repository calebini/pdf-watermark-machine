"""Generate synthetic fixtures under ignored tmp/; never ship source documents."""

from pathlib import Path
import io
import json

import pikepdf
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "tmp" / "web-tests"
FOLDER.mkdir(parents=True, exist_ok=True)


def original():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(595, 842))
    c.setTitle("Synthetic browser test white paper")
    for width, height in ((595, 842), (792, 612)):
        c.setPageSize((width, height))
        c.setFont("Helvetica", 16)
        c.drawString(40, height - 50, "TOP EDGE ORIGINAL")
        c.setFont("Helvetica", 11)
        c.drawString(40, height / 2, "Searchable original browser-test content")
        c.linkURL("https://example.com", (40, height / 2 - 10, 300, height / 2 + 10))
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


with pikepdf.open(original()) as pdf:
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array(), DA="/Helv 0 Tf 0 g", DR=pikepdf.Dictionary())
    pdf.save(FOLDER / "mixed.pdf")

for rotation in (0, 90, 180, 270):
    with pikepdf.open(original()) as pdf:
        page = pdf.pages[0]
        page.cropbox = pikepdf.Array([20, 30, 570, 820])
        page.obj.Rotate = rotation
        pdf.save(FOLDER / f"rotation-{rotation}.pdf")

for kind in ("form", "signature", "widget", "scaled", "encrypted", "password"):
    with pikepdf.open(original()) as pdf:
        if kind == "form":
            field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Tx, T="Customer"))
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([field]))
        elif kind == "signature":
            signature = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Sig))
            field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Signature", V=signature))
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([field]))
        elif kind == "widget":
            widget = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget,
                FT=pikepdf.Name.Tx, T="Orphan", Rect=pikepdf.Array([40, 40, 100, 60])))
            pdf.pages[0].Annots.append(widget)
        elif kind == "scaled":
            pdf.pages[0].obj.UserUnit = 2
        pdf.save(FOLDER / f"{kind}.pdf", encryption=pikepdf.Encryption(
            owner="owner", user="user" if kind == "password" else "")
            if kind in ("encrypted", "password") else None)
(FOLDER / "invalid.pdf").write_bytes(b"Not a valid PDF")
print(FOLDER)
