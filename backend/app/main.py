import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import require_auth
from app.chunking.chunker import chunk_pages
from app.embeddings.embedder import get_model
from app.ingestion.pdf_loader import extract_pages
from app.rag.chain import answer_question, make_snippet
from app.rag.llm_provider import AllProvidersUnavailableError
from app.rerank.reranker import get_reranker
from app.retrieval.faiss_store import add_chunks, query_index

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("studylens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load models once at startup, not on the first request — otherwise
    # whichever request happens to be first pays a multi-second model-load
    # penalty that has nothing to do with what it actually asked for.
    get_model()
    get_reranker()
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


@app.exception_handler(AllProvidersUnavailableError)
async def all_providers_unavailable_handler(request, exc: AllProvidersUnavailableError):
    logger.error("All LLM providers unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"error": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    # Never leak a raw traceback to a client — log the full detail
    # server-side (exc_info gives us the real stack trace in the logs)
    # and return a generic, safe message to whoever called the API.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error. Check server logs for details."},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...), _user: str = Depends(require_auth)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        pages = extract_pages(dest, source=file.filename)
    except Exception as e:
        logger.warning("Failed to parse %s as a PDF: %s", file.filename, e)
        raise HTTPException(
            status_code=400, detail=f"Could not read '{file.filename}' as a PDF."
        ) from e

    logger.info("[ingestion] %s: %d pages with extractable text", file.filename, len(pages))
    for p in pages:
        preview = p.text[:80].replace("\n", " ")
        logger.debug("  page %d: %d chars — %r", p.page, len(p.text), preview)

    chunks = chunk_pages(pages)
    logger.info("[chunking] %s: %d chunks from %d pages", file.filename, len(chunks), len(pages))

    total_indexed = add_chunks(chunks)
    logger.info(
        "[index] %s: %d chunks embedded and added to FAISS "
        "(index now holds %d chunks total across all uploads)",
        file.filename, len(chunks), total_indexed,
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
async def query(request: QueryRequest, _user: str = Depends(require_auth)):
    results = query_index(request.question, request.k)
    logger.info("[query] %r -> %d results", request.question, len(results))

    return {
        "question": request.question,
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "source": r["source"],
                "page": r["page"],
                "score": r["score"],
                "snippet": make_snippet(r["text"]),
            }
            for r in results
        ],
    }


class AskRequest(BaseModel):
    question: str
    k: int | None = None


@app.post("/api/ask")
async def ask(request: AskRequest, _user: str = Depends(require_auth)):
    result = answer_question(request.question, request.k)
    logger.info(
        "[ask] %r -> grounded in %d source chunk(s)",
        request.question, len(result["sources"]),
    )

    return result
