# ADR 0075 — `just agent-bump` は、未 commit の宣言があっても止まらない

- **id**: ADR-0075
- **title**: `just agent-bump` は、未 commit の宣言があっても止まらない
- **status**: Accepted
- **date**: 2026-11-12
- **decided-date**: 2026-11-12
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: [ADR-0074](0074-bump-declared-agent-plugins-without-the-wait.md) の一部（D4 の 1 つ目「版が書かれたファイルに未 commit の変更が無い」と、D5 の「書き換えたファイルを元に戻す」を、bump の途中で編集されたファイルについてだけ）
- **superseded-by**: none
- **related**: [0043](0043-self-authored-skills-through-the-skills-cli.md)、[0058](0058-pi-web-search-ollama.md)
- **consultation-trace**: 2026-11-12 の本セッションでの所有者の選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

`just agent-bump` は、版を書いたファイルに commit していない変更があると、止まっていた。
そのため、同じファイルの 2 つを続けて動かすには、間に commit が要った。
これからは止まらずに続けて動かせるので、最後に 1 回 commit すればよい。
手で書いた変更は、bump が失敗しても消えない。

## Context

- 2026-11-12、ADR-0074 の merge のあとに main の checkout から試した。`just agent-bump openai-codex v1.0.5` は通った。直後の `just agent-bump openai-codex v1.0.6` は「commit or revert these first: dump/harness/claude-plugins.json」で止まった。原因は ADR-0074 の D4 の 1 つ目（版が書かれたファイルに未 commit の変更が無いこと、MUST）。
- shell のテストはこの失敗を見逃していた。テスト用の偽物（fake）の checkout は、書いたファイルを「変更あり」にせず、無いファイルへの書き込みも通していたため。本物は git の状態を読み、無いファイルには書かない。
- この検査は、計画のレビューの「戻す処理で人の編集を消さないため」という指摘から足した。実装は、失敗したときに git の HEAD ではなく、bump が始めに読んだ中身を書き戻す。なので、未 commit の手の変更は、検査が無くても戻す処理で消えない。
- 独立レビューが、検査を外したときの残りの危険を 2 つ見つけた。
    - Pi の installer は pi-packages.json の source を全部入れる。一方、Pi の基準の検査は対象の 1 件しか見ていなかった。そのため、まだ入れていない手の書きかけも一緒に入る。
    - bump の途中（installer は数分かかる）にエディタで保存した編集は、戻す処理が上書きする。
- 所有者は 2026-11-12 に、検査を外すことを選んだ。

## Decision

所有者の選択を、次の必須事項（MUST）として採択する。

- D1: `just agent-bump` は、版が書かれたファイルに未 commit の変更があっても止まってはならない（MUST NOT）。ADR-0074 の D4 の 1 つ目を、この項で置き換える。D4 の残り（基準の検査、上流の確認）は変えない。
- D2: Pi の package と EGM の bump の基準の検査は、pi-packages.json の npm の source をすべて見なければならない（MUST）。Pi の settings にあり、ファイルがあり、pin どおりの版であること。足りなければ、何も書かずに止め、入れていない宣言の変更かもしれないと伝える。EGM の git の source は、今までどおり `--verify-egm` で見る。
- D3: 戻す処理は、bump が書いたファイルだけを対象にしなければならない（MUST）。そのファイルが今も bump の書いた中身と完全に一致するときだけ、始めに読んだ中身を書き戻す。一致しないファイル（bump の途中で編集されたもの）は書き戻さない。1 つでもそうなら、前の版を入れ直さずに、残したファイルの名前を報告して 0 以外で終わる。ADR-0074 の D5 は、この場合に限って置き換える。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) 検査を外し、戻す処理と基準の検査を強める（本案） | 同じファイルの 2 つを続けて動かし、1 回で commit できる。手の変更は消えない | 宣言の全体を見る分、Pi と EGM の bump の前の検査が増える | 所有者が採択 |
| B) 今のまま、1 つずつ commit する | 変更が無い | 下げてすぐ戻すにも、間に commit が要る | 所有者が検査を外すことを選んだため却下 |
| C) 検査を外し、未 commit のファイルを一覧で知らせるだけにする | 書きかけに気づける | D2 で入れていない宣言の書きかけは止まるので、通知の仕組みが余る（YAGNI） | 採らない |

## Consequences

- **Positive**: 同じ宣言のファイルの項目を、続けて上げ下げしてから 1 回で commit できる。fake の checkout を本物に合わせる契約テストが、同じ種類の見逃しを止める。
- **Negative**:
    - bump の途中で宣言を編集すると、bump が失敗したときに前の版を入れ直さない。この機体と宣言がずれたまま残るので、報告を見て宣言を確かめ、installer を手で回す。
    - store の skill の宣言を書くときは、`version` と `skills` 以外の最上位の key が消える（`scripts/skills_lock.py` の `_write_dump`）。対象の skill の記録そのもの（source など）を手で変えていれば、その値で update される。
    - installer のコード（`scripts/*.py`）に書きかけがあれば、bump はそのまま動かす（`just deploy` と同じ）。
- **Neutral**: Claude の marketplace の基準の検査（`claude-plugins-install --check`）は、もともと宣言の全体を見ている。store の skill の bump は、対象の記録しか入れない。

## 反転記録 (Reversal)

- 反転はない。ADR-0074 の D4 の 1 つ目と、D5 の一部を部分置換する（ADR-0074 の本文は変えず、Status 行と superseded-by に置換先を書く）。

## 他の DR との照合

0001〜0074 の 73 件（0046 は欠番）の題名・状態・置換関係を走査し、`just agent-bump`・未 commit・Pi の package・skill の宣言に触れる記録の全文を読んだ（0043、0058、0073、0074）。PDR はない。

- **矛盾**: 0074 の D4 の 1 つ目と D5 と食い違う。所有者（0074 の決定者）が本セッションで、検査を外すことを選んだ。
- **重複**: 番号 0075 は未使用。同じ決定の記録はない。
- **誤読**: 0074 の D5 の「store の skill は新しい hash を残す」は、もとから戻さない扱いで、この ADR と衝突しない。
- **偽の関連**: 0058 の Pi の npm の待機（`min-release-age=0`）は版の待機の話で、D2 の「入っているか」の検査とは別。0043 の宣言と store の仕組みは変えない。
- **関係誤認**: 0074 の D1〜D3、D4 の 2 つ目と 3 つ目、D6 は変えない。

## 相談の記録

- 2026-11-12、本セッションで所有者（@hironow、0074 の決定者）が、実地で止まった件の説明を聞き、「この検査を外す」を選んだ。説明は「失敗して戻すときは実行前の中身を書き戻すので、手の変更は消えない。D4 を部分置換する ADR を書く」。
- 計画は独立サブエージェントが 2 回レビューした（Codex はクレジット切れ）。宣言の全体を見る Pi の基準の検査、途中の編集を上書きしない戻し方と D5 との関係、書いたファイルだけを戻すこと、fake と本物の契約テスト、Tidy First の commit の分け方を、その指摘から採った。

## 決定（2026-11-12）

- [x] A を Accepted（D1〜D3 を MUST 文で確定し、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（今のまま）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-12（所有者の選択により代理記入）

- B 案は所有者が検査を外すことを選んだため却下し、C 案は D2 で書きかけが止まり通知が余るため採らない。
- 採択時に索引、変更ログ、queue の決定済みログを同時に更新し、ADR-0074 は Status 行と superseded-by だけを変えた。
