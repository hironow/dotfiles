# Search and replacement tools

Use `rg` for file contents, `fd` for paths, and `sd` for text replacements.
Keep every search inside the current project or a named, task-relevant directory.

These commands have different arguments and defaults from `grep`, `find`, and
`sed`. Call them by their own names. Keep portable bootstrap commands usable
before these tools are installed.

## Content: ripgrep (`rg`)

| Task | Command |
| --- | --- |
| Search recursively, with line numbers | `rg -n 'pattern' src/` |
| Match literal text | `rg -n -F 'literal.text' src/` |
| List matching files | `rg -l 'pattern' src/` |
| List files by glob | `rg --files -g '*.go' src/` |
| Include hidden files in a named directory | `rg --hidden -n 'pattern' config/` |
| Include ignored files too | `rg --hidden --no-ignore -n 'pattern' output/` |

`rg` recurses by default and skips hidden, ignored, and binary files.
Use ignore overrides only when the task needs those files; keep an explicit path.
It is case-sensitive by default (`-i` ignores case; `-S` enables smart case).
Its default regex engine has no lookaround or pattern backreferences;
use `-P` only when needed and supported by the installed build.
Exit 0 means a match, 1 means no match, and 2 means an error.
`rg --replace` prints replacements; it does not edit files.

## Paths: fd (`fd`)

| Task | Command |
| --- | --- |
| Find files by glob | `fd --type f --glob '*.go' src/` |
| Find directories by name | `fd --type d 'cache' output/` |
| Match the full path | `fd --full-path 'internal/.+test' src/` |
| Include hidden and ignored paths | `fd --hidden --no-ignore --type f . config/` |
| Produce NUL-delimited paths | `fd --print0 --type f --glob '*.go' src/` |

The order is `fd [options] PATTERN [DIRECTORY...]`, unlike `find DIRECTORY …`.
The pattern is a regex matched against the basename; use `--glob` for shell
globs and quote them. Searches use smart case and skip hidden and ignored paths.
`fd -H` includes hidden paths; `rg -H` instead prints filenames.
Use `--case-sensitive` when the filename's case must match exactly.
Mise installs the command as `fd`, including on Ubuntu; no `fdfind` alias is needed.
For commands on matches, put `--exec` last: it runs once per match, in parallel.
`--exec-batch` runs with batches of paths. Use NUL delimiters when piping paths.

## Replacements: sd (`sd`)

| Task | Command |
| --- | --- |
| Preview a literal replacement | `sd --preview --fixed-strings 'old.text' 'new.text' file.txt` |
| Apply a literal replacement | `sd --fixed-strings 'old.text' 'new.text' file.txt` |
| Use a capture group | `sd '(item)_[0-9]+' '${1}_next' file.txt` |
| Replace text across lines | `sd --across 'first\nsecond' 'joined' file.txt` |

The order is `sd [options] FIND REPLACEMENT [FILES...]`.
Files are edited in place by default; preview first and inspect `git diff` after.
Without file arguments, `sd` reads stdin and writes stdout.
Regex replacement applies to every match; there is no `s/…/…/g` expression or
`sed -i` option. Use `--fixed-strings` for literal find and replacement strings.
Regex replacements use `$1` or `${1}`, not `\1`; single-quote them in the shell.
The default regex engine has no lookaround or pattern backreferences.
Version 1.1 processes one line at a time by default; `--across` reads the full
input for multiline matches. `sd` handles substitution, not `sed` line-address
printing or deletion; choose a tool that implements the required operation.

## References

- [ripgrep guide](https://github.com/BurntSushi/ripgrep/blob/15.2.0/GUIDE.md)
- [fd usage](https://github.com/sharkdp/fd/tree/v10.5.0#how-to-use)
- [sd usage](https://github.com/chmln/sd/tree/v1.1.0#quick-guide)
