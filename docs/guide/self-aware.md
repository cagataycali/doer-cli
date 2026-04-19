# Self-Aware

doer reads its own source code and injects it into the system prompt on every call. The agent always knows what it is.

## How It Works

```python
def _source():
    if getattr(sys, "frozen", False):
        # PyInstaller: source bundled in _MEIPASS
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for candidate in (base / "doer" / "__init__.py", base / "__init__.py"):
            if candidate.exists():
                return candidate.read_text()
    return Path(__file__).read_text()
```

Works in three modes:

1. **Installed as package** — reads `__file__`
2. **Editable install** — reads `__file__`
3. **PyInstaller frozen binary** — reads bundled source from `_MEIPASS`

## Why?

- **Introspection** — ask `doer "what tools do you have?"` and it actually knows
- **Self-modification** — ask it to modify itself and it has a reference
- **Debugging** — misbehaving? Ask it to explain its own logic
- **Trust** — no hidden behavior; the agent sees exactly what you run

## Prompt Structure

The system prompt contains:

1. Environment info (platform, cwd, my path)
2. Behavioral rules (terse, no markdown when piped)
3. Recent Q/A history (last 10)
4. Recent shell commands (last 20, bash + zsh)
5. **Full own source code**

See [History](history.md) for how past interactions flow in.

## Try It

```bash
doer "what's in your system prompt?"
doer "what tools do you have available?"
doer "how do you detect pipes?"
doer "what's your source file path?"
```
