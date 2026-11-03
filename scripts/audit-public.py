"""Scan Git's public index without printing secret values; use before publication."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    paths = [Path(p.decode("utf-8")) for p in raw.split(b"\0") if p]
    issues = []
    patterns = {
        "private-key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "openai-key": rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b",
        "github-token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
        "jwt": rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b",
        "personal-path": rb"C:[\\/]+Users[\\/]+(?!Public[\\/]|YOUR_|<)[^\s<>\"\r\n]+",
    }
    for relative in paths:
        path = ROOT / relative
        lower = relative.as_posix().lower()
        if path.is_symlink():
            issues.append({"path": lower, "category": "symlink"})
        if (
            (relative.name.startswith(".env") and relative.name != ".env.example")
            or any(x in relative.parts for x in ["private", "node_modules", ".venv", ".tools"])
            or re.search(r"\.(?:db|sqlite)(?:$|[-.])", relative.name)
            or relative.suffix in {".pem", ".pfx", ".key"}
        ):
            issues.append({"path": lower, "category": "private-or-runtime-file"})
        if path.stat().st_size > 100 * 1024 * 1024:
            issues.append({"path": lower, "category": "github-file-limit"})
        if relative.suffix.lower() in {".mp4", ".png", ".wav", ".woff2"}:
            continue
        content = path.read_bytes()
        for category, pattern in patterns.items():
            if re.search(pattern, content):
                issues.append({"path": lower, "category": category})
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if "://" not in target and not target.startswith("#"):
            if not (ROOT / target.split("#")[0]).is_file():
                issues.append({"path": "README.md", "category": "broken-link", "target": target})
    print(json.dumps({"indexed_files": len(paths), "issues": issues}, indent=2))
    return bool(issues)


if __name__ == "__main__":
    sys.exit(main())
