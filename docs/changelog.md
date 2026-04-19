# Changelog

Compressed history. Newest first.

## v0.2.1 — *curl or pipx*

- `do` shortcut alongside `doer` (less typing)
- One-line installer (`curl | sh`) planned via GitHub Releases
- Renamed to **`doer-cli`** on PyPI (`doer` was squatted)
- Repo moved to `github.com/cagataycali/doer-cli`
- Docs: migrated to **mkdocs-material** (mobile-first, proper nav, dark/light, cookbook)

## v0.2.0 — *new brand*

- Bold, solid, pipe-first identity (orange `#FF3D00` + black + paper)
- Custom SVG logo
- Clean README, stripped marketing copy
- Auto-inject `SOUL.md` + `AGENTS.md` into system prompt

## v0.1.x — *the primordial soup*

- **164 LOC** — fits on one screen (barely)
- Only dep: `strands-agents`
- Ollama-only (local, private, no keys)
- Injects own source, `$HOME/.bash_history`, `$HOME/.zsh_history`, `~/.doer_history`
- Hot-reload tools from `./tools/*.py`
- PyInstaller + Nuitka standalone binaries (linux/macos)
- Rename: `tiny` → `doer` (better verb)

## pre-history

- Spawned from **[DevDuck](https://github.com/cagataycali/devduck)** — 60+ tools, every protocol
- DevDuck asked itself at 4am: *what if we deleted almost everything?*
- Two hours later: `doer`.

---

> *the cathedral teaches you which stones are load-bearing.*
