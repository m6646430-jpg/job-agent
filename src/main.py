"""job-agent: discover -> score -> tailor -> apply, fully hands-off.

Usage:
  python -m src.main discover     # pull new jobs from all sources
  python -m src.main score        # LLM-score unscored jobs against your profile
  python -m src.main apply        # apply to top-scored jobs (respects config caps)
  python -m src.main run          # all three, in order  (cron this)
  python -m src.main report       # pipeline status counts
"""

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src import sources
from src.llm import LLM, BudgetExceeded
from src.matcher import score_job, tailor
from src.store import Store


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def load_profile(cfg) -> str:
    path = ROOT / cfg["candidate"]["profile_file"]
    if not path.exists():
        raise SystemExit(f"Profile not found: {path} — write your background there first.")
    return path.read_text()


def cmd_discover(cfg, store):
    jobs = sources.discover(cfg["search"])
    new = 0
    for job in jobs:
        if store.seen(job["job_id"]):
            continue
        if not sources.location_ok(job["location"], cfg["search"].get("locations_allow", [])):
            continue
        store.add_job(job)
        new += 1
    print(f"discover: {len(jobs)} fetched, {new} new")


def cmd_score(cfg, store):
    profile = load_profile(cfg)
    llm = LLM(cfg["llm"])
    rows = store.unscored()
    print(f"score: {len(rows)} unscored, LLM budget left today: {llm.remaining_budget()}")
    for row in rows:
        try:
            s, reason = score_job(llm, profile, dict(row))
        except BudgetExceeded:
            print("  budget exhausted — resuming tomorrow")
            break
        except Exception as e:
            print(f"  [{row['title']} @ {row['company']}] score failed: {e}")
            continue
        store.set_score(row["job_id"], s, reason)
        if s < cfg["matching"]["min_score"]:
            store.set_status(row["job_id"], "skipped", f"score {s}: {reason}")
        print(f"  {s:>3}  {row['title']} @ {row['company']} — {reason}")


def cmd_apply(cfg, store):
    from src.apply import apply_to_job  # import here: playwright is heavy

    profile = load_profile(cfg)
    llm = LLM(cfg["llm"])
    candidate = cfg["candidate"]
    resume = ROOT / candidate["resume_file"]
    if not resume.exists():
        raise SystemExit(f"Resume not found: {resume}")

    rows = store.apply_candidates(cfg["matching"]["min_score"],
                                  cfg["matching"]["max_applications_per_run"])
    print(f"apply: {len(rows)} candidates")
    for row in rows:
        job = dict(row)
        print(f"  -> {job['title']} @ {job['company']} (score {job['score']})")
        try:
            tailor_fn = lambda questions: tailor(llm, profile, job, questions)
            status, note = apply_to_job(job, candidate, tailor_fn, cfg["apply"])
        except BudgetExceeded:
            print("  budget exhausted — resuming tomorrow")
            break
        except Exception as e:
            status, note = "failed", str(e)
        store.set_status(job["job_id"], status, note)
        print(f"     {status}: {note}")


def cmd_report(cfg, store):
    for row in store.report():
        print(f"  {row['status']:>8}  {row['n']}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg = load_config()
    store = Store()
    if cmd == "discover":
        cmd_discover(cfg, store)
    elif cmd == "score":
        cmd_score(cfg, store)
    elif cmd == "apply":
        cmd_apply(cfg, store)
    elif cmd == "run":
        cmd_discover(cfg, store)
        cmd_score(cfg, store)
        cmd_apply(cfg, store)
    elif cmd == "report":
        cmd_report(cfg, store)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
