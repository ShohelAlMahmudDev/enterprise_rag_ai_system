from typing import Any

from pydantic import BaseModel, Field, ConfigDict, field_validator


class QueryRequest(BaseModel):
    """
    Incoming query request from API/UI.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str
    session_id: str | None = None
    debug: bool = False
    filters: dict[str, Any] | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be empty.")
        return value


class RetrievedChunkDebug(BaseModel):
    """
    Debug view of a retrieved chunk.
    """

    model_config = ConfigDict(extra="ignore")

    filename: str | None = None
    logical_name: str | None = None
    chunk_id: int | str | None = None
    score: float = 0.0
    preview: str = ""


class QueryDebugInfo(BaseModel):
    """
    Optional debug payload returned when debug=True.
    """

    model_config = ConfigDict(extra="ignore")

    retrieved_chunks: list[RetrievedChunkDebug] = Field(default_factory=list)
    top_k: int = 0
    llm_context_preview: str | None = None


class QuerySource(BaseModel):
    """
    Structured source/citation returned with an answer.
    """

    model_config = ConfigDict(extra="ignore")

    logical_name: str | None = None
    filename: str | None = None
    file_type: str | None = None

    page: int | None = None
    page_number: int | None = None

    slide: int | None = None
    slide_number: int | None = None

    sheet: str | None = None
    sheet_name: str | None = None
    row: int | None = None

    heading: str | None = None
    title: str | None = None

    chunk_id: int | str | None = None
    document_id: str | None = None
    version_id: str | None = None

    diagram_type: str | None = None
    has_structured_extraction: bool | None = None
    source_modality: str | None = None
    content_type: str | None = None

    score: float | None = None
    final_score: float | None = None

    label: str | None = None

    @field_validator("score", "final_score", mode="before")
    @classmethod
    def validate_scores(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            score = float(value)
        except Exception:
            return None
        return score

    @property
    def display_location(self) -> str | None:
        parts: list[str] = []

        effective_page = self.page if self.page is not None else self.page_number
        effective_slide = self.slide if self.slide is not None else self.slide_number
        effective_sheet = self.sheet if self.sheet is not None else self.sheet_name

        if effective_page is not None:
            parts.append(f"page {effective_page}")
        if effective_slide is not None:
            parts.append(f"slide {effective_slide}")
        if effective_sheet:
            parts.append(f"sheet {effective_sheet}")
        if self.row is not None:
            parts.append(f"row {self.row}")
        if self.chunk_id is not None:
            parts.append(f"chunk {self.chunk_id}")

        if not parts:
            return None

        return ", ".join(parts)

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label

        logical_name = self.logical_name or "Unknown"
        filename = self.filename or "Unknown"
        location = self.display_location

        if location:
            return f"{logical_name} / {filename} ({location})"

        return f"{logical_name} / {filename}"


class QueryResponse(BaseModel):
    """
    Final answer payload returned to the client.
    """

    model_config = ConfigDict(extra="ignore")

    answer: str
    sources: list[QuerySource] = Field(default_factory=list)
    language: str = "unknown"
    tool_used: str | None = None
    confidence: float | None = None
    debug: QueryDebugInfo | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None

        try:
            confidence = float(value)
        except Exception:
            return 0.0

        if confidence < 0.0:
            return 0.0
        if confidence > 1.0:
            return 1.0
        return confidence


class ChatHistoryItem(BaseModel):
    """
    Single chat history item.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    role: str
    content: str
    created_at: str | None = None


class ChatHistoryResponse(BaseModel):
    """
    Chat history response for a session.
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str
    items: list[ChatHistoryItem] = Field(default_factory=list)