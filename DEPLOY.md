# Deploying and operating (Google Cloud Run Jobs)

## What is deployed

| Thing | Value |
|---|---|
| Project ID | `crypto-newsletter-503220` |
| Region | `europe-west1` |
| Artifact Registry repo | `crypto-newsletter` |
| Image (shared by both jobs) | `europe-west1-docker.pkg.dev/crypto-newsletter-503220/crypto-newsletter/weekly-job` |
| Weekly job | `crypto-weekly-job`: default `CMD` runs `weekly_job.py`, timeout 600s, 512Mi |
| Monthly job | `crypto-monthly-job`: same image, entrypoint overridden to `python monthly_job.py`, timeout 3600s, 512Mi |
| Scheduler triggers | `crypto-weekly-trigger` (Saturday 08:00 UTC, cron `0 8 * * SAT`) and `crypto-monthly-trigger` (16th of the month 08:00 UTC, cron `0 8 16 * *`) |
| Invoker service account | `crypto-bot-invoker@crypto-newsletter-503220.iam.gserviceaccount.com` (needs `roles/run.invoker` on **each** job) |
| Secrets (Secret Manager) | `OPENAI_API_KEY`, `X_BEARER_TOKEN`, `GMAIL_TOKEN` (= `token.pickle`, mounted at `/secrets/token.pickle`) |
| Job env var | `TOKEN_PATH=/secrets/token.pickle` |

The schedules were edited in the console, so confirm the real ones with
`gcloud scheduler jobs describe crypto-weekly-trigger --location europe-west1`.

## Day to day: deploy a code change

From the project folder in cmd.exe:

```
deploy.bat
```

It checks `config.yaml` and the Python syntax first (so a typo never gets baked into the
image), then builds and pushes. Both jobs use the `:latest` tag, so the next run uses the
new code and no job update is needed. Options: `deploy.bat weekly`, `deploy.bat monthly` or
`deploy.bat both` also run that job once afterwards. That sends a real email and spends real credits.

The plain command behind it:

```
gcloud builds submit --project=crypto-newsletter-503220 --tag europe-west1-docker.pkg.dev/crypto-newsletter-503220/crypto-newsletter/weekly-job .
```

If you add a new module that either job imports, add it to the `COPY` line in the
`Dockerfile` or the job crashes on import. (`lookup_x_ids.py`, `gmail_auth.py` and
`deploy.bat` are local-only and are not copied into the image.)

## Run a job manually

```
gcloud run jobs execute crypto-weekly-job --region europe-west1 --wait
gcloud run jobs execute crypto-monthly-job --region europe-west1 --wait
```

Logs: Cloud Console -> Cloud Run -> Jobs -> the job -> Logs. Each summarization call logs a
`Usage --` line, and the email's "RUN COST" footer shows the cost.

## Change a setting without rebuilding

Env vars override the code defaults (see the settings table in `README.md`):

```
gcloud run jobs update crypto-weekly-job --region europe-west1 --update-env-vars="SUMMARIZE_MODEL=gpt-4.1"
gcloud run jobs update crypto-weekly-job --region europe-west1 --remove-env-vars="SUMMARIZE_MODEL"
```

Do not set `DISABLE_CONTINUITY` on the deployed jobs. It is for local testing only.

## Secrets

- **Gmail token expired or revoked** (revocation, a Google password change, or about 6 months of
  non-use): run `python gmail_auth.py` locally, then
  `gcloud secrets versions add GMAIL_TOKEN --data-file=token.pickle`.
  The OAuth consent screen is published to Production, which avoids the 7-day expiry of Testing mode.
- **Rotate an API key** (cmd.exe's `echo` does not support `-n` and would add a newline or the
  literal `-n`, so write the key to a file without a newline first, then delete the file):
  `<nul set /p="new-key"> newkey.txt` then
  `gcloud secrets versions add OPENAI_API_KEY --data-file=newkey.txt` then `del newkey.txt`.
  The jobs read `:latest`, so no redeploy is needed.
- `credentials.json` is never uploaded: `token.pickle` already carries what is needed to
  refresh itself. Never commit `credentials.json` or `token.pickle`.

## Gotchas (already fixed, don't repeat)

1. Never mount a secret file under `/app`. A secret volume hides the whole directory, including
   the Python files. Mount it at `/secrets/...` and point `TOKEN_PATH` there.
2. The default compute service account needs `roles/secretmanager.secretAccessor`
   (granted at project level, which covers both jobs).
3. `gcloud builds submit --tag` only builds a file literally named `Dockerfile`, which is why
   weekly and monthly share one image.
4. In a `.bat` file, `gcloud` must be run with `call`, or the batch file stops after it.

## One-time setup (reference; already done)

Adapted from the original setup notes. These commands were not re-run when this file was
rewritten, so check them against `gcloud ... --help` if you ever redo the setup.

APIs and registry:

```
gcloud config set project crypto-newsletter-503220
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories create crypto-newsletter --repository-format=docker --location=europe-west1
```

Secrets (run from the folder with your real `token.pickle`; the two keys go through a temporary
file because cmd.exe's `echo` would add a newline):

```
<nul set /p="your-openai-key"> key.txt
gcloud secrets create OPENAI_API_KEY --data-file=key.txt
<nul set /p="your-x-bearer-token"> key.txt
gcloud secrets create X_BEARER_TOKEN --data-file=key.txt
del key.txt
gcloud secrets create GMAIL_TOKEN --data-file=token.pickle
```

Let the jobs read the secrets (find your project number with
`gcloud projects describe crypto-newsletter-503220 --format="value(projectNumber)"`):

```
gcloud projects add-iam-policy-binding crypto-newsletter-503220 --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Create the jobs (build and push the image first):

```
gcloud run jobs create crypto-weekly-job --image europe-west1-docker.pkg.dev/crypto-newsletter-503220/crypto-newsletter/weekly-job --region europe-west1 --set-secrets="/secrets/token.pickle=GMAIL_TOKEN:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,X_BEARER_TOKEN=X_BEARER_TOKEN:latest" --set-env-vars="TOKEN_PATH=/secrets/token.pickle" --memory 512Mi --task-timeout 600 --max-retries 1

gcloud run jobs create crypto-monthly-job --image europe-west1-docker.pkg.dev/crypto-newsletter-503220/crypto-newsletter/weekly-job --region europe-west1 --command="python" --args="monthly_job.py" --set-secrets="/secrets/token.pickle=GMAIL_TOKEN:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,X_BEARER_TOKEN=X_BEARER_TOKEN:latest" --set-env-vars="TOKEN_PATH=/secrets/token.pickle" --memory 512Mi --task-timeout 3600 --max-retries 1
```

Scheduler: a service account that may invoke each job, then one trigger per job:

```
gcloud iam service-accounts create crypto-bot-invoker
gcloud run jobs add-iam-policy-binding crypto-weekly-job --region europe-west1 --member="serviceAccount:crypto-bot-invoker@crypto-newsletter-503220.iam.gserviceaccount.com" --role="roles/run.invoker"
gcloud run jobs add-iam-policy-binding crypto-monthly-job --region europe-west1 --member="serviceAccount:crypto-bot-invoker@crypto-newsletter-503220.iam.gserviceaccount.com" --role="roles/run.invoker"
gcloud scheduler jobs create http crypto-weekly-trigger --location europe-west1 --schedule="0 8 * * SAT" --time-zone="Etc/UTC" --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/crypto-newsletter-503220/jobs/crypto-weekly-job:run" --http-method=POST --oauth-service-account-email="crypto-bot-invoker@crypto-newsletter-503220.iam.gserviceaccount.com"
gcloud scheduler jobs create http crypto-monthly-trigger --location europe-west1 --schedule="0 8 16 * *" --time-zone="Etc/UTC" --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/crypto-newsletter-503220/jobs/crypto-monthly-job:run" --http-method=POST --oauth-service-account-email="crypto-bot-invoker@crypto-newsletter-503220.iam.gserviceaccount.com"
```
