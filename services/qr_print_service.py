"""
HimShiksha API - High-Resolution QR Print Sheet Service
Generates print-ready PDFs with custom grid layouts (A4/Letter, Portrait/Landscape),
cutting guidelines, QR code imposition, and typography labels using ReportLab.
"""

import io
from typing import List, Optional
from PIL import Image
import qrcode
from reportlab.lib.pagesizes import A4, letter, landscape as rl_landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

from schemas.qr_schemas import QRPrintSheetItem
from services.qr_generation_service import parse_color, ERROR_CORRECTION_MAP


def generate_print_sheet_pdf(
    items: List[QRPrintSheetItem],
    paper_size: str = "A4",
    orientation: str = "portrait",
    rows: int = 4,
    cols: int = 3,
    margin_pt: float = 36.0,
    show_labels: bool = True,
    show_cut_lines: bool = True,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    error_correction: str = "M",
) -> bytes:
    """
    Generates a print-ready vector/raster PDF sheet containing a grid of QR codes.

    :param items: List of QRPrintSheetItem objects.
    :param paper_size: 'A4' or 'LETTER' (case-insensitive).
    :param orientation: 'portrait' or 'landscape'.
    :param rows: Number of grid rows per sheet (e.g. 4).
    :param cols: Number of grid columns per sheet (e.g. 3).
    :param margin_pt: Outer page margin in points (72 points = 1 inch).
    :param show_labels: Whether to print primary/secondary labels under QR codes.
    :param show_cut_lines: Whether to draw subtle dashed borders around cells.
    :param fill_color: QR module foreground color.
    :param back_color: Background color.
    :param error_correction: Error correction level ('L', 'M', 'Q', 'H').
    :return: Raw PDF file bytes.
    """
    if not items:
        raise ValueError("At least one QR item is required to generate a print sheet.")

    # 1. Resolve Paper Size & Orientation
    norm_paper = paper_size.upper().strip()
    base_size = letter if norm_paper in ["LETTER", "US_LETTER"] else A4

    norm_orient = orientation.lower().strip()
    if norm_orient == "landscape":
        page_size = rl_landscape(base_size)
    else:
        page_size = base_size

    page_width, page_height = page_size

    # Validate rows and columns
    rows = max(1, min(12, int(rows)))
    cols = max(1, min(8, int(cols)))
    items_per_page = rows * cols

    # Margin bounds
    margin = max(14.0, min(100.0, float(margin_pt)))
    usable_width = page_width - (2.0 * margin)
    usable_height = page_height - (2.0 * margin)

    cell_w = usable_width / float(cols)
    cell_h = usable_height / float(rows)

    # QR Error Correction
    ec_level = error_correction.upper().strip()
    qr_ec = ERROR_CORRECTION_MAP.get(ec_level, qrcode.constants.ERROR_CORRECT_M)

    clean_fill = parse_color(fill_color, "#000000")
    clean_back = parse_color(back_color, "#ffffff")
    if clean_back == "transparent":
        clean_back = "#ffffff"

    # 2. Setup ReportLab Canvas
    out_buf = io.BytesIO()
    c = canvas.Canvas(out_buf, pagesize=page_size)

    # 3. Render items
    for idx, item in enumerate(items):
        page_index = idx % items_per_page
        if idx > 0 and page_index == 0:
            c.showPage()

        r = page_index // cols
        col = page_index % cols

        x0 = margin + (col * cell_w)
        y0 = page_height - margin - ((r + 1) * cell_h)

        # Draw cell cut guidelines
        if show_cut_lines:
            c.saveState()
            c.setStrokeColor(colors.HexColor("#cbd5e1"))
            c.setLineWidth(0.5)
            c.setDash(2, 2)
            c.rect(x0, y0, cell_w, cell_h)
            c.restoreState()

        # Generate QR image for this item
        qr = qrcode.QRCode(
            version=None,
            error_correction=qr_ec,
            box_size=8,
            border=2
        )
        qr.add_data(item.content)
        qr.make(fit=True)
        qr_pil = qr.make_image(fill_color=clean_fill, back_color=clean_back).convert("RGB")

        qr_img_buf = io.BytesIO()
        qr_pil.save(qr_img_buf, format="PNG")
        qr_img_buf.seek(0)
        img_reader = ImageReader(qr_img_buf)

        # Typography & layout calculation
        label_text = item.label.strip() if item.label else None
        sublabel_text = item.sublabel.strip() if item.sublabel else None

        if show_labels and (label_text or sublabel_text):
            has_two_lines = bool(label_text and sublabel_text)
            label_zone_h = 28.0 if has_two_lines else 18.0
            max_qr_size = min(cell_w - 14.0, cell_h - label_zone_h - 14.0)
            qr_size = max(24.0, max_qr_size)

            qr_x = x0 + ((cell_w - qr_size) / 2.0)
            qr_y = y0 + label_zone_h + ((cell_h - label_zone_h - qr_size) / 2.0)
            c.drawImage(img_reader, qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True)

            center_x = x0 + (cell_w / 2.0)
            max_text_w = cell_w - 10.0

            if has_two_lines:
                # Primary bold label
                c.setFont("Helvetica-Bold", 8.5)
                c.setFillColor(colors.HexColor("#0f172a"))
                trunc_primary = _truncate_text(c, label_text, "Helvetica-Bold", 8.5, max_text_w)
                c.drawCentredString(center_x, y0 + 15.0, trunc_primary)

                # Secondary muted sublabel
                c.setFont("Helvetica", 7.0)
                c.setFillColor(colors.HexColor("#64748b"))
                trunc_sub = _truncate_text(c, sublabel_text, "Helvetica", 7.0, max_text_w)
                c.drawCentredString(center_x, y0 + 5.0, trunc_sub)
            elif label_text:
                c.setFont("Helvetica-Bold", 8.5)
                c.setFillColor(colors.HexColor("#0f172a"))
                trunc_primary = _truncate_text(c, label_text, "Helvetica-Bold", 8.5, max_text_w)
                c.drawCentredString(center_x, y0 + 7.0, trunc_primary)
            elif sublabel_text:
                c.setFont("Helvetica", 7.5)
                c.setFillColor(colors.HexColor("#475569"))
                trunc_sub = _truncate_text(c, sublabel_text, "Helvetica", 7.5, max_text_w)
                c.drawCentredString(center_x, y0 + 7.0, trunc_sub)
        else:
            # Full cell QR without text
            max_qr_size = min(cell_w - 14.0, cell_h - 14.0)
            qr_size = max(24.0, max_qr_size)
            qr_x = x0 + ((cell_w - qr_size) / 2.0)
            qr_y = y0 + ((cell_h - qr_size) / 2.0)
            c.drawImage(img_reader, qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True)

    c.showPage()
    c.save()

    out_buf.seek(0)
    return out_buf.getvalue()


def _truncate_text(c: canvas.Canvas, text: str, font_name: str, font_size: float, max_w: float) -> str:
    """Truncates text with ellipsis if it exceeds the specified maximum width."""
    if not text:
        return ""
    if c.stringWidth(text, font_name, font_size) <= max_w:
        return text

    ellipsis = "..."
    ellipsis_w = c.stringWidth(ellipsis, font_name, font_size)
    available_w = max_w - ellipsis_w
    if available_w <= 0:
        return ellipsis

    truncated = text
    while len(truncated) > 1 and c.stringWidth(truncated, font_name, font_size) > available_w:
        truncated = truncated[:-1]

    return truncated.rstrip() + ellipsis
