# Extend

Drop any Python file into `./tools/`. Next call, it's live. No restart.

## a tool in 60 seconds

```python title="./tools/weather.py"
from strands import tool
import urllib.request

@tool
def weather(city: str) -> str:
    """Weather for a city."""
    url = f"https://wttr.in/{city}?format=3"
    return urllib.request.urlopen(url).read().decode()
```

Then:

```bash
do "weather istanbul?"
```

## what Strands gives you

- Hot-reload: save → next call sees it
- Auto-registered: nothing to import
- Type hints = JSON schema = LLM-friendly

## a richer example

```python title="./tools/db.py"
from strands import tool
import sqlite3

@tool
def query_db(sql: str) -> str:
    """Run a read-only SQL query on ./data.db."""
    conn = sqlite3.connect("data.db")
    try:
        rows = conn.execute(sql).fetchall()
        return "\n".join(str(r) for r in rows[:50])
    finally:
        conn.close()
```

```bash
do "how many users signed up last week?"
# → agent writes SQL, calls query_db, formats result
```

## stacking tools

Drop as many files as you want. All of them are available on every call. That's the extension point.
