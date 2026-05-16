import json
import os
import random
import re
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, parse_qs, urlparse

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Python Ruby-GPT", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class SearchRequest(BaseModel):
    input_chat: str = Field(..., min_length=1)
    gpt_engine: str = "CHATGPT"
    gpt_model: str = "gpt-4o"
    complexity: str = "DEEP-DIVE"


def fetch_url(url: str, accept: str = "text/html", timeout: int = 15) -> Dict[str, Any]:
    headers = {
        "User-Agent": "Python-RUBY-GPT/1.0 Mozilla/5.0",
        "Accept": accept,
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return {
            "body": response.text,
            "status": response.status_code,
            "url": response.url,
            "error": None,
        }
    except requests.RequestException as exc:
        return {"body": "", "status": 0, "url": url, "error": str(exc)}


def clean_text(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", html)
    return text.strip()


def is_bad_url(url: str) -> bool:
    if not url:
        return True
    bad_parts = [
        "javascript:",
        "mailto:",
        "/preferences",
        "/settings",
        "duckduckgo.com/y.js",
        "duckduckgo.com/settings",
        "facebook.com",
        "instagram.com",
        "pinterest.",
    ]
    lowered = url.lower()
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
            score += 6
        if word in snippet:
            score += 4
        if word in url:
            score += 2

    if "wikipedia.org" in url:
        score -= 2
    if "youtube.com" in url:
        score -= 2
    return score


def save_flat_file(input_chat: str, answer: str, engine: str, model: str, complexity: str, source_url: Optional[str], provider: str) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    record_id = f"{timestamp}_{suffix}"

    record = {
        "id": record_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
    env_instance = os.getenv("SEARXNG_URL")
    if env_instance:
        instances.append(env_instance.rstrip("/"))
    instances.extend([
        "https://search.inetol.net",
        "https://searx.be",
        "https://search.sapti.me",
        "https://opnxng.com",
    ])

    results: List[Dict[str, Any]] = []
    for instance in instances:
        url = f"{instance}/search?q={quote(query)}&format=json&language=en&safesearch=0&categories=general"
        response = fetch_url(url, "application/json", 12)
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
                "title": item.get("title", "Untitled result").strip(),
                "url": result_url,
                "snippet": item.get("content", "").strip(),
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
    response = fetch_url(url, "application/json", 12)
    if response["status"] != 200 or not response["body"]:
        return None
    try:
        payload = json.loads(response["body"])
    except json.JSONDecodeError:
        return None

    abstract = payload.get("AbstractText", "").strip()
    abstract_url = payload.get("AbstractURL", "").strip()
    heading = payload.get("Heading", "").strip() or query
    if abstract and abstract_url:
        return {
            "provider": "DuckDuckGo Instant Answer",
            "title": heading,
            "url": abstract_url,
            "snippet": abstract,
            "score": result_score({"title": heading, "snippet": abstract, "url": abstract_url}, query),
        }

    for topic in payload.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
            return {
                "provider": "DuckDuckGo Instant Answer Related Topic",
                "title": heading,
                "url": topic["FirstURL"],
                "snippet": topic["Text"],
                "score": result_score({"title": heading, "snippet": topic["Text"], "url": topic["FirstURL"]}, query),
            }
    return None


def duckduckgo_html_search(query: str) -> Optional[Dict[str, Any]]:
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    response = fetch_url(url, "text/html", 15)
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
        title = clean_text(raw_title)
        candidate = {
            "provider": "DuckDuckGo HTML Search",
            "title": title,
            "url": result_url,
            "snippet": "DuckDuckGo returned this open web result.",
        }
        candidate["score"] = result_score(candidate, query)
        results.append(candidate)

    if not results:
        return None
    return sorted(results, key=lambda r: r.get("score", 0), reverse=True)[0]


def wikipedia_fallback(query: str) -> Optional[Dict[str, Any]]:
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query"
        f"&list=search&srsearch={quote(query)}&format=json&utf8=1&srlimit=5"
    )
    response = fetch_url(search_url, "application/json", 12)
    if response["status"] >= 400 or not response["body"]:
        return None
    try:
        payload = json.loads(response["body"])
    except json.JSONDecodeError:
        return None

    search_results = payload.get("query", {}).get("search", [])
    if not search_results:
        return None

    best = None
    best_score = -999
    for item in search_results:
        title = item.get("title", "")
        snippet = clean_text(item.get("snippet", ""))
        candidate = {
            "provider": "Wikipedia Fallback Search",
            "title": title,
            "snippet": snippet,
            "url": "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")),
        }
        score = result_score(candidate, query)
        if score > best_score:
            best_score = score
            best = candidate

    if not best:
        return None

    summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(best["title"].replace(" ", "_"))
    summary = fetch_url(summary_url, "application/json", 12)
    try:
        summary_payload = json.loads(summary["body"]) if summary["body"] else {}
    except json.JSONDecodeError:
        summary_payload = {}
    extract = (summary_payload.get("extract") or best.get("snippet") or "").strip()
    if not extract:
        return None
    best["snippet"] = extract
    best["score"] = best_score
    return best


def recursive_search(query: str) -> Optional[Dict[str, Any]]:
    provider_functions = [searxng_search, duckduckgo_html_search, duckduckgo_instant_answer, wikipedia_fallback]
    results = []
    for provider in provider_functions:
        result = provider(query)
        if result and result.get("url"):
            result["score"] = result_score(result, query)
            results.append(result)
    if not results:
        return None
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    best = results[0]
    combined = "RECURSIVE MULTI-PROVIDER SEARCH RESULTS\n\n"
    for index, result in enumerate(results, start=1):
        combined += f"{index}. {result['provider']}\n"
        combined += f"Title: {result['title']}\n"
        combined += f"URL: {result['url']}\n"
        combined += f"Snippet: {result['snippet']}\n\n"
    best = dict(best)
    best["provider"] = "Recursive Multi-Provider Search"
    best["snippet"] = combined
    return best


def fetch_page_extract(url: str) -> str:
    response = fetch_url(url, "text/html", 15)
    if response["status"] >= 400 or not response["body"]:
        return ""
    text = clean_text(response["body"])
    return text[:3500] + ("..." if len(text) > 3500 else "")


def select_provider(query: str, complexity: str) -> Optional[Dict[str, Any]]:
    mapping = {
        "DEEP-DIVE": searxng_search,
        "DIVE": duckduckgo_instant_answer,
        "LEVEL": duckduckgo_html_search,
        "SHALLOW": wikipedia_fallback,
        "RECURSIVE": recursive_search,
    }
    return mapping.get(complexity, searxng_search)(query)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")


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
        return JSONResponse({"success": False, "answer": answer, "record": record})

    page_extract = fetch_page_extract(result["url"])
    answer = (
        "PYTHON RUBY-GPT INTERNET SEARCH ANSWER\n\n"
        f"Query: {input_chat}\n"
        f"Selected Complexity: {complexity}\n"
        f"Search Provider: {result['provider']}\n"
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
    return JSONResponse({
        "success": True,
        "answer": answer,
        "source_url": result["url"],
        "provider": result["provider"],
        "complexity": complexity,
        "record": record,
    })


@app.get("/api/history")
def history() -> JSONResponse:
    records = []
    for path in DATA_DIR.glob("*.json"):
        if path.name == "latest.json":
            continue
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return JSONResponse(records)
