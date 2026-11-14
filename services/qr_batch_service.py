"""
HimShiksha API - QR Batch Processing Service
Parses CSV or JSON item lists, generates individualized QR assets,
tracks per-record success/failure, and packages assets into a clean ZIP archive with manifests.
"""

import io
import csv
import json
import datetime
import zipfile
from typing import List, Dict, Any, Optional, Tuple, Union

from utils.security import sanitize_filename
from schemas.qr_schemas import QRBatchItem, QRBatchManifest, QRBatchManifestItem
from services.qr_generation_service import generate_qr_bytes


def parse_csv_items(csv_text_or_bytes: Union[str, bytes]) -> List[QRBatchItem]:
    """
    Parses CSV content into a list of QRBatchItem models.
    Supports flexible column headers (name, type, content, filename).
    """
    if isinstance(csv_text_or_bytes, bytes):
        try:
            text = csv_text_or_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = csv_text_or_bytes.decode("latin-1", errors="replace")
    else:
        text = csv_text_or_bytes

    # Detect delimiter (comma, semicolon, tab)
    sample = text[:2048]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    f = io.StringIO(text)
    reader = csv.reader(f, delimiter=delimiter)

    items: List[QRBatchItem] = []
    header: Optional[List[str]] = None

    for row in reader:
        if not row or not any(field.strip() for field in row):
            continue

        if header is None:
            # Normalize header column names
            header = [col.strip().lower().replace(" ", "_") for col in row]
            # If the first row does not look like a header (e.g. it starts directly with URL or http)
            if not any(k in header for k in ["name", "type", "content", "data", "url", "text", "filename", "file"]):
                # Treat as headerless CSV where: col 0 = name, col 1 = type, col 2 = content, col 3 = filename
                # or col 0 = content
                header = ["name", "type", "content", "filename"]
                # Process the first row as an item
                item = _extract_item_from_row(row, header)
                if item:
                    items.append(item)
            continue

        item = _extract_item_from_row(row, header)
        if item:
            items.append(item)

    return items


def _extract_item_from_row(row: List[str], header: List[str]) -> Optional[QRBatchItem]:
    """Maps CSV row fields to QRBatchItem."""
    data = {}
    for i, col in enumerate(row):
        if i < len(header):
            data[header[i]] = col.strip()

    # Determine content column
    has_content_header = any(k in data for k in ["content", "data", "url", "text", "payload"])
    if has_content_header:
        content = (
            data.get("content") or
            data.get("data") or
            data.get("url") or
            data.get("text") or
            data.get("payload") or
            ""
        ).strip()
    elif len(row) == 1:
        content = row[0].strip()
    elif len(row) >= 3 and "content" in header:
        content = ""
    else:
        # Fallback for unheadered data
        content = row[-1].strip()

    name = data.get("name") or data.get("label") or data.get("title") or None
    item_type = data.get("type") or data.get("category") or "text"
    filename = data.get("filename") or data.get("file_name") or data.get("file") or None

    return QRBatchItem(
        name=name,
        type=item_type,
        content=content,
        filename=filename
    )


def process_qr_batch(
    items: List[QRBatchItem],
    export_format: str = "png",
    error_correction: str = "M",
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "#000000",
    back_color: str = "#ffffff",
    size_px: Optional[int] = 512,
    logo_bytes: Optional[bytes] = None,
) -> Tuple[bytes, QRBatchManifest]:
    """
    Generates QR assets for all batch items, collects successes and errors,
    and returns (zip_bytes, manifest_summary).
    """
    total = len(items)
    succeeded = 0
    failed = 0
    manifest_items: List[QRBatchManifestItem] = []
    used_filenames: set = set()

    zip_buf = io.BytesIO()
    norm_format = export_format.lower().strip()
    if norm_format not in ["png", "jpg", "jpeg", "svg", "webp"]:
        norm_format = "png"
    ext = ".jpg" if norm_format in ["jpg", "jpeg"] else f".{norm_format}"

    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, item in enumerate(items, start=1):
            item_name = item.name or f"qr_{idx:03d}"
            item_type = item.type or "text"
            content = item.content.strip()

            # Generate candidate filename
            raw_fname = item.filename or item.name or f"qr_{idx:03d}"
            clean_base = sanitize_filename(raw_fname)
            filename = f"{clean_base}{ext}"

            # Deduplicate filename if already used
            counter = 1
            while filename.lower() in used_filenames:
                filename = f"{clean_base}_{counter}{ext}"
                counter += 1
            used_filenames.add(filename.lower())

            if not content:
                failed += 1
                manifest_items.append(QRBatchManifestItem(
                    index=idx,
                    name=item_name,
                    type=item_type,
                    content="",
                    filename=filename,
                    status="failed",
                    error="Content payload is empty."
                ))
                continue

            try:
                qr_bytes, _, _ = generate_qr_bytes(
                    content=content,
                    error_correction=error_correction,
                    box_size=box_size,
                    border=border,
                    fill_color=fill_color,
                    back_color=back_color,
                    export_format=norm_format,
                    size_px=size_px,
                    logo_bytes=logo_bytes,
                )

                # Store inside ZIP
                zf.writestr(filename, qr_bytes)
                succeeded += 1
                manifest_items.append(QRBatchManifestItem(
                    index=idx,
                    name=item_name,
                    type=item_type,
                    content=content,
                    filename=filename,
                    status="success",
                    error=None
                ))
            except Exception as e:
                failed += 1
                manifest_items.append(QRBatchManifestItem(
                    index=idx,
                    name=item_name,
                    type=item_type,
                    content=content,
                    filename=filename,
                    status="failed",
                    error=str(e)
                ))

        # Generate manifest
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest = QRBatchManifest(
            total=total,
            succeeded=succeeded,
            failed=failed,
            format=norm_format,
            generated_at=now_str,
            items=manifest_items
        )

        # 1. Add manifest.json
        manifest_json_str = manifest.model_dump_json(indent=2)
        zf.writestr("manifest.json", manifest_json_str.encode("utf-8"))

        # 2. Add manifest.csv for spreadsheet convenience
        csv_buf = io.StringIO()
        csv_writer = csv.writer(csv_buf)
        csv_writer.writerow(["index", "name", "type", "content", "filename", "status", "error"])
        for mi in manifest_items:
            csv_writer.writerow([mi.index, mi.name, mi.type, mi.content, mi.filename, mi.status, mi.error or ""])
        zf.writestr("manifest.csv", csv_buf.getvalue().encode("utf-8"))

    zip_buf.seek(0)
    return zip_buf.getvalue(), manifest
