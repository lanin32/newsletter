FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.yaml .
COPY gmail_fetch.py gmail_send.py x_fetch.py weekly_summarize.py weekly_job.py ./

# credentials.json and token.pickle are NOT copied in -- they're mounted at
# runtime from Secret Manager (see deployment steps), since they're secrets,
# not code.

CMD ["python", "weekly_job.py"]
