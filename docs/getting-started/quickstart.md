# Quickstart

## One-Shot Queries

```bash
doer "what day is it?"
doer "count .py files here"
doer "largest file in this directory"
```

## Piping In

doer detects non-TTY stdin automatically. Output stays clean for further piping.

```bash
echo "hello world" | doer "reverse this"

cat README.md | doer "tldr in 3 bullets"

git log --oneline -20 | doer "group commits by theme"

ps aux | doer "which processes eat the most memory?"

curl -s https://api.github.com/repos/cagataycali/doer | doer "summarize"
```

## Chaining

```bash
# debug a test failure
pytest 2>&1 | doer "root cause?" | tee analysis.txt

# generate → review
doer "write a bash script that backs up ~/Documents" | doer "review for bugs"

# multi-step
git diff | doer "explain" | doer "rewrite as changelog entry"
```

## From Python

```python
import doer

answer = doer("uptime?")
print(answer)

# Module is directly callable thanks to __class__ override
```

## As a Module

```bash
python -m doer "hostname"
```

## Interactive Mode

When stdin *is* a TTY and no query is given — prints usage. doer is pipe-first, not a REPL. Use devduck for REPL.

## Tips

- **Be terse.** doer is trained to give one-shot terse answers.
- **No markdown when piped.** Clean output for further processing.
- **Shell tool is always available.** It can run any command you can.
