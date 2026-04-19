# 🐣 tiny

One file. One agent. Pipe-friendly. Jack of all trades.

```bash
pipx install tiny
tiny "what's in this dir"
cat error.log | tiny "summarize"
echo "hello" | tiny | grep world
```

## Features
- Single `__init__.py`, only `strands-agents` dep
- 3 core tools: `shell` + `manage_tools` + `system_prompt`
- Hot tool reload from `./tools/*.py`
- Bash history injected into context
- Agent responses posted back to bash history
- Pipe-friendly stdin/stdout
