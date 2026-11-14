"""
HimShiksha API - QR Scan & Verification Service
Decodes uploaded QR code images using OpenCV `cv2.QRCodeDetector()`.
Computes fidelity scores, detects polygon boundaries, and verifies payloads against expected values.
"""

import io
import difflib
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import cv2
from schemas.qr_schemas import QRScanTestResponse


def scan_and_verify_qr(
    image_bytes: bytes,
    expected_text: Optional[str] = None
) -> QRScanTestResponse:
    """
    Decodes a QR code from image bytes using OpenCV and verifies against expected text.

    :param image_bytes: Raw binary bytes of the uploaded image file.
    :param expected_text: Optional string to verify the decoded payload against.
    :return: QRScanTestResponse object with fidelity metrics.
    """
    if not image_bytes:
        return QRScanTestResponse(
            success=False,
            decoded_text="",
            expected_text=expected_text,
            matches_expected=False if expected_text else None,
            fidelity_score=0.0,
            points=None,
            message="No image data received for scanning."
        )

    # 1. Decode byte buffer into OpenCV image
    np_buf = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)

    if img is None:
        return QRScanTestResponse(
            success=False,
            decoded_text="",
            expected_text=expected_text,
            matches_expected=False if expected_text else None,
            fidelity_score=0.0,
            points=None,
            message="Uploaded file could not be parsed as a valid image."
        )

    # 2. Multi-pass detection to maximize scan success (handling low contrast, camera blur)
    decoded_text, points = _detect_and_decode_multipass(img)

    # 3. Format points into serializable list
    points_list: Optional[List[List[float]]] = None
    if points is not None and len(points) > 0:
        pts = points.reshape(-1, 2)
        points_list = [[float(round(p[0], 2)), float(round(p[1], 2))] for p in pts]

    # 4. Check if QR code was successfully decoded
    if not decoded_text:
        # Detected corners but couldn't decode, or nothing detected
        has_detection = (points_list is not None and len(points_list) >= 4)
        msg = (
            "QR pattern boundary detected, but data modules could not be reliably decoded (scratched or low error correction)."
            if has_detection else
            "No valid QR code pattern detected in the image."
        )
        return QRScanTestResponse(
            success=False,
            decoded_text="",
            expected_text=expected_text,
            matches_expected=False if expected_text else None,
            fidelity_score=0.0,
            points=points_list,
            message=msg
        )

    # 5. Calculate fidelity score and verify match
    success = True
    decoded_clean = decoded_text.strip()

    if expected_text is not None and len(expected_text.strip()) > 0:
        expected_clean = expected_text.strip()
        matches = (decoded_clean == expected_clean)
        # Compute sequence similarity ratio
        similarity = difflib.SequenceMatcher(None, decoded_clean, expected_clean).ratio()
        fidelity_score = 1.0 if matches else round(float(similarity), 4)

        if matches:
            message = "QR code verified successfully: payload perfectly matches expected text."
        else:
            message = f"QR code decoded, but payload differs from expected text ({int(fidelity_score * 100)}% match)."

        return QRScanTestResponse(
            success=True,
            decoded_text=decoded_text,
            expected_text=expected_text,
            matches_expected=matches,
            fidelity_score=fidelity_score,
            points=points_list,
            message=message
        )
    else:
        # No expected text provided: fidelity is 1.0 if decoded successfully
        return QRScanTestResponse(
            success=True,
            decoded_text=decoded_text,
            expected_text=None,
            matches_expected=None,
            fidelity_score=1.0,
            points=points_list,
            message=f"QR code decoded successfully ({len(decoded_text)} chars)."
        )


def _detect_and_decode_multipass(img: np.ndarray) -> Tuple[str, Optional[np.ndarray]]:
    """
    Attempts OpenCV QR detection across multiple image representations:
    1. Direct BGR
    2. Rescaled BGR (if image is huge, e.g. > 1600px)
    3. Grayscale
    4. Otsu binary thresholding
    5. Adaptive thresholding
    """
    detector = cv2.QRCodeDetector()

    # Pass 1: Direct BGR
    text, pts, _ = detector.detectAndDecode(img)
    if text:
        return text, pts

    # Pass 2: High-res downscale (phone camera photos)
    h, w = img.shape[:2]
    if max(h, w) > 1600:
        scale = 1200.0 / max(h, w)
        scaled_img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        t_scaled, p_scaled, _ = detector.detectAndDecode(scaled_img)
        if t_scaled:
            if p_scaled is not None:
                p_scaled = p_scaled / scale
            return t_scaled, p_scaled

    # Pass 3: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    text_gray, pts_gray, _ = detector.detectAndDecode(gray)
    if text_gray:
        return text_gray, pts_gray

    # Pass 4: Otsu threshold
    _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text_otsu, pts_otsu, _ = detector.detectAndDecode(thresh_otsu)
    if text_otsu:
        return text_otsu, pts_otsu

    # Pass 5: Inverted Otsu (for light QR codes on dark backgrounds)
    thresh_inv = cv2.bitwise_not(thresh_otsu)
    text_inv, pts_inv, _ = detector.detectAndDecode(thresh_inv)
    if text_inv:
        return text_inv, pts_inv

    # Return whatever points were detected if any
    return "", pts if pts is not None else pts_gray
