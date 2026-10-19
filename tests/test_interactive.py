from pathlib import Path
import shutil

from pypdf import PdfReader
import pytest
from reportlab.pdfgen import canvas

from pdf_watermark import interactive
from pdf_watermark.cli import main


@pytest.fixture
def portable(tmp_path, monkeypatch):
    root = tmp_path / "Portable App"
    (root / "working" / "template").mkdir(parents=True)
    monkeypatch.setattr(interactive, "application_directory", lambda: root)
    monkeypatch.delenv("PDF_WATERMARK_TEMPLATE", raising=False)
    monkeypatch.delenv("PDF_WATERMARK_OUTPUT_DIR", raising=False)
    return root


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "test-template.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(595, 842))
    pdf.drawString(40, 400, "Original test content")
    pdf.save()
    return path


def answers(monkeypatch, values):
    values = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(values))


def test_default_workflow_from_unrelated_directory(portable, template, tmp_path, monkeypatch):
    shutil.copy2(template, portable / "working" / "template" / "Original.PDF")
    monkeypatch.chdir(tmp_path)
    answers(monkeypatch, [" ", "Bank of Ireland"])
    assert main(["--interactive"]) == 0
    outputs = list((portable / "working" / "output").glob("Customer_Copy_Bank-of-Ireland_*.pdf"))
    assert len(outputs) == 1
    assert "Prepared exclusively for Bank of Ireland" in PdfReader(outputs[0]).pages[0].extract_text()


def test_environment_overrides_with_relative_paths(portable, template, monkeypatch):
    shutil.copy2(template, portable / "External Template.pdf")
    monkeypatch.setenv("PDF_WATERMARK_TEMPLATE", "External Template.pdf")
    monkeypatch.setenv("PDF_WATERMARK_OUTPUT_DIR", "Customer Copies")
    answers(monkeypatch, ["Müller / .. & Co."])
    assert main(["--interactive"]) == 0
    outputs = list((portable / "Customer Copies").glob("*.pdf"))
    assert len(outputs) == 1
    assert outputs[0].name.startswith("Customer_Copy_Muller-Co_")


def test_explicit_arguments_override_environment(portable, template, monkeypatch):
    monkeypatch.setenv("PDF_WATERMARK_TEMPLATE", "does-not-exist.pdf")
    monkeypatch.setenv("PDF_WATERMARK_OUTPUT_DIR", "unused")
    output = portable / "Explicit Folder" / "result.pdf"
    assert main(["--interactive", str(template), "--customer", "Acme", "--output", str(output)]) == 0
    assert output.exists()
    assert not (portable / "unused").exists()


def test_multiple_templates_offer_choice(portable, template, monkeypatch, capsys):
    folder = portable / "working" / "template"
    shutil.copy2(template, folder / "A.pdf")
    shutil.copy2(template, folder / "B.pdf")
    answers(monkeypatch, ["wrong", "0", "3", "2", "Acme"])
    source, output, customer = interactive.collect_inputs(None, None, None)
    assert source == folder / "B.pdf"
    assert customer == "Acme"
    text = capsys.readouterr().out
    assert "1. A.pdf" in text and "2. B.pdf" in text
    assert output.parent == portable / "working" / "output"


def test_missing_template_has_actionable_error(portable, capsys):
    assert main(["--interactive"]) == 1
    text = capsys.readouterr().err
    assert "PDF_WATERMARK_TEMPLATE" in text and "working" in text


def test_invalid_override_does_not_silently_use_other_template(portable, template, monkeypatch, capsys):
    shutil.copy2(template, portable / "working" / "template" / "Default.pdf")
    monkeypatch.setenv("PDF_WATERMARK_TEMPLATE", "missing.pdf")
    assert main(["--interactive"]) == 1
    assert "Template PDF does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_cancel_leaves_no_output(portable, template, monkeypatch, exception):
    shutil.copy2(template, portable / "working" / "template" / "Default.pdf")
    def stop(prompt):
        raise exception
    monkeypatch.setattr("builtins.input", stop)
    assert main(["--interactive"]) == 130
    assert not (portable / "working" / "output").exists()


def test_output_folder_failure_is_actionable(portable, template, monkeypatch, capsys):
    shutil.copy2(template, portable / "working" / "template" / "Default.pdf")
    (portable / "blocked").write_text("existing file")
    monkeypatch.setenv("PDF_WATERMARK_OUTPUT_DIR", "blocked")
    answers(monkeypatch, ["Acme"])
    assert main(["--interactive"]) == 1
    assert "Could not create the output folder" in capsys.readouterr().err


def test_interactive_still_refuses_existing_output(portable, template):
    output = portable / "existing.pdf"
    output.write_bytes(b"keep this")
    assert main(["--interactive", str(template), "--customer", "Acme", "--output", str(output)]) == 1
    assert output.read_bytes() == b"keep this"


def test_normal_cli_keeps_required_arguments():
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
