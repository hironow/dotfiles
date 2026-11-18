# j-cc で再開したセッションには worker のフックを付けない

日付：2026-11-18（JST）

所有者の承認（2026-11-18 19:04）：「resume のときは hook も付けない」形で直す。

## 事実

- `j-cc` は、新しいセッションにも再開したセッション（`-c`、`-r`）にも、同じ 2 つを付ける（`scripts/jev_launch.py:279`、`scripts/jev_core.py:217-230`）。
    - `--agents`：`worker-medium` と `worker-high` の定義。
    - `--settings`：`PreToolUse` のフック（`scripts/jev_claude_hook.py`）。既定の worker の起動（`subagent_type` が `general-purpose`、`worker`、未指定）を `worker-<effort>` に書き換え、`codex:codex-rescue` の prompt に `--model` と `--effort` を足す。
- 2026-11-18、この機で `j-cc -r` で再開したセッションで、subagent の起動がすべて `Agent type 'worker-high' not found` で失敗した。
    - Claude Code の process の command line には、`--agents` も `--settings` も `--resume` もあった（Win32_Process の確認）。
    - 再開の後、session に「`worker-high` と `worker-medium` はもう使えない」と通知が出た。
    - つまり、再開したセッションでは `--settings` のフックは効き、`--agents` の定義は効かない。フックが、存在しない型に書き換える。
- `--agents` が再開で効かないのが、Claude Code の仕様か不具合かは確かめていない。
- `docs/runbook/jev-launchers.md:77` は「再開したセッションにも、新しいセッションと同じ worker の設定を付ける」と書いている。

## 変更

1. **Red**：`tests/unit/test_jev_launch.py` の `test_a_resumed_j_cc_session_keeps_the_jev_wiring` を、次を確かめる形に変える。
   - 再開した `j-cc` のセッションにも、model、effort、`--append-system-prompt`、`--resume <id> <prompt>` は付く。
   - `--settings` と `--agents` は付かない。
   - `-c` でも同じ。
   - 新しいセッションには今までどおり両方が付く（既存の `test_claude_gets_the_worker_hook_and_agents_but_pi_does_not`）。
2. **Green**：`scripts/jev_launch.py` の `main` で、`host == "claude"` かつ `launch.resume` が空のときだけ `claude_session_args` を付ける。
3. **文書**：`docs/runbook/jev-launchers.md` の 77 行目と「Claude Code」の節を直す。
   - 再開したセッションでは、worker の effort の振り分けと `codex:codex-rescue` の model と effort の振り分けが効かない。
   - subagent は Claude Code の既定の定義で起動する。
   - 理由は、Claude Code が再開したセッションで `--agents` の定義を読まず、フックだけが残ると起動が失敗するから。
4. 確かめ：`just ci`。PR の CI。

## 失敗したとき

PR を revert する。再開したセッションの subagent がまた失敗するようになるだけで、ほかへの影響は無い。

## レビューの記録

Codex 1 回目（2026-11-18）：APPROVE。`launch.resume` の分岐で `-c` と `-r` の両方を扱えること、テストの範囲に直す点が無いことを、実装と既存のテストに照らして確かめた。

## 範囲の外

- Claude Code が再開で `--agents` を読まない理由を調べること。
- 再開したセッションで effort の振り分けを取り戻すこと（例：定義を `~/.claude/agents/` に置く）。所有者は、まず安全な形を選んだ。
