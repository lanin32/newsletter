# Crypto Weekly Bot — Milk Road summarizer (step 1)

## Setup

1. `pip install -r requirements.txt`

2. Get Gmail API credentials:
   - Go to console.cloud.google.com → create/select a project
   - Enable the **Gmail API**
   - Credentials → Create Credentials → OAuth client ID → **Desktop app**
   - Download the JSON, save it as `credentials.json` in this folder

3. Authorize (one-time):
   ```
   python gmail_auth.py
   ```
   This opens a browser, you log in and approve read-only Gmail access,
   and it saves `token.pickle` so you don't have to repeat this.

4. Set your Anthropic API key:
   ```
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

5. Check `config.yaml` — update `gmail_query` to match Milk Road's actual
   sender address (check a recent email you received from them and use
   the exact from-address).

## Run it

```
python summarize.py
```

This fetches the last 7 days of Milk Road emails from your inbox and
prints a "General Market" summary to the console.

## Next steps (not built yet)
- Add BTC/ETH news fetching (CryptoPanic + X) alongside this
- Combine into one weekly digest with 3 sections: BTC / ETH / General Market
- Send as an email instead of printing
- Deploy as a Cloud Run job + Cloud Scheduler
