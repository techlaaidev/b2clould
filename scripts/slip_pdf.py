"""Render phiếu giao hàng KiotViet (HTML đã điền dữ liệu) -> PDF khổ A4.

Bộ chuyển HTML->PDF của Google Apps Script không có font Nhật và vỡ trang với
mẫu in KiotViet, nên Apps Script gửi HTML lên đây (POST /api/pdf/render) để
render bằng xhtml2pdf + font Noto Sans JP — ra đúng 1 trang / hóa đơn.
"""

import io
import re
from pathlib import Path

from lxml import html as lxml_html
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa
from xhtml2pdf.default import DEFAULT_FONT

_FONT_DIR = Path(__file__).resolve().parents[1] / "fonts"
FONT_PATH = _FONT_DIR / "NotoSansJP-Regular.ttf"
BOLD_FONT_PATH = _FONT_DIR / "NotoSansJP-Bold.ttf"
_font_ready = False


def _ensure_font() -> None:
    global _font_ready
    if _font_ready:
        return
    if FONT_PATH.exists():
        pdfmetrics.registerFont(TTFont("NotoJP", str(FONT_PATH)))
        bold = str(BOLD_FONT_PATH if BOLD_FONT_PATH.exists() else FONT_PATH)
        # Đăng ký cả bản ĐẬM để <strong>/<b> in đậm thật (thiếu thì tiêu đề
        # render bằng nét thường, nhìn "mờ" so với mẫu in gốc).
        pdfmetrics.registerFont(TTFont("NotoJP-Bold", bold))
        pdfmetrics.registerFontFamily(
            "NotoJP", normal="NotoJP", bold="NotoJP-Bold",
            italic="NotoJP", boldItalic="NotoJP-Bold",
        )
        DEFAULT_FONT["notojp"] = "NotoJP"
    _font_ready = True


_PAGE_CSS = (
    "<style>"
    "@page {size: A4; margin: 4mm 9mm;}"
    "body, div, td, p, span, strong {font-family: notojp;}"
    # Trình duyệt GỘP lề trên/dưới của 2 đoạn liền nhau (còn ~1em), engine PDF
    # thì cộng dồn (2em) làm phiếu giãn dài gấp đôi so với mẫu gốc — chỉnh lề
    # đoạn văn về ~1 nửa để khoảng cách giống hệt bản xem trước của KiotViet.
    "p {margin-top: 3px; margin-bottom: 3px;}"
    "</style>"
)

def _unwrap_single_cell_tables(html: str) -> str:
    """Bảng chỉ có 1 hàng × 1 ô -> <div> (hiển thị y hệt, nhưng cắt trang được).

    Engine PDF coi mỗi <tr> là một khối KHÔNG THỂ cắt giữa chừng; mẫu KiotViet
    bọc cả nửa dưới phiếu trong một <tr> khổng lồ nên khối đó bị đẩy nguyên
    sang trang sau. Mở bọc để nội dung chảy tự nhiên. Bảng nhiều ô (bảng sản
    phẩm, khối chữ + QR 2 cột) giữ nguyên.
    """
    try:
        root = lxml_html.fragment_fromstring(html, create_parent="div")
    except Exception:
        return html  # HTML lạ -> giữ nguyên, đừng làm hỏng
    changed = True
    while changed:
        changed = False
        for table in root.findall(".//table"):
            trs = table.xpath("./tbody/tr | ./tr")
            if len(trs) != 1:
                continue
            cells = trs[0].xpath("./td | ./th")
            if len(cells) != 1:
                continue
            cell = cells[0]
            div = lxml_html.Element("div")
            style = (table.get("style") or "") + ";" + (cell.get("style") or "")
            if style.strip(";"):
                div.set("style", style.strip(";"))
            div.text = cell.text
            for child in list(cell):
                div.append(child)
            table.getparent().replace(table, div)
            changed = True
    return lxml_html.tostring(root, encoding="unicode")


def sanitize_html(html: str) -> str:
    """Chỉ vá những gì engine PDF không hỗ trợ — GIỮ NGUYÊN cỡ chữ, khoảng
    cách, kích thước ảnh của mẫu in gốc (không nén, không chỉnh)."""
    # Bỏ vỏ boilerplate nếu mẫu được dán kèm khung file HTML của Apps Script
    # (<!DOCTYPE html><html><head>...</head><body>...) — tài liệu lồng tài liệu
    # làm xhtml2pdf dàn trang sai.
    html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.I)
    html = re.sub(r"<head[^>]*>[\s\S]*?</head>", "", html, flags=re.I)
    html = re.sub(r"</?(?:html|body)[^>]*>", "", html, flags=re.I)
    # MỌI khai báo font Arial (kể cả viết không dấu cách) -> font Nhật NotoJP.
    html = re.sub(r"font-family:\s*Arial[^;\"'}<]*", "font-family: notojp", html, flags=re.I)
    html = re.sub(r"height:\s*100%", "height:auto", html, flags=re.I)
    html = re.sub(r"position:\s*fixed", "position:static", html, flags=re.I)
    # Mẫu KiotViet cấm ngắt giữa <tr>, nhưng khối promo là MỘT <tr> khổng lồ
    # nên bị đẩy nguyên sang trang sau -> cho phép ngắt.
    html = re.sub(r"page-break-inside:\s*avoid", "page-break-inside: auto", html, flags=re.I)
    html = _unwrap_single_cell_tables(html)
    # xhtml2pdf bỏ qua float:right nên ảnh QR rơi về giữa trang — ép đoạn chứa
    # ảnh căn phải, và chú thích ("Google Maps"/"Scan to Register") ngay dưới
    # ảnh cũng căn phải theo (các <p> căn giữa khác giữ nguyên).
    html = re.sub(r"<p>(\s*<img)", r'<p style="text-align:right">\1', html, flags=re.I)
    html = re.sub(
        r'(<img[^>]*>\s*</p>\s*)<p style="text-align:center">',
        r'\1<p style="text-align:right">',
        html,
        flags=re.I,
    )
    return html


def render_pdf(html: str) -> bytes:
    """HTML (đã điền dữ liệu) -> bytes PDF. Raise RuntimeError khi render lỗi."""
    _ensure_font()
    source = _PAGE_CSS + sanitize_html(html)
    buffer = io.BytesIO()
    result = pisa.CreatePDF(source, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"Render PDF thất bại ({result.err} lỗi)")
    return buffer.getvalue()
