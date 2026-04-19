# AGENTS.md — doer

## project
- **what:** one-file pipe-native AI agent
- **lang:** python 3.10+
- **dep:** `strands-agents[ollama]` (only)
- **entry:** `doer/__init__.py` · 164 lines
- **install:** `pip install doer-cli` or download binary from releases
- **license:** Apache-2.0

## architecture

```
doer/
├── __init__.py    # everything: Agent, shell tool, CLI, prompt
├── __main__.py    # python -m doer
SOUL.md            # identity (injected into system prompt if in cwd)
AGENTS.md          # project rules (injected if in cwd)
doer.svg           # brand mark
build.sh           # local PyInstaller build
.github/workflows/
└── release.yml    # tag v* → binaries + PyPI
```

## design rules

1. **one source file** — all logic in `doer/__init__.py`
2. **one external dep** — `strands-agents[ollama]`, nothing else
3. **no classes unless the SDK forces it** — functions are cheaper
4. **context over memory** — don't store state, recompute from filesystem
5. **unix over RPC** — stdin/stdout/pipes, not HTTP/WebSocket
6. **env vars over config files** — `DOER_*` knobs, never `~/.doerrc`

## prompt injection (what the agent sees every call)

Built fresh on every call by `_prompt()`:
- env (`sys.platform`) + cwd (`Path.cwd()`)
- model info + own `__file__` path
- `SOUL.md` from cwd (if present)
- `AGENTS.md` from cwd (if present)
- `~/.doer_history` — last `DOER_HISTORY` Q/A pairs (default 10)
- `~/.bash_history` + `~/.zsh_history` — last `DOER_SHELL_HISTORY` commands (default 20)
- full source of `doer/__init__.py` — self-awareness

## conventions

- responses are **terse**. no filler.
- when stdin is piped → no markdown decoration.
- tool calls: use `shell` freely, no asking.
- add tools by dropping `@tool` fns into `./tools/*.py` (strands hot-reload).

## env knobs

| var                              | default                                           | purpose                       |
| -------------------------------- | ------------------------------------------------- | ----------------------------- |
| `DOER_PROVIDER`                  | *auto* (bedrock if AWS creds, else ollama)        | `ollama` \| `bedrock`         |
| `DOER_MODEL`                     | `qwen3:1.7b`                                      | ollama model id               |
| `OLLAMA_HOST`                    | `http://localhost:11434`                          | ollama endpoint               |
| `DOER_BEDROCK_MODEL`             | `global.anthropic.claude-opus-4-7`                | bedrock model id              |
| `DOER_BEDROCK_REGION`            | `$AWS_REGION` or `us-west-2`                      | bedrock region                |
| `AWS_BEARER_TOKEN_BEDROCK`       | *(unset)*                                         | bearer-token auth for bedrock |
| `DOER_MAX_TOKENS`                | `128000` (Opus 4.7 native max)                    | bedrock max_tokens            |
| `DOER_TEMPERATURE`               | *(model default)*                                 | bedrock temperature           |
| `DOER_TOP_P`                     | *(model default)*                                 | bedrock top_p                 |
| `DOER_CACHE_PROMPT`              | *off*                                             | bedrock prompt caching (1/true) |
| `DOER_BEDROCK_GUARDRAIL_ID`      | *(unset)*                                         | bedrock guardrail id          |
| `DOER_BEDROCK_GUARDRAIL_VERSION` | *(unset)*                                         | bedrock guardrail version     |
| `DOER_ANTHROPIC_BETA`            | `context-1m-2025-08-07` (on Claude models)        | comma-sep `anthropic_beta` headers |
| `DOER_ADDITIONAL_REQUEST_FIELDS` | *(unset)*                                         | raw JSON for `additional_request_fields` |
| `DOER_HISTORY`                   | `10`                                              | Q/A pairs in prompt           |
| `DOER_SHELL_HISTORY`             | `20`                                              | shell cmds in prompt          |

### provider auto-detect

- if any of `AWS_BEARER_TOKEN_BEDROCK`, `AWS_ACCESS_KEY_ID`, or `AWS_PROFILE` is set → **bedrock**
- otherwise → **ollama**
- force with `DOER_PROVIDER=ollama` or `DOER_PROVIDER=bedrock`

### bedrock notes

- **zero new deps** — `boto3` comes with `strands-agents` core
- credentials via normal boto3 chain (env vars, `~/.aws/credentials`, IAM role, SSO)
- supports bearer-token auth via `AWS_BEARER_TOKEN_BEDROCK`
- full feature surface: guardrails, prompt caching (`cache_config` auto), max_tokens, temperature, top_p
- extend by editing `_model()` in `doer/__init__.py` — the SDK's `BedrockConfig` TypedDict has the full list

### Claude Opus 4.7 defaults (breaking changes from 4.6)

- **Default model**: `global.anthropic.claude-opus-4-7` (1M context, 128k output, adaptive thinking)
- **`max_tokens`** defaults to `128000` (the model's native max)
- **`anthropic_beta`** defaults to `context-1m-2025-08-07` (enables 1M context window)
- **`temperature` / `top_p`** — **do not set** on Opus 4.7+; any non-default value returns 400. Doer only sends these when `DOER_TEMPERATURE` / `DOER_TOP_P` are explicitly set.
- **No `output-300k` yet**: despite appearing in the SDK's `AnthropicBetaParam` list, `output-300k-2026-03-24` isn't accepted by Bedrock for Opus 4.7 (returns `invalid beta flag`). Opus 4.7's real output cap is **128k**, per the [launch notes](https://docs.claude.com/en/docs/about-claude/models/whats-new-claude-4-7).

To opt out of the default beta: `DOER_ANTHROPIC_BETA="" doer "..."`

### bedrock beta headers (`anthropic-beta`)

Both env vars route into Bedrock Converse as `additional_request_fields`.
`DOER_ANTHROPIC_BETA` is the convenient shortcut; `DOER_ADDITIONAL_REQUEST_FIELDS` is the escape hatch. They **merge** — `anthropic_beta` values are concatenated and deduped.

```bash
# 1M context window (Claude 4+)
DOER_ANTHROPIC_BETA=context-1m-2025-08-07 doer "huge prompt..."

# stack multiple betas
DOER_ANTHROPIC_BETA="context-1m-2025-08-07,interleaved-thinking-2025-05-14" doer "..."

# raw escape hatch (for beta fields other than anthropic_beta)
DOER_ADDITIONAL_REQUEST_FIELDS='{"anthropic_beta":["context-1m-2025-08-07"],"tools":[...]}' doer "..."
```

Authoritative list: [anthropic-sdk-python/types/anthropic_beta_param.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/anthropic_beta_param.py). Common headers for Claude Opus 4.7 / Sonnet 4+:

| header                                 | what it does                                   |
| -------------------------------------- | ---------------------------------------------- |
| `context-1m-2025-08-07`                | 1M context window                              |
| `context-management-2025-06-27`        | server-side context editing                    |
| `extended-cache-ttl-2025-04-11`        | 1-hour prompt cache (vs 5min default)          |
| `interleaved-thinking-2025-05-14`      | interleaved extended thinking + tool use       |
| `output-128k-2025-02-19`               | 128K output tokens                             |
| `output-300k-2026-03-24`               | 300K output tokens                             |
| `fast-mode-2026-02-01`                 | low-latency inference                          |
| `token-efficient-tools-2025-02-19`     | fine-grained tool streaming                    |
| `computer-use-2025-01-24`              | computer use tool                              |
| `code-execution-2025-05-22`            | server-side code execution                     |
| `files-api-2025-04-14`                 | files API                                      |
| `mcp-client-2025-11-20`                | MCP client beta                                |
| `skills-2025-10-02`                    | claude skills                                  |
| `advisor-tool-2026-03-01`              | advisor tool                                   |

**Caveats**:
- Not every beta is available on Bedrock yet (API returns `invalid beta flag` — harmless, just drop the unsupported one)
- Not every beta is valid for every model (e.g. `output-300k` is Opus 4.7+ only)

## testing

```bash
pip install -e .
doer "reply: ok"

# pipe test
echo "hello" | doer "translate to turkish, one word"

# self-awareness test
doer "what's your file path? just the path"

# context test
echo "# SOUL\nI am Groot." > /tmp/SOUL.md && cd /tmp && doer "who are you?"
```

## release

```bash
git tag v0.2.0 && git push --tags
# → CI builds binaries (linux/macOS), publishes to PyPI
```

## do not

- add more deps — every byte in the dep tree is scrutinized
- add subcommands — `doer <query>` is the only interface
- add config files — env vars are overkill for this tool
- wrap in docker — it's 100MB, just `pip install doer-cli`
