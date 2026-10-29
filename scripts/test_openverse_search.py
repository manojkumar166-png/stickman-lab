#!/usr/bin/env python3
"""Small, rate-limited Openverse smoke test; does not render a video."""
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openverse.org/v1/images/"
MAX_WORKERS = 3
MAX_RETRIES = 3
TIMEOUT_SECONDS = 15
QUERIES = [
    "cartoon illustration person sleeping in bed",
    "cartoon illustration human brain",
    "REM sleep scientific illustration",
    "cartoon dream thought bubble",
    "sleeping person colorful cartoon",
]

def search(query):
    params = urllib.parse.urlencode({
        "q": query,
        "category": "illustration",
        "page_size": 5,
        "license": "by,by-sa,by-nc,by-nc-sa,by-nd,by-nc-nd,pdm,cc0",
    })
    request = urllib.request.Request(
        API + "?" + params,
        headers={"User-Agent": "stickman-lab-openverse-smoke-test/1.0"},
    )
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            results = payload.get("results", [])
            compact = [{
                "title": item.get("title"),
                "creator": item.get("creator"),
                "license": item.get("license"),
                "license_version": item.get("license_version"),
                "license_url": item.get("license_url"),
                "foreign_landing_url": item.get("foreign_landing_url"),
                "thumbnail": item.get("thumbnail"),
                "width": item.get("width"),
                "height": item.get("height"),
                "category": item.get("category"),
            } for item in results]
            return {"query": query, "count": len(compact), "results": compact, "error": None}
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES:
                delay = exc.headers.get("Retry-After")
                try:
                    wait = min(60, max(1, int(delay))) if delay else 2 ** attempt
                except ValueError:
                    wait = 2 ** attempt
                time.sleep(wait)
                continue
            return {"query": query, "count": 0, "results": [], "error": f"HTTP {exc.code}"}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return {"query": query, "count": 0, "results": [], "error": str(exc)}
    return {"query": query, "count": 0, "results": [], "error": "retry limit reached"}

def main():
    # Deduplicate normalized queries before spending API requests.
    queries = list(dict.fromkeys(" ".join(q.lower().split()) for q in QUERIES))
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(search, queries))
    out = Path("output/openverse-smoke-test.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(f'{result["query"]}: {result["count"]} candidates' +
              (f' (ERROR: {result["error"]})' if result["error"] else ""))
    failures = [r for r in results if r["error"] or not r["results"]]
    if failures:
        raise SystemExit(
            f"Openverse smoke test failed for {len(failures)} of {len(results)} queries. "
            f"Inspect {out}; no video rendering was started."
        )
    print(f"Smoke test passed: {len(results)} queries, at most {MAX_WORKERS} concurrent requests.")
    print("Note: metadata results still require visual relevance and licence review.")

if __name__ == "__main__":
    main()
