# Enterprise RAG Chatbot

This package is a complete local-first Enterprise RAG chatbot with:
- FastAPI backend
- React + TypeScript frontend
- SQLite metadata store
- FAISS vector index
- document upload and versioning
- vector index rebuild
- multilingual semantic search
- support for PDF, DOCX, TXT, XLSX, and PPTX

## Project structure

- `backend/app/main.py` - FastAPI entry point
- `backend/app/routes` - API endpoints
- `backend/app/services` - indexing and RAG logic
- `backend/app/parsers` - document text extraction
- `backend/app/vector_store` - FAISS persistence
- `frontend/src/App.tsx` - UI
- `docker-compose.yml` - end-to-end local stack

## Quick start without Docker

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Windows PowerShell: copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Quick start with Docker

```bash
docker compose up --build
```

## API summary

- `GET /health`
- `GET /documents`
- `POST /documents`
- `POST /documents/{document_id}/versions`
- `GET /documents/{document_id}/versions`
- `DELETE /documents/{document_id}`
- `POST /query`
- `POST /admin/rebuild-index`
- `GET /settings`

## Notes

- The default embedding model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- On first run, the backend may download the embedding model.
- Answer generation is deterministic and extractive by default, which keeps the system light and predictable for enterprise use.
