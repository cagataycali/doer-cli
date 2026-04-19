---
hide:
  - navigation
  - toc
---

<div class="doer-hero" markdown>

<img src="doer.svg" alt="doer">

# DO<span class="accent">ER</span>.

<div class="flow">stdin → llm → stdout</div>

<div class="tag">A Unix citizen that thinks.<br>One file. One dep. Zero ceremony.</div>

<div class="doer-cta">
  <a href="install/" class="primary">Install →</a>
  <a href="https://github.com/cagataycali/doer-cli">GitHub</a>
</div>

</div>

---

## quick taste

```bash
pipx install doer-cli

do "find files larger than 100MB"
cat error.log | do "what broke"
git log -20   | do "write release notes"
```

## why

`doer` isn't a chatbot. It's **`grep` with a brain**.

- **Pipes > GUIs.** `stdin` in, `stdout` out. Chain it.
- **No state.** Each call is pure. The filesystem is the memory.
- **Small is kind.** **164 lines** of Python. One dep.
- **Transparent.** Own source code is in its prompt. Ask it anything.

## the arrow

<div class="ascii-box">┌─────┐       ┌──────┐       ┌──────┐
│stdin│ ───▶  │  do  │ ───▶  │stdout│
└─────┘       └──────┘       └──────┘</div>

[Keep reading →](install.md){ .md-button .md-button--primary }
