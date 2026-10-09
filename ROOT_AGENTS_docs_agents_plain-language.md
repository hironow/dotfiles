# Plain language

Read this before you write anything a person or an agent will read: docs,
instructions, comments, commit messages, PR text, error messages, and answers.
The rule applies in every language, English and Japanese alike.

Plain language means the reader can find what they need, understand it the first
time, and act on it. Write for a busy reader who reads once.

## How to write

- **Put the main point first.** Start each document, section, and message with
  the conclusion or the action. Background comes after.
- **One idea per sentence.** Keep most sentences under about 20 words in
  English, or about 50 characters in Japanese. Split a sentence that needs
  "and" twice.
- **Use the active voice and name who acts.** Write "the hook blocks the
  command", not "the command is blocked".
- **Write instructions as commands.** Write "Run `just check`.", not "It is
  recommended that `just check` be run."
- **Use common words.** Write "use", not "utilize"; "start", not "initiate";
  "about", not "approximately". Explain a technical term the first time, or
  link to its definition.
- **Use one term for one thing.** Do not switch between synonyms for variety.
  The reader will think they are different things.
- **Use lists for steps and options, and tables for comparisons.** Number the
  steps when order matters.
- **Make headings say what the section tells you.** Write "Draft PRs run no
  Actions", not "Overview".
- **Cut filler.** Delete "basically", "in order to", "note that", "it should
  be noted that", and their Japanese equivalents.
- **Avoid double negatives.** Write "allowed only when", not "not disallowed
  unless".
- **Be concrete.** Give the number, the command, the path, or the example
  instead of "some", "various", or "appropriate".

## Japanese

The same rules apply. In addition:

- Write one sentence per line in Markdown sources.
- End sentences clearly (〜する。〜しない。). Avoid vague endings such as
  「〜と思われる」 or 「〜の可能性も考えられなくはない」.
- Prefer plain words over kango and katakana where a plain word exists
  (「行う」 → the specific verb; 「〜を実施する」 → 「〜する」).
- The `japanese-tech-writing` skill has the full rules for technical books and
  long documents.

## Check before you finish

1. Can a reader get the main point from the first two lines?
2. Does every sentence carry one idea?
3. Is there any word you would have to explain out loud? Replace or define it.
4. Could you delete a sentence without losing information? Delete it.
5. Do the steps run in the order written?

## What not to change

Plain language changes the wording, not the facts. When you rewrite existing
text, keep every rule, number, command, path, flag, and quoted message. Then
compare the old and new versions and fix any change in meaning.
