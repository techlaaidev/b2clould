import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz

from scripts.slip_pdf import FONT_PATH, render_pdf, sanitize_html


def test_font_file_bundled():
    # Font Nhật phải nằm trong repo để Render deploy kèm (chữ CJK không thành ô vuông).
    assert FONT_PATH.exists()


def test_sanitize_fixes_page_breaking_css():
    html = (
        '<img style="height:100%">'
        '<div style="position: fixed">x</div>'
        "<style>tr { page-break-inside: avoid; }</style>"
        "<p>&nbsp;</p>"
    )
    out = sanitize_html(html)
    assert "height:100%" not in out
    assert "fixed" not in out
    assert "avoid" not in out
    assert "<p>&nbsp;</p>" not in out


def test_render_japanese_single_page():
    html = (
        '<div style="font-family:Arial, sans-serif">'
        "<h1>納品書 STATEMENT OF DELIVERY</h1>"
        "<table><tr><td>商品名</td><td>iPhone 14 Promax 新品未使用品</td></tr></table>"
        "<p>当店でのご購入誠にありがとうございます。</p>"
        "</div>"
    )
    pdf_data = render_pdf(html)
    assert pdf_data.startswith(b"%PDF")
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    assert doc.page_count == 1
    text = doc[0].get_text()
    # Chữ Nhật phải render ra ký tự thật, không phải ô vuông/trống.
    assert "納品書" in text
