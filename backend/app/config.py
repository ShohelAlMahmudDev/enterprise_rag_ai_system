# from functools import lru_cache
# from typing import List

# from pydantic import Field, field_validator
# from pydantic_settings import BaseSettings, SettingsConfigDict


# class Settings(BaseSettings):
#     model_config = SettingsConfigDict(
#         env_file=".env",
#         env_file_encoding="utf-8",
#         extra="ignore",
#     )

#     APP_NAME: str = "Enterprise RAG Chatbot"
#     APP_ENV: str = "development"
#     APP_HOST: str = "0.0.0.0"
#     APP_PORT: int = 8000
#     CORS_ORIGINS: List[str] | str = Field(
#         default_factory=lambda: ["http://localhost:5173"]
#     )

#     DATABASE_URL: str = "sqlite:///./data/app.db"
#     DATA_DIR: str = "./data"
#     UPLOAD_DIR: str = "./data/uploads"
#     VECTOR_INDEX_PATH: str = "./data/faiss.index"
#     VECTOR_META_PATH: str = "./data/faiss_meta.json"

#     # Ollama configuration
#     OLLAMA_BASE_URL: str = "http://localhost:11434"
#     OLLAMA_CHAT_MODEL: str = "mistral"
#     OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

#     # Ollama config
#     OLLAMA_VISION_MODEL: str = "gemma3"
#     OLLAMA_TIMEOUT_SECONDS: int = 180
#     OLLAMA_KEEP_ALIVE: str = "30m"

#     # ingestion tuning
#     ENABLE_MULTIMODAL_INGESTION: bool = True


#     TOP_K: int = 5
#     MAX_FILE_SIZE_MB: int = 25
#     DEFAULT_CHUNK_SIZE: int = 900
#     DEFAULT_CHUNK_OVERLAP: int = 150
#     ENABLE_GENERATIVE_SUMMARY: bool = True

#     OCR_ENABLED: bool = True
#     TESSERACT_CMD: str | None = None
#     POPPLER_PATH: str | None = None
#     OCR_LANGUAGE: str = "eng"
#     PDF_OCR_MIN_TEXT_LENGTH: int = 40

#     @field_validator("CORS_ORIGINS", mode="before")
#     @classmethod
#     def split_origins(cls, value):
#         if isinstance(value, str):
#             return [item.strip() for item in value.split(",") if item.strip()]
#         return value


# @lru_cache(maxsize=1)
# def get_settings() -> Settings:
#     return Settings()


# settings = get_settings()

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Enterprise RAG Chatbot"
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    CORS_ORIGINS: List[str] | str = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:5174"]
    )

    DATABASE_URL: str = "sqlite:///./data/app.db"
    DATA_DIR: str = "./data"
    UPLOAD_DIR: str = "./data/uploads"
    VECTOR_INDEX_PATH: str = "./data/faiss.index"
    VECTOR_META_PATH: str = "./data/faiss_meta.json"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "mistral"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_VISION_MODEL: str = "gemma3"
    OLLAMA_TIMEOUT_SECONDS: int = 180
    OLLAMA_KEEP_ALIVE: str = "30m"

    ENABLE_MULTIMODAL_INGESTION: bool = True

    TOP_K: int = 5
    MAX_FILE_SIZE_MB: int = 25
    DEFAULT_CHUNK_SIZE: int = 900
    DEFAULT_CHUNK_OVERLAP: int = 150
    ENABLE_GENERATIVE_SUMMARY: bool = True

    OCR_ENABLED: bool = True
    TESSERACT_CMD: str | None = None
    POPPLER_PATH: str | None = None
    OCR_LANGUAGE: str = "eng"
    OCR_DPI: int = 250
    PDF_OCR_MIN_TEXT_LENGTH: int = 40

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("TOP_K")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("TOP_K must be greater than 0")
        return value

    @field_validator("MAX_FILE_SIZE_MB")
    @classmethod
    def validate_max_file_size_mb(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_FILE_SIZE_MB must be greater than 0")
        return value

    @field_validator("DEFAULT_CHUNK_SIZE")
    @classmethod
    def validate_chunk_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("DEFAULT_CHUNK_SIZE must be greater than 0")
        return value

    @field_validator("DEFAULT_CHUNK_OVERLAP")
    @classmethod
    def validate_chunk_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("DEFAULT_CHUNK_OVERLAP cannot be negative")
        return value

    @field_validator("PDF_OCR_MIN_TEXT_LENGTH")
    @classmethod
    def validate_pdf_ocr_min_text_length(cls, value: int) -> int:
        if value < 0:
            raise ValueError("PDF_OCR_MIN_TEXT_LENGTH cannot be negative")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()