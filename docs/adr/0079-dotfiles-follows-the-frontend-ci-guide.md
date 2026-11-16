# ADR 0079 — dotfiles 自身の JS/TS の gate を、フロントエンドの CI の指示に合わせる

- **id**: ADR-0079
- **title**: dotfiles 自身の JS/TS の gate を、フロントエンドの CI の指示に合わせる
- **status**: Proposed
- **date**: 2026-11-16
- **decided-date**: —
- **decision-maker**: TBD（所有者）
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session）
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)、[0051](0051-adopt-decision-queue-for-new-records.md)、[0059](0059-retire-remote-pi.md)、[0076](0076-browser-ui-platform-first-then-ui-sdk.md)、[0078](0078-frontend-ci-under-two-minutes.md)
- **consultation-trace**: 2026-11-16 の本セッションでの所有者の指示（下の「相談の記録」）。決裁はこの ADR を載せた公開 PR で受ける

## やさしい説明

このリポジトリにも、少しだけ JavaScript と TypeScript のコードがある。
それを検査する道具を、[ADR-0078](0078-frontend-ci-under-two-minutes.md) で決めた指示どおりのもの（oxlint と `bun check`）に替え、検査を 4 つに分けて同時に走らせる。
そのために、検査の道具を入れるための `package.json` をリポジトリの直下に置く。

## Context

- 2026-11-16 20:04 JST に、所有者が「dotfilesリポもこの変更に準拠しましょうか」と指示した。「この変更」は、[ADR-0078](0078-frontend-ci-under-two-minutes.md)（同じ日に Accepted）と spoke `ROOT_AGENTS_docs_agents_frontend-ci.md` の 5 つの規則である。
- 自前の JS/TS は 3 ファイル: `site/copy.js`（Pages のサイト）、`config/pi/extensions/jev-sonnet-fallback.ts`（Pi の拡張）、`tests/unit/jev_sonnet_fallback.test.ts`（`bun:test`）。ほかに、編集してはならない第三者のファイルがある: `site/vendor/**`（145 ファイル。`tests/unit/test_site_vendor.py` がバイトを検査する）と `config/pi/extensions/rtk.ts`（rtk から取り込み、変更しない）。
- これまでの gate: `just lint` と `just check` が `vp -C site lint|check` を `site/` の JS にだけ掛けていた（vp 1.6.0 に同梱の oxlint、既定の規則）。Pi の拡張とテストは `just pi-jev-test` が `bun build` と `bun test` を掛けるだけで、lint は無かった。**型を検査するものは、どのファイルにも無かった。**
- CI では、`bun test` は `unit-test.yaml` の `unit` job の 1 step だった（PR #629 でその job は 6 分 50 秒）。`vp` を呼ぶのは、`just check` を回す dev container の job だけだった（同 17 分 24 秒）。
- `.gitignore` は repo 直下の `package.json` と `bun.lock` を「dotfiles では追跡しない」として無視していた（2026-03-21 から）。例外は `site/package.json` だけだった。
- 2026-11-16 の実測（oxlint 1.92.0、7 つの category をすべて error、型を使う規則あり）: 自前の 3 ファイルに、70 の規則で 685 件。`bun check --no-script`（strict）: 22 件（テストに 13 件、`copy.js` に 9 件）。
- `site/copy.js` は、型の無い ui-sdk の bundle を import する。`checkJs` を有効にすると、その bundle に 1,292 件の誤りが出る。`checkJs` を無効にして `copy.js` の先頭に `// @ts-check` を置くと、`copy.js` だけが検査される（実測）。
- Pi は拡張を、この checkout への symlink として置く（`scripts/install_pi_extensions.py`、Windows では copy）。拡張が Pi の package から値を import すると、動いている Pi ではなく、この repo の dev 依存に解決されうる（[ADR-0059](0059-retire-remote-pi.md)）。2 つの拡張はどちらも `import type` だけを使い、それは実行時に消える。
- repo の ruleset（`protect`）には、必須の status check が 1 つも無い（`gh api repos/hironow/dotfiles/rulesets` で確認）。ruleset は IaC で管理されていない。

## Decision

（Proposed。確定後に、次の案を MUST として記述する。）

提案する決定（A 案）:

- D1: repo 直下に `package.json`（private、dev 依存だけ）、`bun.lock`、`bunfig.toml`、`tsconfig.json`、`.oxlintrc.json` を置く。dev 依存は `oxlint`、`oxlint-tsgolint`、`@types/bun`、`@earendil-works/pi-coding-agent` の 4 つで、正確な版に固定する。`.gitignore` は直下の `package.json` と `bun.lock` だけを例外にする。
- D2: 依存は `bun install --frozen-lockfile --ignore-scripts` で入れる。新しい版は 7 日たってから採る（`bunfig.toml` の `minimumReleaseAge` と Dependabot の cooldown）。
- D3: lint は oxlint で行う。7 つの category をすべて error にし、型を使う規則を入れる。対象は自前の JS/TS すべてで、無視するのは `site/vendor/**` と `rtk.ts` だけとする。規則を外すときは 1 つずつ名指しし、その上の行に理由を書く。
- D4: 型検査は `bun check --no-script` で行う。対象は自前の 3 ファイルで、`copy.js` は `// @ts-check` で検査する。
- D5: Pi の拡張は、Pi の package を型としてだけ import する。build の出力にその package の名前が現れたら、`just js-build` は失敗する。
- D6: gate は root の recipe `js-lint`、`js-typecheck`、`js-build`、`js-test` の 4 つとする。`just lint` と `just check` はこれらを呼び、`vp` は整形（`fmt` と `fmt --check`）だけに使う。
- D7: CI は `frontend-ci.yaml` で 4 つを互いに待たない job として走らせ、最後の job「Frontend CI」は 4 つの結果がすべて `success` のときだけ通る。Ubuntu での `bun test` は `unit` job から外し、Windows での実行は残す。
- D8: テストは 1 つの shard で、常にすべて走らせる（`--changed` は使わない）。
- D9: 「Frontend CI」を必須の check に登録するのは所有者が行う。登録が済むまで、この repo は指示の規則 5 に準拠していない。

## 外した規則

次の 9 つだけを外した。ほかの規則は、option の調整か code の修正で通した。

| 規則 | 範囲 | 当たる所 | option や code で通せない理由 |
| --- | --- | --- | --- |
| `import/no-default-export`、`import/no-named-export` | 全体 | 拡張の `export default` と名前付きの `export` | 2 つは互いの唯一の代わりを禁じる。Pi は拡張を default export で読み、テストは名前付きの関数を import する |
| `oxc/no-async-await`、`oxc/no-optional-chaining` | 全体 | `async`、`await`、`?.` | 構文そのものを禁じる規則。Bun と、ページが対象にするブラウザは、どちらもそのまま実行する |
| `typescript/consistent-return` | 全体 | `T \| undefined` を返す関数の `return;`（6 か所） | `return undefined;` に直すと `unicorn/no-useless-undefined` が落とす。両方を通す書き方が無い（`treatUndefinedAsUnspecified` でも 6 件のまま） |
| `typescript/prefer-readonly-parameter-types` | 全体 | Pi の `ExtensionAPI`、`ExtensionContext`、event を受ける引数（26 か所） | Pi 自身の型が変更可能で、`tool_call` の handler は `event.input` をわざと書き換える（`ignoreInferredTypes` と `treatMethodsAsReadonly` でも 26 件のまま） |
| `import/no-relative-parent-imports` | `tests/**` | テストの `../../config/pi/extensions/...` | テストは `tests/unit/` にあり、検査する code は `config/` にある |
| `require-await`、`typescript/require-await` | `tests/**` | Pi と `fetch` の偽物（8 件と 6 件） | 非同期の API の偽物は、待つものの無い promise を返す。`typescript/promise-function-async` はそれを `async` にするよう求める |

code の中で 1 行だけ外した所は 4 つで、それぞれ理由を書いた: Pi の registry の `find(provider, id)`（配列の `find` ではない）、偽物を `ExtensionAPI` として渡す型の言い換え、`null` の入力を試すテスト、テストが環境変数を名前で退避する所。

## Options Considered

| 案 | 利点 | コスト・リスク | 扱い（提案） |
| --- | --- | --- | --- |
| A) root の package に道具と型を入れ、3 ファイルを指示どおりに検査する（本案） | 指示を配る repo が、自分でも指示を守る。型の誤りを初めて検査できる | `node_modules` が 128 package、196 MB。commit のたびに `bun install` が走る。直下に `package.json` を置かない方針を変える | 推奨 |
| B) Pi の型を手書きの `.d.ts` で代用し、root の package を置かない | 依存が増えない | 手書きの型は本物とずれ、検査が何も証明しなくなる | 非推奨: 型検査の意味が無くなる |
| C) `vp lint` と `vp check` のまま、`site/` だけを検査する | 変更が無い | Pi の拡張とテストに lint も型検査も無いまま。oxlint の版が固定されない。指示の規則 1 と 2 に反する | 非推奨: 所有者の指示に反する |
| D) `tools/js-gate/` に package を置き、`paths` で型を引く | 直下が増えない | 設定が増えるだけで、入るバイトは同じ | 非推奨: 複雑になるだけ |

## Consequences

- **Positive**: 自前の JS/TS の 3 ファイルすべてに、lint（517 規則）と型検査が掛かる。CI の 4 つの job は互いを待たない。oxlint の版が lockfile で決まる。
- **Negative**:
    - どの機体でも、`just lint`（prek が commit のたびに呼ぶ）の前に `bun install` が要る。初回は network が要り、`node_modules` は 196 MB になる。
    - 3 ファイルを大きく書き直した（拡張は 186 行から 387 行）。振る舞いは変えていないが、差分は大きい。
    - `nursery` の規則は oxlint の版ごとに変わりうるので、Dependabot の更新で新しい指摘が出ることがある。
    - `@earendil-works/pi-coding-agent` の型は固定した版（1.5.0）のもので、機体の Pi（`latest`）とずれうる。
    - 必須の check の登録（D9）が済むまで、「Frontend CI」が赤でも merge できる。
- **Neutral**: `vp` は整形にだけ残る。`site/package.json` は `vp fmt` のために残る。`rtk.ts` は build するだけで、lint も型検査もしない。

## 反転記録 (Reversal)

none

## 他の DR との照合

0001〜0078 の 77 件（0046 は欠番）の題名と状態を走査し、`package.json`、`bun.lock`、`vp`、`oxlint`、Pi の拡張、`site/` で全文を検索した。当たった 0027、0059、0076、0078 の決定を読んだ。PDR はない。

- **矛盾**: 見つからなかった。0076 は「置いたバイト（`site/vendor`）は vp の fmt、lint、check から外し、`site/copy.js` は検査に残す」と決めている。本案でも vendor は oxlint と型検査の外で、`copy.js` は両方の対象である。0076 の決定者は所有者で、この PR で確認を受ける。
- **重複**: 番号 0079 は未使用。同じ決定の記録はない。
- **誤読**: 0059 は、Pi の拡張が Pi の package を実行時に持ち込むことを禁じる。本案の dev 依存は型だけで、D5 がそれを検査する。
- **偽の関連**: 0027（Node は bun だけ）は、道具の選び方が同じ向きというだけで、置換の関係ではない。
- **関係誤認**: 0078 は指示そのものを決め、本案はその指示をこの repo に当てはめる。置換の関係ではない。

## 相談の記録

- 2026-11-16 20:04 JST、本セッションで所有者（@hironow）が指示した（上の Context）。
- 計画は Codex が独立にレビューした。1 回目は REVISE（4 件）、2 回目は REVISE（3 件）、3 回目は APPROVE。7 件はすべて実物で確かめて取り込んだ: 必須の check の登録、`--ignore-scripts`、`.gitignore` の例外、JSONC の hook、`copy.js` の型検査、外す規則の理由の誤り、Pi の型が実行時に入らない根拠。
- 外す規則は、計画の時点では 30 ほどを見込んでいた。1 つずつ option と code の修正を試し、9 つになった。

## 決定（記入待ち）

- [ ] A 案で Accept / [ ] 修正のうえ Accept（修正点: ____） / [ ] Reject（理由: ____） / [ ] Deferred
- 決定者・日付:
- A 案 Accept 時のアクション: Decision を MUST で確定し、索引、変更ログ、queue の決定済みログを同じ PR で更新して merge する。そのあと所有者が「Frontend CI」を必須の check に登録する。
- 修正 Accept 時のアクション: 指摘の点を設定、code、Decision に反映し、同じ PR で確定する。
- Reject 時のアクション: PR を閉じ、queue に理由を残す。gate は `vp` のまま変えない。
- Deferred 時のアクション: PR を閉じ、再検討の条件と期限を queue に残す。
