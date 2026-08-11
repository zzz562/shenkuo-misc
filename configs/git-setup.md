# Git Setup (Mac Mini)

Last verified: 2026-07-07

## Identity

| Setting | Value |
|---------|-------|
| `user.name` | zeph |
| `user.email` | zong.zizhao@outlook.com |
| Git version | 2.50.1 (Apple Git-155) |

## GitHub Connection

| Check | Status |
|-------|--------|
| SSH (`git@github.com`) | OK — account `zzz562` |
| GitHub CLI (`gh`) | OK — SSH protocol, `repo` scope |
| Remote for this repo | `git@github.com:zzz562/whaletrail-lab.git` |

SSH key: `~/.ssh/id_ed25519` (configured in `~/.ssh/config` with Keychain)

## Global Defaults (applied 2026-07-07)

```
init.defaultBranch = main
push.autoSetupRemote = true
pull.rebase = false
credential.helper = osxkeychain
```

## Local Repos

| Path | Remote | Notes |
|------|--------|-------|
| `~/projects/whaletrail-lab` | `zzz562/whaletrail-lab` | Main Grok collaboration repo |
| `~/github/Lean` | `QuantConnect/Lean` (HTTPS) | QuantConnect engine; local changes present |
| `~/.openclaw/workspace` | (uninitialized) | OpenClaw agent workspace |

## Quick Commands

```bash
# Verify connection
ssh -T git@github.com
gh auth status

# Work in this repo
cd ~/projects/whaletrail-lab
grok --cwd ~/projects/whaletrail-lab
```