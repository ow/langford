import pytest

from pipeline.ingestion.local_pdf_package import (
    build_pdf_package,
    package_for_prompt,
    range_text,
)
from pipeline.ingestion.local_context_extractor import package_needs_pdf_fallback


pytest.importorskip("fitz")


def _write_pdf(path, pages):
    import fitz

    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def test_build_pdf_package_extracts_page_text(tmp_path):
    pdf_path = tmp_path / "agenda.pdf"
    _write_pdf(
        pdf_path,
        [
            "Agenda Item 6.1 Staff Report\nRecommendation: That Council approve the permit. "
            "The report describes background, options, consultation, financial implications, "
            "and implementation next steps for the application.",
            "Appendix A\nThe property is 123 Example Road and the cost is $25,000. "
            "The attachment includes context, rationale, and supporting details.",
        ],
    )

    package = build_pdf_package(str(pdf_path))

    assert package.page_count == 2
    assert package.has_usable_text
    assert "Staff Report" in package.pages[0].text
    assert package.pages[0].quality.word_count > 0
    assert "123 Example Road" in range_text(package, 2, 2)


def test_package_for_prompt_includes_quality_and_pages(tmp_path):
    pdf_path = tmp_path / "minutes.pdf"
    _write_pdf(pdf_path, ["Minutes\nCouncil adopted Bylaw No. 1234."])

    package = build_pdf_package(str(pdf_path))
    prompt_text = package_for_prompt(package)

    assert "PDF: minutes.pdf" in prompt_text
    assert "--- PAGE 1" in prompt_text
    assert "quality=" in prompt_text
    assert "Bylaw No. 1234" in prompt_text


def test_package_needs_pdf_fallback_for_sparse_page(tmp_path):
    pdf_path = tmp_path / "blankish.pdf"
    _write_pdf(pdf_path, [""])

    package = build_pdf_package(str(pdf_path))

    assert package_needs_pdf_fallback(package, 1, 1) is True
