from .utils import random_doc_data, parse_fields_from_text
from pathlib import Path
import os
import json
import urllib.request
import urllib.parse


def _try_imports():
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return pytesseract, Image
    except Exception:
        return None, None


def _ocr_image(image_path: Path) -> str:
    pytesseract, Image = _try_imports()
    if not pytesseract or not Image:
        return ""
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang="fra+eng")


def _ocr_pdf(pdf_path: Path) -> str:
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception:
        return ""
    pytesseract, Image = _try_imports()
    if not pytesseract:
        return ""
    pages = convert_from_path(str(pdf_path), dpi=200)
    text = []
    for p in pages:
        text.append(pytesseract.image_to_string(p, lang="fra+eng"))
    return "\n".join(text)


def _ocr_remote(file_path: Path) -> str:
    provider = os.getenv("OCR_PROVIDER", "").lower()
    if provider != "ocrspace":
        return ""
    api_key = os.getenv("OCRSPACE_API_KEY")
    if not api_key:
        return ""

    url = "https://api.ocr.space/parse/image"
    boundary = "----ComptaFlowBoundary"
    data = []
    data.append(f"--{boundary}")
    data.append('Content-Disposition: form-data; name="apikey"')
    data.append("")
    data.append(api_key)
    data.append(f"--{boundary}")
    data.append('Content-Disposition: form-data; name="language"')
    data.append("")
    data.append("fre")
    data.append(f"--{boundary}")
    data.append('Content-Disposition: form-data; name="file"; filename="document"')
    data.append("Content-Type: application/octet-stream")
    data.append("")
    body_start = "\r\n".join(data).encode("utf-8")
    body_end = f"\r\n--{boundary}--\r\n".encode("utf-8")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = body_start + file_bytes + body_end
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(payload)
            if parsed.get("IsErroredOnProcessing"):
                return ""
            results = parsed.get("ParsedResults") or []
            if results:
                return results[0].get("ParsedText", "") or ""
    except Exception:
        return ""
    return ""


def extract_document(filename: str, file_path: str | None = None):
    """
    OCR + extraction if possible, fallback to simulated data.
    """
    if file_path:
        path = Path(file_path)
        text = ""
        text = _ocr_remote(path)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tiff"}:
            text = text or _ocr_image(path)
        elif path.suffix.lower() == ".pdf":
            text = text or _ocr_pdf(path)
        fields = parse_fields_from_text(text) if text else {}
        if fields:
            fields["filename"] = filename
            return fields
    return random_doc_data(filename)
