"""Deterministic post-processing for job-search results.

The LLM finds and judges jobs. This module:
- normalizes messy agent output into a stable schema
- applies simple filters (date / work mode / location keywords)
- removes duplicates
- caps and sorts the final list

No LLM calls here.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import config

JOB_FIELDS = (
    "title",
    "company",
    "location",
    "work_mode",
    "experience",
    "posted_date",
    "skills",
    "apply_url",
    "source_url",
    "relevance_reason",
    "verified",
)

CRITERIA_FIELDS = ("role", "location", "work_mode", "experience", "posted_within")


def empty_result(criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "search_criteria": _normalize_criteria(criteria or {}),
        "jobs": [],
    }


def parse_agent_output(raw: Any) -> dict[str, Any]:
    """Turn agent return value (str / dict / other) into a Python dict if possible."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raw = str(raw)

    text = raw.strip()
    # Prefer fenced JSON if the model wrapped it
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def finalize(raw: Any, user_query: str = "") -> dict[str, Any]:
    """Main entry: parse → normalize → filter → dedupe → shape."""
    data = parse_agent_output(raw)
    criteria = _normalize_criteria(data.get("search_criteria") or data.get("criteria") or {})
    if not any(criteria.values()) and user_query:
        criteria = _guess_criteria_from_query(user_query)

    jobs_raw = data.get("jobs") or data.get("results") or []
    if not isinstance(jobs_raw, list):
        jobs_raw = []

    jobs: list[dict[str, Any]] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        job = _normalize_job(item)
        if not job.get("title"):
            continue
        if not _passes_filters(job, criteria):
            continue
        jobs.append(job)

    jobs = _dedupe(jobs)
    jobs = _sort_jobs(jobs)
    jobs = jobs[: config.MAX_JOBS]

    return {"search_criteria": criteria, "jobs": jobs}


def _normalize_criteria(raw: dict[str, Any]) -> dict[str, str]:
    out = {k: "" for k in CRITERIA_FIELDS}
    if not isinstance(raw, dict):
        return out
    aliases = {
        "role": ("role", "title", "job_title", "position"),
        "location": ("location", "loc", "place"),
        "work_mode": ("work_mode", "workmode", "remote", "mode"),
        "experience": ("experience", "exp", "years"),
        "posted_within": ("posted_within", "posted", "recency", "within"),
    }
    for key, names in aliases.items():
        for name in names:
            val = raw.get(name)
            if val is not None and str(val).strip():
                out[key] = str(val).strip()
                break
    if not out["posted_within"]:
        out["posted_within"] = f"last {config.DEFAULT_POSTED_WITHIN_DAYS} days"
    return out


def _normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
    job: dict[str, Any] = {k: None for k in JOB_FIELDS}
    for key in JOB_FIELDS:
        if key in raw and raw[key] is not None:
            job[key] = raw[key]

    # Light cleanup
    for text_key in ("title", "company", "location", "work_mode", "experience", "posted_date", "apply_url", "source_url", "relevance_reason"):
        if isinstance(job.get(text_key), str):
            job[text_key] = job[text_key].strip()

    skills = job.get("skills")
    if isinstance(skills, str):
        job["skills"] = [s.strip() for s in re.split(r"[,|;]", skills) if s.strip()]
    elif isinstance(skills, list):
        job["skills"] = [str(s).strip() for s in skills if str(s).strip()]
    else:
        job["skills"] = []

    job["work_mode"] = _normalize_work_mode(job.get("work_mode") or job.get("location") or "")
    job["posted_date"] = _normalize_date(job.get("posted_date"))
    job["verified"] = bool(job.get("verified")) if job.get("verified") is not None else False

    # Prefer apply_url; fall back to source_url
    if not job.get("apply_url") and job.get("source_url"):
        job["apply_url"] = job["source_url"]
    if not job.get("source_url") and job.get("apply_url"):
        job["source_url"] = job["apply_url"]

    return job


def _normalize_work_mode(value: str) -> str:
    text = (value or "").lower()
    if "hybrid" in text:
        return "hybrid"
    if "onsite" in text or "on-site" in text or "in-office" in text or "office" in text:
        return "onsite"
    if "remote" in text or "wfh" in text or "work from home" in text:
        return "remote"
    return (value or "").strip().lower() or "unknown"


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    # Relative phrases: "2 days ago", "posted 1 week ago"
    lower = text.lower()
    m = re.search(r"(\d+)\s*(day|days|week|weeks|hour|hours)\s*ago", lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        today = date.today()
        if unit.startswith("hour"):
            return today.isoformat()
        if unit.startswith("day"):
            return (today - timedelta(days=n)).isoformat()
        if unit.startswith("week"):
            return (today - timedelta(weeks=n)).isoformat()

    if "today" in lower or "just now" in lower or "hours ago" in lower:
        return date.today().isoformat()
    if "yesterday" in lower:
        return (date.today() - timedelta(days=1)).isoformat()

    return text  # keep original if unparsable; filter may skip it


def _posted_within_days(criteria: dict[str, str]) -> int:
    text = (criteria.get("posted_within") or "").lower()
    m = re.search(r"(\d+)", text)
    if m:
        return max(1, int(m.group(1)))
    return config.DEFAULT_POSTED_WITHIN_DAYS


def _passes_filters(job: dict[str, Any], criteria: dict[str, str]) -> bool:
    # Date filter (only when we have a real ISO date)
    posted = job.get("posted_date")
    if posted and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(posted)):
        try:
            posted_d = date.fromisoformat(str(posted))
            cutoff = date.today() - timedelta(days=_posted_within_days(criteria))
            if posted_d < cutoff:
                return False
        except ValueError:
            pass

    # Work mode filter when both sides are known
    want_mode = _normalize_work_mode(criteria.get("work_mode") or "")
    got_mode = _normalize_work_mode(job.get("work_mode") or "")
    if want_mode in {"remote", "hybrid", "onsite"} and got_mode in {"remote", "hybrid", "onsite"}:
        if want_mode != got_mode:
            return False

    # Soft location keyword check (deterministic substring)
    want_loc = (criteria.get("location") or "").lower().strip()
    got_loc = (job.get("location") or "").lower()
    if want_loc and got_loc and want_loc not in {"remote", "anywhere"}:
        # Accept if location text matches OR job is remote (remote often omits city)
        tokens = [t for t in re.split(r"[,\s/|-]+", want_loc) if len(t) > 2]
        if tokens and not any(t in got_loc for t in tokens):
            if got_mode != "remote" and "remote" not in got_loc:
                return False

    return True


def _dedupe(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for job in jobs:
        key = _dedupe_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def _dedupe_key(job: dict[str, Any]) -> str:
    url = (job.get("apply_url") or job.get("source_url") or "").strip().lower()
    if url:
        parsed = urlparse(url)
        return f"url:{parsed.netloc}{parsed.path}".rstrip("/")
    title = (job.get("title") or "").strip().lower()
    company = (job.get("company") or "").strip().lower()
    return f"tc:{title}|{company}"


def _sort_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(job: dict[str, Any]):
        posted = job.get("posted_date") or ""
        # ISO dates sort correctly as strings; unknowns go last
        is_iso = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(posted)))
        return (0 if is_iso else 1, posted if is_iso else "", job.get("title") or "")

    return sorted(jobs, key=sort_key, reverse=False)


def _guess_criteria_from_query(query: str) -> dict[str, str]:
    """Lightweight fallback if the agent forgot to emit search_criteria."""
    q = query.strip()
    criteria = _normalize_criteria({})
    criteria["role"] = q[:120]

    lower = q.lower()
    if "remote" in lower:
        criteria["work_mode"] = "remote"
    elif "hybrid" in lower:
        criteria["work_mode"] = "hybrid"
    elif "onsite" in lower or "on-site" in lower:
        criteria["work_mode"] = "onsite"

    for loc in ("india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "chennai", "usa", "uk", "europe"):
        if loc in lower:
            criteria["location"] = loc.title() if loc != "usa" else "USA"
            break

    exp = re.search(r"(\d+\s*[-–to]+\s*\d+\s*years?|\d+\+?\s*years?|fresher|entry[- ]level)", lower)
    if exp:
        criteria["experience"] = exp.group(0)

    days = re.search(r"(?:last|past|within)\s+(\d+)\s+days?", lower)
    if days:
        criteria["posted_within"] = f"last {days.group(1)} days"
    return criteria


def to_pretty_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)
