import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.chunking.chunker import chunk_pages
from app.ingestion.pdf_loader import extract_pages

load_dotenv()

app = FastAPI(title="StudyLens API")

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

    return {
        "filename": file.filename,
        "page_count": len(pages),
        "pages": [{"page": p.page, "char_count": len(p.text)} for p in pages],
        "chunk_count": len(chunks),
        "chunks": [
            {"chunk_id": c.chunk_id, "page": c.page, "char_count": len(c.text)}
            for c in chunks
        ],
    }
