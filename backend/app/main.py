from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.init_db import init_db
from app.routes import admin, documents, query, settings as settings_route
from app.utils.file_utils import ensure_directories
from app.utils.logging import configure_logging

configure_logging()
ensure_directories()
init_db()

app = FastAPI(title=settings.APP_NAME, version='3.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)
app.include_router(settings_route.router)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': settings.APP_NAME, 'environment': settings.APP_ENV}
