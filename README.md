# Crypto Newsletter Bot

Two scheduled email digests that summarize crypto news, running on Google Cloud
Run Jobs. For deployment and day-to-day operations, see `DEPLOY.md`.

- **Weekly digest**: one email with three sections (Bitcoin / Ethereum / General
  Market). Sources: newsletters read from Gmail, plus posts from specific X accounts.
- **Monthly digest**: one email with a section per tracked small/mid-cap token.
  Sources: X posts only, from each token's own accounts.

Both emails are sent through the Gmail API and BCC'd back into the reading
inbox, so the next run can find "the previous digest" and avoid repeating old
news as new (continuity, no database needed).

## How it works

```
config.yaml  (newsletters, X accounts, email addresses, monthly token list)
   |
weekly_job.py / monthly_job.py     orchestrators
   |-- gmail_fetch.py              newsletters from Gmail; latest previous digest
   |-- x_fetch.py                  X posts (+ a tally of reads, for the cost footer)
   |-- weekly_summarize.py         ONE pooled LLM call across all sources
   |-- monthly_summarize.py        ONE LLM call per token
   |-- citations.py                turns [N] markers into links
   |-- email_render.py             shared HTML cards / sections / cost footer
   |-- usage_cost.py               token + X-read pricing for the cost footer
   `-- gmail_send.py               sends the HTML email (optional BCC)
```

Other files: `gmail_auth.py` (one-time Gmail authorization), `lookup_x_ids.py`
(one-time X user-id lookup, see below), `deploy.bat` (build and push),
`Dockerfile` (one image for both jobs), `requirements.txt`.

Design choices worth knowing:
- Summaries use the OpenAI Responses API (default model `gpt-6-luna`).
- The weekly digest is a single pooled call so every story lands in exactly one
  section. The monthly digest is one call per token, since there is nothing to route between tokens.
- Output is plain text with `##BTC##` / `##ETH##` / `##GENERAL##` markers (not JSON).
- Citations are inline `[N]` links. X posts always get a number; newsletters get
  one only when a "view online" link can be extracted.

## Setup (local, Windows cmd.exe)

1. Install dependencies: `pip install -r requirements.txt`
2. Create Gmail API credentials: in console.cloud.google.com enable the **Gmail API**, then
   Credentials -> Create Credentials -> OAuth client ID -> **Desktop app**. Download the
   JSON and save it as `credentials.json` in this folder (never commit it).
3. Authorize once: `python gmail_auth.py`. It opens a browser, you approve read and send
   access, and it saves `token.pickle`.
4. Set the API keys for your cmd window (no quotes, no trailing spaces):
   `set OPENAI_API_KEY=sk-...` and `set X_BEARER_TOKEN=...`
5. Edit `config.yaml`: newsletter sender queries, X accounts, `email.to` and `email.read_account`
   (the account `token.pickle` belongs to), and the monthly token list.
6. Optional but saves money: run `python lookup_x_ids.py` once and paste the block it prints into
   `config.yaml`, replacing the `x_user_ids: {}` line. X bills $0.01 for every username lookup,
   and the ids never change.

## Running locally

```
python weekly_job.py
python monthly_job.py
```

These really send the email and really call the X and OpenAI APIs, so they cost money.
When testing several runs close together, turn continuity off. Otherwise the model
sees the digest you just sent as "already reported" and trims fresh material:

```
set DISABLE_CONTINUITY=true&& python weekly_job.py
```

Leave `DISABLE_CONTINUITY` unset for the deployed, scheduled runs.

### Settings (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `SUMMARIZE_MODEL` | `gpt-6-luna` | `gpt-4.1` is the known-good-quality fallback (30k TPM cap on a low tier) |
| `REASONING_EFFORT` | `low` | medium/high showed no coverage benefit in testing |
| `REASONING_MODE` | `standard` | `pro` is untested |
| `ENABLE_REASONING_SUMMARY` | `true` | logs the model's reasoning summary; needs an OpenAI-verified org, else it retries without |
| `DISABLE_CONTINUITY` | unset | `true` skips the previous-digest lookup (local testing only) |
| `TOKEN_PATH` | `token.pickle` | where the Gmail token lives (set to `/secrets/token.pickle` on Cloud Run) |

Example: `set SUMMARIZE_MODEL=gpt-4.1&& set DISABLE_CONTINUITY=true&& python weekly_job.py`

## Config reference (`config.yaml`)

- `newsletters`: name, Gmail search query, lookback days. Entries whose query still
  contains `REPLACE_ME` are skipped.
- `x_accounts`: a flat list. Each entry is a username, or `{username, phrases}`. With
  `phrases`, only posts containing one of those exact phrases are fetched, using X's search
  endpoint (cheaper, last 7 days only, so weekly use only). In YAML, `phrases:` must line up
  with `username:`.
- `x_user_ids`: username -> numeric id, to skip the paid lookup (see Setup step 6).
- `x_api_pricing`: X's price per post and per user read, used for the cost footer.
  X has no pricing endpoint, so update it by hand if X changes its rates.
- `email`: `to`, `read_account`, `subject` (the subject is how the next run finds the previous digest).
- `monthly`: `subject` and the `tokens` list of `{symbol, x_accounts}`.

## Cost footer

Each email ends with a "RUN COST" section: model, reasoning effort, tokens, estimated LLM cost,
X posts and user lookups read with their cost, and a total. LLM prices are read at run time from
LiteLLM's public price list (OpenAI has no pricing endpoint), with a small built-in fallback table.
X rates come from `config.yaml`. Both are estimates, so check them against your actual bills.
The dominant cost is X API reads, not the LLM.

## Known gaps

- X self-thread continuations are dropped (replies are excluded), so only the first post of a thread is captured.
- Some accounts post 70-90 times a month; they are left unfiltered, which costs more X reads.
- The sentence splitter in `email_render.py` is a regex heuristic and can mis-split around abbreviations.
- Luna's quality on narrative-heavy newsletter weeks is not yet fully proven; watch the first few runs.
