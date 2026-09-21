import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.chunking.chunker import chunk_pages
from app.embeddings.embedder import embed_texts, get_model
from app.ingestion.pdf_loader import extract_pages

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model once at startup, not on the first request —
    # otherwise whichever user's upload happens to be first pays a multi-
    # second model-load penalty that has nothing to do with their PDF.
    get_model()
    yield


app = FastAPI(title="StudyLens API", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BACKEND_DIR.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    pages = extract_pages(dest, source=file.filename)

    print(f"[ingestion] {file.filename}: {len(pages)} pages with extractable text")
    for p in pages:
        preview = p.text[:80].replace("\n", " ")
        print(f"  page {p.page}: {len(p.text)} chars — {preview!r}")

    chunks = chunk_pages(pages)
    print(f"[chunking] {file.filename}: {len(chunks)} chunks from {len(pages)} pages")
    for c in chunks:
        preview = c.text[:80].replace("\n", " ")
        print(f"  {c.chunk_id}: {len(c.text)} chars — {preview!r}")

    embeddings = embed_texts([c.text for c in chunks]) if chunks else None
    embedding_dim = int(embeddings.shape[1]) if embeddings is not None else 0
    print(
        f"[embeddings] {file.filename}: {len(chunks)} chunks embedded, "
        f"dim={embedding_dim}, model={os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')}"
    )

    return {
        "filename": file.filename,
        "page_count": len(pages),
        "pages": [{"page": p.page, "char_count": len(p.text)} for p in pages],
        "chunk_count": len(chunks),
        "chunks": [
            {"chunk_id": c.chunk_id, "page": c.page, "char_count": len(c.text)}
            for c in chunks
        ],
        "embedding_dim": embedding_dim,
    }
