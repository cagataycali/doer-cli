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

| var                    | default                  | purpose                             |
| ---------------------- | ------------------------ | ----------------------------------- |
| `DOER_MODEL`           | `qwen3:1.7b`             | any model Ollama can run            |
| `OLLAMA_HOST`          | `http://localhost:11434` | point at a remote Ollama            |
| `DOER_HISTORY`         | `10`                     | Q/A pairs injected into prompt      |
| `DOER_SHELL_HISTORY`   | `20`                     | shell history lines in prompt       |
| `DOER_MAX_TOKENS`      | model default            | cap output length                   |

```bash
# faster little model
DOER_MODEL=qwen3:0.5b  do "summarize this" < README.md

# bigger brain for tougher queries
DOER_MODEL=qwen3:4b    do "rewrite this function idiomatic" < utils.py

# remote ollama (on your beefy box)
OLLAMA_HOST=http://gpu-box:11434 do "explain this codebase"
```

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
