---
hide:
  - navigation
  - toc
---

<div class="doer-hero" markdown>

<img src="doer.svg" alt="doer">

# DO<span class="accent">ER</span>.

<div class="flow">stdin → agent → stdout</div>

<div class="tag">A Unix citizen that thinks.<br>In text, images, audio, and video.</div>

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

<div class="term" markdown>
<div class="term-header">
  <span class="dot red"></span>
  <span class="dot amber"></span>
  <span class="dot green"></span>
  <span class="title">~/projects — do</span>
</div>
<div class="term-body">
<span class="prompt">$</span> <span class="cmd">pipx install doer-cli</span>
<span class="out">installed package doer-cli 0.3.0, installed using Python 3.13</span>
<span class="out">  · </span><span class="ok">do</span><span class="out">   (short form)</span>
<span class="out">  · </span><span class="ok">doer</span><span class="out"> (long form)</span>

<span class="prompt">$</span> <span class="cmd">do "find files larger than 100MB"</span>
<span class="out">./video.mp4      412M
./archive.tar.gz 168M
./model.bin      124M</span>

<span class="prompt">$</span> <span class="cmd">cat error.log | do "what broke"</span>
<span class="out">redis connection timeout at 14:22 —
likely the </span><span class="hl">REDIS_URL</span><span class="out"> env var is stale.</span>

<span class="prompt">$</span> <span class="cmd">do --img screenshot.png "what's in this UI?"</span>
<span class="out">login form, 3 fields, submit button disabled.
a password validator is throwing — check </span><span class="hl">password_regex.py:22</span><span class="out"></span>

<span class="prompt">$</span> <span class="cmd">do --train 200 && DOER_PROVIDER=mlx DOER_ADAPTER=~/.doer_adapter do "reply terse"</span>
<span class="out">loading 127 turns...
training LoRA (rank 8, 200 iters)...
✓ saved → ~/.doer_adapter
ok.</span>

<span class="prompt">$</span> <span class="cursor"></span>
</div>
</div>

## why `doer`

Not a chatbot. Not a wrapper. **`grep` with a brain.**

<div class="grid cards" markdown>

-   :material-pipe: __Pipes > GUIs__

    `stdin` in, `stdout` out. Chain it. Cron it. Ship it.

-   :material-file-document-outline: __No state__

    Every call is pure. The filesystem is the memory.

-   :material-feather: __Small is kind__

    **~730 lines** of Python. Core is one dep. Auditable in an afternoon. Closes its own training loop (text + VLM).

-   :material-magnify: __Transparent__

    Own source in its system prompt. Ask it how it works.

</div>

## the arrow

<div class="ascii-box">┌─────┐       ┌──────┐       ┌──────┐
│stdin│ ───▶  │  do  │ ───▶  │stdout│
└─────┘       └──────┘       └──────┘</div>

[Install →](install.md){ .md-button .md-button--primary }
[See the Cookbook →](cookbook.md){ .md-button }
