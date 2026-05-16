# Python Ruby-GPT User Guide

## 1. Unzip Project

```bash
unzip python-ruby-gpt.zip
cd python-ruby-gpt
```

## 2. Start Docker App

```bash
docker compose up --build
```

## 3. Open Browser

```text
http://localhost:8080
```

## 4. Example Queries

```text
Poem about Life
Winston Churchill Wikipedia
Ruby on Rails official documentation
Open source search engine SearXNG
```

## 5. Complexity Examples

### SHALLOW
Uses Wikipedia only.

### LEVEL
Uses DuckDuckGo HTML.

### DIVE
Uses DuckDuckGo Instant Answer.

### DEEP-DIVE
Uses SearXNG open-source metasearch.

### RECURSIVE
Runs multiple providers, scores results, and returns the best combined answer.

## 6. Stop App

```bash
docker compose down
```

## 7. View Flat File Records

```bash
ls data
cat data/latest.json
```
