# Extend

`doer` has **one** built-in tool: `shell`. Every other skill comes from dropping Python files into `./tools/`.

## the 60-second tool

```python title="./tools/weather.py"
from strands import tool
import urllib.request

@tool
def weather(city: str) -> str:
    """Weather for a city."""
    return urllib.request.urlopen(
        f"https://wttr.in/{city}?format=3"
    ).read().decode()
```

Next call:

```bash
do "weather istanbul?"
# → istanbul: ☀️ +22°C
```

**No restart. No import. No registration.** Strands hot-reloads `./tools/*.py` on every call.

## rules

1. **Decorate with `@tool`** from `strands`.
2. **Type-hint everything.** Types become the JSON schema the LLM sees.
3. **Docstring is the description.** The first line is what shows up in tool picker.
4. **Keep side-effects predictable.** The agent will call you more than you expect.

## richer: sqlite tool

```python title="./tools/db.py"
from strands import tool
import sqlite3
from pathlib import Path

@tool
def query_db(sql: str) -> str:
    """Run a read-only SQL query on ./data.db. Returns up to 50 rows."""
    db = Path("data.db")
    if not db.exists():
        return "error: data.db not found in cwd"
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        try:
            rows = conn.execute(sql).fetchall()
            if not rows:
                return "(no rows)"
            return "\n".join(str(r) for r in rows[:50])
        except sqlite3.Error as e:
            return f"sql error: {e}"
```

```bash
do "how many users signed up last week?"
# → agent writes SQL, calls query_db, formats the answer
```

## richer: http client

```python title="./tools/http.py"
from strands import tool
import urllib.request, json

@tool
def http_get(url: str, accept: str = "application/json") -> str:
    """GET a URL. Returns the body as text (truncated to 10KB)."""
    req = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read(10_000).decode("utf-8", errors="replace")
```

```bash
do "fetch the latest hn stories, pick 3 about rust"
```

## patterns

=== "batch worker"

    ```python title="./tools/resize.py"
    from strands import tool
    from PIL import Image
    from pathlib import Path

    @tool
    def resize_images(glob: str, max_px: int = 1200) -> str:
        """Resize all images matching glob, longest side = max_px. Writes in-place."""
        n = 0
        for p in Path.cwd().glob(glob):
            im = Image.open(p)
            im.thumbnail((max_px, max_px))
            im.save(p)
            n += 1
        return f"resized {n} images"
    ```

=== "shell wrapper"

    ```python title="./tools/git_tools.py"
    from strands import tool
    import subprocess

    @tool
    def git_blame_line(file: str, line: int) -> str:
        """Who wrote a specific line of a file, and when."""
        out = subprocess.check_output(
            ["git", "blame", "-L", f"{line},{line}", "--porcelain", file],
            text=True
        )
        return out.splitlines()[0] if out else "(no blame)"
    ```

=== "api wrapper"

    ```python title="./tools/openai_image.py"
    from strands import tool
    import os, base64, urllib.request, json

    @tool
    def generate_image(prompt: str, out: str = "out.png") -> str:
        """Generate an image via OpenAI, save to disk."""
        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps({"model": "gpt-image-1", "prompt": prompt}).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        r = json.load(urllib.request.urlopen(req))
        b64 = r["data"][0]["b64_json"]
        with open(out, "wb") as f:
            f.write(base64.b64decode(b64))
        return f"saved → {out}"
    ```

## stacking

Drop as many tools as you want into `./tools/`. The agent sees all of them, picks the right one per call. **You don't wire anything.**

```
project/
├── SOUL.md              ← identity
├── AGENTS.md            ← project rules
├── tools/
│   ├── db.py            ← sqlite helper
│   ├── http.py          ← http client
│   └── weather.py       ← wttr.in
└── data.db
```

`cd` into the project → `do` inherits **all** of it. Leave → it's gone.

## where tools live

- **cwd**: `./tools/*.py` — project-specific, under version control
- **home**: `~/doer/tools/*.py` — personal, cross-project (opt-in)

!!! warning "security"
    Tools run as **you**. They have full filesystem + network access. Only drop in tools you trust.

## where to find more

- The **`strands-agents-tools`** package bundles dozens: http, filesystem, speech, screen, spotify, github…  
  ```bash
  pipx inject doer-cli strands-agents-tools
  ```
- See also: [**DevDuck**](https://github.com/cagataycali/devduck) — the cathedral — ships 60+ tools out of the box. Copy whatever you like back into `doer`.

---

> **`do` is small so you can grow it.**

---

## tools in the training corpus

Every `@tool` you drop into `./tools/` is captured in `~/.doer_training.jsonl` alongside its `input_schema`. When you run `do --train`, the LoRA adapter learns **your** tool surface — not a generic one.

Drop a tool, use it 20 times, train for 200 iters → a small MLX model that knows *your* weather tool, *your* db schema, *your* shell idioms.

Training works on multimodal turns too — `do --img screenshot.png --train-vlm` teaches the vision adapter your screenshot-debug workflow. See [**Train on yourself**](train.md).
