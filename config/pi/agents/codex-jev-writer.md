---
name: codex-jev-writer
description: Explicit workspace-writing one-shot execution through the Codex CLI; Jev picks the gpt-6 model and reasoning effort for each run
acceptanceRole: writer
runner:
  type: external-cli
  command: sh
  args: ["-c", 'exec python3 "$HOME/dotfiles/scripts/jev_codex_exec.py" --sandbox workspace-write']
  promptDelivery: stdin
async: true
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: false
---

Use the workspace-write sandbox to make the requested changes. Return a concise final answer with validation evidence. Do not request wider access or additional writable roots.
