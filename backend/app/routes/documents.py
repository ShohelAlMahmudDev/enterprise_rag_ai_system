from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.document import DocumentOut, DocumentVersionOut, UploadResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix='/documents', tags=['documents'])
service = DocumentService()


@router.post('', response_model=UploadResponse)
async def create_document(
    logical_name: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    try:
        document, version = await service.create_document(file, logical_name, notes)
        return UploadResponse(message='Document created successfully', document=document, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/{document_id}/versions', response_model=UploadResponse)
async def create_new_version(document_id: str, notes: Optional[str] = Form(None), file: UploadFile = File(...)):
    try:
        document, version = await service.create_new_version(document_id, file, notes)
        return UploadResponse(message='New document version created successfully', document=document, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('', response_model=list[DocumentOut])
def list_documents():
    return service.list_documents()


@router.get('/{document_id}/versions', response_model=list[DocumentVersionOut])
def get_versions(document_id: str):
    return service.get_versions(document_id)


@router.delete('/{document_id}')
def delete_document(document_id: str):
    if not service.soft_delete_document(document_id):
        raise HTTPException(status_code=404, detail='Document not found')
    return {'message': 'Document soft deleted successfully'}
