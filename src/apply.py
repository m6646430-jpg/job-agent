"""Playwright form filler for ATS application pages (Greenhouse, Lever, Ashby).

Strategy: label-driven heuristics for the standard fields, LLM answers for
custom questions. Hard rules:
  - if a captcha is present, abort and mark the job 'captcha' (never bypass)
  - screenshot before submit, always, into data/screenshots/
  - auto_submit=false fills everything and stops short of the submit click
"""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SHOTS = Path(__file__).resolve().parent.parent / "data" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

CAPTCHA_MARKERS = ["recaptcha", "hcaptcha", "h-captcha", "cf-turnstile", "captcha"]

STANDARD_FIELDS = {
    "first name": "first_name",
    "last name": "last_name",
    "full name": "full_name",
    "name": "full_name",
    "email": "email",
    "phone": "phone",
    "location": "location",
    "city": "location",
    "linkedin": "linkedin",
    "github": "github",
    "website": "website",
    "portfolio": "website",
    "current company": "current_company",
}


def _has_captcha(page) -> bool:
    content = page.content().lower()
    return any(m in content for m in CAPTCHA_MARKERS if f'"{m}"' in content or f"class=\"{m}" in content or m in content)


def _label_for(page, el):
    """Best-effort visible label text for an input element."""
    try:
        lid = el.get_attribute("id")
        if lid:
            lab = page.query_selector(f'label[for="{lid}"]')
            if lab:
                return lab.inner_text().strip()
        aria = el.get_attribute("aria-label")
        if aria:
            return aria.strip()
        ph = el.get_attribute("placeholder")
        if ph:
            return ph.strip()
        handle = el.evaluate_handle("e => e.closest('label')")
        if handle.as_element():
            return handle.as_element().inner_text().strip()
    except Exception:
        pass
    return ""


def _classify(label: str) -> str | None:
    norm = re.sub(r"[*✱:]|\(required\)|\(optional\)", "", label.lower()).strip()
    for key, field in STANDARD_FIELDS.items():
        if norm == key or norm.startswith(key):
            return field
    return None


def collect_questions(page) -> list[tuple[object, str]]:
    """(element, label) pairs for visible text inputs/areas/selects on the form."""
    out = []
    for el in page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], input:not([type]), textarea, select"):
        try:
            if not el.is_visible():
                continue
        except Exception:
            continue
        label = _label_for(page, el)
        if label:
            out.append((el, label))
    return out


def apply_to_job(job, candidate: dict, tailor_fn, cfg: dict) -> tuple[str, str]:
    """Returns (status, note). status in: applied|queued|captcha|failed."""
    values = {
        "first_name": candidate["first_name"],
        "last_name": candidate["last_name"],
        "full_name": f'{candidate["first_name"]} {candidate["last_name"]}',
        "email": candidate["email"],
        "phone": candidate.get("phone", ""),
        "location": candidate.get("location", ""),
        "linkedin": candidate.get("linkedin", ""),
        "github": candidate.get("github", ""),
        "website": candidate.get("website", ""),
        "current_company": "",
    }
    resume = str(Path(__file__).resolve().parent.parent / candidate["resume_file"])
    shot = SHOTS / f"{job['job_id'].replace(':', '_')}.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=cfg.get("headless", True))
        page = browser.new_page()
        try:
            page.goto(job["apply_url"], timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            if cfg.get("skip_if_captcha", True) and _has_captcha(page):
                return "captcha", "captcha on form — apply manually: " + job["apply_url"]

            # Resume upload first: some ATSes autofill fields from it.
            for finput in page.query_selector_all("input[type='file']"):
                try:
                    finput.set_input_files(resume)
                    page.wait_for_timeout(4000)
                    break
                except Exception:
                    continue

            fields = collect_questions(page)
            custom = [(el, lab) for el, lab in fields if _classify(lab) is None
                      and el.evaluate("e => e.tagName.toLowerCase()") != "select"]
            content = tailor_fn([lab for _, lab in custom])

            for el, lab in fields:
                std = _classify(lab)
                try:
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    if std and values.get(std) and tag != "select":
                        el.fill(values[std])
                    elif not std and tag != "select":
                        answer = content["answers"].get(lab, "")
                        if not answer and "cover letter" in lab.lower():
                            answer = content["cover_letter"]
                        if answer:
                            el.fill(answer)
                except Exception:
                    continue

            # Dedicated cover-letter textarea, if any and still empty
            for el in page.query_selector_all("textarea"):
                try:
                    if el.is_visible() and not el.input_value() and "cover" in (_label_for(page, el) or "").lower():
                        el.fill(content["cover_letter"])
                except Exception:
                    pass

            page.screenshot(path=str(shot), full_page=True)

            if not cfg.get("auto_submit", False):
                return "queued", f"filled, not submitted (auto_submit=false); review {shot.name}"

            if _has_captcha(page):
                return "captcha", "captcha appeared before submit — apply manually"

            submit = page.query_selector(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Submit application'), button:has-text('Submit Application'), "
                "button:has-text('Apply')"
            )
            if not submit:
                return "failed", "no submit button found"
            submit.click()
            page.wait_for_timeout(6000)

            body = page.inner_text("body").lower()
            if any(s in body for s in ("thank", "received", "submitted", "application has been")):
                page.screenshot(path=str(SHOTS / f"{shot.stem}_confirm.png"))
                return "applied", "confirmation text detected"
            page.screenshot(path=str(SHOTS / f"{shot.stem}_after.png"))
            return "failed", "submitted but no confirmation detected — check screenshot"
        except PWTimeout:
            return "failed", "page load timeout"
        except Exception as e:
            return "failed", f"{type(e).__name__}: {e}"
        finally:
            browser.close()
