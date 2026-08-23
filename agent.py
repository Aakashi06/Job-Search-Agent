"""Job Search Agent — fast local pipeline (~10s target).

1. Python: DuckDuckGo search
2. Python: fetch a couple of pages (short timeout)
3. Tiny local LLM (optional, hard timeout): extract JSON jobs
4. Fallback: show search hits immediately if the LLM is slow/fails
5. Python post-process: filter / dedupe / format
"""

from __future__ import annotations

import re
import threading
from typing import Any, Generator
from urllib.parse import urlparse

import requests

import config
import postprocess

_model = None
_tokenizer = None

EXTRACT_PROMPT = """List up to {max_jobs} jobs as JSON only:
{{"search_criteria":{{"role":"{role}","location":"{location}","work_mode":"{work_mode}","experience":"{experience}","posted_within":"{posted_within}"}},"jobs":[{{"title":"","company":"","location":"","work_mode":"","experience":"","posted_date":"","skills":[],"apply_url":"","source_url":"","relevance_reason":"","verified":true}}]}}

Request: {query}

Data:
{pages}
"""


def preload_model() -> None:
    get_model()


def get_model():
    global _model, _tokenizer
    if _model is not None and _tokenizer is not None:
        return _tokenizer, _model

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _tokenizer = AutoTokenizer.from_pretrained(config.MODEL_ID)
    _model = AutoModelForCausalLM.from_pretrained(
        config.MODEL_ID,
        dtype=torch.float32,
        device_map="cpu",
        low_cpu_mem_usage=True,
    )
    _model.eval()
    return _tokenizer, _model


def run_job_search(
    query: str,
    criteria: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    query = (query or "").strip()
    if not query:
        yield {"type": "status", "phase": "error", "message": "Please enter a job search request."}
        yield {"type": "result", "data": postprocess.empty_result()}
        return

    criteria = criteria or {}
    role = criteria.get("role") or "relevant"
    location = criteria.get("location") or "Anywhere"
    work_mode = criteria.get("work_mode") or "any"
    experience = criteria.get("experience") or "any"
    posted_within = (
        criteria.get("posted_within")
        or f"last {config.DEFAULT_POSTED_WITHIN_DAYS} days"
    )

    yield {"type": "status", "phase": "thinking", "message": "Thinking"}
    yield {"type": "log", "message": f"Query: {query}"}

    yield {"type": "status", "phase": "searching", "message": "Searching"}
    search_hits = _web_search(_build_search_string(query, criteria))
    yield {"type": "log", "message": f"Hits: {len(search_hits)}"}

    if not search_hits:
        result = postprocess.empty_result(criteria)
        yield {"type": "status", "phase": "done", "message": "No listings found."}
        yield {"type": "result", "data": result}
        return

    yield {"type": "status", "phase": "reading", "message": "Reading"}
    pages = _fetch_pages(search_hits[: config.PAGES_TO_READ])
    pages_blob = _format_pages(pages) if pages else _format_search_only(search_hits)

    yield {"type": "status", "phase": "thinking", "message": "Matching"}
    raw = _llm_extract_timed(
        query=query,
        role=role,
        location=location,
        work_mode=work_mode,
        experience=experience,
        posted_within=posted_within,
        pages=pages_blob,
        timeout=config.LLM_TIMEOUT_SECONDS,
    )

    used_fallback = raw is None
    if used_fallback:
        yield {"type": "log", "message": "Using fast search results"}
        raw = _fallback_from_hits(search_hits, criteria)

    yield {"type": "status", "phase": "refining", "message": "Refining"}
    result = postprocess.finalize(raw, user_query=query)

    if not result.get("jobs"):
        result = postprocess.finalize(
            _fallback_from_hits(search_hits, criteria),
            user_query=query,
        )

    if criteria:
        sc = result.get("search_criteria") or {}
        for key, value in criteria.items():
            if value and not sc.get(key):
                sc[key] = value
        result["search_criteria"] = sc

    n = len(result.get("jobs") or [])
    yield {
        "type": "status",
        "phase": "done",
        "message": f"Found {n} matching job{'s' if n != 1 else ''}.",
    }
    yield {"type": "result", "data": result}


def _build_search_string(query: str, criteria: dict[str, Any]) -> str:
    bits = [query]
    for key in ("role", "location", "work_mode"):
        val = criteria.get(key)
        if val and str(val).lower() not in query.lower():
            bits.append(str(val).split(",")[0].strip())
    bits.append("job apply")
    return " ".join(bits)


def _web_search(q: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore

        with DDGS() as ddgs:
            for item in ddgs.text(q, max_results=config.SEARCH_RESULTS):
                url = (item.get("href") or item.get("link") or "").strip()
                title = (item.get("title") or "").strip()
                body = (item.get("body") or item.get("snippet") or "").strip()
                if url and title:
                    hits.append({"title": title, "url": url, "snippet": body})
    except Exception:
        return hits
    return hits


def _fetch_pages(hits: list[dict[str, str]]) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    for hit in hits:
        try:
            resp = requests.get(hit["url"], headers=headers, timeout=2.5)
            resp.raise_for_status()
            text = _html_to_text(resp.text)[: config.PAGE_CHAR_LIMIT]
            if len(text) < 60:
                continue
            pages.append({"title": hit["title"], "url": hit["url"], "text": text})
        except Exception:
            continue
    return pages


def _html_to_text(html: str) -> str:
    try:
        from markdownify import markdownify as md

        return md(html, heading_style="ATX", strip=["script", "style", "nav", "footer"])
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _format_pages(pages: list[dict[str, str]]) -> str:
    blocks = []
    for i, p in enumerate(pages, 1):
        blocks.append(f"[{i}] {p['title']}\nURL: {p['url']}\n{p['text']}\n")
    return "\n".join(blocks)[:2800]


def _format_search_only(hits: list[dict[str, str]]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(
            f"[{i}] {h['title']}\nURL: {h['url']}\n{h.get('snippet', '')}\n"
        )
    return "\n".join(blocks)


def _llm_extract_timed(**kwargs) -> str | None:
    timeout = float(kwargs.pop("timeout", config.LLM_TIMEOUT_SECONDS))
    box: dict[str, Any] = {"text": None, "error": None}

    def worker() -> None:
        try:
            box["text"] = _llm_extract(**kwargs)
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or box["text"] is None:
        return None
    return box["text"]


def _llm_extract(
    *,
    query: str,
    role: str,
    location: str,
    work_mode: str,
    experience: str,
    posted_within: str,
    pages: str,
) -> str:
    tokenizer, model = get_model()
    import torch

    prompt = EXTRACT_PROMPT.format(
        query=query,
        role=role,
        location=location,
        work_mode=work_mode,
        experience=experience,
        posted_within=posted_within,
        max_jobs=config.MAX_JOBS,
        pages=pages[:2500],
    )

    messages = [{"role": "user", "content": prompt}]
    try:
        chat_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        chat_text = prompt

    encoded = tokenizer(chat_text, return_tensors="pt", truncation=True, max_length=1024)
    input_ids = encoded["input_ids"]

    with torch.inference_mode():
        output = model.generate(
            input_ids,
            max_new_tokens=config.MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = output[0][input_ids.shape[-1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def _fallback_from_hits(
    hits: list[dict[str, str]],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    jobs = []
    for hit in hits[: config.MAX_JOBS]:
        host = urlparse(hit["url"]).netloc.replace("www.", "")
        jobs.append(
            {
                "title": hit["title"],
                "company": host or "Unknown",
                "location": criteria.get("location") or "",
                "work_mode": criteria.get("work_mode") or "",
                "experience": criteria.get("experience") or "",
                "posted_date": None,
                "skills": [],
                "apply_url": hit["url"],
                "source_url": hit["url"],
                "relevance_reason": hit.get("snippet") or "From web search results.",
                "verified": False,
            }
        )
    return {
        "search_criteria": {
            "role": criteria.get("role") or "",
            "location": criteria.get("location") or "",
            "work_mode": criteria.get("work_mode") or "",
            "experience": criteria.get("experience") or "",
            "posted_within": criteria.get("posted_within")
            or f"last {config.DEFAULT_POSTED_WITHIN_DAYS} days",
        },
        "jobs": jobs,
    }
