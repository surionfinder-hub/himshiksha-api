"""
HimShiksha API - Office & Spreadsheets Service
Handles Word (.docx), Excel (.xlsx, .xls), and CSV conversions.
"""

from fastapi import HTTPException
from office_engine import OfficeEngine

office_engine = OfficeEngine()


def convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Convert DOCX file bytes to PDF bytes."""
    return office_engine.docx_to_pdf(docx_bytes)


def extract_docx_to_txt_str(docx_bytes: bytes) -> str:
    """Extract clean text from DOCX."""
    return office_engine.docx_to_txt(docx_bytes)


def convert_xlsx_to_pdf_bytes(xlsx_bytes: bytes) -> bytes:
    """Convert Excel spreadsheet to PDF."""
    return office_engine.xlsx_to_pdf(xlsx_bytes)


def convert_xlsx_to_csv_str(xlsx_bytes: bytes) -> str:
    """Convert Excel spreadsheet to CSV text."""
    return office_engine.xlsx_to_csv(xlsx_bytes)


def convert_csv_to_xlsx_bytes(csv_text: str) -> bytes:
    """Convert CSV text into formatted Excel (.xlsx) workbook."""
    return office_engine.csv_to_xlsx(csv_text)
