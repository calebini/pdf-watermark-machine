"""Generate synthetic white-paper pages; only synthetic material is included."""

from pathlib import Path
from reportlab.pdfgen import canvas


def main():
    folder = Path(__file__).resolve().parents[1] / "output" / "pdf"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "demo-original.pdf"
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.setTitle("Synthetic white paper - layout demonstration")
    for page, size in enumerate(((595, 842), (792, 612)), 1):
        c.setPageSize(size)
        width, height = size
        c.setFillColorRGB(0.06, 0.17, 0.25)
        c.rect(0, height - 160, width, 160, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 10)
        c.drawString(42, height - 45, "SYNTHETIC WHITE PAPER / LAYOUT DEMO")
        c.setFont("Helvetica-Bold", 27)
        c.drawString(42, height - 88, "Document personalization")
        c.setFont("Helvetica", 12)
        c.drawString(42, height - 119, "Original searchable content remains intact.")
        c.setFillColorRGB(0.15, 0.19, 0.24)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(42, height - 208, "A customer-specific copy")
        c.setFont("Helvetica", 11)
        lines = [
            "This document is a synthetic white paper for layout testing.",
            "It demonstrates a header above the original page and a diagonal watermark.",
            "The original text remains searchable; copying and printing depend on the reader.",
            "Permission flags allow accessibility extraction and deny general extraction.",
        ]
        for index, line in enumerate(lines):
            c.drawString(42, height - 240 - index * 22, line)
        c.setFillColorRGB(0.91, 0.94, 0.96)
        c.rect(42, 95, width - 84, 110, fill=1, stroke=0)
        c.setFillColorRGB(0.06, 0.17, 0.25)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(58, 174, "PDF CONTENT + CUSTOMER OVERLAY + AES-256")
        c.setFont("Helvetica", 10)
        c.drawString(58, 148, "Original page dimensions and content are preserved below the new header.")
        c.setFont("Helvetica", 9)
        c.drawString(42, 38, f"Demo page {page} / 2")
        c.showPage()
    c.save()
    print(path)


if __name__ == "__main__":
    main()
