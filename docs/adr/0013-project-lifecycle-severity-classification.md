# 0013. Project lifecycle severity classification (= cdr-project / runops project)

**Date:** 2026-05-09
**Status:** Proposed

## Context

[refs/docs/issues/0020-multi-project-lifecycle-completion](../../../tap/refs/docs/issues/0020-multi-project-lifecycle-completion.md) (= 0013 親 issue の fix-up tracker) の 軸 4 で「AI agent からの project 作成 / 削除 (= `cdr project up/down`、 `runops project create/archive/delete`) を 4-eyes approval (= ADR 0019 + 0035 + 0036 + 0037) の対象 (HIGH severity) として扱うか、 no-approval path (LOW severity) として扱うか」 を policy として pin する必要がある。

本 ADR が決定する範囲:

- gateway 側 `cmd/runops project create/archive/delete` (= 軸 1、 既に着地 `acb0fda`)
- dotfiles 側 `cdr-project up/down/list/show` (= 軸 2/3、 PR #98 `87616fc` で着地)
- workspace VM 側 `project-up.sh` / `project-down.sh` (= 軸 2 と同 PR)

severity 判定が pin されないと:

- HIGH の場合: Slack `/runops project up <id>` 経由 dispatch で 4-eyes approval flow が必要、 0011 architectural pin (= AI が AI を approve できない) が自動適用
- LOW の場合: cdr CLI 直叩きのみ許可、 Slack path 不実装、 approval flow 走らない

両者で実装範囲 / セキュリティモデルが大きく異なる。

## Decision

**3 段階 severity 分類** を pin する。 ただし **approval orchestration の自動適用は本 ADR scope 外** であり、 各 severity に対応する approval flow 実装は別 ADR / 別 PR で順次着地。

| Severity | 対象 operation | approval guard |
|---|---|---|
| **HIGH-CRITICAL** | `runops project delete --hard` / `cdr project down --hard` | 4-eyes approval **+ 追加 guard 3 種** (= explicit `--hard` flag、 typed project_id confirmation、 dry-run preview) |
| **HIGH** | `runops project create / archive` / `cdr project up / down` (default = soft) | 4-eyes approval (= 別 actor が approve、 0011 architectural pin で AI が AI を approve できない自動適用) |
| **LOW** | `runops project list / show` / `cdr project list / show` (= read-only) | no approval (= 直 invoke 可) |

**重要 (= codex 2026-05-09 review 反映)**: gateway 側現状の 4-eyes flow は `severity=high` convergence D-Mail を `dispatch_result_handler` が approval request にルーティングする経路で、 `runops project` CLI / admin registry mutation はその D-Mail approval path に **乗っていない**。 本 ADR は severity classification を pin するが、 「`runops project` 専用 approval orchestration」 は別 ADR (= gateway 側) で新設する必要がある。 本 ADR Accepted 時点では HIGH severity の implementation gate は **不在** であり、 「pin したが gate なし」 を明示状態として運用する。

理由:

1. **read-only と mutation の境界 (= LOW vs HIGH)**: `list/show` は副作用ゼロ + sensitive data 不在 (= internal infrastructure metadata のみ) で operator daily flow 頻発、 HIGH UX 劣化が回避優先。 mutation は tenant-level resource 変更で 0011 architectural pin と同 semantics。

2. **mutation と hard-delete の境界 (= HIGH vs HIGH-CRITICAL)**: hard-delete は不可逆 = 4-eyes だけでは事故防止が弱い (= approve clicker の誤操作で project が永久消失)。 explicit flag + typed confirmation + dry-run の 3 種 guard を追加 (= "are you sure" の 4 重)。 soft archive は復旧可能 (= `~/projects/.archive/<id>-<timestamp>/` から `mv` で戻る) なので HIGH 単独で十分。

3. **`runops project` 専用 approval orchestration の不在**: gateway 側 D-Mail-driven 4-eyes path は convergence severity ベースで、 admin registry mutation には現状適用されない。 本 ADR は severity を pin するが、 実装 gate は次のいずれかで充足:
   - (a) gateway 側で `cmd/runops project create/archive/delete` 実行前に severity-aware approval gate を新設 (= 別 ADR + 別 PR、 推奨 path)
   - (b) cdr-project wrapper で host 側 approval gate を新設 (= ad-hoc、 client side で gate なので bypass 可能性あり)

4. **AI agent path の 4-eyes 自動適用 *ではない* こと**: 本 ADR の HIGH 分類は「policy 上 HIGH」 であり、 「ADR Accepted ですぐ自動 reject される」 ではない。 AI agent が `cdr project up` を実行しても、 上記 (a) gateway 側 gate が integrate されるまでは reject されない (= 本 ADR が次の implementation milestone を定義)。

## Enforcement inventory

### Entry points

`project lifecycle` 操作を発生させ得る path 全列挙:

1. **operator local CLI**: `cdr project up/down/list/show` (= dotfiles host 側 wrapper、 cdr-exec 経由で workspace VM 上の `runops project` + `project-up.sh / project-down.sh` を invoke)
2. **AI agent dispatch**: cdr-job 経由の workspace VM 上の自動 cdr-project 呼出 (= dotfiles ADR 0012 Path B で `RUNOPS_ACTOR_TYPE=ai-agent` set、 gateway 側 4-eyes path で reject)
3. **Slack dispatch (= 将来の path)**: `/runops project up <id> --org=<org> --repo=<repo>` 経由 (= gateway ADR 0019 + 0035 の dispatch flow を再利用、 本 ADR は path を pin するが Slack 実装そのものは別 PR)
4. **direct gateway API call**: workspace VM 内 `runops project create` (= `cdr-exec runner -- 'runops project create'`、 ただし HIGH severity flag が gateway 側で適用)

### Persistent / carried data needed at each enforcement point

各 entry point で以下の actor / severity 情報が carried されること:

- `RUNOPS_ACTOR_TYPE` env (= dotfiles ADR 0012 で全 caller path から set 済): `human-operator` / `ai-agent` / `workspace-daemon` / `gateway-service` のいずれか
- gateway 側 `runops project create/archive/delete` の internal severity classification = `HIGH` / `HIGH-CRITICAL` (= 本 ADR で pin、 ただし implementation gate は別 ADR)
- gateway 側 `runops project list/show` の internal severity classification = `LOW`
- 4-eyes flow に integrate された後は ADR 0035 + 0036 carry data (= effective_requester_actor_type / initiating_actor_type) が approval request に乗る

### Bypass candidates (= "where can this go wrong?")

1. **HIGH severity classification は pin したが approval gate が未実装**: 本 ADR Accepted 時点では HIGH 分類されても reject されない (= **既知の gap**)。 mitigation: 本 ADR の References に "next ADR for runops project approval orchestration" を pin、 gateway repo の milestone tracker で gate 実装を追跡

2. **approval gate が composite operation 全体の前に置かれていない (= cdr-project の 2 step 設計)**: 現 cdr-project は up = (1) gateway create → (2) workspace script、 down = (1) workspace script → (2) gateway archive。 approval が gateway entry の前なら up は OK だが、 down は **workspace 側 cleanup が承認前に実行される**。 mitigation: approval gate 実装時 (= 上記 next ADR) に「全 side effect 開始前に approval ack を確認する」 contract を pin、 cdr-project 改修必須項目とする (= down 順序逆転 or pre-flight approval check 追加)

3. **AI agent laundering via cdr-exec actor override**: dotfiles ADR 0012 Path C で cdr-exec は **常に `RUNOPS_ACTOR_TYPE=human-operator` 上書き** = AI agent が cdr-project を invoke しても gateway 側で human-operator として伝播。 cdr-project が cdr-exec 経由なので、 AI agent → human-operator laundering が発生。 → mitigation: 本 ADR で **cdr-project は host 側 entry point として AI agent から直接呼び出すことを禁止** と pin。 AI agent 経由の lifecycle mutation を許可する場合は次のいずれか:
   - (a) cdr-job (= ADR 0012 Path B、 `RUNOPS_ACTOR_TYPE=ai-agent`) 経由で workspace VM 内 `runops project` 直接 invoke
   - (b) dedicated AI agent dispatch path (= Slack `/runops project up` etc.、 別 PR)
   - cdr-exec (= Path C、 always human-operator) 経由は **明示禁止**、 cdr-project に AI 用 flag は実装しない

4. **hard-delete short-circuit (= --hard 単独で誤実行)**: explicit `--hard` flag + typed project_id confirmation + dry-run preview の 3 種 guard を実装必須。 cdr-project の `--hard` は現在 flag のみ = unsafe、 typed confirmation prompt と dry-run option を追加実装する (= 本 ADR の followup PR、 cdr-project ver 2)

5. **gateway side で project create/archive/delete の severity を LOW に誤設定**: 本 ADR で HIGH/HIGH-CRITICAL pin、 gateway code review + 下記 test (TestProjectLifecycleSeverity_HIGH) で fail-loud

6. **read-only (`list/show`) で誤って HIGH に上げる将来 PR**: operator UX 劣化、 invariant 違反ではないが annoyance、 gateway code review で気付ける

### Tests proving coverage

各 enforcement point に対して 1 つ以上 test を追加:

1. **gateway side severity classification**: `cmd/runops/project_test.go` 内で `TestProjectLifecycleSeverity_HIGH` (`create / archive` が HIGH を返すこと)、 `TestProjectLifecycleSeverity_HIGH_CRITICAL` (`delete --hard` が HIGH-CRITICAL を返すこと)、 `TestProjectLifecycleSeverity_LOW` (`list / show` が LOW を返すこと)
2. **dotfiles cdr-project wrapper sequence**: `tests/exe/test_project_lifecycle.py` 内で `test_cdr_project_invokes_gateway_runops_project` (= up/down で `runops project create/archive/delete` が呼ばれる順序 assertion)、 `test_cdr_project_validates_id_canonical` (= regex / max-len)、 `test_cdr_project_hard_requires_explicit_flag` (= --hard 不在で hard delete が呼ばれないこと)
3. **AI agent forbidden path**: `test_cdr_project_rejects_when_invoked_via_cdr_exec_with_ai_agent_actor` (= AI agent override が host 側で起こる pattern を test 化、 本 ADR の bypass #3 mitigation)
4. **integration test (= refs 0020-multi 軸 5、 別 PR)**: 上記 next ADR の approval gate が integrate された後に、 AI agent identity で `cdr project up` を invoke すると gateway 4-eyes flow で reject されることを確認

## Consequences

### Positive

- AI agent 経由の project lifecycle が自動的に 0011 architectural pin の保護下に入る (= 別途 implementation 不要、 既存 4-eyes path が適用)
- read-only operation は LOW で operator UX を保つ
- soft archive / hard delete を同 severity で扱うため、 operator の severity 認識が単純化 (= 「lifecycle mutation = HIGH」 1 ルールで覚えられる)

### Negative

- Slack `/runops project up` 経由の dispatch を将来実装する場合は 4-eyes approval flow に乗せる必要 (= 実装 cost あり、 ただし既存 ADR 0019 path 再利用なので marginal)
- AI agent が project create/archive を頻繁に行いたい場合 (= e.g., autonomous research session で project per-task) 4-eyes が friction として作用。 ただしこの use case は本 ADR 起案時点では存在しない (= 検討時に別 ADR で hybrid policy を pin、 e.g., "research-prefixed project は LOW、 production-prefixed は HIGH")

### Neutral

- Slack 実装そのものは scope 外 (= 本 ADR は severity policy のみ pin、 Slack `/runops project` subcommand 実装は別 PR / 別 ADR)
- 軸 5 (= integration test) は本 ADR の test coverage と部分重複、 統合 implementation で 1 つの test suite にまとめ可

## Out of scope

- Slack dispatch path の実装 (= 別 PR)
- AI agent autonomous project creation の hybrid policy (= 必要になった時点で別 ADR)
- gateway side severity classification の実装 detail (= gateway repo の cmd/runops project code 内、 本 ADR はインターフェース pin のみ)

## References

- [refs/docs/issues/0020-multi-project-lifecycle-completion.md](../../../tap/refs/docs/issues/0020-multi-project-lifecycle-completion.md) — parent issue (軸 4 が本 ADR で決定)
- [refs/docs/archive/0013-multi-project-lifecycle-cli.md](../../../tap/refs/docs/archive/0013-multi-project-lifecycle-cli.md) — gateway 側 lifecycle CLI (= 軸 1)
- runops-gateway docs/adr/0019 — 4-eyes approval flow (HIGH severity が乗る path)
- runops-gateway docs/adr/0035-0037 — AI agent identity + 4-eyes architectural pin
- dotfiles ADR 0012 — RUNOPS_ACTOR_TYPE env injection (= 各 caller path から actor type set、 本 ADR の前提)
- dotfiles ADR 0011 — multi-project systemd env delivery (= project ディレクトリ規約、 本 ADR が触る lifecycle の対象)
