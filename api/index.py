import json
import os
import random
import re
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

APP_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = APP_ROOT / "public"
IS_VERCEL = os.getenv("VERCEL") == "1"

# Vercel serverless functions can write only to /tmp.
# Local Docker/local uvicorn keeps flat files in ./data.
DATA_DIR = Path("/tmp/python-ruby-gpt-data") if IS_VERCEL else APP_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Python Ruby-GPT", version="2.0.0")


class SearchRequest(BaseModel):
    input_chat: str = Field(..., min_length=1)
    gpt_engine: str = "CHATGPT"
    gpt_model: str = "gpt-4o"
    complexity: str = "DEEP-DIVE"


def json_response(payload: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)


def fetch_url(url: str, accept: str = "text/html", timeout: int = 12) -> Dict[str, Any]:
    headers = {
        "User-Agent": "Python-RUBY-GPT/2.0 Mozilla/5.0",
        "Accept": accept,
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return {
            "body": response.text or "",
            "status": response.status_code,
            "url": response.url,
            "error": None,
        }
    except requests.RequestException as exc:
        return {"body": "", "status": 0, "url": url, "error": str(exc)}


def clean_text(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html or "", flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    replacements = {
        "&nbsp;": " ", "&amp;": "&", "&quot;": '"', "&#039;": "'", "&rsquo;": "'", "&ldquo;": '"', "&rdquo;": '"'
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return re.sub(r"\s+", " ", html).strip()


def is_bad_url(url: str) -> bool:
    if not url:
        return True
    lowered = url.lower()
    bad_parts = [
        "javascript:", "mailto:", "/preferences", "/settings",
        "duckduckgo.com/y.js", "duckduckgo.com/settings",
        "facebook.com", "instagram.com", "pinterest.",
    ]
    return any(part in lowered for part in bad_parts)


def result_score(result: Dict[str, Any], query: str) -> int:
    score = 0
    title = str(result.get("title", "")).lower()
    snippet = str(result.get("snippet", "")).lower()
    url = str(result.get("url", "")).lower()
    for word in re.split(r"\s+", query.lower()):
        word = word.strip()
        if len(word) < 3:
            continue
        if word in title:
            score += 7
        if word in snippet:
            score += 5
        if word in url:
            score += 2
    if "wikipedia.org" in url:
        score -= 2
    if "youtube.com" in url:
        score -= 2
    return score


def save_flat_file(
    input_chat: str,
    answer: str,
    engine: str,
    model: str,
    complexity: str,
    source_url: Optional[str],
    provider: str,
) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    record_id = f"{timestamp}_{suffix}"
    record = {
        "id": record_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": "vercel" if IS_VERCEL else "local",
        "data_dir": str(DATA_DIR),
        "input_chat": input_chat,
        "gpt_engine": engine,
        "gpt_model": model,
        "complexity": complexity,
        "provider": provider,
        "source_url": source_url,
        "answer": answer,
    }
    (DATA_DIR / f"{record_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def searxng_search(query: str) -> Optional[Dict[str, Any]]:
    instances: List[str] = []
    if os.getenv("SEARXNG_URL"):
        instances.append(os.getenv("SEARXNG_URL", "").rstrip("/"))
    instances.extend([
        "https://search.inetol.net",
        "https://searx.be",
        "https://search.sapti.me",
        "https://opnxng.com",
    ])
    results: List[Dict[str, Any]] = []
    for instance in instances:
        url = f"{instance}/search?q={quote(query)}&format=json&language=en&safesearch=0&categories=general"
        response = fetch_url(url, "application/json", 10)
        if response["status"] != 200 or not response["body"]:
            continue
        try:
            payload = json.loads(response["body"])
        except json.JSONDecodeError:
            continue
        for item in payload.get("results", []):
            result_url = item.get("url", "")
            if is_bad_url(result_url):
                continue
            candidate = {
                "provider": "SearXNG Open Source Metasearch",
                "title": str(item.get("title") or "Untitled result").strip(),
                "url": result_url,
                "snippet": str(item.get("content") or "").strip(),
                "engine": item.get("engine", "unknown"),
            }
            candidate["score"] = result_score(candidate, query)
            results.append(candidate)
        if results:
            break
    if not results:
        return None
    return sorted(results, key=lambda r: r.get("score", 0), reverse=True)[0]


def duckduckgo_instant_answer(query: str) -> Optional[Dict[str, Any]]:
    url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
    response = fetch_url(url, "application/json", 10)
    if response["status"] != 200 or not response["body"]:
        return None
    try:
        payload = json.loads(response["body"])
    except json.JSONDecodeError:
        return None
    abstract = str(payload.get("AbstractText") or "").strip()
    abstract_url = str(payload.get("AbstractURL") or "").strip()
    heading = str(payload.get("Heading") or query).strip()
    if abstract and abstract_url:
        candidate = {"provider": "DuckDuckGo Instant Answer", "title": heading, "url": abstract_url, "snippet": abstract}
        candidate["score"] = result_score(candidate, query)
        return candidate
    for topic in payload.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
            candidate = {
                "provider": "DuckDuckGo Instant Answer Related Topic",
                "title": heading,
                "url": topic["FirstURL"],
                "snippet": topic["Text"],
            }
            candidate["score"] = result_score(candidate, query)
            return candidate
    return None


def duckduckgo_html_search(query: str) -> Optional[Dict[str, Any]]:
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    response = fetch_url(url, "text/html", 12)
    if response["status"] >= 400 or not response["body"]:
        return None
    matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', response["body"], flags=re.I | re.S)
    results: List[Dict[str, Any]] = []
    for raw_url, raw_title in matches:
        result_url = raw_url.replace("&amp;", "&")
        if "uddg=" in result_url:
            parsed = urlparse(result_url)
            qs = parse_qs(parsed.query)
            if qs.get("uddg"):
                result_url = unquote(qs["uddg"][0])
        if is_bad_url(result_url):
            continue
        candidate = {
            "provider": "DuckDuckGo HTML Search",
            "title": clean_text(raw_title),
            "url": result_url,
            "snippet": "DuckDuckGo returned this open web result.",
        }
        candidate["score"] = result_score(candidate, query)
        results.append(candidate)
    if not results:
        return None
    return sorted(results, key=lambda r: r.get("score", 0), reverse=True)[0]


def wikipedia_fallback(query: str) -> Optional[Dict[str, Any]]:
    search_url = "https://en.wikipedia.org/w/api.php?action=query" + f"&list=search&srsearch={quote(query)}&format=json&utf8=1&srlimit=5"
    response = fetch_url(search_url, "application/json", 10)
    if response["status"] >= 400 or not response["body"]:
        return None
    try:
        payload = json.loads(response["body"])
    except json.JSONDecodeError:
        return None
    search_results = payload.get("query", {}).get("search", [])
    if not search_results:
        return None
    candidates: List[Dict[str, Any]] = []
    for item in search_results:
        title = item.get("title", "")
        candidate = {
            "provider": "Wikipedia Fallback Search",
            "title": title,
            "snippet": clean_text(item.get("snippet", "")),
            "url": "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")),
        }
        candidate["score"] = result_score(candidate, query)
        candidates.append(candidate)
    best = sorted(candidates, key=lambda r: r.get("score", 0), reverse=True)[0]
    summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(best["title"].replace(" ", "_"))
    summary = fetch_url(summary_url, "application/json", 10)
    try:
        summary_payload = json.loads(summary["body"]) if summary["body"] else {}
    except json.JSONDecodeError:
        summary_payload = {}
    extract = str(summary_payload.get("extract") or best.get("snippet") or "").strip()
    if extract:
        best["snippet"] = extract
    return best


def recursive_search(query: str) -> Optional[Dict[str, Any]]:
    providers: List[Callable[[str], Optional[Dict[str, Any]]]] = [
        searxng_search,
        duckduckgo_html_search,
        duckduckgo_instant_answer,
        wikipedia_fallback,
    ]
    results: List[Dict[str, Any]] = []
    for provider in providers:
        result = provider(query)
        if result and result.get("url"):
            result["score"] = result_score(result, query)
            results.append(result)
    if not results:
        return None
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    best = dict(results[0])
    combined = "RECURSIVE MULTI-PROVIDER SEARCH RESULTS\n\n"
    for index, result in enumerate(results, start=1):
        combined += f"{index}. {result['provider']}\n"
        combined += f"Title: {result['title']}\n"
        combined += f"URL: {result['url']}\n"
        combined += f"Snippet: {result['snippet']}\n\n"
    best["provider"] = "Recursive Multi-Provider Search"
    best["snippet"] = combined
    return best


def fetch_page_extract(url: str) -> str:
    response = fetch_url(url, "text/html", 10)
    if response["status"] >= 400 or not response["body"]:
        return ""
    text = clean_text(response["body"])
    return text[:3000] + ("..." if len(text) > 3000 else "")


def select_provider(query: str, complexity: str) -> Optional[Dict[str, Any]]:
    mapping: Dict[str, Callable[[str], Optional[Dict[str, Any]]]] = {
        "DEEP-DIVE": searxng_search,
        "DIVE": duckduckgo_instant_answer,
        "LEVEL": duckduckgo_html_search,
        "SHALLOW": wikipedia_fallback,
        "RECURSIVE": recursive_search,
    }
    return mapping.get(complexity.upper(), searxng_search)(query)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index_file = PUBLIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>Python Ruby-GPT is running</h1>"


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": "Python Ruby-GPT",
        "platform": "vercel" if IS_VERCEL else "local",
        "data_dir": str(DATA_DIR),
    }


@app.post("/api/search")
def search(request: SearchRequest) -> JSONResponse:
    input_chat = request.input_chat.strip()
    complexity = request.complexity.strip().upper()
    result = select_provider(input_chat, complexity)
    if not result:
        answer = (
            "ERROR:\n"
            "No useful result was found for this selected complexity.\n\n"
            f"Selected Complexity: {complexity}\n\n"
            "Search Mapping:\n"
            "- DEEP-DIVE = SearXNG Open Source Metasearch\n"
            "- DIVE = DuckDuckGo Instant Answer\n"
            "- LEVEL = DuckDuckGo HTML Search\n"
            "- SHALLOW = Wikipedia Fallback Search\n"
            "- RECURSIVE = Multi-provider aggregate search\n\n"
            f"Original query: {input_chat}"
        )
        record = save_flat_file(input_chat, answer, request.gpt_engine, request.gpt_model, complexity, None, "NONE")
        return json_response({"success": False, "answer": answer, "record": record})
    page_extract = fetch_page_extract(result["url"])
    answer = (
        "PYTHON RUBY-GPT INTERNET SEARCH ANSWER\n\n"
        f"Query: {input_chat}\n"
        f"Selected Complexity: {complexity}\n"
        f"Search Provider: {result['provider']}\n"
        f"Platform: {'Vercel Serverless' if IS_VERCEL else 'Local/Docker'}\n"
        f"Engine Selected: {request.gpt_engine}\n"
        f"Model Selected: {request.gpt_model}\n\n"
        f"Title:\n{result['title']}\n\n"
        f"Source URL:\n{result['url']}\n\n"
        f"Search Snippet:\n{result['snippet']}\n\n"
    )
    if page_extract:
        answer += "Extracted Page Content:\n\n" + page_extract
    else:
        answer += "Extracted Page Content:\n\nThe result was found, but Python Ruby-GPT could not extract readable page content. Use the Source URL above."
    record = save_flat_file(input_chat, answer, request.gpt_engine, request.gpt_model, complexity, result["url"], result["provider"])
    return json_response({
        "success": True,
        "answer": answer,
        "source_url": result["url"],
        "provider": result["provider"],
        "complexity": complexity,
        "record": record,
    })


@app.get("/api/history")
def history() -> JSONResponse:
    records: List[Dict[str, Any]] = []
    for path in DATA_DIR.glob("*.json"):
        if path.name == "latest.json":
            continue
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return json_response({
        "success": True,
        "platform": "vercel" if IS_VERCEL else "local",
        "note": "On Vercel, flat-file history is stored in /tmp and is ephemeral between cold starts.",
        "records": records,
    })


# Vercel rewrites can send any GET path here. Return the SPA for unknown browser routes.
@app.get("/{path:path}", response_class=HTMLResponse)
def catch_all(path: str) -> str:
    if path.startswith("api/"):
        return "<h1>API route not found</h1>"
    return home()
