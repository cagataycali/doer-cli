# Hot-Reload Tools

doer uses strands-agents' built-in tool auto-discovery. Drop a `@tool` decorated function in `./tools/*.py` — it's instantly available on the next invocation.

## How It Works

```python
Agent(
    ...
    load_tools_from_directory=True,  # ← scans ./tools/
)
```

Each invocation scans `./tools/` and loads any Python file that exposes `@tool` functions.

## Create a Tool

```python
# tools/greet.py
from strands import tool

@tool
def greet(name: str) -> str:
    """Say hi to someone."""
    return f"hi {name}!"
```

Use immediately:

```bash
doer "greet alice"
# → hi alice!
```

## Real Examples

### `tools/weather.py`

```python
from strands import tool
import urllib.request, json

@tool
def weather(city: str) -> str:
    """Get current weather for a city."""
    url = f"https://wttr.in/{city}?format=j1"
    data = json.loads(urllib.request.urlopen(url, timeout=5).read())
    cur = data["current_condition"][0]
    return f"{cur['temp_C']}°C, {cur['weatherDesc'][0]['value']}"
```

### `tools/sqlite_query.py`

```python
from strands import tool
import sqlite3

@tool
def sqlite_query(db_path: str, query: str) -> str:
    """Run a SELECT against a SQLite DB."""
    with sqlite3.connect(db_path) as con:
        rows = con.execute(query).fetchall()
    return "\n".join(map(str, rows))
```

### `tools/k8s.py`

```python
from strands import tool
import subprocess

@tool
def kubectl(args: str) -> str:
    """Run kubectl with given args."""
    return subprocess.check_output(["kubectl", *args.split()], text=True)
```

## Project Layout

```
my-project/
├── tools/
│   ├── greet.py
│   ├── weather.py
│   └── k8s.py
└── ... (your code)
```

Run `doer` from that directory and all tools are loaded.

## Tips

- Tool names must be **unique** — last loaded wins.
- Keep tool fns **small and focused** — one action per tool.
- Use type hints — strands uses them for the JSON schema.
- Docstrings become the tool description the LLM sees.
