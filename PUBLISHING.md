# Publish this reviewed source release

This folder is an independent fresh Git repository. The original project/history
is not involved. Publication requires your authenticated GitHub account. No
repository URL is claimed until the remote has actually been created and verified.

Install [GitHub CLI](https://github.com/cli/cli/blob/trunk/docs/install_windows.md)
if needed, then open a new terminal window:

```powershell
winget install --id GitHub.cli --source winget
```

If this prepared folder reports Git's **dubious ownership**
error under the restricted Windows runner, trust only this explicit directory in
this terminal session (no global configuration is changed):

```powershell
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = (Get-Location).Path.Replace('\', '/')
```

Then run the following from this repository root:

```powershell
gh auth login
gh auth status
git status --short
.venv/Scripts/python.exe scripts/audit-public.py
```

Resolve any audit finding before continuing. Determine the actual namespace and
check for a conflicting repository:

```powershell
$owner = gh api user --jq .login
if ($LASTEXITCODE -ne 0 -or -not $owner) { throw 'GitHub authentication failed.' }
gh repo view "$owner/BARIA" --json nameWithOwner,url
```

If BARIA exists, **stop** and choose a different new repository name; do not
overwrite, delete or force-push it. If the API confirms it does not exist (404),
and all local publication checks pass:

```powershell
gh repo create "$owner/BARIA" --public --source . --remote origin --push --description "AI restaurant booking desktop application with multi-agent orchestration and execution observability"
gh repo view --json nameWithOwner,url,isPrivate,defaultBranchRef
git remote -v
git ls-remote --heads origin main
```

Open the returned URL and verify the rendered README, both SVGs, screenshots and
the relative product-demo download. The approved MP4 is about 68.4 MiB: ordinary
Git accepts it but issues GitHub's >50 MiB warning. It remains below the 100 MiB
hard limit. No LFS setup or invented external video URL is required. See
[GitHub's size policy](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

Once published, update the publication receipts with the verified URL/commit. A
GitHub Release can later duplicate the unchanged MP4 for easier downloading;
do not remove the working README link until a real replacement exists.
