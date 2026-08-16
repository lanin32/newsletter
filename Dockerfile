FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.yaml .
COPY gmail_fetch.py gmail_send.py x_fetch.py citations.py email_render.py weekly_summarize.py weekly_job.py monthly_summarize.py monthly_job.py ./

# credentials.json and token.pickle are NOT copied in -- they're mounted at
# runtime from Secret Manager (see deployment steps), since they're secrets,
# not code.

# Default entrypoint runs the weekly job. The monthly Cloud Run Job overrides
# this at job-creation time via --command/--args, using this same image --
# see the deploy steps.
CMD ["python", "weekly_job.py"]
