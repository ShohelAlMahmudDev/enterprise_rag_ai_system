from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    logical_name: str
    current_version: int
    is_deleted: bool
    created_at: str
    updated_at: str
    filename: str | None = None
    file_type: str | None = None
    language: str | None = None
    chunk_count: int | None = None
    status: str | None = None
    uploaded_at: str | None = None
    active: bool = True


class DocumentVersionOut(BaseModel):
    version_id: str
    document_id: str
    version: int
    filename: str
    file_type: str
    language: str
    chunk_count: int
    status: str
    created_at: str
    notes: str | None = None


class UploadResponse(BaseModel):
    message: str
    document: DocumentOut
    version: DocumentVersionOut
