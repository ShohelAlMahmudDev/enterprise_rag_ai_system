
# from pathlib import Path

# SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


# def is_image_file(path: str | Path) -> bool:
#     return Path(path).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


from pathlib import Path
from typing import Literal

from PIL import Image

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

ImageCategory = Literal["diagram", "screenshot", "document", "photo", "unknown"]


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def validate_image_file(path: str | Path) -> None:
    """
    Ensure the file is a valid image and not corrupted.
    """
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        raise ValueError(f"Invalid or corrupted image file: {path}") from exc


def get_image_size(path: str | Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.width, img.height


def is_large_image(path: str | Path, max_pixels: int = 10_000_000) -> bool:
    """
    Detect overly large images (e.g. >10MP).
    """
    width, height = get_image_size(path)
    return (width * height) > max_pixels


def classify_image_type(path: str | Path) -> ImageCategory:
    """
    Heuristic classification of image type.
    This is lightweight and fast (no AI yet).
    """
    try:
        with Image.open(path) as img:
            width, height = img.size
            aspect_ratio = width / height if height else 1

            # Heuristic rules
            if width > 1200 and height > 800:
                # Likely screenshot or document
                if 1.2 < aspect_ratio < 2.5:
                    return "screenshot"
                return "document"

            if width < 800 and height < 800:
                return "diagram"

            return "photo"

    except Exception:
        return "unknown"


def should_apply_ocr(image_type: ImageCategory) -> bool:
    """
    Decide if OCR should be applied based on image type.
    """
    return image_type in {"document", "screenshot", "diagram"}


def should_use_vision_model(image_type: ImageCategory) -> bool:
    """
    Decide if the image should go to the vision model.
    """
    return image_type in {"diagram", "screenshot", "photo"}