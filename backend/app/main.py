import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

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

    return {
        "filename": file.filename,
        "page_count": len(pages),
        "pages": [{"page": p.page, "char_count": len(p.text)} for p in pages],
    }
