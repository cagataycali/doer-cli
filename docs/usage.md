# Usage

## one-shot query

```bash
do "find files larger than 100MB"
do "current git branch?"
do "what's my public IP?"
```

## piped input

`stdin` becomes the context.

```bash
cat error.log  | do "what broke"
git diff        | do "review this"
git log -20     | do "release notes"
curl -s api.io  | do "summarize"
echo '{"a":1}'  | do "to yaml"
```

## chained

`stdout` is clean — no markdown when piped. Just the answer. Chain with `|`, `tee`, `xargs`:

```bash
doer "list top 5 largest files in cwd" | xargs -n1 ls -lh
curl -s api.com/users | do "filter admins only" | jq .
```

## env knobs

| var                    | default                  | purpose                 |
| ---------------------- | ------------------------ | ----------------------- |
| `DOER_MODEL`           | `qwen3:1.7b`             | ollama model id         |
| `OLLAMA_HOST`          | `http://localhost:11434` | ollama endpoint         |
| `DOER_HISTORY`         | `10`                     | Q/A rows in prompt      |
| `DOER_SHELL_HISTORY`   | `20`                     | shell rows in prompt    |

```bash
DOER_MODEL=llama3.2:3b do "explain this file"
```
