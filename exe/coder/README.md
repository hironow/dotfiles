# exe/coder/

Coder workspace template for `exe.hironow.dev`.

The template is based on
[`coder/coder/examples/templates/gcp-vm-container`](https://github.com/coder/coder/tree/main/examples/templates/gcp-vm-container)
and references this repository's `.devcontainer/devcontainer.json` so
that workspace == CI environment.

Files (added in subsequent commits):

- `template.tf` — Coder template definition
- `startup.sh` — VM startup script (mise install, just install-hooks)
