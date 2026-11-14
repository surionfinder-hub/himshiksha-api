"""
HimShiksha API - QR Studio Pydantic Schemas
Defines request and response validation models for QR generation, batch processing,
scan testing, and print sheet generation.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class QRErrorCorrection(str, Enum):
    L = "L"  # ~7% recovery
    M = "M"  # ~15% recovery
    Q = "Q"  # ~25% recovery
    H = "H"  # ~30% recovery


class QRFormat(str, Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    SVG = "svg"
    WEBP = "webp"


class QRGenerateRequest(BaseModel):
    """Payload model for server-side single QR generation."""
    content: str = Field(..., description="The raw data, URL, or text to encode inside the QR code.")
    error_correction: str = Field("M", description="Error correction level: L, M, Q, or H.")
    box_size: int = Field(10, ge=1, le=50, description="Size of each QR box/module in pixels.")
    border: int = Field(4, ge=0, le=20, description="White margin border width in modules.")
    fill_color: str = Field("#000000", description="Foreground/data module color (hex or CSS name).")
    back_color: str = Field("#ffffff", description="Background color (hex, CSS name, or transparent).")
    format: str = Field("png", description="Output export format: png, jpg, jpeg, svg, or webp.")
    size_px: Optional[int] = Field(None, ge=64, le=4096, description="Optional target square dimension in pixels.")
    logo_base64: Optional[str] = Field(None, description="Optional base64-encoded logo image to embed in center.")
    logo_size_ratio: float = Field(0.22, ge=0.10, le=0.30, description="Logo dimension as ratio of QR width.")
    badge_radius: int = Field(12, ge=0, le=48, description="Corner radius for the logo badge.")


class QRBatchItem(BaseModel):
    """Single item entry for batch QR processing."""
    name: Optional[str] = Field(None, description="Human readable label or product name.")
    type: Optional[str] = Field("text", description="Type identifier (url, text, wifi, vcard, email, etc.).")
    content: str = Field(..., description="Data/content string to encode.")
    filename: Optional[str] = Field(None, description="Preferred output filename (without extension).")


class QRBatchRequest(BaseModel):
    """Batch generation request payload."""
    items: List[QRBatchItem] = Field(..., description="List of items to generate QR codes for.")
    format: str = Field("png", description="Output export format: png, jpg, svg, or webp.")
    error_correction: str = Field("M", description="Error correction level: L, M, Q, or H.")
    box_size: int = Field(10, ge=1, le=40, description="Size of each QR module in pixels.")
    border: int = Field(4, ge=0, le=20, description="Quiet zone border in modules.")
    fill_color: str = Field("#000000", description="Foreground color.")
    back_color: str = Field("#ffffff", description="Background color.")
    size_px: Optional[int] = Field(512, ge=64, le=2048, description="Target dimension in pixels.")
    logo_base64: Optional[str] = Field(None, description="Optional common base64 logo to embed in each QR.")


class QRBatchManifestItem(BaseModel):
    """Single item record within batch ZIP manifest."""
    index: int
    name: str
    type: str
    content: str
    filename: str
    status: str
    error: Optional[str] = None


class QRBatchManifest(BaseModel):
    """Manifest summary stored inside generated ZIP archive."""
    total: int
    succeeded: int
    failed: int
    format: str
    generated_at: str
    items: List[QRBatchManifestItem]


class QRScanTestResponse(BaseModel):
    """Response model for OpenCV QR code detection & verification."""
    success: bool = Field(..., description="True if a QR code was detected and decoded.")
    decoded_text: str = Field("", description="Decoded payload string from the QR code.")
    expected_text: Optional[str] = Field(None, description="Expected text passed in for verification.")
    matches_expected: Optional[bool] = Field(None, description="True if decoded text strictly matches expected text.")
    fidelity_score: float = Field(0.0, ge=0.0, le=1.0, description="Fidelity score: 1.0 for perfect match, ratio for partial.")
    points: Optional[List[List[float]]] = Field(None, description="Bounding corner coordinates [[x,y], ...] of detected QR.")
    message: str = Field("", description="Human-readable status summary.")


class QRPrintSheetItem(BaseModel):
    """Single item to print on the printable PDF sheet."""
    content: str = Field(..., description="Data to encode in the QR code.")
    label: Optional[str] = Field(None, description="Primary bold label displayed under QR code.")
    sublabel: Optional[str] = Field(None, description="Secondary subtitle / metadata snippet.")


class QRPrintSheetRequest(BaseModel):
    """Configuration for high-resolution print-ready PDF sheet."""
    items: List[QRPrintSheetItem] = Field(..., description="Items to generate on printable sheet.")
    paper_size: str = Field("A4", description="Sheet paper standard: 'A4' or 'LETTER'.")
    orientation: str = Field("portrait", description="Orientation: 'portrait' or 'landscape'.")
    rows: int = Field(4, ge=1, le=12, description="Number of grid rows per page.")
    cols: int = Field(3, ge=1, le=8, description="Number of grid columns per page.")
    margin_pt: float = Field(36.0, ge=10.0, le=100.0, description="Outer sheet margins in points (1 in = 72 pt).")
    show_labels: bool = Field(True, description="Whether to render text labels below each QR code.")
    show_cut_lines: bool = Field(True, description="Whether to render subtle dashed cutting guidelines.")
    fill_color: str = Field("#000000", description="QR foreground color.")
    back_color: str = Field("#ffffff", description="Sheet & QR background color.")
    error_correction: str = Field("M", description="Error correction level: L, M, Q, or H.")
