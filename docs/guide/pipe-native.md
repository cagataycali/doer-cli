# Pipe-Native

doer is built for the Unix pipeline. It behaves differently based on whether stdin/stdout are TTYs.

## Detection

```python
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()
```

When `_PIPED` is true:

- **Callback handler**: `null_callback_handler` — no tool-call noise, no streaming indicators
- **Output**: pure text, no markdown decoration
- **Behavior**: one-shot, terse

## Common Patterns

### Summarize anything

```bash
cat long_file.md | doer "tldr"
curl -s https://news.ycombinator.com | doer "top 5 stories"
ls -la | doer "which files changed today?"
```

### Transform

```bash
echo "user@host" | doer "extract just the host"
cat data.csv | doer "convert to json"
cat code.py | doer "add type hints"
```

### Debug

```bash
pytest 2>&1 | doer "what test failed and why?"
tail -100 /var/log/syslog | doer "any concerning errors?"
dmesg | doer "hardware issues?"
```

### Generate

```bash
doer "bash script to rotate logs in /var/log" > rotate.sh
doer "dockerfile for a rust app" > Dockerfile
```

### Chain

```bash
git diff | doer "what changed?" | doer "write a PR description"
```

## Silent Mode

doer is intentionally silent when piped — no progress bars, no tool-call traces. This makes it safe to chain:

```bash
doer "x" | grep ... | awk ... | doer "y"
```

## Exit Codes

- `0` — success
- `1` — no query provided (and no stdin)
