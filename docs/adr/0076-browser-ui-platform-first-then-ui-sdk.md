# ADR 0076 — ブラウザの UI はプラットフォームを先に使い、足りない振る舞いは ui-sdk で作る

- **id**: ADR-0076
- **title**: ブラウザの UI はプラットフォームを先に使い、足りない振る舞いは ui-sdk で作る
- **status**: Proposed
- **date**: 2026-11-13
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session）
- **author-contact**: @hironow
- **supersedes**: none（[ADR-0052](0052-renew-global-agent-instructions.md) の Decision 1 の範囲を明確にする。0052 の本文と決定は変えない）
- **superseded-by**: none
- **related**: [0014](0014-vendor-emulator-telemetry-from-submodules.md)、[0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)、[0043](0043-self-authored-skills-through-the-skills-cli.md)、[0051](0051-adopt-decision-queue-for-new-records.md)、[0052](0052-renew-global-agent-instructions.md)、[0053](0053-stop-using-flatt-mirrors.md)、[0073](0073-mwg-v1-before-the-plugin-cooldown.md)、[0074](0074-bump-declared-agent-plugins-without-the-wait.md)
- **consultation-trace**: 2026-11-13 の本セッションでの所有者の指示と裁定（下の「相談の記録」）。同じ内容を draft PR の本文に残し、所有者の確認をその PR で受ける

## やさしい説明

ブラウザで動く画面を作るときの、agent への決まりを足す。
まず HTML とブラウザに最初からある機能を使い、それで足りないところ（キーボード操作や読み上げなど）だけ ui-sdk という部品集を使う。
このリポジトリの公開ページ（GitHub Pages）も、この決まりに合わせて作り直す。

## Context

- 全エージェント共通の指示（`ROOT_AGENTS.md` と spoke）に、ブラウザの UI の決まりは無かった。hub の「新しいコードは Go」の規則は「Python、TypeScript ではなく Go」と書き、ブラウザで動くページのコードを範囲に含むようにも読めた（[ADR-0052](0052-renew-global-agent-instructions.md) の Decision 1 は「新しいサービス、CLI、ツール」を対象にする）。
- 所有者は 2026-11-13 04:48 JST に、UI の指示の更新と、Pages のサイトをそれに合わせることを指示した。[vercel-labs/ui](https://github.com/vercel-labs/ui)（ui-sdk）を推奨し、利用者の指定や既存の依存の制約が無ければ web components と HTML、ある程度の制約なら web components と Vite をさらに推奨する。上流の setup の手順（`https://ui-sdk.dev/web.js` と `web.css` の 2 タグ、AGENTS.md への注記、npm の CLI での skill の追加）も示した。
- ui-sdk の npm の版は `0.1.0-beta.1` だけで、公開は 2026-11-12T17:09:47Z（`@ui-sdk/web`）と 17:12:06Z（`@ui-sdk/core`）。Apache-2.0。repo の作成は 2026-10-26。依存方針では、新しく利用者の少ない依存は Class 2 で、7 日の待機がかかる。
- 上流の `web.js`、`web@0.js`、`web.css` は 307 で最新の版へ転送する。版付きの URL は変わらない。ローダーは自分と同じ folder から部品と chunk を `import()` するので、`<script>` の `integrity` はローダーしか覆わない。
- `~/.npmrc` の `min-release-age=7` は bun に効かない（`docs/cli-tools.md` の実測、bun の文書）。bun の待機は `--minimum-release-age` か bunfig の `install.minimumReleaseAge`。2026-11-13 に、隔離した dir で `bun add --exact --minimum-release-age 7d @ui-sdk/web@0.1.0-beta.1` が拒否され、`0` なら入ることを確かめた。入ったバイトは、registry の `dist.integrity` と一致する tarball の `browser/` と同一だった。
- [ADR-0073](0073-mwg-v1-before-the-plugin-cooldown.md) で入れた Modern Web Guidance の skill は、HTML、CSS とクライアントの JS を書く前にまず使うよう求める。hub の規則は「第三者の package には標準ライブラリで足りない理由が要る」。
- Pages のサイトは repo 直下の `index.html` 1 枚で、install のコマンド（`curl … | bash`、`irm … | iex`）を配る。外部の script は無かった。

## Decision

所有者の指示と裁定を、次の必須事項（MUST）として提案する。

- D1: ブラウザの UI について、全エージェントに ui-sdk を勧める。利用者の指定や既存の依存の制約が無ければ HTML と ui-sdk の web components（build なし）、ある程度の制約があれば ui-sdk の web components と Vite を使う。
- D2: Pages のサイトは D1 の指示に従う。
- D3: この変更（draft PR）では、`@ui-sdk/web@0.1.0-beta.1` に 7 日の待機をかけない。この版だけの例外で、これからの版には Class 2 の待機がかかる。
- D4: この変更は draft PR で出す。

## Claude が常設の指示（2026-11-08）のもとで選んだこと

所有者は、許可を求めずに推奨案を選んで記録し、報告するよう常設で指示している。次の点は Claude が選んだ。所有者はこの PR で覆せる。

- 指示の最初の規則は「プラットフォームを先に使う」。hub の「標準ライブラリを先に」と Modern Web Guidance に合わせ、ui-sdk に回すのは、キーボード操作、focus、menu や combobox などの ARIA の pattern、popup の位置、処理中の状態と読み上げとする。
- 「ある程度の制約」を、TypeScript、npm の package、束ねる複数のファイル、既存の bundler のどれかがあること、と具体化する。利用者が指定したフレームワークや、既存の依存が決めているフレームワークには、そのフレームワークの ui-sdk の package を使う。
- hub の Go の規則に「ブラウザで動くページのコードは範囲外、そのサーバー側は Go のまま」の 1 文を足す。0052 の Decision 1 の範囲の明確化で、例外を増やすものではない。
- 上流の手順とこの指示が食い違うときは指示が勝つ: 正確な版を pin し、bare の `web.js` を使わず、npm の CLI の代わりに bun を使う。
- ui-sdk の skill（`packages/core/skills/ui-sdk`）は宣言に足して全 home に配り、上流の最新を追う（[ADR-0074](0074-bump-declared-agent-plugins-without-the-wait.md) は宣言済みの skill に待機を課さない）。
- サイトは CDN を読まず、検証した npm のバイトを `site/vendor/ui-sdk/<version>/` に置く。install のコマンドを配るページで、CDN のバイトが変われば配るコマンドも書き換えられるため。folder は版ごとに 1 つ、SHA-256 と出所の記録をテストで確かめ、`just site-vendor-ui-sdk-check` で registry の版と照合する。
- 置いたバイトは vp の fmt、lint、check と、prek の `end-of-file-fixer`、`trailing-whitespace` から外す。整形で変わると検証したバイトと一致しなくなるため。代わりに上のバイトの検査を入れる。ページ自身の JS（`site/copy.js`）は検査に残す（[ADR-0014](0014-vendor-emulator-telemetry-from-submodules.md) の emulator と同じ扱い）。
- 置いたバイトのこれからの更新は Class 2 の 7 日の待機に従う。0074 は宣言済みの plugin、Pi の package、skill だけが対象で、これを含まない。置いたコピーには Dependabot の alert が来ないので、ページを変えるときに上流の release と advisory を確かめる（指示に書く）。
- サイトは tabs を使わない（2 つの install コマンドは両方見えていればよい）。copy のボタンだけを `ui-button` にして、処理中の状態と読み上げを ui-sdk に任せる。
- サイトから、週ごとに変わる数（skill、recipe、ADR などの数）を外す。

## Options Considered

| 案 | 利点 | コスト・リスク | 扱い |
| --- | --- | --- | --- |
| A) プラットフォームを先に、足りない振る舞いは ui-sdk（本案） | hub の標準ライブラリ優先と MWG に合う。ARIA の手書きと UI ライブラリの乱立を防ぐ | ui-sdk はまだ beta で、API が変わりうる | 提案 |
| B) UI はすべて ui-sdk から始める（上流の手順のまま） | 指示が短い | native の `<button>` で足りる場面でも部品を足す。hub の規則と MWG に反する | 提案しない |
| C) サイトは CDN の版付き URL を読む | 置くファイルが無い | install のコマンドを配るページに、検証していない第三者の JS が入る。`integrity` は部品の module を覆わない | 提案しない |

## Consequences

- **Positive**: ブラウザの UI の作り方が全 agent でそろう。待機と版の固定を bun の実際の設定で書くので、指示どおりにすれば守られる。サイトは第三者のバイトを検証して置くので、配るコマンドが外から書き換えられない。
- **Negative**:
    - ui-sdk は `0.1.0-beta.1` で、破壊的な変更がありうる。
    - サイトは公開から 1 日の版を使う（D3）。上流が取り下げても先に入る。
    - repo に約 1.0MB、146 ファイルの第三者の生成物が入る。
    - skill は上流の最新を追うので、上流の変更がそのまま入る。
- **Neutral**: 他の repo の UI は移行しない。Claude の Artifact は外部の script を許さないので、この指示の対象外。

## 反転記録 (Reversal)

- 反転はない。

## 他の DR との照合

0001〜0075 の 74 件（0046 は欠番）の題名・状態・置換関係を走査し、UI、web、TypeScript、Vite、Pages、skill、待機、vendor に触れる記録の全文を読んだ（0014、0027、0043、0052、0053、0073、0074）。PDR はない。

- **矛盾**: 0052 の Decision 1（新しいサービス、CLI、ツールは Go）は、ブラウザで動くページのコードを対象にしていない。hub の文の読み違いを防ぐ 1 文を足すだけで、0052 の決定は変えない。0052 の決定者は所有者で、この PR で確認を受ける。
- **重複**: 番号 0076 は未使用。同じ決定の記録はない。
- **誤読**: 0053 の npm の待機は bun に効かない。この ADR は bun の待機を別に書く。0074 は置いたバイトを対象にしない。
- **偽の関連**: 0067（Podman）、0072（telemetry）は関係しない。
- **関係誤認**: 0073 の MWG の skill は「HTML、CSS、JS の前にまず使う」で、本案の「プラットフォームを先に」と同じ向き。置換の関係ではない。

## 相談の記録

- 2026-11-13 04:48 JST、本セッションで所有者（@hironow、0052 の決定者）が指示した（上の Context）。
- その後 Claude は所有者に次を伝えた: ui-sdk は `0.1.0-beta.1` だけで公開は 2026-11-12、Class 2 なので 7 日待つ。指示と skill は先に、サイトは待機明けに分ける案。bare の `web.js` は使わず正確な版を pin する。npm の CLI は bun に読み替える。
- 2026-11-13 05:08 JST、所有者は「そうだね。PR内は7日ルールなしでいいが draft PR として出してください」と答えた（D3、D4）。
- 計画は独立サブエージェントが 3 回レビューした（Codex はクレジット切れ）。1 回目と 2 回目は REVISE で、指摘はすべて取り込んだ。3 回目は APPROVE。

## 決定（記入待ち）

- [ ] D1〜D4 と上の選択のとおり Accepted
- [ ] 修正して Accepted（修正点: ____）
- [ ] Rejected / Deferred（理由: ____）

決定者: 　決定日:

- Accepted のとき: Decision を確定し、索引、変更ログ、queue の決定済みログを同じ PR で更新してから merge する。
- 修正のとき: 指摘の点を直し、同じ PR で確定する。
- Rejected / Deferred のとき: PR を閉じ、queue に理由を残す。
