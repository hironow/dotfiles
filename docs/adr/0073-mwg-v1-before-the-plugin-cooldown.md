# ADR 0073 — Modern Web Guidance の v1.0.0 は、7 日の待機を待たずに pin する

- **id**: ADR-0073
- **title**: Modern Web Guidance の v1.0.0 は、7 日の待機を待たずに pin する
- **status**: Accepted
- **date**: 2026-11-12
- **decided-date**: 2026-11-12
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: [ADR-0056](0056-common-claude-plugin-set.md) の一部（Decision 4「タグは公開から 7 日以上たった版」を、googlechrome の `v1.0.0` についてだけ外す。他の marketplace と、googlechrome のこれからの版には Decision 4 がそのまま効く）
- **superseded-by**: none
- **related**: [0048](0048-required-claude-plugins.md)、[0053](0053-stop-using-flatt-mirrors.md)、[0057](0057-shared-plugins-need-no-per-home-settings.md)
- **consultation-trace**: 2026-11-11〜12 の本セッションでの所有者の指示と選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

Claude Code の plugin「Modern Web Guidance」（Web の書き方の最新の助言を agent に渡す skill）を、出たばかりの 1.0.0 に上げる。
ふだんは、出てから 7 日たった版だけを使う決まり（ADR-0056）がある。
今回だけ、所有者の判断でその決まりの外に置く。

## Context

- 所有者は 2026-11-11 に「<https://developer.chrome.com/blog/modern-web-guidance-v1?hl=ja> をこのリポジトリのセットアップに加えてほしい」と指示した。
- `dump/harness/claude-plugins.json` は marketplace `googlechrome` を `GoogleChrome/modern-web-guidance#v0.0.193` に pin し、plugin `modern-web-guidance@googlechrome` を全 Claude home に入れている（ADR-0048、0056）。
- ADR-0056 の Decision 4 は「タグは、公開から 7 日以上たった版を選ばなければならない（MUST）」とする。テストは版の年齢を見ていない。
- GitHub の release `v1.0.0` は 2026-11-10T03:24:59Z に公開された（2026-11-12 には 2 日目）。v1.0.0 の plugin の中身は、skill 2 つ（`modern-web-guidance`、`chrome-extensions`）と guides の markdown と `policies/modern-web-guidance.toml` である。hooks と MCP は無い。
- skill は実行時に `npx -y modern-web-guidance@latest ...` で CLI を取ってくる（v0.0.193 も同じ）。この機体の `~/.npmrc` は `min-release-age=7`（ADR-0053 が残した 7 日の待機）。
    - npm の 1.0.0 は 2026-11-10T03:29Z 公開。2026-11-11 の時点で、待機を通る最新は 0.0.197（2026-11-02）だった。
    - 0.0.197 の CLI のソース（`modern-web.mjs`）にあるコマンドは search、retrieve、list、install、uninstall、update、set-allow-origin-trials で、v1.0.0 の skill が使う `legacy-scan` は無い。
- 所有者は 2026-11-11 に、Claude だけ、今上げる、npx の件は今回触れない、を選んだ。2026-11-12 に、上の ADR-0056 との食い違いと `legacy-scan` が 2026-11-17 まで動かないことを聞いたうえで、「今上げ、ADR で例外にする」を選んだ。

## Decision

所有者の裁定を、次の必須事項（MUST）として採択する。

- D1: `dump/harness/claude-plugins.json` の googlechrome は `GoogleChrome/modern-web-guidance#v1.0.0` に pin してよい。公開から 7 日たっていないことは、この版に限り ADR-0056 の Decision 4 に反しない。
- D2: D1 のほかは、ADR-0056 の Decision 4 が効く。7 日未満のタグを選ぶときは、marketplace と tag の組を名指しした所有者の裁定を DR に残さなければならない（MUST）。名指しの無い例外を作ってはならない。
- D3: skill が呼ぶ npx と `~/.npmrc` の待機は変えない。2026-11-17T03:29Z より前は、skill の `legacy-scan` は動かない。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) 2026-11-17 まで待って上げる | ADR-0056 をそのまま守る。上げた日から npx も 1.0.0 に解決され、`legacy-scan` も動く | 6 日間、v0.0.193 のまま | 所有者が今上げることを選んだため却下 |
| B) 今上げ、v1.0.0 だけ例外にする（本案） | 1.0 の skill と guides をすぐ使える | 待機を飛ばす。2026-11-17 までは skill と CLI の版がずれ、`legacy-scan` が動かない | 所有者が採択 |
| C) 今上げ、MWG の CLI だけ npm の待機を外す | skill と CLI の版がそろう | npx の扱いを変えることになり、所有者が「今回は触れない」と選んだ範囲を超える | 範囲の外のため却下 |

## Consequences

- **Positive**: 全 Claude home で、MWG 1.0 の skill（guides の追加と、検証された知識の差分）を使える。
- **Negative**:
    - 7 日の待機を飛ばすので、上流が版を取り下げても先に入る。plugin の中身は markdown と policy だけで、実行するコードは npx で別に取るので、影響はそこに限られる。
    - 2026-11-17T03:29Z までは、skill が `legacy-scan` を呼ぶと、待機で選ばれた 0.0.197 の CLI が知らないコマンドとして失敗する。
    - marketplace を差し替えるので、各 home で plugin を一度外して入れ直す。
- **Neutral**: Codex・Antigravity などには入れない（所有者が Claude だけを選んだ）。skill が npx を使うことは前からで、この ADR では決めない（handover に残す）。Mac の Claude home には、Mac で `just claude-plugins-install` を実行したときに入る。

## 反転記録 (Reversal)

- 反転はない。ADR-0056 の Decision 4 を、googlechrome の `v1.0.0` についてだけ部分置換する（0056 の本文は変えず、Status 行に置換先を書く）。

## 他の DR との照合

0001〜0072 の 71 件（0046 は欠番）の題名・状態・置換関係を走査し、plugin・marketplace・待機（cooldown、`min-release-age`）・MWG に触れる記録の全文を読んだ（0017、0048、0053、0056、0057、0058）。PDR はない。

- **矛盾**: 0056 の Decision 4 と食い違う。所有者（0056 の決定者）に食い違いを示し、所有者がこの部分置換を選んだ。
- **重複**: 番号 0073 は未使用。同じ決定の記録はない。
- **誤読**: 0048 の Decision 1（リリースタグで pin）は `v1.0.0` もタグなので満たす。0057（home ごとの設定が要らない plugin だけ）も、MWG は設定が要らないので満たす。
- **偽の関連**: 0053 と 0058 の npm の待機は `~/.npmrc` の話で、plugin のタグではない。D3 で変えない。0017 の `min-release-age` は corepack の話で関係しない。
- **関係誤認**: 0056 の他の Decision（1〜3、5）と、0057 が置き換えた部分は変えない。

## 相談の記録

- 2026-11-11、本セッションで所有者（@hironow、0048・0056・0057 の決定者）が指示し、Claude だけ、今上げる、npx は今回触れない、を選んだ。
- 計画は独立サブエージェントがレビューした（Codex はクレジット切れ）。ADR-0056 の Decision 4 との食い違いと、npm の待機で `legacy-scan` が動かないことは、その指摘から見つかった。待機で選ばれる版はレジストリの公開日時から、`legacy-scan` が無いことは 0.0.197 の CLI のソースから確かめた（npx は実行していない）。
- 2026-11-12、本セッションで所有者が上の 2 点を聞いたうえで「今上げ、ADR で例外にする」を選んだ。

## 決定（2026-11-12）

- [x] B を Accepted（D1〜D3 を MUST 文で確定し、索引、変更ログ、queue を更新する）
- [ ] A を Accepted（2026-11-17 まで v0.0.193 のままにする）
- [ ] Rejected / Deferred（宣言の変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-12（所有者の選択により代理記入）

- A 案は所有者が今上げることを選んだため、C 案は所有者が npx に触れないと選んだ範囲を超えるため却下する。
- 採択時に索引、変更ログ、queue の決定済みログを同時に更新し、ADR-0056 は Status 行だけを変えた。
