# ADR 0074 — 宣言済みの agent の plugin の版は、待機を待たずに 1 つのコマンドで上げ下げする

- **id**: ADR-0074
- **title**: 宣言済みの agent の plugin の版は、待機を待たずに 1 つのコマンドで上げ下げする
- **status**: Accepted
- **date**: 2026-11-12
- **decided-date**: 2026-11-12
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: [ADR-0056](0056-common-claude-plugin-set.md) の一部（Decision 4 の 7 日の待機を、宣言済みの marketplace の tag を動かすときだけ外す。新しく足す marketplace には残る）、[ADR-0073](0073-mwg-v1-before-the-plugin-cooldown.md) の一部（D2 の「7 日未満の tag には名指しの DR が要る」を、宣言済みの marketplace について外す）
- **superseded-by**: none
- **related**: [0043](0043-self-authored-skills-through-the-skills-cli.md)、[0048](0048-required-claude-plugins.md)、[0057](0057-shared-plugins-need-no-per-home-settings.md)、[0058](0058-pi-web-search-ollama.md)
- **consultation-trace**: 2026-11-12 の本セッションでの所有者の依頼と選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

agent の plugin や skill の版を、`just agent-bump <名前> [版]` の 1 つのコマンドで上げ下げできるようにする。
すでに入れているものなら、出たばかりの版にもすぐ上げられる（7 日待たない）。
新しく入れるものは、今までどおりの決まりに従う。

## Context

- 所有者は 2026-11-12 に「このリポジトリで管理している agent 系の skill の update をするコマンドを作りたい。複数入れていて、版を上げ下げするたびに頼むより、コマンドだけで上げられるのが理想。特に、すでに入っている skill は 7 日の待機の例外として扱いたい」と依頼した。
- 版が書かれている場所:
    - Claude の plugin の marketplace は、`dump/harness/claude-plugins.json` で tag に固定する（ADR-0048、0056）。ADR-0056 の Decision 4 は「tag は公開から 7 日以上（MUST）」、ADR-0073 の D2 は「7 日未満の tag には marketplace と tag を名指しした DR が要る」とした。
    - EGM の版は 5 か所にあった。claude-plugins.json、pi-packages.json、`scripts/install_pi_extensions.py` の `EGM_SOURCE` と `EGM_COMMIT`、justfile の `egm-install` の Codex の `--ref`。Codex と Antigravity には `egm-install` だけが入れていた（`just deploy` は入れない）。
    - 2026-11-12 に所有者が「EGM だけの特別コマンドはなくしてもいい。ただし EGM 自体を agent に入れるのは必要」とし、Codex と Antigravity も `just deploy` で入れることを選んだ。
    - Pi の package は npm の名前を版なしで並べ、Pi の npm は `min-release-age=0` で待機なし（ADR-0058）。
    - store の skill は宣言に版を持たず、`just skills-update` が上流の最新を取る（ADR-0043、待機の規則なし）。skills CLI 1.5.22 は ref や版を指定できない。
- 2026-11-12 に確かめた上流の状態: EGM の最新 v0.1.1（2026-11-06）は skill の dir 名を `egm_review` から `egm-review` に変えた（7 つすべて）。今の `verify_egm` は v0.1.0 の名前を固定で持つので、v0.1.1 へは版の文字列を変えるだけでは上がらない。
- 所有者の選択（2026-11-12）: 対象は Claude の plugin の tag、EGM の全箇所、store の skill、Pi の package。待機の例外は宣言済みのものの版上げ・版下げだけで、新しく足すものは今までどおり。コマンドは宣言を書き換えてこの機体に入れて確かめるまでで、commit と PR は人が行う。

## Decision

所有者の選択を、次の必須事項（MUST）として採択する。

- D1: 宣言済みの Claude の marketplace の tag（EGM を含む。tag を持たない claude-plugins-official と repo 相対の hironow-plugins は対象外）、Pi の package、store の skill の版を変えるときは、`just agent-bump <name> [version]` を使わなければならない（MUST）。引数なしの `just agent-bump` は、宣言済みの全部の今の版と最新の版を出すだけで、何も変えない。全部を一度に上げる入口は作らない。
- D2: 宣言済みの marketplace の tag は、7 日の待機を待たずに、どの release の tag にも上げ下げしてよい。ADR-0056 の Decision 4 は、新しく宣言に足す marketplace にだけ効く。ADR-0073 の D2 の名指しの DR は、宣言済みの marketplace には要らない。
- D3: `just agent-bump` は宣言に無い名前を拒まなければならない（MUST）。新しく足すものは今までどおり手で足す。Pi の npm と store の skill の待機の扱いは変えない（どちらも今までどおり待機なし）。
- D4: `just agent-bump` は、書き換える前に次を確かめ、どれかが満たされなければ何も変えずに止まらなければならない（MUST）。
    - 版が書かれたファイルに未 commit の変更が無い。
    - その種類の検査が今の状態で通る（基準）。
    - 目標の版が上流にある。Claude の plugin は、その tag の marketplace.json の version が tag と一致する。EGM は、installer が必須とするファイルがその tag の tree にすべてある。
- D5: 入れる手順か確かめる手順が失敗したら、書き換えたファイルを元に戻し、戻した宣言で同じ installer をもう一度回し、その結果を報告して 0 以外で終わらなければならない（MUST）。store の skill は CLI で前の版に戻せないので、新しい hash を宣言に残し、そう報告する。
- D6: 入れるのはコマンドを実行した機体だけとする。commit、PR、ほかの機体への導入は人が行う。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) 宣言済みのものは待たず、1 つのコマンドで上げ下げする（本案） | 版を変えるたびに頼まずに済む。宣言と各 home が同じ手順でそろう | 出たばかりの版が先に入る。コマンドと installer の保守が要る | 所有者が採択 |
| B) 今のまま（tag ごとに手で書き換え、7 日未満は名指しの DR） | 変更が無い | 版を変えるたびに依頼と ADR が要る | 所有者の依頼に合わないため却下 |
| C) 新しく足すものも含め、すべて待たない | 例外の線引きが要らない | 新しい依存を待機なしで入れることになる | 所有者が「新しく足すものは今までどおり」を選んだため却下 |

## Consequences

- **Positive**: 宣言済みの plugin・EGM・Pi package・skill の版を、1 つのコマンドで上げ下げできる。EGM の pin は 4 か所（claude-plugins.json、pi-packages.json、`EGM_SOURCE`、`EGM_COMMIT`）になり、コマンドがまとめて書き換え、テストが一致を確かめる。EGM 専用の導入コマンドは無くなり、4 つの agent すべてに `just deploy` が入れる（Codex と Antigravity は `scripts/codex_agy_plugins.py` が Pi の pin に合わせ、CLI の無い機体では飛ばす）。
- **Negative**:
    - 宣言済みの marketplace は、出たばかりの版が先に入る。上流が版を取り下げても、先に入っている。
    - EGM の形が変わる版（v0.1.1 など）は、installer を人が直すまで上げられない。コマンドは pre-flight でそう言って止まる。
    - store の skill は最新にしか動かせない（CLI に版の指定が無い）。
    - ほかの機体は、merge の後で各 installer を回すまで前の版のまま。
- **Neutral**: Pi の npm と store の skill は、もともと待機なしで、変わらない。

## 反転記録 (Reversal)

- 反転はない。ADR-0056 の Decision 4 と ADR-0073 の D2 を、宣言済みの marketplace についてだけ部分置換する（どちらも本文は変えず、Status 行に置換先を書く）。

## 他の DR との照合

0001〜0073 の 72 件（0046 は欠番）の題名・状態・置換関係を走査し、plugin・marketplace・skill・Pi の package・EGM・待機（cooldown、`min-release-age`）に触れる記録の全文を読んだ（0043、0048、0053、0056、0057、0058、0073）。PDR はない。

- **矛盾**: 0056 の Decision 4 と 0073 の D2 と食い違う。所有者（両方の決定者）が本セッションで、宣言済みのものの例外を選んだ。
- **重複**: 番号 0074 は未使用。同じ決定の記録はない。
- **誤読**: 0048 の Decision 1（リリースタグで pin）は、agent-bump も tag で書くので満たす。0057（home ごとの設定が要らない plugin）は対象を変えない。
- **偽の関連**: 0053 と 0058 の npm の待機は `~/.npmrc` と Pi の npm の話で、D3 で変えない。0043 の store と宣言の仕組みは、そのまま使う（skill の宣言は対象の 1 件の hash だけを書き換える）。
- **関係誤認**: 0073 の D1（googlechrome の v1.0.0）はそのまま有効。0056 の Decision 1〜3 と 5、0057 が置き換えた部分は変えない。

## 相談の記録

- 2026-11-12、本セッションで所有者（@hironow、0048・0056・0073 の決定者）が依頼し、対象（4 種すべて）、待機の例外（宣言済みの版上げ・版下げだけ）、範囲（この機体に入れるまで）を選んだ。
- 計画は独立サブエージェントが 2 回レビューした（Codex はクレジット切れ）。EGM の形の変化、版なしの Pi package の更新、戻すときに home も戻すこと、種類ごとの確かめ方、ADR を tag の pin に限ること、一括更新の入口を作らないこと、skill は戻せないこと、基準の検査を、その指摘から採った。
- 2026-11-12、所有者が「EGM だけの特別コマンドはなくしてもいい。ただし EGM 自体を agent に入れるのは必要」とし、Codex と Antigravity も `just deploy` に含めることを選んだ。その計画も独立サブエージェントがレビューし、Codex を Pi の失敗から切り離す別の deploy の手順、justfile の pin の削除、Codex の導入済みの判定、Codex の無い機体での確認の扱いを、その指摘から採った。
- 実地: worktree から試した bump は、基準の検査が赤（hironow-plugins の登録先が worktree と違う）で何も書かずに止まった。これを受けて、worktree からの bump は最初に断るようにした。

## 決定（2026-11-12）

- [x] A を Accepted（D1〜D6 を MUST 文で確定し、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（今のままにする）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-12（所有者の選択により代理記入）

- B 案は版を変えるたびに依頼と ADR が要り所有者の依頼に合わないため、C 案は所有者が「新しく足すものは今までどおり」を選んだため却下する。
- 採択時に索引、変更ログ、queue の決定済みログを同時に更新し、ADR-0056 と ADR-0073 は Status 行だけを変えた。
