# Production image for the StudyLens backend, built for Railway.
#
# Build context is the `backend/` directory (Railway "Root Directory").
# The embedding + reranker models are downloaded once at BUILD time and
# baked into the image, so the container never needs Hugging Face network
# access at startup or per-request -- HF_HUB_OFFLINE=1 below is safe
# because the models are already on disk.
FROM python:3.12-slim

# libgomp1: required by faiss-cpu / torch at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

ENV EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "\
import os; \
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer(os.environ['EMBEDDING_MODEL']); \
CrossEncoder(os.environ['RERANKER_MODEL'])"

COPY app ./app

# WORKDIR is /app, so this file lives at /app/app/main.py -- one level
# deeper than WORKDIR. app/main.py and app/retrieval/faiss_store.py both
# resolve their data directory relative to their own file location up to
# this image's filesystem root ("/"), landing on /data -- so a Railway
# volume mounted at /data is where uploads and the FAISS index persist
# across deploys and restarts.
ENV HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
