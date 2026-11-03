from pathlib import Path

from alembic.config import Config

from alembic import command


def migration_config(database_url: str | None = None) -> Config:
    backend = Path(__file__).resolve().parent.parent
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


def upgrade(database_url: str) -> None:
    command.upgrade(migration_config(database_url), "head")


if __name__ == "__main__":
    from app.core.config import get_settings

    upgrade(get_settings().database_url)
