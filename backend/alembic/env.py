import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

from alembic import context
from app.ai import models as ai_models  # noqa: F401 -- include AI metadata for migration checks
from app.models import Base
from app.observability import models as observation_models  # noqa: F401

load_dotenv()
config = context.config
url = (
    config.attributes.get("database_url")
    or os.environ.get("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
)

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
