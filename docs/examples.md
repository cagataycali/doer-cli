# Examples

Real-world doer usage.

## DevOps

```bash
# find the largest files hogging disk
du -ah / 2>/dev/null | sort -rh | head -50 | doer "group these by directory"

# analyze nginx logs
tail -1000 /var/log/nginx/access.log | doer "top 10 IPs, and any suspicious patterns?"

# what services are listening?
lsof -iTCP -sTCP:LISTEN -n -P | doer "explain what each service does"

# systemd unit health
systemctl --failed | doer "what should I fix first?"
```

## Git Workflows

```bash
# PR description from diff
git diff origin/main | doer "write a PR description with bullet points"

# commit message
git diff --cached | doer "conventional commit message for this diff"

# changelog
git log v1.0..HEAD --oneline | doer "write CHANGELOG entry"

# blame an issue
git log -p --follow src/bad_file.py | doer "when did this bug enter?"
```

## Data Munging

```bash
# CSV → JSON
cat data.csv | doer "convert to json array"

# log → SQL
cat events.log | doer "generate INSERT statements for table events(ts, user, action)"

# YAML → env vars
cat config.yml | doer "flatten to KEY=VALUE env vars"
```

## Code

```bash
# add type hints
cat old.py | doer "add type hints" > new.py

# write tests for existing code
cat src/calculator.py | doer "write pytest tests" > tests/test_calculator.py

# security audit
cat auth.py | doer "security issues?"

# refactor suggestion
cat messy_function.py | doer "refactor for readability, keep behavior"
```

## One-Liners Saved as Aliases

```bash
# in your ~/.zshrc or ~/.bashrc

alias 'explain'='doer "explain what this command does:"'
alias 'why'='doer "why did this fail?"'
alias 'tldr'='doer "tldr"'

# usage:
ls -la | tldr
pytest 2>&1 | why
echo "rsync -avz --progress --delete src/ dst/" | explain
```

## Compose with Other Tools

```bash
# fzf + doer: interactively pick a file, then ask about it
cat "$(fzf)" | doer "explain this file"

# ripgrep + doer: find something, then ask for context
rg "TODO" -A 3 | doer "group todos by urgency"

# jq + doer
curl -s api.example.com/data | jq '.items[]' | doer "any anomalies?"
```

## Hot-Reload Tool + doer

```python
# tools/slack.py
from strands import tool
import urllib.request, json, os

@tool
def post_slack(channel: str, text: str) -> str:
    """Post a message to Slack via webhook."""
    url = os.environ["SLACK_WEBHOOK"]
    urllib.request.urlopen(url, data=json.dumps({"channel": channel, "text": text}).encode())
    return "posted"
```

```bash
doer "summarize latest git log and post to #eng in slack"
```

## From Python Scripts

```python
import doer, subprocess

# use doer as a helper
logs = subprocess.run(["journalctl", "-n", "500"], capture_output=True, text=True).stdout
analysis = doer(f"analyze these logs:\n{logs}")
print(analysis)
```
