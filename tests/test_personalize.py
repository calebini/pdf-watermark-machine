from dataclasses import replace
import hashlib
import subprocess

import pikepdf
from pypdf import PdfReader
import pytest
from reportlab.pdfgen import canvas

from pdf_watermark import Options, WatermarkError, personalize
from pdf_watermark.cli import main
from pdf_watermark.core import find_qpdf


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "white paper.pdf"
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.setTitle("Original white paper")
    c.drawString(40, 810, "TOP EDGE ORIGINAL")
    c.drawString(40, 400, "Searchable original text")
    c.linkURL("https://example.com", (40, 390, 200, 410))
    c.showPage()
    c.setPageSize((792, 612))
    c.drawString(40, 570, "Landscape original")
    c.showPage()
    c.save()
    return path


def test_real_qpdf_permissions_content_and_source_unchanged(source, tmp_path):
    before = hashlib.sha256(source.read_bytes()).digest()
    output = tmp_path / "customer paper.pdf"
    result = personalize(source, output, Options(customer="Acme & Müller", owner_password="private-owner"))
    assert result.pages == 2
    assert hashlib.sha256(source.read_bytes()).digest() == before
    with pikepdf.open(output) as pdf:
        assert pdf.is_encrypted and pdf.encryption.R == 6 and pdf.encryption.bits == 256
        assert str(pdf.trailer.Encrypt.CF.StdCF.CFM) == "/AESV3"
        assert pdf.user_password_matched and not pdf.owner_password_matched
        assert pdf.allow.accessibility
        assert not any((pdf.allow.extract, pdf.allow.print_lowres, pdf.allow.print_highres,
                        pdf.allow.modify_annotation, pdf.allow.modify_assembly,
                        pdf.allow.modify_form, pdf.allow.modify_other))
        assert len(pdf.pages[0].Annots) == 1
        assert str(pdf.docinfo.Title) == "Original white paper"
        assert list(pdf.pages[0].cropbox) == [0, 0, 595, 878]
    with pikepdf.open(output, password="private-owner") as pdf:
        assert pdf.owner_password_matched
    # pypdf ignores permissions here intentionally, to verify preserved text.
    reader = PdfReader(output)
    reader.decrypt("")
    text = reader.pages[0].extract_text()
    assert "Searchable original text" in text
    assert "TOP EDGE ORIGINAL" in text
    assert "Acme & Müller" in text
    assert "Prepared exclusively for Acme & Müller" in text
    assert all("Under NDA" in page.extract_text() and "Not for redistribution" in page.extract_text()
               for page in reader.pages)
    assert not list(tmp_path.glob(".pdf-watermark-*"))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotation_crop_and_offset(source, tmp_path, rotation):
    adjusted = tmp_path / "cropped.pdf"
    with pikepdf.open(source) as pdf:
        page = pdf.pages[0]
        page.cropbox = pikepdf.Array([20, 30, 570, 820])
        page.obj.Rotate = rotation
        pdf.save(adjusted)
    output = tmp_path / "result.pdf"
    personalize(adjusted, output, Options(customer="Customer"))
    with pikepdf.open(output) as pdf:
        box = list(map(float, pdf.pages[0].cropbox))
        width, height = (550, 790) if rotation in (0, 180) else (790, 550)
        assert box[2] - box[0] == pytest.approx(width)
        assert box[3] - box[1] == pytest.approx(height + 36)
        assert pdf.pages[0].rotation == 0


def test_no_overwrite_or_source_replacement(source, tmp_path):
    with pytest.raises(WatermarkError, match="different"):
        personalize(source, source, Options(customer="Acme"))
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep me")
    with pytest.raises(WatermarkError, match="already exists"):
        personalize(source, target, Options(customer="Acme"))
    assert target.read_bytes() == b"keep me"


@pytest.mark.parametrize("change", [
    {"customer": " "}, {"customer": "Acme\nInjected"}, {"customer": "Acme\x00"},
    {"customer": "a" * 301}, {"customer": "客户"}, {"header": ""},
    {"opacity": float("nan")}, {"opacity": 0.01}, {"opacity": 0.9},
    {"owner_password": ""}, {"owner_password": "bad\npassword"},
    {"owner_password": "a" * 128},
])
def test_invalid_options_leave_no_output(source, tmp_path, change):
    target = tmp_path / "result.pdf"
    with pytest.raises(WatermarkError):
        personalize(source, target, replace(Options(customer="Acme"), **change))
    assert not target.exists()
    assert not list(tmp_path.glob(".pdf-watermark-*"))


@pytest.mark.parametrize("kind", ["malformed", "encrypted", "form", "signed", "empty", "scaled"])
def test_unsupported_inputs_leave_no_output(tmp_path, kind):
    source = tmp_path / "input.pdf"
    if kind == "malformed":
        source.write_bytes(b"Not a PDF")
    else:
        with pikepdf.new() as pdf:
            if kind != "empty":
                pdf.add_blank_page()
            if kind == "form":
                field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Tx, T="Customer"))
                pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([field]))
            if kind == "signed":
                pdf.Root.Perms = pikepdf.Dictionary(DocMDP=pikepdf.Dictionary(Type=pikepdf.Name.Sig))
            if kind == "scaled":
                pdf.pages[0].obj.UserUnit = 2
            pdf.save(source, encryption=pikepdf.Encryption(owner="owner", user="user")
                     if kind == "encrypted" else None)
    target = tmp_path / "output.pdf"
    with pytest.raises(WatermarkError):
        personalize(source, target, Options(customer="Acme"))
    assert not target.exists()
    assert not list(tmp_path.glob(".pdf-watermark-*"))


def test_cli_reads_secret_file_without_echo(source, tmp_path, capsys):
    secret = tmp_path / "secret.txt"
    secret.write_text("a long secret\n", encoding="utf-8")
    target = tmp_path / "cli.pdf"
    assert main([str(source), "--customer", "Acme", "--output", str(target),
                 "--owner-password-file", str(secret)]) == 0
    captured = capsys.readouterr()
    assert "a long secret" not in captured.out + captured.err
    with pikepdf.open(target, password="a long secret") as pdf:
        assert pdf.owner_password_matched


def test_qpdf_receives_password_on_stdin(source, tmp_path, monkeypatch):
    real_run = subprocess.run
    calls = []
    def record(args, **kwargs):
        calls.append((args, kwargs))
        return real_run(args, **kwargs)
    monkeypatch.setattr(subprocess, "run", record)
    personalize(source, tmp_path / "result.pdf", Options(customer="Acme", owner_password="secret-xyz"))
    assert all(args == [str(find_qpdf()), "@-"] for args, _ in calls)
    assert "secret-xyz" in calls[0][1]["input"]


def test_qpdf_failure_is_redacted_and_cleans_up(source, tmp_path, monkeypatch):
    def fail(args, **kwargs):
        return subprocess.CompletedProcess(args, 2, "secret-xyz", "secret-xyz")
    monkeypatch.setattr(subprocess, "run", fail)
    output = tmp_path / "result.pdf"
    with pytest.raises(WatermarkError, match="qpdf reported") as error:
        personalize(source, output, Options(customer="Acme", owner_password="secret-xyz"))
    assert "secret-xyz" not in str(error.value)
    assert not output.exists()
    assert not list(tmp_path.glob(".pdf-watermark-*"))


def test_missing_qpdf_is_actionable(source, tmp_path):
    assert main([str(source), "--customer", "Acme", "--output", str(tmp_path / "result.pdf"),
                 "--qpdf-path", str(tmp_path / "missing")]) == 1


def test_failed_permission_verification_never_publishes(source, tmp_path, monkeypatch):
    from pdf_watermark import core
    def bad_encrypt(executable, args):
        if args[0] == "--encrypt":
            with pikepdf.open(args[-2]) as pdf:
                # Deliberately allow copying, simulating an encryption regression.
                pdf.save(args[-1], encryption=pikepdf.Encryption(owner="owner", user=""))
    monkeypatch.setattr(core, "_run_qpdf", bad_encrypt)
    output = tmp_path / "result.pdf"
    with pytest.raises(WatermarkError, match="verification"):
        personalize(source, output, Options(customer="Acme", owner_password="owner"))
    assert not output.exists()


def test_no_hardlink_filesystem_fallback(source, tmp_path, monkeypatch):
    from pdf_watermark import core
    def unsupported(*args):
        raise OSError("Hard links unavailable")
    monkeypatch.setattr(core.os, "link", unsupported)
    output = tmp_path / "result.pdf"
    personalize(source, output, Options(customer="Acme"))
    assert output.is_file()


def test_long_customer_and_custom_header_fit(source, tmp_path):
    customer = "International Customer Corporation - European Division"
    output = tmp_path / "long-name.pdf"
    personalize(source, output, Options(customer=customer, header="Confidential - Customer review"))
    reader = PdfReader(output)
    assert all(customer in page.extract_text() for page in reader.pages)
    assert all("Confidential - Customer review" in page.extract_text() for page in reader.pages)


def test_decorations_are_marked_as_accessibility_artifacts(source, tmp_path):
    output = tmp_path / "tagged-overlay.pdf"
    personalize(source, output, Options(customer="Acme"))
    with pikepdf.open(output) as pdf:
        for page in pdf.pages:
            overlays = [obj for obj in page.Resources.XObject.values()
                        if obj.get("/Subtype") == pikepdf.Name.Form]
            assert overlays
            assert any(b"/Artifact BMC" in obj.read_bytes() and b"EMC" in obj.read_bytes()
                       for obj in overlays)


def test_output_race_never_overwrites_new_file(source, tmp_path, monkeypatch):
    from pdf_watermark import core
    output = tmp_path / "result.pdf"
    real_verify = core._verify
    def concurrent_writer(*args):
        real_verify(*args)
        output.write_bytes(b"another process created this")
    monkeypatch.setattr(core, "_verify", concurrent_writer)
    with pytest.raises(WatermarkError, match="already exists"):
        personalize(source, output, Options(customer="Acme"))
    assert output.read_bytes() == b"another process created this"


@pytest.mark.parametrize("form_kind", ["empty-fields", "no-fields", "empty-perms"])
def test_empty_form_containers_are_static_inputs(source, tmp_path, form_kind):
    adjusted = tmp_path / "exported-template.pdf"
    with pikepdf.open(source) as pdf:
        if form_kind == "empty-fields":
            pdf.Root.AcroForm = pikepdf.Dictionary(
                Fields=pikepdf.Array(), DA="/Helv 0 Tf 0 g", DR=pikepdf.Dictionary())
        elif form_kind == "no-fields":
            pdf.Root.AcroForm = pikepdf.Dictionary(DR=pikepdf.Dictionary())
        else:
            pdf.Root.Perms = pikepdf.Dictionary()
        pdf.save(adjusted)
    output = tmp_path / "result.pdf"
    result = personalize(adjusted, output, Options(customer="Acme"))
    assert result.pages == 2
    assert "Searchable original text" in PdfReader(output).pages[0].extract_text()


@pytest.mark.parametrize("kind", ["widget", "xfa", "signature", "timestamp", "invalid-fields"])
def test_real_form_or_signature_markers_still_rejected(source, tmp_path, kind):
    adjusted = tmp_path / "interactive.pdf"
    with pikepdf.open(source) as pdf:
        if kind == "widget":
            widget = pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget,
                Rect=pikepdf.Array([10, 10, 100, 30]), FT=pikepdf.Name.Tx, T="Orphan field"))
            pdf.pages[0].Annots.append(widget)
            # Keep a valid form tree while also checking the widget safeguard.
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([widget]))
        elif kind in ("signature", "timestamp"):
            signature = pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.Sig if kind == "signature" else pikepdf.Name("/DocTimeStamp")))
            field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Signature", V=signature))
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([field]))
        elif kind == "xfa":
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array(), XFA=pdf.make_stream(b"<xfa/>"))
        else:
            pdf.Root.AcroForm = pikepdf.Dictionary(Fields="invalid")
        pdf.save(adjusted)
    output = tmp_path / "result.pdf"
    with pytest.raises(WatermarkError):
        personalize(adjusted, output, Options(customer="Acme"))
    assert not output.exists()


@pytest.mark.parametrize("owner", ["-secret", "--secret", "@secret"])
def test_owner_passwords_that_look_like_arguments(source, tmp_path, owner):
    output = tmp_path / "result.pdf"
    personalize(source, output, Options(customer="Acme", owner_password=owner))
    with pikepdf.open(output, password=owner) as pdf:
        assert pdf.owner_password_matched


@pytest.mark.parametrize("width,header", [
    (595, "Prepared exclusively for Bank of Ireland"),
    (792, "Prepared exclusively for Bank of Ireland"),
    (595, "Prepared exclusively for International Customer Corporation"),
])
def test_three_part_header_alignment_and_spacing(width, header):
    from pdf_watermark.core import _load_font, _overlay
    from reportlab.pdfbase import pdfmetrics
    font = _load_font(None, ("Customer", header))
    reader = PdfReader(_overlay(width, 842, "Customer", header, font, 0.16))
    positions = {}
    def collect(text, cm, tm, font_dict, size):
        if text.strip() in ("Under NDA", header, "Not for redistribution"):
            positions[text.strip()] = (tm[4], tm[5], size)
    reader.pages[0].extract_text(visitor_text=collect)
    assert len(positions) == 3
    left, center, right = (positions[label] for label in ("Under NDA", header, "Not for redistribution"))
    assert left[1] == center[1] == right[1] == pytest.approx(856)
    assert left[2] == center[2] == right[2]
    size = center[2]
    text_width = lambda text: pdfmetrics.stringWidth(text, font, size)
    assert left[0] == pytest.approx(24)
    assert center[0] + text_width(header) / 2 == pytest.approx(width / 2)
    assert right[0] + text_width("Not for redistribution") == pytest.approx(width - 24)
    assert left[0] + text_width("Under NDA") + 12 <= center[0] + 0.001
    assert center[0] + text_width(header) + 12 <= right[0] + 0.001


def test_new_random_encryption_key_even_with_same_owner_password(source, tmp_path):
    keys = []
    for i in range(2):
        output = tmp_path / f"copy-{i}.pdf"
        personalize(source, output, Options(customer="Acme", owner_password="same-owner-password"))
        with pikepdf.open(output, password="same-owner-password") as pdf:
            keys.append(pdf.encryption.encryption_key)
    assert len(keys[0]) == len(keys[1]) == 32
    assert keys[0] != keys[1]
