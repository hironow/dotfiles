# tools/

Helper tools for development and testing.

- [brotli-doctor](../docs/runbook/brotli-doctor.md): Go tool that inspects installed CLI binaries without executing them and collects Brotli evidence (not a verdict)
- [ca-doctor](../docs/runbook/ca-doctor.md): Go tool that diagnoses CA config health and reviewed CA incidents
- [kernel-doctor](../docs/runbook/kernel-doctor.md): Go tool that checks the running or reported Linux kernel version against a reviewed CVE fix floor (not a verdict)
- [mise-versions](./mise-versions/README.md): Go tool that writes `config/mise/image-tools.toml` versions into both `install.sh` files and checks for drift
- [run-hidden](../docs/runbook/windows-host.md): Windowless launcher started by Windows scheduled tasks; starts a console program without a window and returns its exit code (Go tool, ADR 0081)
- [rttm](./rttm/README.md): Python tool that converts RTTM files to ELAN (EAF) format and visualizes them
- [simple-server](./simple-server/README.md): Simple Go server for verifying localhost HTTPS
- [tmux](./tmux/CHEATSHEET.md): tmux keybinding quick reference

Usage is documented in each directory's README or source code.
See [`../README.md`](../README.md) for the overall repository layout.
