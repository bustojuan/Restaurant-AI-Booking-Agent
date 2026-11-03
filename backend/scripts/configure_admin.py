"""Create an independent local admin secret without printing or overwriting it."""

import secrets
from pathlib import Path

from dotenv import dotenv_values


def main():
    path = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(path) if path.exists() else {}
    if values.get("ADMIN_API_TOKEN"):
        print("Administrative token already configured; no changes made.")
        return
    if not values.get("LOCAL_API_TOKEN"):
        raise SystemExit("Configure backend/.env with LOCAL_API_TOKEN first.")
    with path.open("a", encoding="utf-8") as target:
        target.write(
            f"\n# Independent AI Control Center access (Electron Main only).\nADMIN_API_TOKEN={secrets.token_urlsafe(48)}\n"
        )
    print("Administrative token configured securely in backend/.env. Restart backend and Electron.")


if __name__ == "__main__":
    main()
