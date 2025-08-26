<<<<<<< HEAD
# policypilot
=======
# EX Copilot – Policy Q&A (FastAPI + PDF + RAG)

This app answers HR/Employee Experience questions **using only** the policy PDF.
It parses the PDF, chunks text, embeds with OpenAI, stores a FAISS index, and uses GPT to compose grounded answers.

## 1) Setup

```bash
cd ex_copilot_fastapi
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # put your OpenAI key here
```

Place the PDF at:
```
app/data/employee_policy_handbook.pdf
```
(A copy was already added if you used the provided ZIP.)

## 2) Run locally

```bash
uvicorn app.main:app --reload --port 8000
# Open http://localhost:8000
```

## 3) Build Docker image

```bash
docker build -t ex-copilot:latest .
docker run -p 8000:8000 --env-file .env ex-copilot:latest
```

## 4) Push to Azure Container Registry (ACR)

```bash
az acr create -g <rg> -n <acrName> --sku Basic
az acr login -n <acrName>
docker tag ex-copilot:latest <acrName>.azurecr.io/ex-copilot:latest
docker push <acrName>.azurecr.io/ex-copilot:latest
```

## 5) Deploy to Azure App Service (Linux)

```bash
az appservice plan create -g <rg> -n ex-copilot-plan --sku B1 --is-linux
az webapp create -g <rg> -p ex-copilot-plan -n <webAppName>   -i <acrName>.azurecr.io/ex-copilot:latest

# Set settings (ensure your OPENAI_API_KEY is set)
az webapp config appsettings set -g <rg> -n <webAppName> --settings   OPENAI_API_KEY=<your_key>   EMBED_MODEL=text-embedding-3-small   GEN_MODEL=gpt-4o-mini   PDF_PATH=/app/app/data/employee_policy_handbook.pdf   INDEX_DIR=/app/app/data   TOP_K=5

# If ACR auth required:
az webapp config container set -g <rg> -n <webAppName>   --docker-custom-image-name <acrName>.azurecr.io/ex-copilot:latest   --docker-registry-server-url https://<acrName>.azurecr.io
```

## Notes
- If your PDF is a scanned image, add OCR (e.g., Tesseract or Azure Form Recognizer) before indexing.
- To rebuild the index after updating the PDF: POST to `/reindex`.
- The app cites pages used under **Sources** and refuses to answer outside-policy questions.
>>>>>>> 11c8250 (Initial commit: PolicyPilot FastAPI RAG app)
