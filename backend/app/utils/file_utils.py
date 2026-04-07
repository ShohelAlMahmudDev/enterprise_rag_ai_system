import os
import re
import uuid
from pathlib import Path

from app.config import settings
from app.utils.image_utils import SUPPORTED_IMAGE_EXTENSIONS

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".xlsx",
    ".csv",
    ".pptx",
}

ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | SUPPORTED_IMAGE_EXTENSIONS


def ensure_directories() -> None:
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed_extension(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


def is_document_extension(filename: str) -> bool:
    return get_extension(filename) in DOCUMENT_EXTENSIONS


def is_image_extension(filename: str) -> bool:
    return get_extension(filename) in SUPPORTED_IMAGE_EXTENSIONS


def validate_extension(filename: str) -> str:
    ext = get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext or 'unknown'}. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    return ext


def validate_file_size(size_bytes: int) -> None:
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(
            f"File too large. Maximum supported size is {settings.MAX_FILE_SIZE_MB} MB."
        )


def sanitize_filename(filename: str) -> str:
    clean = os.path.basename(filename).strip()
    clean = clean.replace(" ", "_")
    clean = re.sub(r"[^A-Za-z0-9._-]", "", clean)

    if not clean or clean in {".", ".."} or clean.startswith("."):
        raise ValueError("Invalid filename.")

    stem = Path(clean).stem.strip("._-")
    suffix = Path(clean).suffix.lower()

    if not stem:
        raise ValueError("Invalid filename stem.")

    return f"{stem}{suffix}"


def generate_unique_filename(filename: str) -> str:
    clean = sanitize_filename(filename)
    stem = Path(clean).stem
    suffix = Path(clean).suffix.lower()
    unique_id = uuid.uuid4().hex[:8]
    return f"{stem}_{unique_id}{suffix}"


def safe_join_upload(filename: str, unique: bool = True) -> str:
    """
    Create a safe upload path inside the configured upload directory.

    By default, filenames are made unique to avoid collisions.
    """
    ensure_directories()

    clean = generate_unique_filename(filename) if unique else sanitize_filename(filename)

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    final_path = (upload_dir / clean).resolve()

    if upload_dir not in final_path.parents and final_path != upload_dir / clean:
        raise ValueError("Resolved upload path is outside the upload directory.")

    return str(final_path)