# Python Ruby-GPT

Python Ruby-GPT is a FastAPI refactor of the original PHP/Apache RUBY-GPT project.

It is a single-page chatbot-style website that stores user prompts and answers in flat JSON files. It does not call a real LLM by default. Instead, it performs open internet search using selectable complexity strategies.

## Search Complexity Mapping

| Complexity | Provider |
|---|---|
| SHALLOW | Wikipedia fallback search only |
| LEVEL | DuckDuckGo HTML search |
| DIVE | DuckDuckGo Instant Answer |
| DEEP-DIVE | SearXNG open-source metasearch |
| RECURSIVE | Multi-provider aggregate search |

## Run with Docker Compose

```bash
unzip python-ruby-gpt.zip
cd python-ruby-gpt
docker compose up --build
```

Open:

```text
http://localhost:8080
```

## Run Locally Without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## Flat File Storage

Search records are saved in:

```text
data/*.json
data/latest.json
```

Each record stores:

- input_chat
- gpt_engine
- gpt_model
- complexity
- provider
- source_url
- answer
- created_at

## Recommended Production Upgrade

For best SearXNG reliability, self-host SearXNG and set:

```yaml
environment:
  - SEARXNG_URL=http://searxng:8080
```

Public SearXNG instances can disable JSON or rate-limit requests, so self-hosting is the most reliable option.
