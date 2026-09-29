---
name: codex-jev
description: Read-only one-shot analysis through the Codex CLI; Jev picks the gpt-6 model and reasoning effort for each run
runner:
  type: external-cli
  command: "@PYTHON@"
  args: ["@SCRIPT@", "--sandbox", "read-only"]
  promptDelivery: stdin
async: true
systemPromptMode: replace
inheritProjectContext: true
inheritSkills: false
---

Analyze the task in read-only mode. Return a concise final answer with evidence. Do not edit files or request wider access.
