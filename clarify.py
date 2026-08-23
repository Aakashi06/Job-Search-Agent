"""Preference clarification before job search.

Missing slots are asked as multiple-choice only (no free-text answers).
"""

from __future__ import annotations

import re
from typing import Any

import config

REQUIRED_SLOTS = ("role", "experience", "work_mode", "location")

ROLE_OPTIONS = [
    {"value": "AI Engineer", "label": "AI Engineer"},
    {"value": "ML Engineer", "label": "ML Engineer"},
    {"value": "Data Scientist", "label": "Data Scientist"},
    {"value": "Software Engineer", "label": "Software Engineer"},
    {"value": "Backend Developer", "label": "Backend Developer"},
    {"value": "Frontend Developer", "label": "Frontend Developer"},
    {"value": "Full Stack Developer", "label": "Full Stack Developer"},
    {"value": "Python Developer", "label": "Python Developer"},
    {"value": "Data Engineer", "label": "Data Engineer"},
    {"value": "DevOps Engineer", "label": "DevOps Engineer"},
    {"value": "Product Manager", "label": "Product Manager"},
    {"value": "QA Engineer", "label": "QA Engineer"},
    {"value": "Mobile Developer", "label": "Mobile Developer"},
    {"value": "Cloud Engineer", "label": "Cloud Engineer"},
]

EXPERIENCE_OPTIONS = [
    {"value": "fresher", "label": "Fresher / Intern"},
    {"value": "0-1 years", "label": "0–1 years"},
    {"value": "0-2 years", "label": "0–2 years"},
    {"value": "1-3 years", "label": "1–3 years"},
    {"value": "2-4 years", "label": "2–4 years"},
    {"value": "3-5 years", "label": "3–5 years"},
    {"value": "5-8 years", "label": "5–8 years"},
    {"value": "8+ years", "label": "8+ years"},
]

WORK_MODE_OPTIONS = [
    {"value": "remote", "label": "Remote"},
    {"value": "hybrid", "label": "Hybrid"},
    {"value": "onsite", "label": "Onsite"},
    {"value": "any", "label": "Any"},
]

LOCATION_OPTIONS = [
    {"value": "India", "label": "India"},
    {"value": "Bangalore", "label": "Bangalore"},
    {"value": "Hyderabad", "label": "Hyderabad"},
    {"value": "Pune", "label": "Pune"},
    {"value": "Mumbai", "label": "Mumbai"},
    {"value": "Delhi NCR", "label": "Delhi NCR"},
    {"value": "Chennai", "label": "Chennai"},
    {"value": "Kolkata", "label": "Kolkata"},
    {"value": "Ahmedabad", "label": "Ahmedabad"},
    {"value": "USA", "label": "USA"},
    {"value": "UK", "label": "UK"},
    {"value": "Canada", "label": "Canada"},
    {"value": "Germany", "label": "Germany"},
    {"value": "Singapore", "label": "Singapore"},
    {"value": "Anywhere", "label": "Anywhere"},
]

OTHER_OPTION = {"value": "__other__", "label": "Other"}

QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "role": {
        "id": "role",
        "prompt": "Role",
        "input": "choice",
        "options": ROLE_OPTIONS,
        "required": True,
        "multi": True,
        "other_placeholder": "e.g. NLP Engineer",
    },
    "experience": {
        "id": "experience",
        "prompt": "Experience",
        "input": "choice",
        "options": EXPERIENCE_OPTIONS,
        "required": True,
        "multi": False,
        "other_placeholder": "e.g. 4 years",
    },
    "work_mode": {
        "id": "work_mode",
        "prompt": "Work mode",
        "input": "choice",
        "options": WORK_MODE_OPTIONS,
        "required": True,
        "multi": True,
        "other_placeholder": "e.g. remote-first",
    },
    "location": {
        "id": "location",
        "prompt": "Location",
        "input": "choice",
        "options": LOCATION_OPTIONS,
        "required": True,
        "multi": True,
        "other_placeholder": "City or country",
    },
}


def clarify(query: str, answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return whether we can search, plus multiple-choice questions if needed."""
    answers = _normalize_answers(answers or {})
    extracted = extract_preferences(query)
    criteria = {**extracted, **answers}

    # Vague role extracts (e.g. "Ai") → force a clear choice
    if criteria.get("role") and not _is_solid_role(str(criteria["role"]).split(",")[0].strip()):
        # Keep multi roles if any part is solid
        parts = [p.strip() for p in str(criteria["role"]).split(",") if p.strip()]
        solid = [p for p in parts if _is_solid_role(p)]
        if solid:
            criteria["role"] = ", ".join(solid)
        else:
            criteria.pop("role", None)

    missing_required = [s for s in REQUIRED_SLOTS if not criteria.get(s)]

    if missing_required:
        questions = [_question_payload(s, query=query, criteria=criteria) for s in missing_required]
        return {
            "ready": False,
            "message": "Refine your search",
            "criteria": criteria,
            "questions": questions,
            "pending_slot": None,
            "search_query": "",
        }

    if not criteria.get("posted_within"):
        criteria["posted_within"] = f"last {config.DEFAULT_POSTED_WITHIN_DAYS} days"

    search_query = build_search_query(query, criteria)
    return {
        "ready": True,
        "message": "Searching",
        "criteria": criteria,
        "questions": [],
        "pending_slot": None,
        "search_query": search_query,
    }


def _normalize_answers(raw: dict[str, Any]) -> dict[str, str]:
    """Accept str or list values; store multi picks as comma-separated text."""
    out: dict[str, str] = {}
    for key, val in raw.items():
        if val is None:
            continue
        if isinstance(val, list):
            parts = [str(v).strip() for v in val if str(v).strip() and str(v).strip() != "__other__"]
            if parts:
                out[key] = ", ".join(parts)
            continue
        text = str(val).strip()
        if text and text != "__other__":
            out[key] = text
    return out


def extract_preferences(query: str) -> dict[str, str]:
    """Pull known preference slots out of free-text (deterministic)."""
    q = (query or "").strip()
    lower = q.lower()
    out: dict[str, str] = {}

    if re.search(r"\bremote\b|\bwfh\b|work from home", lower):
        out["work_mode"] = "remote"
    elif re.search(r"\bhybrid\b", lower):
        out["work_mode"] = "hybrid"
    elif re.search(r"\bonsite\b|\bon-site\b|\bin-office\b", lower):
        out["work_mode"] = "onsite"

    # Map experience phrases onto our MCQ values
    if re.search(r"\bfresher\b|\bintern(?:ship)?\b|\bentry[- ]level\b", lower):
        out["experience"] = "fresher"
    else:
        exp = re.search(r"(\d+)\s*[-–to]{1,3}\s*(\d+)\s*years?", lower)
        if exp:
            lo, hi = int(exp.group(1)), int(exp.group(2))
            out["experience"] = _nearest_experience(lo, hi)
        else:
            single = re.search(r"(\d+)\+?\s*years?", lower)
            if single:
                n = int(single.group(1))
                out["experience"] = _nearest_experience(n, n)

    days = re.search(r"(?:last|past|within)\s+(\d+)\s+days?", lower)
    if days:
        out["posted_within"] = f"last {days.group(1)} days"
    elif re.search(r"\bthis week\b|\bpast week\b", lower):
        out["posted_within"] = "last 7 days"

    loc_map = [
        ("delhi ncr", "Delhi NCR"),
        ("bangalore", "Bangalore"),
        ("bengaluru", "Bangalore"),
        ("hyderabad", "Hyderabad"),
        ("gurgaon", "Delhi NCR"),
        ("gurugram", "Delhi NCR"),
        ("noida", "Delhi NCR"),
        ("mumbai", "Mumbai"),
        ("pune", "Pune"),
        ("chennai", "Chennai"),
        ("india", "India"),
        ("united states", "USA"),
        ("usa", "USA"),
        ("united kingdom", "UK"),
        ("uk", "UK"),
        ("anywhere", "Anywhere"),
    ]
    for needle, pretty in loc_map:
        if needle in lower:
            out["location"] = pretty
            break

    role = _extract_role(q, lower)
    if role:
        # Prefer canonical MCQ value when close
        out["role"] = _match_role_option(role) or role

    return out


def build_search_query(original: str, criteria: dict[str, str]) -> str:
    role = criteria.get("role") or "relevant"
    parts = [f"Find {role} jobs"]

    mode = (criteria.get("work_mode") or "").strip()
    if mode and mode.lower() != "any":
        modes = [m.strip() for m in mode.split(",") if m.strip() and m.strip().lower() != "any"]
        if modes:
            parts.append(f"that are {' or '.join(modes)}")

    loc = (criteria.get("location") or "").strip()
    if loc:
        locs = [x.strip() for x in loc.split(",") if x.strip()]
        if locs:
            parts.append(f"in {' or '.join(locs)}")

    if criteria.get("experience"):
        parts.append(f"for {criteria['experience']} of experience")
    if criteria.get("posted_within"):
        parts.append(f"posted within the {criteria['posted_within']}")

    composed = " ".join(parts) + "."
    original = (original or "").strip()
    if original and original.lower() not in composed.lower():
        return f"{composed} Extra context from the user: {original}"
    return composed


def _nearest_experience(lo: int, hi: int) -> str:
    mid = (lo + hi) / 2
    if mid < 0.5:
        return "fresher"
    if mid <= 1:
        return "0-1 years"
    if mid <= 2:
        return "0-2 years"
    if mid <= 3.5:
        return "1-3 years"
    if mid <= 4.5:
        return "2-4 years"
    if mid <= 6.5:
        return "3-5 years"
    if mid <= 8:
        return "5-8 years"
    return "8+ years"


def _is_solid_role(role: str) -> bool:
    text = (role or "").strip()
    if len(text) < 4:
        return False
    # Single token acronyms / stubs
    if text.lower() in {"ai", "ml", "ds", "sde", "swe", "dev", "job", "jobs", "role"}:
        return False
    return True


def _match_role_option(role: str) -> str | None:
    lower = role.lower().strip()
    for opt in ROLE_OPTIONS:
        if opt["value"].lower() == lower or opt["label"].lower() == lower:
            return opt["value"]
    # Fuzzy contains
    for opt in ROLE_OPTIONS:
        v = opt["value"].lower()
        if lower in v or v in lower:
            return opt["value"]
    aliases = {
        "ai": "AI Engineer",
        "artificial intelligence": "AI Engineer",
        "machine learning": "ML Engineer",
        "ml": "ML Engineer",
        "data science": "Data Scientist",
        "backend": "Backend Developer",
        "frontend": "Frontend Developer",
        "full stack": "Full Stack Developer",
        "fullstack": "Full Stack Developer",
        "python": "Python Developer",
        "devops": "DevOps Engineer",
        "sde": "Software Engineer",
        "software": "Software Engineer",
    }
    for key, val in aliases.items():
        if key in lower:
            return val
    return None


def _extract_role(q: str, lower: str) -> str:
    patterns = [
        r"(?:find|looking for|search for|want|need)\s+(?:a |an |some )?(.+?)\s+jobs?",
        r"(.+?)\s+jobs?\b",
        r"(.+?)\s+roles?\b",
        r"(.+?)\s+positions?\b",
    ]
    noise = {
        "remote", "hybrid", "onsite", "on-site", "fresh", "fresher",
        "entry-level", "entry level", "the", "a", "an", "some", "good", "best", "latest",
    }
    for pat in patterns:
        m = re.search(pat, lower)
        if not m:
            continue
        raw = m.group(1).strip(" .,")
        tokens = [t for t in re.split(r"\s+", raw) if t and t not in noise]
        cut = []
        for t in tokens:
            if t in {"in", "for", "with", "posted", "within", "last", "past", "from"}:
                break
            if re.match(r"\d", t):
                break
            cut.append(t)
        role = " ".join(cut).strip(" -")
        if 2 <= len(role) <= 60 and role not in noise:
            return role.title() if role.islower() else role
    return ""


def _question_payload(slot: str, query: str = "", criteria: dict[str, str] | None = None) -> dict[str, Any]:
    spec = QUESTION_SPECS[slot]
    options = list(spec.get("options") or [])

    if slot == "role":
        hint = _match_role_option(query) or _match_role_option((criteria or {}).get("role", ""))
        if hint:
            options = sorted(options, key=lambda o: 0 if o["value"] == hint else 1)

    # Always offer Other so users can type a custom value
    if not any(o.get("value") == "__other__" for o in options):
        options = options + [OTHER_OPTION]

    return {
        "id": spec["id"],
        "prompt": spec["prompt"],
        "input": "choice",
        "placeholder": "",
        "other_placeholder": spec.get("other_placeholder", "Type your answer"),
        "options": options,
        "required": bool(spec.get("required", True)),
        "multi": bool(spec.get("multi", False)),
    }
