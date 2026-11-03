# Security and release audit

Keep API keys, local/admin tokens, `.env` variants, databases, Electron profiles,
audio and private logs outside Git. Setup generates distinct local/admin tokens.
Only the loopback business API and typed Electron bridges handle application
credentials; only the separate signed voice gateway should be exposed publicly.

The release audit uses Gitleaks, a public-index/path/link scanner, a comparison
against private source credential values, `pip-audit` and `npm audit`. See
[validation receipts](docs/validation/dependency-security.json) and
[TEST_REPORT.md](TEST_REPORT.md) for the actual scope and results. Secret scanning
does not prove the absence of every possible secret; binary media were reviewed
through their isolated-data provenance and selected rendered frames.

The original `filelock` 3.32.7 triggered 13 advisories. Only that dependency was
updated, to locked 4.2.7, with the backend regression suite repeated. The
[upstream Windows advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-8mx5-7m5m-r77g)
and [patched release](https://github.com/tox-dev/filelock/releases/tag/4.2.1)
document why a compatibility/security correction was necessary.

The audited Python runtime, frontend runtime dependencies and video project have
no known vulnerability findings in this release's scans. The complete frontend
development tree has **17 moderate findings**, centered on `minimatch` and
transitive packaging/code-generation tools. There are no high/critical findings
in that npm report. The suggested automatic fixes involve incompatible major
downgrades of Electron Builder/OpenAPI tooling; no force fix was applied.

These tools process the repository's own trusted build paths/schema, not arbitrary
remote user glob patterns. Do not use this build toolchain as a service accepting
untrusted patterns or schemas. This is a documented residual development-tool
risk, not a claim of a completely vulnerability-free dependency tree.

Do not put secrets in public issues. Use GitHub's private vulnerability reporting
if enabled on the eventual repository. No security contact address or reporting
URL is invented before publication.
