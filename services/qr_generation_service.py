"""
HimShiksha API - QR Code Generation Service
Modular, high-fidelity QR generation engine utilizing Python `qrcode` and `PIL` (Pillow).
Features:
- Standard Reed-Solomon Error Correction levels (L, M, Q, H).
- Custom foreground and background hex/RGB colors with transparency support.
- Embedded center logo with antialiased rounded badge and protective border.
- Vector SVG generation (pure vector paths + embedded SVG logos).
- High-resolution raster export (PNG, JPEG, WebP) with optional Lanczos dimension resampling.
"""

import io
import re
import base64
from typing import Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageColor
import qrcode
from qrcode.image.svg import SvgPathFillImage, ET

# Error correction mapping
ERROR_CORRECTION_MAP = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}

FORMAT_MIME_MAP = {
    "png": ("image/png", ".png"),
    "jpg": ("image/jpeg", ".jpg"),
    "jpeg": ("image/jpeg", ".jpg"),
    "webp": ("image/webp", ".webp"),
    "svg": ("image/svg+xml", ".svg"),
}


def parse_color(color_str: Optional[str], default: str = "#000000") -> str:
    """Normalize and validate a color string (hex or CSS name)."""
    if not color_str or not color_str.strip():
        return default
    c = color_str.strip()
    if c.lower() in ["transparent", "none"]:
        return "transparent"
    if not c.startswith("#") and len(c) in [3, 6, 8] and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return f"#{c}"
    return c


def create_svg_image_factory(fill_color: str, back_color: str):
    """
    Dynamically constructs an SvgPathFillImage subclass configured with custom
    fill and background colors.
    """
    is_transparent = (back_color == "transparent")

    class DynamicSvgFactory(SvgPathFillImage):
        background = None if is_transparent else back_color
        QR_PATH_STYLE = dict(SvgPathFillImage.QR_PATH_STYLE, fill=fill_color)

    return DynamicSvgFactory


def generate_qr_bytes(
    content: str,
    error_correction: str = "M",
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    export_format: str = "png",
    size_px: Optional[int] = None,
    logo_bytes: Optional[bytes] = None,
    logo_size_ratio: float = 0.22,
    badge_radius: int = 12,
) -> Tuple[bytes, str, str]:
    """
    Generates a high-fidelity QR code in memory and returns (output_bytes, mime_type, file_extension).

    :param content: Text or URL data to encode.
    :param error_correction: 'L', 'M', 'Q', or 'H'. Upgraded to 'Q' or 'H' if logo is embedded.
    :param box_size: Module pixel box size.
    :param border: Margin width in modules.
    :param fill_color: Hex color or CSS name for QR modules.
    :param back_color: Hex color or CSS name for background, or 'transparent'.
    :param export_format: 'png', 'jpg', 'jpeg', 'webp', or 'svg'.
    :param size_px: Optional dimension in pixels to resample output image.
    :param logo_bytes: Optional raw bytes of logo image to embed in center.
    :param logo_size_ratio: Ratio of logo width relative to total QR width (0.10 to 0.30).
    :param badge_radius: Corner curvature radius for the logo background badge.
    :return: (bytes, mime_type, extension)
    """
    if not content:
        raise ValueError("Content for QR code generation cannot be empty.")

    norm_format = export_format.lower().strip()
    if norm_format not in FORMAT_MIME_MAP:
        norm_format = "png"
    mime_type, ext = FORMAT_MIME_MAP[norm_format]

    # Validate / normalize error correction
    ec_level = error_correction.upper().strip()
    if ec_level not in ERROR_CORRECTION_MAP:
        ec_level = "M"

    # If a logo is embedded, enforce high error correction (Q or H) to preserve scannability
    if logo_bytes is not None and ec_level in ["L", "M"]:
        ec_level = "Q" if ec_level == "M" else "H"

    qr_ec = ERROR_CORRECTION_MAP[ec_level]
    clean_fill = parse_color(fill_color, "#000000")
    clean_back = parse_color(back_color, "#ffffff")

    # 1. Handle SVG Export
    if norm_format == "svg":
        return _generate_svg_qr(
            content=content,
            qr_ec=qr_ec,
            box_size=box_size,
            border=border,
            fill_color=clean_fill,
            back_color=clean_back,
            size_px=size_px,
            logo_bytes=logo_bytes,
            logo_size_ratio=logo_size_ratio,
            badge_radius=badge_radius
        ), mime_type, ext

    # 2. Handle Raster Formats (PNG, JPG, WEBP)
    return _generate_raster_qr(
        content=content,
        qr_ec=qr_ec,
        box_size=box_size,
        border=border,
        fill_color=clean_fill,
        back_color=clean_back,
        export_format=norm_format,
        size_px=size_px,
        logo_bytes=logo_bytes,
        logo_size_ratio=logo_size_ratio,
        badge_radius=badge_radius
    ), mime_type, ext


def _generate_raster_qr(
    content: str,
    qr_ec: int,
    box_size: int,
    border: int,
    fill_color: str,
    back_color: str,
    export_format: str,
    size_px: Optional[int],
    logo_bytes: Optional[bytes],
    logo_size_ratio: float,
    badge_radius: int,
) -> bytes:
    """Generates raster format (PNG, JPG, WEBP) using PIL."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qr_ec,
        box_size=box_size,
        border=border,
    )
    qr.add_data(content)
    qr.make(fit=True)

    is_transparent = (back_color == "transparent")
    # For transparent background in PNG/WEBP, initialize PIL with RGBA
    if is_transparent:
        pil_back = (255, 255, 255, 0)
    else:
        pil_back = back_color

    qr_pil = qr.make_image(fill_color=fill_color, back_color=pil_back)
    qr_img = qr_pil.convert("RGBA")

    # If logo is provided, embed with rounded badge
    if logo_bytes:
        qr_img = _embed_logo_on_image(
            base_img=qr_img,
            logo_bytes=logo_bytes,
            back_color=back_color,
            logo_size_ratio=logo_size_ratio,
            badge_radius=badge_radius
        )

    # Optional target dimension resize
    if size_px and size_px > 0 and (qr_img.width != size_px or qr_img.height != size_px):
        qr_img = qr_img.resize((size_px, size_px), Image.Resampling.LANCZOS)

    # Format specific save
    buf = io.BytesIO()
    if export_format in ["jpg", "jpeg"]:
        # JPEG doesn't support transparency; composite over solid white/back_color
        solid_bg_color = (255, 255, 255) if is_transparent else ImageColor.getrgb(back_color)
        rgb_img = Image.new("RGB", qr_img.size, solid_bg_color)
        rgb_img.paste(qr_img, (0, 0), qr_img)
        rgb_img.save(buf, format="JPEG", quality=95, optimize=True)
    elif export_format == "webp":
        qr_img.save(buf, format="WEBP", quality=95)
    else:  # PNG default
        qr_img.save(buf, format="PNG", optimize=True)

    buf.seek(0)
    return buf.getvalue()


def _embed_logo_on_image(
    base_img: Image.Image,
    logo_bytes: bytes,
    back_color: str,
    logo_size_ratio: float,
    badge_radius: int,
) -> Image.Image:
    """Embeds logo with antialiased rounded badge in the center of base_img."""
    try:
        logo_in = Image.open(io.BytesIO(logo_bytes))
    except Exception as e:
        # If logo image is corrupt, continue without embedding
        return base_img

    logo_in = logo_in.convert("RGBA")

    # Clamp ratio between 10% and 28%
    ratio = max(0.10, min(0.28, logo_size_ratio))
    target_logo_w = int(base_img.width * ratio)
    target_logo_h = int(base_img.height * ratio)

    # Maintain aspect ratio of logo
    logo_in.thumbnail((target_logo_w, target_logo_h), Image.Resampling.LANCZOS)
    actual_logo_w, actual_logo_h = logo_in.size

    # Badge padding around logo
    padding = max(6, int(base_img.width * 0.02))
    badge_w = actual_logo_w + padding * 2
    badge_h = actual_logo_h + padding * 2

    # Badge background color
    if back_color == "transparent":
        badge_bg = (255, 255, 255, 255)
    else:
        try:
            badge_bg = ImageColor.getrgb(back_color)
        except Exception:
            badge_bg = (255, 255, 255)

    # Create rounded badge
    badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    outline_color = (226, 232, 240, 255)  # Light slate boundary
    draw.rounded_rectangle(
        [0, 0, badge_w - 1, badge_h - 1],
        radius=badge_radius,
        fill=badge_bg,
        outline=outline_color,
        width=2
    )

    # Paste logo centered into badge
    logo_pos = ((badge_w - actual_logo_w) // 2, (badge_h - actual_logo_h) // 2)
    badge.paste(logo_in, logo_pos, logo_in)

    # Center badge on QR image
    badge_x = (base_img.width - badge_w) // 2
    badge_y = (base_img.height - badge_h) // 2
    base_img.paste(badge, (badge_x, badge_y), badge)

    return base_img


def _generate_svg_qr(
    content: str,
    qr_ec: int,
    box_size: int,
    border: int,
    fill_color: str,
    back_color: str,
    size_px: Optional[int],
    logo_bytes: Optional[bytes],
    logo_size_ratio: float,
    badge_radius: int,
) -> bytes:
    """Generates pure SVG QR code with optional embedded badge & logo."""
    factory = create_svg_image_factory(fill_color=fill_color, back_color=back_color)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qr_ec,
        box_size=box_size,
        border=border,
        image_factory=factory,
    )
    qr.add_data(content)
    qr.make(fit=True)

    svg_img = qr.make_image()
    root = svg_img._img
    pixel_size = svg_img.pixel_size

    # If size_px is provided, update SVG width and height attributes
    if size_px and size_px > 0:
        root.attrib["width"] = f"{size_px}px"
        root.attrib["height"] = f"{size_px}px"

    # Embed logo in SVG if provided
    if logo_bytes:
        try:
            logo_in = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            ratio = max(0.10, min(0.28, logo_size_ratio))
            badge_dim = int(pixel_size * (ratio + 0.05))
            logo_dim = int(pixel_size * ratio)

            badge_pos = (pixel_size - badge_dim) / 2
            logo_pos = (pixel_size - logo_dim) / 2

            # Badge background rect in SVG
            badge_bg = "#ffffff" if back_color == "transparent" else back_color
            badge_rect = ET.Element("rect", {
                "x": str(round(badge_pos, 2)),
                "y": str(round(badge_pos, 2)),
                "width": str(badge_dim),
                "height": str(badge_dim),
                "rx": str(badge_radius),
                "fill": badge_bg,
                "stroke": "#e2e8f0",
                "stroke-width": "2"
            })
            root.append(badge_rect)

            # Convert logo to base64 PNG data URL
            png_buf = io.BytesIO()
            logo_in.save(png_buf, format="PNG")
            logo_b64 = base64.b64encode(png_buf.getvalue()).decode("ascii")
            data_uri = f"data:image/png;base64,{logo_b64}"

            # Embed SVG <image> element
            image_elem = ET.Element("image", {
                "x": str(round(logo_pos, 2)),
                "y": str(round(logo_pos, 2)),
                "width": str(logo_dim),
                "height": str(logo_dim),
                "href": data_uri
            })
            root.append(image_elem)
        except Exception:
            pass  # Fallback to SVG without logo

    buf = io.BytesIO()
    svg_img.save(buf)
    buf.seek(0)
    return buf.getvalue()
