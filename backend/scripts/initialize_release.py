"""Create independent local credentials once and migrate an empty release database."""

import secrets
from pathlib import Path

from app.core.config import Settings
from app.migrate import upgrade


def main():
    path = Path(".env")
    if not path.exists():
        template = Path(".env.example").read_text(encoding="utf-8")
        template = template.replace("change-this-local-token-at-least-24-chars", secrets.token_urlsafe(36))
        template = template.replace("change-this-admin-token-at-least-24-chars", secrets.token_urlsafe(36))
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(template)
        print("Created private backend/.env with separate random local and admin tokens.")
    settings = Settings()
    if settings.admin_api_token is None:
        raise SystemExit("Set a distinct ADMIN_API_TOKEN in backend/.env to enable AI Control Center.")
    if settings.admin_api_token.get_secret_value() == settings.local_api_token.get_secret_value():
        raise SystemExit("Local and administrative tokens must be different.")
    upgrade(settings.database_url)
    print("Database migrated. Mock restaurants and checkpoints initialize on backend startup.")


if __name__ == "__main__":
    main()
