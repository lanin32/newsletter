# Deploying to Cloud Run (weekly job)

## 0. One-time setup

```
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## 1. Store your secrets

Three things need to live in Secret Manager: `OPENAI_API_KEY`, `X_BEARER_TOKEN`,
and `token.pickle`. Note: `credentials.json` is NOT needed at runtime -- the
`Credentials` object inside `token.pickle` already carries the client_id,
client_secret, and refresh_token needed to silently refresh the access token
going forward. `credentials.json` is only needed locally, for the one-time
browser consent flow in `gmail_auth.py`.

```
echo -n "sk-your-openai-key" | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "your-x-bearer-token" | gcloud secrets create X_BEARER_TOKEN --data-file=-
gcloud secrets create GMAIL_TOKEN --data-file=token.pickle
```

(Run these from the folder containing your actual `token.pickle` file.)

## 2. Build and push the container image

```
gcloud artifacts repositories create crypto-bot \
  --repository-format=docker \
  --location=us-central1

gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot/weekly-job
```

## 3. Grant the job's service account access to read the secrets

Cloud Run Jobs use a default service account (usually
`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) that needs explicit
permission to read Secret Manager secrets -- otherwise job creation fails with
a "Permission denied on secret" error.

```
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Find your project number (different from project ID) via:
```
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

## 4. Create the Cloud Run Job

Only `token.pickle` is file-mounted -- IMPORTANT: mount it to its own directory
(e.g. `/secrets/token.pickle`), NOT under `/app` -- mounting a secret volume
into the same directory as your app code hides everything else already in that
directory (Cloud Run mounts a whole volume over the target directory, not just
the single file), which breaks the container's ability to find your Python
files. Point the code at the new path via a `TOKEN_PATH` env var:

```
gcloud run jobs create crypto-weekly-job \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/crypto-bot/weekly-job \
  --region us-central1 \
  --set-secrets="/secrets/token.pickle=GMAIL_TOKEN:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,X_BEARER_TOKEN=X_BEARER_TOKEN:latest" \
  --set-env-vars="TOKEN_PATH=/secrets/token.pickle" \
  --memory 512Mi \
  --task-timeout 600 \
  --max-retries 1
```

Test it manually before scheduling anything:

```
gcloud run jobs execute crypto-weekly-job --region us-central1
```

Check the logs (Cloud Console → Cloud Run → Jobs → crypto-weekly-job → Logs) to
confirm it actually sent the email successfully.

## 5. Create a service account for the scheduler to invoke the job

```
gcloud iam service-accounts create crypto-bot-invoker

gcloud run jobs add-iam-policy-binding crypto-weekly-job \
  --region us-central1 \
  --member="serviceAccount:crypto-bot-invoker@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## 6. Create the weekly Cloud Scheduler trigger

```
gcloud scheduler jobs create http crypto-weekly-trigger \
  --location us-central1 \
  --schedule="0 8 * * MON" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT_ID/jobs/crypto-weekly-job:run" \
  --http-method=POST \
  --oauth-service-account-email="crypto-bot-invoker@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

This runs every Monday at 8am (in the scheduler location's timezone — add
`--time-zone="America/New_York"` or similar if you want a specific one instead
of UTC default).

## Notes

- `token.pickle` ends up mounted as a real file at `/secrets/token.pickle`
  inside the container (never under `/app`, to avoid shadowing your code) --
  `gmail_fetch.py` and `gmail_send.py` read the path from the `TOKEN_PATH` env
  var, falling back to a local `token.pickle` for when you run things locally
  without that env var set. `credentials.json` is never uploaded anywhere in
  this deployment; it stays local, since the running job never needs it.
- If the OAuth token ever expires or gets revoked, you'll need to re-run
  `gmail_auth.py` locally and update the `GMAIL_TOKEN` secret:
  ```
  gcloud secrets versions add GMAIL_TOKEN --data-file=token.pickle
  ```
- To update the code after making changes, just re-run the `gcloud builds submit`
  command from step 2 -- Cloud Run Jobs always uses the `:latest` tag unless you
  pin a specific one.
