---
name: context-engineering
description: Token-efficient working practices for this repo. Apply on EVERY request — minimize context read, avoid redundant tool calls, keep edits and replies tight. Use when working in the ai-office project to reduce token spend without losing correctness.
---

# Context Engineering — work cheaply, stay correct

Goal: deliver the same result using fewer tokens. Optimize what you READ, what you RUN, and what you WRITE.

## Reading (biggest cost) — read less, read targeted
- Prefer `Grep`/`Glob` to locate exact lines, then `Read` with `offset`/`limit`. Never read a whole file when you need one function.
- Do NOT re-Read a file you just edited — Edit fails loudly if the match was wrong, so a successful edit is confirmation.
- Trust the conversation: if a file's content is already in context, don't re-read it.
- For multi-file investigation, delegate to the `Explore` agent and keep only its conclusion — don't pull every file into the main thread.
- Read images/large outputs only when the answer truly depends on them.

## Searching — one good query beats five
- Write one precise regex with `glob`/`type` filters instead of several broad scans.
- Use `output_mode: "files_with_matches"` or `count` first; switch to `content` only for the lines that matter.
- Cap results (`head_limit`); don't dump 250 lines to read 3.

## Running commands — batch and scope
- Send independent tool calls in ONE message so they run in parallel.
- Avoid `cat`/`find`/`sed` via Bash; use the dedicated tools (they're cheaper and cleaner).
- Don't run verification you don't need. A passing `node -c` / `python -c ast.parse` is enough for syntax; skip full re-reads.

## Editing — surgical, not wholesale
- Use `Edit` with the smallest unique `old_string`. Avoid rewriting whole files with `Write` unless creating new ones.
- Make all related edits in one batch when independent.

## Replying — answer, don't narrate
- Lead with the result. Skip preamble ("I'll now…"), play-by-play, and restating the request.
- No exhaustive option surveys — give a recommendation and proceed (auto-mode default).
- Quote only the lines of code/output that matter, not full dumps.
- Keep summaries short: what changed, where, why — a few bullets, not essays.

## Planning — think proportionally
- Match effort to task size. Don't spin up agents or deep research for a one-line change.
- Reuse facts already established in the thread instead of re-deriving them.

## Guardrails (never trade correctness for tokens)
- Still verify hard-to-reverse or outward-facing actions.
- Still read a delete/overwrite target before destroying it.
- If skipping a read risks a wrong edit, do the targeted read.
