# ADR 0078 — フロントエンドの CI を 2 分未満に保つ規則を、全エージェント共通の指示に足す

- **id**: ADR-0078
- **title**: フロントエンドの CI を 2 分未満に保つ規則を、全エージェント共通の指示に足す
- **status**: Accepted
- **date**: 2026-11-16
- **decided-date**: 2026-11-16
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session）
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)、[0051](0051-adopt-decision-queue-for-new-records.md)、[0052](0052-renew-global-agent-instructions.md)、[0069](0069-type-check-and-lint-for-every-os.md)、[0076](0076-browser-ui-platform-first-then-ui-sdk.md)
- **consultation-trace**: 2026-11-16 の本セッションでの所有者の指示（下の「相談の記録」）。[公開 PR #629 の所有者の裁定](https://github.com/hironow/dotfiles/pull/629#issuecomment-6914709771)

## やさしい説明

ブラウザで動くコードの自動検査（CI）を、2 分より短く終わらせるための決まりを、agent への指示に足す。
型の検査と lint（書き方の検査）を速い道具に替え、テストを時間が均等になるように分けて同時に走らせる。
速くするために検査を減らすことはしない。

## Context

- 2026-11-16 18:52 JST に、所有者が次の 5 点を全エージェント共通の指示に足すよう指示した。似た既存の指示があれば、これで上書きする。
    - `tsc` を `bun check` に替える。
    - oxlint を使い、入れられる規則をすべて入れる。
    - テストの shard（分割）を、記録した実行時間で埋める。
    - PR では、diff が届くテストだけを走らせる。
    - lint、型検査、build、テストをすべて並列に走らせる。
- 全エージェント共通の指示（`ROOT_AGENTS.md`、`ROOT_CLAUDE.md`、spoke）に、`tsc`、oxlint、shard、`--changed`、CI の job の並列に触れる文は無かった（`rg` で確認）。上書きする既存の指示は無い。近いのは testing の spoke の「TypeScript tests」（`bun:test` で書く）と web-ui の spoke（何で作るか）で、CI の回し方は書いていない。
- hub（常に読まれる指示）の箇条書きは 32 個で、上限は 40 個（`just instruction-budget`）。表の行は数えない。
- この機体の bun 1.4.4 は `bun check` を持つ。`tsconfig.json` を読み、TypeScript 7 の `tsc` と同じ誤りを報告し、ファイルを書かない（[bun の文書](https://bun.com/docs/runtime/check)）。
- 2026-11-16 に実測した。`package.json` に `check` という script があると、`bun check` は型検査ではなくその script を走らせる。型の誤りがあるファイルで `"check": "echo formatter-only"` を置くと exit 0 で終わり、`bun check --no-script` は誤りを報告した。
- 2026-11-16 に実測した。`bun test --changed=<ref>` は、変えた module を `import` するテストだけを走らせる。`node:fs` で読む fixture を変えても、`package.json` を変えても、そのテストは走らなかった。変更が無ければ 0 件を走らせて exit 0、ref が無ければ失敗した。
- `bun test` は `--shard=i/n`、`--timings`、`--update-timings` を持つ。記録した時間は shard の境界を決めるので、1 回の run の shard はすべて同じ記録を読む必要がある（[bun の文書](https://bun.com/docs/test#large-codebases)）。
- oxlint の category は 7 つ（`correctness`、`suspicious`、`pedantic`、`perf`、`style`、`restriction`、`nursery`）で、既定は `correctness` だけ。型を使う規則には `oxlint-tsgolint` の package が要る（[oxlint の文書](https://oxc.rs/docs/guide/usage/linter/config.html)）。
- GitHub Actions では、`needs` だけの job は、待っている job が失敗すると skip される。skip された必須の check は、merge を止めない。

## Decision

A 案の次の 8 項を、必須事項（MUST）として採択する。

- D1: フロントエンド（TypeScript と、ブラウザのページで動くコード）の CI は、PR の結果が 2 分未満で出ることを目標にしなければならない。変更の前後で実行時間を測り、PR に書く。
- D2: 型検査は `tsc --noEmit` ではなく `bun check --no-script` で行わなければならない。`tsc` は、使われる出力（`.d.ts`、JavaScript など）を書く所にだけ残す。
- D3: lint は oxlint で行い、7 つの category をすべて error にし、型を使う規則も入れなければならない。守れない規則は、理由を書いて 1 つずつ名指しで外す。category ごと外したり `warn` に下げたりしてはならない。
- D4: テストの shard は、記録した実行時間で分けなければならない。1 回の run の shard はすべて同じ記録を読み、各 shard は自分の新しいファイルに書き、記録は全 shard が通ったあとで次の run のために保存する。
- D5: PR では、変えたファイルがすべて静的な `import` で届く module のときだけ、diff が届くテストに絞ってよい。それ以外（fixture、設定、lockfile、workflow など）に触れた PR と、default branch への push は、テストをすべて走らせなければならない。
- D6: lint、型検査、build、テストの各 shard は、互いを待たない別々の job にしなければならない。最後に、その workflow の必須の job すべての結果が `success` のときだけ通る job を 1 つ置き、その workflow の必須の check にする。別の workflow や外部のサービスが出す必須の check は、そのまま必須に残す。
- D7: 速くするために必須の検査を減らしてはならない。D4 と D5 は `bun:test` の suite にだけ当て、e2e と別の runner の suite はそのまま走らせる。
- D8: これらは spoke（`ROOT_AGENTS_docs_agents_frontend-ci.md`）に書き、hub には表の 1 行だけを足す。テスト（`tests/unit/test_frontend_ci_guidance.py`）が規則の文を保つ。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) 5 点を、検査が抜ける所の歯止めと一緒に spoke に書く（本案） | 所有者の 5 点がそのまま入る。`check` script、import の届かない fixture、skip された必須 check で、検査をせずに通る道をふさぐ | spoke が 1 つ増える。歯止めの分、文が長い | 所有者が採択 |
| B) 5 点を、そのまま hub に 5 行で足す | 短い。常に読まれる | hub の箇条書きが 37 個になり、上限 40 に近づく。フロントエンドを触らない作業でも読まれる。歯止めが無いので、実測した 2 つの抜け（D2、D5）がそのまま起きる | 却下: 検査をせずに通る道が残る |
| C) lint を oxlint ではなく `bun lint` にする | 入れる package が無い。oxlint の設定も読める | 所有者は oxlint を名指しした | 却下: 所有者の指示と違う |
| D) 指示を足さず、repo ごとに決める | 変更が無い | repo ごとに同じ調査と同じ抜けを繰り返す | 却下: 所有者の指示に反する |

## Consequences

- **Positive**: フロントエンドの CI の作り方が全 agent でそろう。速くする 5 つの手それぞれに、検査が抜けないための条件が付く。
- **Negative**:
    - `bun check` は TypeScript 7 として振る舞うので、TypeScript 5 や 6 の repo では新しい誤りが出て、直す作業が要る。
    - oxlint の 7 つの category をすべて error にすると、既存の repo では最初に多くの指摘が出る。`nursery` の規則は版ごとに変わりうる。
    - D5 の「すべて走らせる」条件は安全側なので、設定や fixture に触れる PR は速くならない。
    - 記録の保存と、最後の job の分だけ、workflow が複雑になる。
- **Neutral**: 既存の repo は、この ADR では移行しない。hook は `tsc` を止めない（`.d.ts` を書く用途が残る）。dotfiles 自身の JS の gate（`site/` の `vp`）は変えない。`templates/agent-baseline/` に TypeScript の CI の雛形は足さない。

## 反転記録 (Reversal)

none

## 他の DR との照合

0001〜0077 の 76 件（0046 は欠番）の題名と状態を走査し、`oxlint`、`tsc`、`bun check`、`shard`、`eslint`、TypeScript、フロントエンド、型検査で全文を検索した。当たった 0052、0069、0076 と、bun と依存に関わる 0027 の決定を読んだ。PDR はない。

- **矛盾**: 見つからなかった。0052 は既存の TypeScript の道具を残すと書く。本案は CI の回し方を足すだけで、言語の選び方は変えない。
- **重複**: 番号 0078 は未使用。同じ決定の記録はない。
- **誤読**: 0069（型検査と lint を OS ごとに回す）は Python と Go だけを決めている。TypeScript を OS ごとに回すことは、本案でも決めない。
- **偽の関連**: 0076 はブラウザの UI を何で作るかの決定で、CI は決めていない。関係は、対象のコードが同じというだけである。
- **関係誤認**: 0027（Node は bun だけ）と同じ向きで、置換の関係ではない。

## 相談の記録

- 2026-11-16 18:52 JST、本セッションで所有者（@hironow）が 5 点を指示した（上の Context）。
- 計画は Codex が独立にレビューした。1 回目は REVISE で、6 件（P1 5 件、P2 1 件）をすべて実物で確かめて取り込んだ: 最後の job が skip されて通る、import の届かないファイルで 0 件のまま通る、`check` script が型検査を隠す、shard が違う記録を読む、`tsc -b` の出力が消える、`bun:test` 以外の suite が落ちる。2 回目も REVISE で、3 件（P1 1 件、P2 2 件）を取り込んだ: 最後の job だけを必須にすると別の workflow の check が外れる、`--update-timings` は最初の `--timings` に書く、絞ってよい条件をテストが保っていない。
- 歯止め（D2 の `--no-script`、D5 の条件、D6 の最後の job、D7）は、所有者の 5 点には無く、Claude がレビューと実測から足した。Claude は PR #629 と本セッションで、この歯止めを表にして所有者に示した。
- 2026-11-16 20:04 JST、所有者はその表を見たうえで「OK, dotfilesリポもこの変更に準拠しましょうか」と答えた。Claude はこれを採択とは扱わず、採択かどうかを尋ねた。
- 2026-11-16 22:29 JST、所有者は「0078 okで」と答えた。これを A 案の採択とし、PR に記録した（[裁定](https://github.com/hironow/dotfiles/pull/629#issuecomment-6914709771)）。dotfiles 自身の準拠は別の PR（ADR-0079）で行う。

## 決定（2026-11-16）

- [x] A 案で Accepted（D1〜D8 のとおり）
- [ ] 修正のうえ Accepted（修正点: ____）
- [ ] Rejected / Deferred（理由: ____）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-16（所有者の裁定により代理記入）

- Accepted のとき: Decision を確定し、索引、変更ログ、queue の決定済みログを同じ PR で更新して merge する。merge のあと main の checkout で `just sync-agents all` を実行する。
- 修正のとき: 指摘の点を spoke、テスト、Decision に反映し、同じ PR で確定する。
- Rejected / Deferred のとき: PR を閉じ、queue に理由を残す。
