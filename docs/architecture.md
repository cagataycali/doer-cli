# Architecture

doer in one file: `doer/__init__.py` (~166 lines).

## Flow

```
┌──────────┐      ┌──────────┐      ┌──────────────┐     ┌─────────┐
│  stdin   │──┐   │          │      │              │     │         │
│          │  ├──▶│  cli()   │─────▶│   Agent()    │────▶│ stdout  │
│  argv    │──┘   │          │      │              │     │         │
└──────────┘      └──────────┘      └──────────────┘     └─────────┘
                                          │  ▲
                                          │  │
                                          │  │  system_prompt:
                                          │  │   - env info
                                          │  │   - _source() (own code)
                                          │  │   - _history(10)
                                          │  │   - _shell_history(20)
                                          │  │
                                          ▼  │
                                    ┌──────────────┐
                                    │  shell tool  │
                                    │  +./tools/*  │
                                    └──────────────┘
```

## Key Design Decisions

### 1. One file

Everything — the agent, the shell tool, the history parser, the CLI, the source reader — lives in `doer/__init__.py`. No submodules. No internal abstractions. If you want to understand doer, read one file.

### 2. Pipe detection drives behavior

```python
_PIPED = not sys.stdin.isatty() or not sys.stdout.isatty()
```

When piped:

- `null_callback_handler` — no streaming UI
- Terse output — no markdown bloat

### 3. Stateless per-invocation

```python
conversation_manager=NullConversationManager()
```

Each invocation is independent. History flows in via the system prompt *for context only*, not as chat messages. This means:

- No state bleed between calls.
- Parallel invocations are safe.
- Cheap — no memory accumulation.

### 4. Self-aware via source injection

The full `__init__.py` is embedded in the system prompt. Works in:

- Regular installs (`__file__`)
- PyInstaller frozen binaries (`_MEIPASS`)

### 5. Module itself is callable

```python
class _Callable(sys.modules[__name__].__class__):
    def __call__(self, q): return ask(q)
sys.modules[__name__].__class__ = _Callable
```

So `import doer; doer("query")` works directly. No `.ask()` method needed.

### 6. Hot-reload via strands

`load_tools_from_directory=True` tells strands to scan `./tools/` on each agent init. Zero code in doer for this.

## Dependencies

- `strands-agents` — agent framework, tool system, model abstraction.

That's it. Everything else is stdlib.

## Where Is Each Thing?

| Concern | Location |
|---------|----------|
| Entry point | `cli()` |
| Shell tool | `shell()` @tool |
| Self-source reader | `_source()` |
| doer history parser | `_history()` |
| bash/zsh history parser | `_shell_history()` |
| History append | `_append()` |
| System prompt | `PROMPT` |
| Agent factory | `_agent()` |
| Public API | `ask()` + module `__call__` |

## Build System

| File | Purpose |
|------|---------|
| `pyproject.toml` | PEP 517 package definition |
| `build.sh` | PyInstaller onefile binary |
| `build-nuitka.sh` | Nuitka native compile |
| `doer-darwin-arm64.spec` | PyInstaller spec reference |

## CI

| Workflow | Trigger | Output |
|----------|---------|--------|
| `docs.yml` | push to main | MkDocs → GitHub Pages |
| `release.yml` | tag `v*.*.*` | PyPI publish + GH release + binaries |
