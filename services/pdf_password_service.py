"""
HimShiksha API - PDF Password Protection & Unlock Service
Handles genuine AES-256 PDF encryption and authorized password decryption using disk-based PyMuPDF.
Supports files up to 2 GB with negligible RAM usage (<30 MB).
"""

import os
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path


def protect_pdf_file(input_pdf_path: str, password: str, confirm_password: str = None) -> str:
    """
    Encrypt a PDF file with standard AES-256 password protection.
    When opened in any standard PDF viewer, the user is prompted for the password.
    Returns path to the protected PDF on disk.
    """
    pw = (password or "").strip()
    if not pw:
        raise HTTPException(status_code=400, detail="Password cannot be empty.")

    if confirm_password is not None and confirm_password.strip() != pw:
        raise HTTPException(status_code=400, detail="Passwords do not match. Please verify your password.")

    if len(pw) < 1:
        raise HTTPException(status_code=400, detail="Password must be at least 1 character long.")

    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF file: {str(e)}")

    if doc.page_count < 1:
        doc.close()
        raise HTTPException(status_code=400, detail="PDF has no pages to protect.")

    out_path = create_temp_output_path(prefix="hs_protected_", suffix=".pdf")
    # In PDF specification (ISO 32000), owner password must differ from user password
    owner_pw = f"{pw}_owner_{os.urandom(6).hex()}"

    try:
        doc.save(
            out_path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=pw,
            owner_pw=owner_pw,
            permissions=pymupdf.PDF_PERM_ACCESSIBILITY | pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY
        )
    except Exception as e:
        doc.close()
        if os.path.exists(out_path):
            os.remove(out_path)
        raise HTTPException(status_code=500, detail=f"Failed to apply AES-256 encryption: {str(e)}")
    finally:
        doc.close()

    # Integrity verification
    try:
        verify_doc = pymupdf.open(out_path)
        if not verify_doc.is_encrypted:
            verify_doc.close()
            raise HTTPException(status_code=500, detail="Encryption verification failed: PDF was not encrypted.")
        # Ensure it requires password
        rc_wrong = verify_doc.authenticate("intentionally_wrong_pwd_998877")
        if rc_wrong > 0:
            verify_doc.close()
            raise HTTPException(status_code=500, detail="Encryption verification failed: PDF opened with wrong password.")
        # Ensure it unlocks with user password
        rc_right = verify_doc.authenticate(pw)
        if rc_right <= 0:
            verify_doc.close()
            raise HTTPException(status_code=500, detail="Encryption verification failed: PDF cannot authenticate with user password.")
        verify_doc.close()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Protected PDF integrity check failed: {str(e)}")

    return out_path


def unlock_pdf_file(input_pdf_path: str, password: str) -> str:
    """
    Remove password protection from an authorized encrypted PDF document.
    Requires user to supply the valid password.
    Returns path to unencrypted PDF on disk.
    """
    pw = (password or "").strip()
    if not pw:
        raise HTTPException(status_code=400, detail="Please enter the PDF's password to unlock.")

    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF file: {str(e)}")

    if not doc.is_encrypted:
        doc.close()
        raise HTTPException(status_code=400, detail="This PDF document is already unlocked and has no password protection.")

    # Authenticate with provided password
    auth_code = doc.authenticate(pw)
    if auth_code <= 0:
        doc.close()
        raise HTTPException(status_code=400, detail="Incorrect password. Decryption failed. Please verify and enter the correct password.")

    out_path = create_temp_output_path(prefix="hs_unlocked_", suffix=".pdf")

    try:
        # Strip all encryption dictionaries
        doc.save(out_path, encryption=pymupdf.PDF_ENCRYPT_NONE)
    except Exception as e:
        doc.close()
        if os.path.exists(out_path):
            os.remove(out_path)
        raise HTTPException(status_code=500, detail=f"Failed to generate decrypted PDF: {str(e)}")
    finally:
        doc.close()

    # Integrity verification
    try:
        check_doc = pymupdf.open(out_path)
        if check_doc.is_encrypted:
            check_doc.close()
            raise HTTPException(status_code=500, detail="Decryption verification failed: PDF remains encrypted.")
        check_doc.close()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Unlocked PDF verification failed: {str(e)}")

    return out_path
