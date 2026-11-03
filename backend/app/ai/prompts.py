import hashlib
from pathlib import Path

NAMES = ("supervisor", "planning", "research", "voice", "negotiation", "verification", "memory", "evaluation")


def prompt_bundle() -> dict[str, dict[str, str]]:
    bundle = {}
    for name in NAMES:
        text = (Path(__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")
        version = text.splitlines()[0].removeprefix("version: ").strip()
        bundle[name] = {"version": version, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}
    return bundle
