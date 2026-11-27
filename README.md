# job-agent

A job-search agent you run on your own computer. It finds jobs on company
career pages, scores each one against your profile, drafts a tailored cover
letter, fills the application form, and **stops before Submit** so you review
every application yourself.

```
FIND    jobs from public job-board APIs (Greenhouse, Lever, Ashby, Remotive)
SCORE   each job 0-100 against profile/profile.md with an LLM; below 70 is skipped
TAILOR  a cover letter and answers, using only what your profile says
FILL    the form with Playwright, save a full-page screenshot, stop before Submit
```

Everything is logged to `data/jobs.db`. Every filled form gets a screenshot in
`data/screenshots/`.

## What you need

- A computer with Python 3.9 or newer
- A free OpenRouter API key (openrouter.ai)
- Your resume as a PDF
- 20 minutes

## Setup, step by step

**1. Download the code**

```bash
git clone https://github.com/m6646430-jpg/job-agent.git
cd job-agent
```

**2. Install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

On Windows, replace the second line with `.venv\Scripts\activate`.

**3. Add your API key**

Create a free key at openrouter.ai, then:

```bash
echo 'OPENROUTER_API_KEY=paste-your-key-here' > .env
```

Never share this file or put it on GitHub.

**4. Write your profile**

Open `profile/profile.md` and fill it in. This is the only source the agent may
use. It is told never to invent experience you do not have, so anything missing
here is missing from your applications.

**5. Add your resume**

Save it as `profile/resume.pdf`.

**6. Edit `config.yaml`**

- `candidate`: your name, email, phone, location, links, work authorization
- `search.keywords`: the job titles you want
- `search.greenhouse_boards`, `lever_companies`, `ashby_boards`: the companies
  to watch. The name is the last part of the company's careers URL. For
  `boards.greenhouse.io/stripe` it is `stripe`.
- `search.locations_allow`: your country, cities, `remote`
- `matching.min_score`: 70 is a good start

**7. Run it one step at a time the first time**

```bash
python -m src.main discover   # find jobs
python -m src.main score      # score them against your profile
python -m src.main report     # see the counts
python -m src.main apply      # fill forms, screenshot, stop before Submit
```

Open `data/screenshots/` and check each filled form. Submit the good ones
yourself.

**8. Run it daily**

```bash
python -m src.main run        # discover + score + apply in one go
```

Schedule that with cron (Mac/Linux) or Task Scheduler (Windows) to have a list
waiting every morning.

## The rule: stop before Submit

`apply.auto_submit` is `false` by default. The agent fills the form and stops.
You read it and click Submit. Leave it that way until you have reviewed enough
applications to trust the output. A wrong application sent in your name costs
more than the minute it takes to check.

## Free-tier limits

OpenRouter's free tier allows about 20 requests a minute and 50 a day
(`max_requests_per_day: 48` guards this). The agent uses about 2 calls per
application (1 score + 1 tailor), so the free tier covers roughly 15-20 scored
jobs and 5 applications a day. The free model list changes often, so the config
has a fallback chain; edit `llm.models` if all of them stop responding.

## Known limits

- **CAPTCHA forms are never filled.** The agent does not bypass bot protection.
  Instead it reads the form's questions and writes an application kit to
  `data/kits/`: a cover letter plus answers, for you to paste and submit by
  hand. Many Greenhouse and Ashby forms carry a CAPTCHA, so expect the kit to
  be the usual outcome.
- **Listing pages have no form.** Jobs found through Remotive often link to a
  listing page; those are marked `failed` with "no application form".
- **LinkedIn and Indeed are not supported.** Their terms prohibit automation
  and accounts get banned. Company career pages are the reliable path.
- Unusual form widgets (multi-step wizards, some dropdowns) can end as
  `failed`. Check the screenshot and apply by hand.
- This is a personal project shared as is. Tested on real boards: discovery,
  scoring and the application kit. Automatic form filling has not been
  confirmed on a live company form, because the forms tested had a CAPTCHA.

## The part the agent cannot do

For each role worth applying to, find the recruiter or hiring manager on
LinkedIn and send a short personal message: the role, two lines on why you fit,
your resume. 20 good applications beat 300 lazy ones.

Made by [@heymahesh.ai](https://www.instagram.com/heymahesh.ai/). MIT licence.
