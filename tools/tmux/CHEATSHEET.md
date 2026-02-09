# tmux Cheatsheet

This cheatsheet is based on the custom `tmux.conf` in this repository.
The **Prefix key** is `Ctrl-q` (not the default `Ctrl-b`).

All tmux shortcuts follow the pattern: **press Prefix first, release, then press the next key**.

## Getting Started

```
tmux                     # Start a new session
tmux new -s work         # Start a named session
tmux a                   # Reattach to last session
tmux a -t work           # Reattach to a named session
tmux ls                  # List all sessions
tmux kill-session -t work  # Kill a named session
```

## Session (Detach / Switch)

| Action              | Keys            |
| ------------------- | --------------- |
| Detach from session | `Prefix` + `d`  |
| List sessions       | `Prefix` + `s`  |
| Rename session      | `Prefix` + `$`  |

> Detach (`Prefix d`) leaves everything running in the background.
> Come back anytime with `tmux a`.

## Windows (like browser tabs)

| Action          | Keys            |
| --------------- | --------------- |
| New window      | `Prefix` + `c`  |
| Previous window | `Prefix` + `[`  |
| Next window     | `Prefix` + `]`  |
| Go to window N  | `Prefix` + `1`..`9` |
| Rename window   | `Prefix` + `,`  |
| Close window    | `exit` or `Ctrl-d` in the last pane |

## Panes (split screen)

| Action               | Keys                    |
| -------------------- | ----------------------- |
| Split left/right     | `Prefix` + `\|`        |
| Split top/bottom     | `Prefix` + `-`          |
| Move to pane         | `Prefix` + Arrow keys   |
| Move to pane (mouse) | Click on the pane        |
| Resize pane (mouse)  | Drag the border          |
| Close pane           | `exit` or `Ctrl-d`      |
| Toggle zoom (fullscreen) | `Prefix` + `z`      |

## Scrolling

| Action           | How                                      |
| ---------------- | ---------------------------------------- |
| Scroll up/down   | Mouse wheel                              |
| Exit scroll mode | `q` or `Esc`                             |

## Session Save / Restore (tmux-resurrect)

| Action          | Keys                     |
| --------------- | ------------------------ |
| Save session    | `Prefix` + `Ctrl-s`     |
| Restore session | `Prefix` + `Ctrl-r`     |

> Save before shutting down your PC. After reboot, start `tmux` and hit Restore to get everything back.

## Utility

| Action        | Keys            |
| ------------- | --------------- |
| Reload config | `Prefix` + `r`  |
| Command mode  | `Prefix` + `:`  |

## Quick Reference

```
Prefix = Ctrl-q

Prefix d        detach
Prefix c        new window
Prefix [ / ]    prev / next window
Prefix |        split left-right
Prefix -        split top-bottom
Prefix Arrow    move between panes
Prefix z        zoom pane
Prefix Ctrl-s   save session (resurrect)
Prefix Ctrl-r   restore session (resurrect)
Prefix r        reload config
```
