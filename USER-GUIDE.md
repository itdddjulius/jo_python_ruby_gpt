# USER-GUIDE — Python Ruby-GPT Vercel Deployment

## 1. Unzip project

```bash
unzip python-ruby-gpt-vercel-ready.zip
cd python-ruby-gpt-vercel
```

## 2. Test locally with Docker

```bash
docker compose up --build
```

Open:

```text
http://localhost:8080
```

## 3. Test locally without Docker

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

## 4. Verify health endpoint

```bash
curl http://localhost:8080/health
```

Expected:

```json
{"status":"ok"}
```

## 5. Push to GitHub

```bash
git init
git add .
git commit -m "Deploy Python Ruby-GPT to Vercel"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## 6. Deploy on Vercel

1. Go to Vercel.
2. Import the GitHub repository.
3. Leave framework preset as Other if FastAPI is not detected.
4. Deploy.

The important files are:

```text
api/index.py
requirements.txt
vercel.json
```

## 7. Test Vercel deployment

```text
https://your-project.vercel.app/health
```

Then open:

```text
https://your-project.vercel.app/
```

## 8. If you still see FUNCTION_INVOCATION_FAILED

Check Vercel logs:

```bash
npm i -g vercel
vercel logs your-project.vercel.app
```

Common fixes:

- Ensure `api/index.py` exists.
- Ensure `app = FastAPI(...)` exists inside `api/index.py`.
- Ensure `requirements.txt` exists.
- Ensure flat-file writes use `/tmp` on Vercel.
- Ensure `vercel.json` exists.

## 9. Recommended production upgrade

Because `/tmp` is ephemeral on Vercel, replace flat-file storage with persistent storage for production:

```text
Vercel Postgres / Supabase / Neon / MongoDB Atlas / Redis / S3
```
