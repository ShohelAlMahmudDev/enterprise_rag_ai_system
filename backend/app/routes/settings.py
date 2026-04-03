# from fastapi import APIRouter

# from app.config import settings

# router = APIRouter(prefix='/settings', tags=['settings'])


# @router.get('')
# def get_settings():
#     return {
#         'app_name': settings.APP_NAME,
#         'embedding_model_name': settings.OLLAMA_EMBED_MODEL,
#         'top_k': settings.TOP_K,
#         'max_file_size_mb': settings.MAX_FILE_SIZE_MB,
#         'allowed_extensions': ['.pdf', '.docx', '.txt', '.xlsx', '.pptx'],
#     }

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.config import settings
from app.utils.file_utils import ALLOWED_EXTENSIONS

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    app_name: str
    embedding_model_name: str
    top_k: int
    max_file_size_mb: int
    allowed_extensions: List[str]


@router.get("", response_model=SettingsResponse)
def get_settings():
    return {
        "app_name": settings.APP_NAME,
        "embedding_model_name": settings.OLLAMA_EMBED_MODEL,
        "top_k": settings.TOP_K,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    }