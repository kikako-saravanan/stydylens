import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.chunking.chunker import chunk_pages
from app.embeddings.embedder import get_model
from app.ingestion.pdf_loader import extract_pages
from app.retrieval.faiss_store import add_chunks, query_index

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

    total_indexed = add_chunks(chunks)
    print(
        f"[index] {file.filename}: {len(chunks)} chunks embedded and added to FAISS "
        f"(index now holds {total_indexed} chunks total across all uploads)"
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
        "index_total_chunks": total_indexed,
    }


class QueryRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/api/query")
async def query(request: QueryRequest):
    results = query_index(request.question, request.k)
    print(f"[query] {request.question!r} -> {len(results)} results")
    for r in results:
        preview = r["text"][:80].replace("\n", " ")
        print(f"  score={r['score']:.4f} {r['source']} p{r['page']} — {preview!r}")

    return {
        "question": request.question,
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "source": r["source"],
                "page": r["page"],
                "score": r["score"],
                "snippet": r["text"][:200],
            }
            for r in results
        ],
    }
