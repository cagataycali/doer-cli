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
  <a href="cookbook/">Cookbook</a>
  <a href="https://github.com/cagataycali/doer-cli">GitHub</a>
</div>

<div class="doer-badges" markdown>
[![PyPI](https://img.shields.io/pypi/v/doer-cli.svg?style=for-the-badge&color=FF3D00&labelColor=0A0A0A)](https://pypi.org/project/doer-cli/)
[![License](https://img.shields.io/badge/APACHE-2.0-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](https://github.com/cagataycali/doer-cli/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.10%2B-FAFAF7?style=for-the-badge&labelColor=0A0A0A)](https://python.org)
</div>

</div>

---

## 60-second taste

```bash
pipx install doer-cli

do "find files larger than 100MB"
cat error.log | do "what broke"
git log -20   | do "write release notes"
```

## why `doer`

Not a chatbot. Not a wrapper. **`grep` with a brain.**

<div class="grid cards" markdown>

-   :material-pipe: __Pipes > GUIs__

    `stdin` in, `stdout` out. Chain it. Cron it. Ship it.

-   :material-file-document-outline: __No state__

    Every call is pure. The filesystem is the memory.

-   :material-feather: __Small is kind__

    **164 lines** of Python. One dep. Auditable in a lunch break.

-   :material-magnify: __Transparent__

    Own source in its system prompt. Ask it how it works.

</div>

## the arrow

<div class="ascii-box">┌─────┐       ┌──────┐       ┌──────┐
│stdin│ ───▶  │  do  │ ───▶  │stdout│
└─────┘       └──────┘       └──────┘</div>

[Install →](install.md){ .md-button .md-button--primary }
[See the Cookbook →](cookbook.md){ .md-button }
