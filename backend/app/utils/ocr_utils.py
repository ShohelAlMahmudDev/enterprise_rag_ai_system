from pathlib import Path

import pytesseract
from pdf2image import convert_from_path

from app.config import settings


def configure_tesseract() -> None:
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def extract_ocr_text_from_pdf_page(pdf_path: str | Path, page_number: int) -> str:
    """
    page_number is 1-based.
    """
    configure_tesseract()

    images = convert_from_path(
        str(pdf_path),
        first_page=page_number,
        last_page=page_number,
        poppler_path=settings.POPPLER_PATH,
        dpi=settings.OCR_DPI,
    ) 
    
    if not images:
        return ""

    image = images[0]
    text = pytesseract.image_to_string(image, lang=settings.OCR_LANGUAGE)
    return " ".join(text.split()).strip()