# Usage

`do` and `doer` are the same program. Use whichever your fingers prefer.

## one-shot

```bash
do "find files larger than 100MB"
do "current git branch?"
do "what's my public IP?"
```

Direct question → direct answer. No `> ` prompts. No conversation.

## piped

When you pipe to `do`, `stdin` becomes **the context**. Your query becomes **the instruction**.

```bash
cat error.log | do "what broke"
git diff      | do "review this"
git log -20   | do "release notes"
curl -s api.io | do "summarize"
echo '{"a":1}' | do "to yaml"
```

!!! tip "piped = no markdown"
    `doer` detects TTY. When its output goes to a pipe or file, it strips markdown.  
    Just the answer. Clean. Parseable.

## chained

Because output is clean, chaining with `|`, `tee`, `xargs`, `awk`, `jq` just works.

```bash
# top 5 big files → long-format listing
do "list top 5 largest files in cwd" | xargs -n1 ls -lh

# fetch → filter → jq
curl -s api.com/users | do "filter admins only" | jq .

# branch graph → plain english
git log --graph --oneline -30 | do "explain this branch topology"

# extract → email
tail -200 sales.csv | do "top 3 customers by revenue" | mail -s "weekly" boss@co
```

## env knobs

No config file. Every knob is an env var. Put them in your `.zshrc`/`.bashrc` or inline.

| var                    | default                                      | purpose                             |
| ---------------------- | -------------------------------------------- | ----------------------------------- |
| `DOER_PROVIDER`        | *(auto: bedrock if AWS creds, else ollama)*  | `bedrock` \| `ollama`               |
| `DOER_HISTORY`         | `10`                                         | Q/A pairs injected into prompt      |
| `DOER_SHELL_HISTORY`   | `20`                                         | shell history lines in prompt       |
| **Bedrock**            |                                              |                                     |
| `DOER_BEDROCK_MODEL`   | `global.anthropic.claude-opus-4-7`           | bedrock model id or inference profile |
| `DOER_BEDROCK_REGION`  | `us-west-2`                                  | bedrock region                      |
| `DOER_ANTHROPIC_BETA`  | `context-1m-2025-08-07` *(Claude only)*      | comma-sep `anthropic_beta` headers  |
| `DOER_MAX_TOKENS`      | `128000` (Opus 4.7 native max)               | cap output length                   |
| `DOER_TEMPERATURE`     | *(unset — Opus 4.7 rejects non-default)*     | sampling temperature                |
| `DOER_TOP_P`           | *(unset — Opus 4.7 rejects non-default)*     | nucleus sampling                    |
| `DOER_CACHE_PROMPT`    | *(unset)*                                    | enable prompt caching               |
| `AWS_BEARER_TOKEN_BEDROCK` | *(preferred)*                            | bedrock bearer token                |
| **Ollama**             |                                              |                                     |
| `DOER_MODEL`           | `qwen3:1.7b`                                 | any model Ollama can run            |
| `OLLAMA_HOST`          | `http://localhost:11434`                     | point at a remote Ollama            |

```bash
# default: Claude Opus 4.7 on Bedrock (1M context, 128k output)
do "review this pull request" < diff.patch

# force ollama for offline/private work
DOER_PROVIDER=ollama DOER_MODEL=qwen3:4b do "rewrite idiomatic" < utils.py

# pin a specific Bedrock model (Sonnet 4 for cost savings)
DOER_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0 do "summarize"

# disable the 1M context beta (saves a header, ≤200k ctx)
DOER_ANTHROPIC_BETA="" do "short one"

# remote ollama (on your beefy box)
OLLAMA_HOST=http://gpu-box:11434 DOER_PROVIDER=ollama do "explain this codebase"
```

!!! warning "Opus 4.7 breaking changes"
    - `temperature` / `top_p` **are not sent by default** — Opus 4.7 returns 400 on any non-default value.
    - `output-300k-2026-03-24` (seen in SDKs) is **not yet accepted by Bedrock**. Opus 4.7's real cap is **128k** — `doer` defaults to that.
    - Both issues go away for older models (Sonnet 4, Opus 4.6) — just pin `DOER_BEDROCK_MODEL`.

## when to use which binary

| situation                        | prefer   |
| -------------------------------- | -------- |
| inline one-liner, tight pipe     | `do`     |
| script where clarity wins        | `doer`   |
| aliasing to something shorter    | `do`     |

Both resolve to the same Python. Zero difference in behavior.

## exit codes

| code | meaning                                     |
| ---- | ------------------------------------------- |
| 0    | clean run                                   |
| 1    | uncaught error (usually Ollama down)        |
| 130  | Ctrl-C                                      |

Use in scripts:

```bash
if ! do "is there a TODO in $FILE?" < "$FILE" | grep -qi yes; then
    echo "clean" && exit 0
fi
echo "has todos" && exit 1
```

## interactive mode

Run `do` with no args, no pipe → interactive REPL.

```bash
$ do
🦆 > how many files here?
23
🦆 > which is the biggest?
video.mp4 — 412 MB
🦆 > ^D
```

Each turn writes to `~/.doer_history`, which is re-injected next session.
**No active connection. No websocket. Just files.**

## read the [Cookbook →](cookbook.md)

for 40+ real-world recipes.
