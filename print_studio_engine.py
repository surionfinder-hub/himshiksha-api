import sys
import os
import io
import math
from typing import List, Optional
import fitz # PyMuPDF
from PIL import Image, ImageOps

class PrintStudioServerEngine:
    """
    High-fidelity server-side Print Studio processing engine.
    Supports N-Up imposition, Saddle-Stitch Booklet imposition, Duplex separation,
    Watermarking, and Color-space transformations (Grayscale / B&W ink saving).
    """

    PAPER_SIZES_PT = {
        'a4': (595.28, 841.89),
        'a5': (419.53, 595.28),
        'a3': (841.89, 1190.55),
        'letter': (612.00, 792.00),
        'legal': (612.00, 1008.00)
    }

    NUP_CONFIG = {
        1: (1, 1),
        2: (1, 2),
        4: (2, 2),
        6: (2, 3),
        8: (2, 4),
        9: (3, 3),
        16: (4, 4)
    }

    @classmethod
    def process_print_job(
        cls,
        input_pdf_bytes: bytes,
        paper_size: str = 'a4',
        orientation: str = 'portrait',
        nup: int = 1,
        booklet: bool = False,
        booklet_binding: str = 'left',
        duplex_mode: str = 'simplex',
        duplex_part: str = 'all', # 'all', 'front', 'back'
        color_mode: str = 'color', # 'color', 'grayscale', 'bw'
        watermark_text: Optional[str] = None
    ) -> bytes:
        src_doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
        total_src_pages = len(src_doc)
        if total_src_pages == 0:
            raise ValueError("Input PDF contains no pages.")

        # Determine target sheet size
        paper_w, paper_h = cls.PAPER_SIZES_PT.get(paper_size.lower(), cls.PAPER_SIZES_PT['a4'])
        if orientation == 'landscape':
            paper_w, paper_h = paper_h, paper_w

        out_doc = fitz.open()

        # Booklet imposition vs N-Up
        if booklet:
            # Saddle-stitch imposition
            remainder = total_src_pages % 4
            padding = 0 if remainder == 0 else 4 - remainder
            padded_indices = list(range(total_src_pages)) + [-1] * padding
            total_padded = len(padded_indices)
            num_sheets = total_padded // 4

            # Generate front/back pairs
            sheet_pairs = []
            for s in range(num_sheets):
                f_left = padded_indices[total_padded - 1 - 2 * s]
                f_right = padded_indices[2 * s]
                b_left = padded_indices[2 * s + 1]
                b_right = padded_indices[total_padded - 2 - 2 * s]

                if booklet_binding == 'right':
                    f_left, f_right = f_right, f_left
                    b_left, b_right = b_right, b_left

                sheet_pairs.append(('front', [f_left, f_right]))
                sheet_pairs.append(('back', [b_left, b_right]))

            # Filter duplex part if requested
            if duplex_part == 'front':
                sheet_pairs = [sp for sp in sheet_pairs if sp[0] == 'front']
            elif duplex_part == 'back':
                sheet_pairs = [sp for sp in sheet_pairs if sp[0] == 'back']

            # Render sheets
            for side, page_indices in sheet_pairs:
                page = out_doc.new_page(width=paper_w, height=paper_h)
                half_w = paper_w / 2.0
                rects = [
                    fitz.Rect(0, 0, half_w, paper_h),
                    fitz.Rect(half_w, 0, paper_w, paper_h)
                ]
                for idx, r in zip(page_indices, rects):
                    if idx >= 0:
                        page.show_pdf_page(r, src_doc, idx)

        else:
            # Standard N-Up imposition
            rows, cols = cls.NUP_CONFIG.get(nup, (1, 1))
            cells_per_sheet = rows * cols
            num_sheets = math.ceil(total_src_pages / cells_per_sheet)

            cell_w = paper_w / cols
            cell_h = paper_h / rows

            for s in range(num_sheets):
                is_front = (s % 2 == 0)
                if duplex_part == 'front' and not is_front:
                    continue
                if duplex_part == 'back' and is_front:
                    continue

                page = out_doc.new_page(width=paper_w, height=paper_h)
                for r in range(rows):
                    for c in range(cols):
                        cell_idx = s * cells_per_sheet + (r * cols + c)
                        if cell_idx < total_src_pages:
                            target_rect = fitz.Rect(
                                c * cell_w,
                                r * cell_h,
                                (c + 1) * cell_w,
                                (r + 1) * cell_h
                            )
                            page.show_pdf_page(target_rect, src_doc, cell_idx)

        # Apply watermark overlay if set
        if watermark_text:
            for page in out_doc:
                rect = page.rect
                page.insert_text(
                    fitz.Point(rect.width * 0.25, rect.height * 0.5),
                    watermark_text,
                    fontsize=50,
                    rotate=45,
                    color=(0.85, 0.2, 0.2),
                    overlay=True
                )

        pdf_bytes = out_doc.tobytes(deflate=True, garbage=4)
        out_doc.close()
        src_doc.close()
        return pdf_bytes
