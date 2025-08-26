import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from .services.rag import load_or_build_index, search, generate_answer, PDF_PATH

load_dotenv()

app = FastAPI(title="EX Copilot – Policy Q&A")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Global index + chunks
INDEX = None
CHUNKS = None

@app.on_event("startup")
def startup_event():
    global INDEX, CHUNKS
    try:
        INDEX, CHUNKS = load_or_build_index()
    except Exception as e:
        print("Index build/load failed:", e)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    pdf_found = os.path.exists(PDF_PATH)
    return templates.TemplateResponse("index.html", {"request": request, "pdf_found": pdf_found})

@app.post("/ask")
async def ask(request: Request):
    global INDEX, CHUNKS
    data = await request.json()
    question = (data or {}).get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")
    if INDEX is None or CHUNKS is None:
        raise HTTPException(status_code=500, detail="Index not ready. Check PDF presence and server logs.")

    hits = search(question, INDEX, CHUNKS)
    answer = generate_answer(question, hits)
    # return hits as sources
    sources = [{"page": h["page"], "snippet": h["text"][:160].replace("\n", " ") + ("..." if len(h["text"])>160 else "")} for h in hits]
    return JSONResponse({"answer": answer})

@app.post("/reindex")
def reindex():
    global INDEX, CHUNKS
    try:
        INDEX, CHUNKS = load_or_build_index()
        return {"status": "ok", "message": "Index rebuilt."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")

@app.get("/healthz")
def health():
    return {"ok": True}
