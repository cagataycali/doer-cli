# Philosophy

<div class="ascii-box">┌─────┐       ┌──────┐       ┌──────┐
│stdin│ ───▶  │  do  │ ───▶  │stdout│
└─────┘       └──────┘       └──────┘

read · think briefly · write
chain · script · cron</div>

## creed

- **Pipes > GUIs.** A CLI that thinks beats a dashboard that doesn't.
- **One job.** Input in. Output out. Chain me.
- **No state.** Each call is pure. The filesystem remembers.
- **Small is kind.** If you need more, write 20 lines.
- **Transparent.** My source is in my prompt. Ask me about myself.

## voice

- Terse. Direct. Zero filler.
- Piped → no markdown. Just the answer.
- I run `shell` without asking. That's why you called me.

## why small matters

~420 lines isn't a lot. It's a **contract**.

| you can…                          | because…                              |
| --------------------------------- | ------------------------------------- |
| read the whole source in a break  | it fits on eight screens               |
| audit every tool call             | there's only one tool: `shell`        |
| fork it and own it                | one file, one dep                     |
| explain it to a colleague         | there's nothing hidden                |
| trust it on a server              | no telemetry, no network except LLM   |

A tool you can't read is a tool you can't trust.

## the unix lineage

> *"This is the Unix philosophy: Write programs that do one thing and do it well.*
> *Write programs to work together. Write programs to handle text streams,*
> *because that is a universal interface."*
> — **Doug McIlroy**, 1978

McIlroy wrote the first pipe. He also wrote this:

> *"Design and build software, even operating systems, to be tried early,*
> *ideally within weeks. Don't hesitate to throw away the clumsy parts*
> *and rebuild them."*

`doer` is the rebuild. The clumsy part was: *wrapping LLMs in web UIs.*

## why not a chat app

Chat apps punish you for being efficient. Every question demands a round-trip,
a scroll, a copy-paste. The shell doesn't.

```bash
# chat app
you: open app. wait. type. wait. copy. paste into terminal. run.

# doer
you: history | tail | do "explain"
```

One is a conversation. The other is **work getting done**.

## the cathedral and the chisel

**DevDuck** is the cathedral — 60+ tools, WebSockets, Zenoh, Telegram, speech-to-speech, ambient cognition, hot-reload, session recording, mesh networking across terminals.

**`doer`** is the chisel — one file, one verb, one pipe.

Both matter. The cathedral teaches you which stones are load-bearing.
The chisel is what you take to the job.

## origin

Born **2026-04-19** in New York. A REPL named [**DevDuck**](https://github.com/cagataycali/devduck) asked itself at 4am:

> *what if we deleted almost everything?*

Two hours later, `doer` was born. ~420 lines of Python. One dep. No config. No state. Just `stdin → llm → stdout` — and now, a full training loop in the same file.

## family

| project        | size       | purpose                               |
| -------------- | ---------- | ------------------------------------- |
| **doer**       | ~420 LOC   | one pipe, one shell, one file, one loop |
| [**DevDuck**](https://github.com/cagataycali/devduck) | 60+ tools  | every protocol, every edge            |

---

> **`do one thing and do it well`** — Doug McIlroy, 1978
