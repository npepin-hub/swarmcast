# SwarmCast

SwarmCast is a multi-agent forecast application with a FastAPI backend and a browser-based frontend. The backend provides forecast and WebSocket endpoints, while the frontend uses a static HTML/CSS/JavaScript UI served by the backend.

## Requirements

- Python 3.11+ recommended
- `pip` package manager

## Install dependencies

From the repository root:

```bash
pip install -r requirements.txt
```

## Configure environment variables

The backend uses `pydantic-settings` and expects the following required values to be set before startup:

- `ANTHROPIC_API_KEY`
- `VOYAGE_API_KEY`
- `WANDB_API_KEY`

Optional values can also be provided in a `.env` file at the repo root.

Example `.env` file:

```env
ANTHROPIC_API_KEY=your-anthropic-key
VOYAGE_API_KEY=your-voyage-key
WANDB_API_KEY=your-wandb-key
WANDB_PROJECT=swarmcast
```

## RAG data requirement

The backend relies on a static RAG corpus for the `/forecast` pipeline.
It expects the following files to exist:

- `backend/data/static/embeddings.npy`
- `backend/data/static/metadata.json`

If these files are missing, forecast requests will fail with:
`FileNotFoundError: backend/data/static/embeddings.npy`.

If you have a document corpus, you can generate the embeddings and metadata using the `embed_corpus()` helper in `backend/data/rag.py`.
For example:

```bash
python - <<'PY'
from backend.data.rag import embed_corpus
# Replace this with your corpus documents
corpus = [
    {"text": "Example doc text.", "source": "source-name", "tags": ["example"]}
]
embed_corpus(corpus)
PY
```

## Run the backend

The backend is the main application entrypoint and also serves frontend static files.

Run this from the repository root:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

If you prefer to run it with Python directly:

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

If you run from inside `backend/`, set the repository root on `PYTHONPATH`:

```bash
cd backend
PYTHONPATH=.. uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

> Note: The backend mounts the `frontend` folder at `/static`, so the frontend is available from the same FastAPI server.

## Open the frontend

After starting the backend, open your browser at:

```text
http://localhost:8000/
```

This loads `frontend/index.html` and connects to the backend through the `/forecast` and `/ws` endpoints.

## Project structure

- `backend/` — FastAPI application and server code
- `frontend/` — static UI files served by the backend
- `requirements.txt` — Python dependencies

## Notes

- The frontend assets are served from `/static` by the FastAPI app.
- The main API endpoints are:
  - `GET /` — serve the frontend
  - `GET /health` — health check
  - `POST /forecast` — run a forecast request
  - `GET /ws` — WebSocket event stream
