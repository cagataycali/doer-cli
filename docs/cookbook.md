# Cookbook

Real one-liners. Copy, paste, ship.

## dev flow

```bash
# review what you're about to commit
git diff --cached | do "any bugs? be ruthless"

# write a conventional commit message from the diff
git diff --cached | do "write a conventional commit message, one line"

# release notes from last 20 commits
git log -20 --oneline | do "write release notes, markdown, grouped by type"

# find the one commit that broke tests
git log --oneline -50 | do "which commit likely broke test_auth?"
```

## shell archaeology

```bash
# figure out what that cryptic one-liner does
history | tail -1 | do "explain this command"

# find heavy hitters in a big log
tail -10000 /var/log/system.log | do "top 5 error patterns, count them"

# audit your last session
fc -l -100 | do "summarize what I was working on"
```

## data wrangling

```bash
# JSON → anything
curl -s api.io/users | do "convert to csv, only id and email"

# CSV → insights
cat sales.csv | do "top 3 products by revenue"

# messy log → structured
tail -500 nginx.log | do "extract 5xx requests only, show path + count"
```

## ops

```bash
# quick disk audit
du -sh * | sort -h | tail -10 | do "which of these can I probably delete?"

# process detective
ps aux | sort -rk 3 | head -10 | do "what's eating CPU?"

# port sleuth
lsof -iTCP -sTCP:LISTEN -P | do "any suspicious listeners?"
```

## writing

```bash
# polish a paragraph from clipboard
pbpaste | do "tighten this, cut filler, keep voice" | pbcopy

# markdown → tweet
cat post.md | do "compress to 280 chars, keep hook"

# translate a file
cat notes.md | do "translate to turkish, keep code blocks as-is"
```

## chained pipelines

```bash
# find → summarize → action
find . -name "*.py" -mtime -7 |
  do "which of these changed most significantly?" |
  xargs -n1 wc -l

# scrape → filter → act
curl -s news.ycombinator.com/rss |
  do "list top 10 titles related to rust" |
  tee hot-rust.md

# inbox → inventory
ls ~/Downloads | do "group by probable purpose"
```

## one-off utilities (faster than googling)

```bash
do "regex to match IPv4"
do "sql: find duplicate emails in users table"
do "awk: sum column 3 of CSV"
do "curl command to post JSON with bearer token"
do "cron expression for every monday 9am"
```

## scripted

`do` is just a program. Put it in scripts. Put it in cron.

```bash
#!/usr/bin/env bash
# daily-digest.sh — run at 9am
{
  echo "## git"; git -C ~/work log --since=yesterday --oneline
  echo "## mail"; mail -H | tail -20
  echo "## agenda"; cat ~/today.txt
} | do "turn this into a one-paragraph morning briefing" | terminal-notifier -title "Digest"
```

```cron
0 9 * * 1-5  cd ~ && ./daily-digest.sh
```

---

> if you find yourself writing the same pipe twice, make a script.
> if you find yourself writing the same script twice, make a tool.  
> see [Extend →](extend.md)
