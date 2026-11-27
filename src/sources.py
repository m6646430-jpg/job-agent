"""Job discovery from public ATS APIs — no scraping, no auth, no captcha.

Greenhouse / Lever / Ashby publish full job boards as JSON. Remotive gives
cross-company keyword search; its results often link back to those same ATSes.
"""

import html
import re

import requests

UA = {"User-Agent": "job-agent/1.0 (personal job search)"}
TIMEOUT = 30


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def greenhouse_jobs(board: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "job_id": f"greenhouse:{j['id']}",
            "source": "greenhouse",
            "company": board,
            "title": j["title"],
            "location": (j.get("location") or {}).get("name", ""),
            "url": j["absolute_url"],
            "apply_url": j["absolute_url"],
            "jd_text": _strip_html(j.get("content", "")),
        })
    return out


def lever_jobs(company: str) -> list:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json():
        out.append({
            "job_id": f"lever:{j['id']}",
            "source": "lever",
            "company": company,
            "title": j["text"],
            "location": (j.get("categories") or {}).get("location", ""),
            "url": j["hostedUrl"],
            "apply_url": j.get("applyUrl", j["hostedUrl"] + "/apply"),
            "jd_text": _strip_html(j.get("descriptionPlain") or j.get("description", "")),
        })
    return out


def ashby_jobs(board: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "job_id": f"ashby:{j['id']}",
            "source": "ashby",
            "company": board,
            "title": j["title"],
            "location": j.get("location", ""),
            "url": j.get("jobUrl", ""),
            "apply_url": j.get("applyUrl", j.get("jobUrl", "")),
            "jd_text": _strip_html(j.get("descriptionPlain") or j.get("descriptionHtml", "")),
        })
    return out


def remotive_jobs(keyword: str) -> list:
    url = "https://remotive.com/api/remote-jobs"
    r = requests.get(url, params={"search": keyword, "limit": 50}, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "job_id": f"remotive:{j['id']}",
            "source": "remotive",
            "company": j.get("company_name", ""),
            "title": j.get("title", ""),
            "location": j.get("candidate_required_location", "Remote"),
            "url": j.get("url", ""),
            "apply_url": j.get("url", ""),
            "jd_text": _strip_html(j.get("description", "")),
        })
    return out


def discover(search_cfg: dict) -> list:
    """Pull every configured source; failures in one source don't kill the run."""
    jobs, errors = [], []
    for board in search_cfg.get("greenhouse_boards", []):
        try:
            jobs += greenhouse_jobs(board)
        except Exception as e:
            errors.append(f"greenhouse/{board}: {e}")
    for company in search_cfg.get("lever_companies", []):
        try:
            jobs += lever_jobs(company)
        except Exception as e:
            errors.append(f"lever/{company}: {e}")
    for board in search_cfg.get("ashby_boards", []):
        try:
            jobs += ashby_jobs(board)
        except Exception as e:
            errors.append(f"ashby/{board}: {e}")
    if search_cfg.get("remotive_search"):
        for kw in search_cfg.get("keywords", []):
            try:
                jobs += remotive_jobs(kw)
            except Exception as e:
                errors.append(f"remotive/{kw}: {e}")
    for e in errors:
        print(f"  [source error] {e}")
    return jobs


def location_ok(location: str, allow: list) -> bool:
    if not allow:
        return True
    loc = (location or "").lower()
    return any(a.lower() in loc for a in allow) or loc == ""
