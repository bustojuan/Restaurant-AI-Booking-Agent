"""Serve a generated isolated demo using its own configuration."""

import argparse
from pathlib import Path

import uvicorn

from app.core.config import Settings
from app.main import create_app

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", required=True, type=Path)
args = parser.parse_args()
directory = args.directory.resolve()
if not (directory / "manifest.json").is_file():
    raise SystemExit("Not a generated demo directory.")
settings = Settings(_env_file=directory / ".env")
if (
    settings.real_telephony_enabled
    or settings.voice_sandbox_enabled
    or settings.ai_extraction_mode != "deterministic"
):
    raise SystemExit("This launcher only serves deterministic, provider-free demonstrations.")
uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, access_log=False)
