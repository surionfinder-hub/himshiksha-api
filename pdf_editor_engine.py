"""
HimShiksha - PDF Page Editor Engine
Executes server-side page reordering, per-page rotation, deletion, merging,
and validates output structure prior to transmission.
"""

import io
import json
from typing import List, Dict, Any, Optional

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


class PDFEditorEngine:
    def edit_pages(
        self,
        primary_pdf_bytes: bytes,
        page_operations_json: str,
        additional_pdf_bytes_list: Optional[List[bytes]] = None
    ) -> bytes:
        """
        page_operations format:
        [
          { "source_doc": 0, "page_index": 0, "rotate": 90 },
          { "source_doc": 0, "page_index": 2, "rotate": 0 },
          { "source_doc": 1, "page_index": 0, "rotate": 0 }
        ]
        """
        try:
            ops = json.loads(page_operations_json)
        except Exception:
            ops = []

        # Load primary doc
        docs = [pymupdf.open(stream=primary_pdf_bytes, filetype="pdf")]

        # Load additional docs if provided
        if additional_pdf_bytes_list:
            for b in additional_pdf_bytes_list:
                docs.append(pymupdf.open(stream=b, filetype="pdf"))

        out_doc = pymupdf.open()

        if ops:
            for op in ops:
                doc_idx = int(op.get("source_doc", 0))
                p_idx = int(op.get("page_index", 0))
                rot_delta = int(op.get("rotate", op.get("rotation", 0)))

                if 0 <= doc_idx < len(docs):
                    src_doc = docs[doc_idx]
                    if 0 <= p_idx < len(src_doc):
                        out_doc.insert_pdf(src_doc, from_page=p_idx, to_page=p_idx)
                        if rot_delta != 0:
                            last_page = out_doc[-1]
                            last_page.set_rotation((last_page.rotation + rot_delta) % 360)
        else:
            # If no ops provided, copy all pages from all docs sequentially
            for d in docs:
                out_doc.insert_pdf(d)

        # Close all source docs
        for d in docs:
            d.close()

        # Validation
        if len(out_doc) == 0:
            out_doc.close()
            raise ValueError("Edited PDF document resulted in 0 pages.")

        out_buf = io.BytesIO()
        out_doc.save(out_buf, garbage=3, deflate=True)
        out_doc.close()
        out_bytes = out_buf.getvalue()

        # Verify output is valid PDF
        verify_doc = pymupdf.open(stream=out_bytes, filetype="pdf")
        if not verify_doc.is_pdf or len(verify_doc) == 0:
            verify_doc.close()
            raise ValueError("Output validation failed: Corrupted PDF generated.")
        verify_doc.close()

        return out_bytes


pdf_editor_engine = PDFEditorEngine()
