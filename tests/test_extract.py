import io

import docx

from deepl_translator.extract import extract_text


def test_docx_keeps_table_in_document_order():
    doc = docx.Document()
    doc.add_paragraph("Before table.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Value"
    doc.add_paragraph("After table.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    assert extract_text(buf, filename="x.docx") == "Before table.\n\nName | Value\n\nAfter table."


def test_clean_pdf_glyphs_removes_leaders_and_restores_decimal():
    from deepl_translator.extract import _clean_pdf_glyphs

    assert _clean_pdf_glyphs("Introduction ����4") == "Introduction  4"
    assert _clean_pdf_glyphs("Seattle \x08\x08\x08\x08266") == "Seattle  266"
    assert _clean_pdf_glyphs("Anarchy 2�0 game") == "Anarchy 2.0 game"
    assert _clean_pdf_glyphs(" Item\x08 one\n\tnext") == " Item one\n\tnext"
