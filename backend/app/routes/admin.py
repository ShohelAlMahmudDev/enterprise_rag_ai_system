from fastapi import APIRouter

from app.services.admin_service import AdminService

router = APIRouter(prefix='/admin', tags=['admin'])
service = AdminService()


@router.post('/rebuild-index')
def rebuild_index():
    return service.rebuild_index()
