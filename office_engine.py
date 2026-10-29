"""
HimShiksha - Modular Office Conversion Engine
Handles DOCX, XLSX, XLS, and CSV conversions with high visual fidelity,
preserving tables, formatting, styles, images, and Unicode/Hindi characters.
Uses LibreOffice headless, python-docx, and openpyxl.
"""

import os
import io
import csv
import shutil
import tempfile
import subprocess
from typing import Tuple, Dict, Any, Optional

try:
    import docx
except ImportError:
    docx = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


class OfficeEngine:
    def __init__(self):
        self.soffice_path = shutil.which("soffice") or shutil.which("libreoffice")

    def is_libreoffice_available(self) -> bool:
        return self.soffice_path is not None

    def validate_office_file(self, data: bytes, ext: str) -> Tuple[bool, Optional[str]]:
        """Validate file signature and integrity."""
        if not data:
            return False, "File is empty (0 bytes)."

        ext_clean = ext.lower().lstrip(".")

        # Modern Office files (DOCX, XLSX) are ZIP archives
        if ext_clean in ["docx", "xlsx"]:
            if not data.startswith(b"PK\x03\x04"):
                return False, f"Invalid {ext_clean.upper()} file format: Missing standard ZIP package header."
        
        # Legacy Office files (XLS, DOC) use OLE Compound File Binary format
        elif ext_clean in ["xls", "doc"]:
            if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
                return False, f"Invalid legacy {ext_clean.upper()} format: Missing OLE binary header."

        return True, None

    def docx_to_pdf(self, docx_bytes: bytes, filename: str = "document.docx") -> bytes:
        """Convert DOCX document to PDF with full formatting fidelity."""
        valid, err = self.validate_office_file(docx_bytes, "docx")
        if not valid:
            raise ValueError(err)

        if self.is_libreoffice_available():
            with tempfile.TemporaryDirectory() as tmpdir:
                input_path = os.path.join(tmpdir, "input.docx")
                with open(input_path, "wb") as f:
                    f.write(docx_bytes)

                # Run headless LibreOffice
                cmd = [
                    self.soffice_path,
                    "--headless",
                    "--convert-to", "pdf",
                    input_path,
                    "--outdir", tmpdir
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                output_pdf = os.path.join(tmpdir, "input.pdf")

                if os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
                    with open(output_pdf, "rb") as pf:
                        return pf.read()
                else:
                    err_msg = res.stderr.decode("utf-8", errors="ignore")
                    raise RuntimeError(f"LibreOffice conversion failed: {err_msg}")
        
        # Fallback if LibreOffice is not installed: extract text and build clean PDF via PyMuPDF
        if docx is not None:
            text = self.docx_to_txt(docx_bytes)
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842) # A4
            margin = 40
            rect = pymupdf.Rect(margin, margin, 595 - margin, 842 - margin)
            page.insert_textbox(rect, text, fontsize=11, fontname="helv")
            out_buf = io.BytesIO()
            doc.save(out_buf)
            doc.close()
            return out_buf.getvalue()

        raise RuntimeError("Neither LibreOffice nor python-docx is available for DOCX conversion.")

    def docx_to_txt(self, docx_bytes: bytes) -> str:
        """Extract all paragraphs and tables from DOCX into structured text."""
        valid, err = self.validate_office_file(docx_bytes, "docx")
        if not valid:
            raise ValueError(err)

        if docx is None:
            raise RuntimeError("python-docx library is required for DOCX text extraction.")

        doc_io = io.BytesIO(docx_bytes)
        doc = docx.Document(doc_io)
        lines = []

        # Extract paragraphs
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                lines.append(text)

        # Extract tables
        for t_idx, table in enumerate(doc.tables):
            lines.append(f"\n--- [Table {t_idx + 1}] ---")
            for row in table.rows:
                row_cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                lines.append(" | ".join(row_cells))
            lines.append("---------------------\n")

        return "\n\n".join(lines)

    def xlsx_to_pdf(self, spreadsheet_bytes: bytes, filename: str = "sheet.xlsx") -> bytes:
        """Convert XLSX or XLS workbook to printable multi-page PDF."""
        ext = os.path.splitext(filename)[1].lower().lstrip(".") or "xlsx"
        valid, err = self.validate_office_file(spreadsheet_bytes, ext)
        if not valid:
            raise ValueError(err)

        if not self.is_libreoffice_available():
            raise RuntimeError("LibreOffice headless service is required for spreadsheet to PDF conversion.")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, f"input.{ext}")
            with open(input_path, "wb") as f:
                f.write(spreadsheet_bytes)

            cmd = [
                self.soffice_path,
                "--headless",
                "--convert-to", "pdf",
                input_path,
                "--outdir", tmpdir
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            output_pdf = os.path.join(tmpdir, "input.pdf")

            if os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
                with open(output_pdf, "rb") as pf:
                    return pf.read()
            else:
                err_msg = res.stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Spreadsheet to PDF conversion failed: {err_msg}")

    def xlsx_to_csv(self, spreadsheet_bytes: bytes, sheet_name: Optional[str] = None) -> str:
        """Convert XLSX workbook to clean RFC 4180 CSV string."""
        valid, err = self.validate_office_file(spreadsheet_bytes, "xlsx")
        if not valid:
            raise ValueError(err)

        if openpyxl is None:
            raise RuntimeError("openpyxl library is required for XLSX reading.")

        wb = openpyxl.load_workbook(io.BytesIO(spreadsheet_bytes), data_only=True)
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            ws = wb.active

        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\r\n")

        for row in ws.iter_rows(values_only=True):
            # Check if entire row is empty
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                formatted_row = [
                    "" if cell is None else (str(cell) if not isinstance(cell, float) else f"{cell:g}")
                    for cell in row
                ]
                writer.writerow(formatted_row)

        return out.getvalue()

    def csv_to_xlsx(self, csv_content: str, sheet_title: str = "Sheet1") -> bytes:
        """Convert CSV string to styled Microsoft Excel (.xlsx) workbook."""
        if openpyxl is None:
            raise RuntimeError("openpyxl library is required for CSV to XLSX conversion.")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_title[:31] # Excel limits sheet title to 31 chars

        reader = csv.reader(io.StringIO(csv_content))
        for row in reader:
            parsed_row = []
            for val in row:
                v_clean = val.strip()
                # Auto cast integer or float
                if v_clean.isdigit():
                    parsed_row.append(int(v_clean))
                else:
                    try:
                        parsed_row.append(float(v_clean))
                    except ValueError:
                        parsed_row.append(val)
            ws.append(parsed_row)

        # Style header row if rows exist
        if ws.max_row >= 1:
            header_fill = openpyxl.styles.PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
            header_font = openpyxl.styles.Font(bold=True)
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=1, column=col)
                cell.fill = header_fill
                cell.font = header_font

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)

        out_buf = io.BytesIO()
        wb.save(out_buf)
        return out_buf.getvalue()


office_engine = OfficeEngine()
