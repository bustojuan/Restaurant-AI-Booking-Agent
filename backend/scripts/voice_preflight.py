"""Report missing voice configuration without connecting, dialing or printing secrets."""

import json

from app.core.config import get_settings
from app.voice.preflight import readiness


def main():
    print(json.dumps(readiness(get_settings()), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
