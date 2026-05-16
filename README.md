# Python Ruby-GPT — Vercel Ready

Python Ruby-GPT is a single-page FastAPI web app that behaves like a chatbot but sources answers from open internet search providers.

## What changed for Vercel

Vercel serverless deployments do not run `docker compose`, and the deployed filesystem is read-only except for `/tmp`.

This project has therefore been refactored so that:

- Vercel entrypoint is `api/index.py`.
- FastAPI exposes a top-level `app = FastAPI(...)`.
- The UI is served from `public/index.html`.
- `vercel.json` rewrites `/`, `/api/search`, and `/api/history` to the FastAPI app.
- Flat-file JSON storage writes to `/tmp/python-ruby-gpt-data` on Vercel.
- Local Docker usage still writes to `./data`.

## Project structure

```text
python-ruby-gpt-vercel/
├── api/
│   └── index.py
├── public/
│   └── index.html
├── data/
├── app.py
├── requirements.txt
├── vercel.json
├── Dockerfile
├── docker-compose.yml
├── README.md
└── USER-GUIDE.md
```

## Search complexity mapping

- `DEEP-DIVE` = SearXNG open-source metasearch
- `DIVE` = DuckDuckGo Instant Answer
- `LEVEL` = DuckDuckGo HTML search
- `SHALLOW` = Wikipedia fallback search
- `RECURSIVE` = Aggregates multiple providers and scores the strongest result

## Deploy to Vercel

Push the project to GitHub, then import it in Vercel.

Vercel should automatically detect Python because of:

```text
api/index.py
requirements.txt
vercel.json
```

After deployment, test:

```text
https://your-vercel-url.vercel.app/health
```

Expected response:

```json
{
  "status": "ok",
  "app": "Python Ruby-GPT",
  "platform": "vercel"
}
```

## Important Vercel note

On Vercel, flat-file history is stored in `/tmp`. This is writable, but it is ephemeral. It may disappear between cold starts or deployments.

For permanent production storage, replace flat-file storage with one of:

- Vercel Postgres
- Supabase
- Neon Postgres
- MongoDB Atlas
- Redis/KV
- S3-compatible object storage

## Local Docker run

```bash
docker compose up --build
```

Open:

```text
http://localhost:8080
```

## Local Python run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

Open:

```text
http://localhost:8080
```

## Optional SearXNG configuration

For best DEEP-DIVE reliability, self-host SearXNG and set:

```bash
SEARXNG_URL=https://your-searxng-instance.example.com
```

In Vercel:

```text
Project → Settings → Environment Variables → SEARXNG_URL
```
