# app/services/rag.py

import os
import json
from typing import List, Tuple, Dict, Any

import faiss
import numpy as np
from PyPDF2 import PdfReader
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # ensure .env is loaded even if main didn't load it yet

# --- OpenAI / Azure OpenAI client bootstrap ---------------------------------
from openai import OpenAI

# ENV (models can be OpenAI model names or Azure deployment names)
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
GEN_MODEL = os.getenv("GEN_MODEL", "gpt-4o-mini")

# Paths (default to local dev paths; container paths can be passed via .env)
PDF_PATH = os.getenv("PDF_PATH", "app/data/employee_policy_handbook.pdf")
INDEX_DIR = os.getenv("INDEX_DIR", "app/data")
TOP_K = int(os.getenv("TOP_K", "5"))

# OpenAI (non-Azure)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Azure OpenAI (optional)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

# Instantiate client (Azure if vars provided, else OpenAI)
if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
    client = OpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        base_url=f"{AZURE_OPENAI_ENDPOINT}/openai",
        default_query={"api-version": AZURE_OPENAI_API_VERSION},
    )
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

# --- Small helpers -----------------------------------------------------------

def _ensure_paths() -> None:
    """
    Make INDEX_DIR if missing. If PDF_PATH doesn't exist but a local default does,
    fallback to it (helps when switching between container and local).
    """
    global PDF_PATH, INDEX_DIR

    # Ensure index dir exists
    Path(INDEX_DIR).mkdir(parents=True, exist_ok=True)

    # Fallback to local relative path if configured path doesn't exist
    if not Path(PDF_PATH).exists():
        local_pdf = Path("app/data/employee_policy_handbook.pdf")
        if local_pdf.exists():
            PDF_PATH = str(local_pdf)

def _read_pdf_text(pdf_path: str) -> List[Dict[str, Any]]:
    """Return list of pages with text: [{page: int, text: str}]"""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        pages.append({"page": i + 1, "text": t})
    return pages

def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    """
    Sliding-window chunking by characters to preserve context.
    Filters tiny chunks (< 50 chars).
    """
    text = text.replace("\r", " ")
    parts: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        parts.append(text[start:end].strip())
        if end == n:
            break
        start = max(0, end - overlap)
    return [p for p in parts if len(p) > 50]

def _embed_texts(texts: List[str]) -> np.ndarray:
    """
    Return embeddings as float32 numpy array (N, D).
    Batched calls for efficiency.
    """
    all_vecs: List[List[float]] = []
    B = 64
    for i in range(0, len(texts), B):
        batch = texts[i:i + B]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        vecs = [d.embedding for d in resp.data]
        all_vecs.extend(vecs)
    return np.array(all_vecs, dtype="float32")

def _build_index(pdf_path: str, index_dir: str) -> Tuple[faiss.IndexFlatL2, List[Dict[str, Any]]]:
    pages = _read_pdf_text(pdf_path)
    chunks: List[Dict[str, Any]] = []
    for p in pages:
        for c in _chunk_text(p["text"]):
            chunks.append({"page": p["page"], "text": c})

    if not chunks:
        raise RuntimeError(
            "No text extracted from PDF. Ensure the PDF is text-based or run OCR for scanned PDFs."
        )

    texts = [c["text"] for c in chunks]
    embs = _embed_texts(texts)
    dim = embs.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embs)

    Path(index_dir).mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, os.path.join(index_dir, "index.faiss"))
    with open(os.path.join(index_dir, "index_meta.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    return index, chunks

def load_or_build_index(pdf_path: str = PDF_PATH, index_dir: str = INDEX_DIR) -> Tuple[faiss.IndexFlatL2, List[Dict[str, Any]]]:
    _ensure_paths()
    idx_path = os.path.join(index_dir, "index.faiss")
    meta_path = os.path.join(index_dir, "index_meta.json")

    if os.path.exists(idx_path) and os.path.exists(meta_path):
        index = faiss.read_index(idx_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        return index, chunks

    return _build_index(pdf_path, index_dir)

def search(query: str, index: faiss.IndexFlatL2, chunks: List[Dict[str, Any]], k: int = TOP_K) -> List[Dict[str, Any]]:
    qvec = _embed_texts([query])
    D, I = index.search(qvec, k)
    hits: List[Dict[str, Any]] = []
    for rank, idx in enumerate(I[0]):
        if idx == -1:
            continue
        item = chunks[idx]
        hits.append({"rank": rank + 1, "page": item["page"], "text": item["text"]})
    return hits

# --- LLM answer generation (no sources in the final answer) ------------------

SYSTEM_PROMPT = (
    "You are an HR policy assistant. Answer ONLY using the provided policy excerpts. "
    "If the policy does not specify something, reply exactly: 'Not specified in the policy.' "
    "Be concise and professional. Do not include citations, sources, or page numbers in your answer."
)

def generate_answer(question: str, context_chunks: List[Dict[str, Any]]) -> str:
    """
    Generate a clean answer with no 'Sources' or page citations.
    """
    context = "\n\n---\n\n".join([c["text"] for c in context_chunks]) if context_chunks else ""
    user_msg = (
        f"Policy excerpts:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer briefly and clearly. Do not add sources, citations, or page numbers."
    )

    resp = client.chat.completions.create(
        model=GEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()
