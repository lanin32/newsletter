"""
One-time helper: looks up the numeric X user id of every account in
config.yaml that needs one, and prints an `x_user_ids:` block to paste into
config.yaml (replacing the `x_user_ids: {}` line). With the ids in config, the
jobs skip X's paid username lookup ($0.01 each) on every run.

Costs about $0.01 per account, once. Accounts that use a phrase filter
(weekly x_accounts entries with `phrases`) are skipped -- the search endpoint
doesn't need an id.

Usage:
    python lookup_x_ids.py
"""
import time
import yaml

from x_fetch import _get_user_id


def accounts_needing_ids(config: dict) -> list[str]:
    names: dict[str, str] = {}  # lowercase -> original spelling

    def add(username: str) -> None:
        names.setdefault(username.lower(), username)

    for account in config.get("x_accounts", []):
        if isinstance(account, dict):
            if not account.get("phrases"):
                add(account["username"])
        else:
            add(account)

    for token in config.get("monthly", {}).get("tokens", []):
        for username in token.get("x_accounts", []):
            add(username)

    return list(names.values())


def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    usernames = accounts_needing_ids(config)
    print(f"Looking up {len(usernames)} accounts (~${len(usernames) * 0.01:.2f})...\n")

    found: dict[str, str] = {}
    failed: list[str] = []
    for username in usernames:
        user_id = _get_user_id(username)
        if user_id:
            found[username.lower()] = user_id
        else:
            failed.append(username)
        time.sleep(1)  # polite pause between lookups

    print("\n--- paste into config.yaml (replace the `x_user_ids: {}` line) ---\n")
    print("x_user_ids:")
    for username, user_id in found.items():
        print(f'  "{username}": "{user_id}"')  # quoted: a name like 0xabc would parse as a number

    if failed:
        print(f"\nCould not look up: {', '.join(failed)} (check the spelling in config.yaml)")


if __name__ == "__main__":
    main()
