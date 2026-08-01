"""
Run this once locally to authorize Gmail read + send access and cache a token.
Requires credentials.json (downloaded from Google Cloud Console) in this folder.

If you already authorized with the old read-only scope, run this again --
it will prompt a fresh consent screen covering both scopes and overwrite
token.pickle with a token that can do both.

Usage:
    python gmail_auth.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    with open("token.pickle", "wb") as f:
        pickle.dump(creds, f)

    print("Authorized. Token saved to token.pickle — you won't need to do this again")
    print("(until the token expires or you revoke access).")

if __name__ == "__main__":
    main()
