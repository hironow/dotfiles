# EGMを導入して使う

Elephant-Goldfish Model（EGM）は、設計書を作成し、会話履歴を持たない別のエージェントにレビューさせるプラグインである。
実装の変更、テスト、人間の承認は代行しない。

## 固定版と配置

導入版は `google/elephant-goldfish-model` の `v0.1.0`、commit `b3a35956759bf7f024af2ff061b2e0b44b438e4c`。
skillだけをコピーすると、実行時に読むpersonaやstandardが欠けるため、一式を導入する。

| 環境 | 配置の所有者 | 宣言 |
| --- | --- | --- |
| Claude Code | ネイティブのplugin CLI。既存の各Claude homeを対象とする | `dump/harness/claude-plugins.json` |
| Codex | ネイティブのmarketplaceとplugin CLI。`--ref v0.1.0`で固定する | `just egm-install` |
| Antigravity | `agy plugin install`。検証済みのローカルbundleを渡す | `just egm-install` |
| Pi | ネイティブのgit package。7つのskillをbundle内から発見する | `dump/harness/pi-packages.json` |

Piのbundleは `<PI_CODING_AGENT_DIR>/git/github.com/google/elephant-goldfish-model` にある。
既定のagent directoryは `~/.pi/agent`。
インストーラは既存のcloneについて固定commit、必須ファイル、追跡ファイルの変更、未追跡ファイル（ignore対象も含む）を検査する。
sparse checkout、skip-worktree、assume-unchangedなど、変更や欠損を隠せるindex状態も受理しない。
通常installerが他のpackageを復旧した場合は、その処理後にもEGMを検査する。
不一致なら停止し、resetや削除で利用者の変更を消さない。

## 導入

先に指示配布の差分を確認する。
`egm-install`の最初の処理は既存の`sync-agents all`であり、EGMの補足だけでなく、通常の共通指示、hooks、settingsも配布する。

```sh
just sync-agents-preview all
just egm-install
```

続いてPiとClaudeのEGM限定installer、Codex、Antigravityの順に実行する。
EGM限定installerは、他のpackageやpluginを更新せず、Ollamaなどのシステムソフトウェアも導入しない。
通常の`just deploy`とは異なる、明示的な導入手順である。
失敗した場合はその場で止まり、完了していない環境を成功扱いしない。
各CLIを再起動してから使う。

Piの補足は `docs/agents/egm.md` と `egm-reviewer` profileを既存installerが置く。
Piの優先順位に従って選んだglobal context fileには、EGM用のマーカーで囲んだ参照だけを追加する。
利用者の本文は残し、壊れたマーカーや他者所有の同名guide/profileは上書きしない。
symlinkのcontext fileも編集せず、所有者に解決を求める。

## 呼び出し

| 用途 | skill名 |
| --- | --- |
| 問題と選択肢の検討 | `egm-brainstorm` |
| 設計書の作成 | `egm-draft` |
| 設計書のレビュー | `egm-review` |
| 指摘の裁定 | `egm-resolve` |
| 個別のレビュー処理 | `egm-review-loop` |
| README契約の作成 | `egm-bootstrap` |
| 設計書と実装の差分検出 | `egm-drift-report` |

Claudeでは `/egm:egm-brainstorm` のように呼ぶ。
Codexでは導入済みskillを選び、Antigravityでは `/egm-brainstorm` のように呼ぶ。
Piでは `/skill:egm-brainstorm` のように呼ぶ。
上流のディレクトリ名にunderscoreがあっても、Piが発見するskill名はhyphenである。

補足の正本は [`ROOT_AGENTS_docs_agents_egm.md`](../../ROOT_AGENTS_docs_agents_egm.md)。
既存の質問UI、承認、指定された出力言語、ローカルの実行前ゲートを優先する。
EGMのreadinessやuninterrupted modeを、その承認の代わりにしない。
設計作業を終えて実装へ移るときも、利用者の指示を確認する。

## レビューの分離条件

Claudeは`omitClaudeMd`に対応する **2.1.271以上** を使う。
古い版や版が不明な環境ではGoldfishの起動を止める。
CodexとAntigravityでも、利用できる実際のnative toolで新しい会話contextを確保する。

Piは上流の公式対応先ではない。
`egm-reviewer`のファイルがあるだけで分離を確認したことにはならない。
実効profile、project/user override、hostが必須にするchild extension、実際の起動情報を調べる。
`extensions: []`でもhost必須extensionは残り得る。
呼び出しには毎回`options.context: "fresh"`を指定する。
追加の権限、会話履歴、model/effortの変更がないと確認できなければ、レビューを止めて未検証と報告する。

persona、standard、対象文書を読み切れなかった子や失敗した子は、「指摘なし」ではなく未完了である。
新しい会話contextはfilesystem sandboxを意味しない。
実際のchild/sessionの証拠で確かめ、自己申告だけを分離の証拠にしない。

## 重複skillの移行

公開のinstall宣言では、会話から仕様をissueにまとめる`to-prd`を残し、同じ手順の`to-spec`を対象外にする。
`grilling`は0.3.0で`grit-grill`だけを提供し、handover作成は`intent-handover-governance`に任せる。
コード差分の`review`、API案を比較する`design-an-interface`、安全な細分化を行う`request-refactor-plan`などは残す。
EGMとは成果物や手順が異なるためである。

既存機体のstoreは、宣言から外しただけでは消えない。
移行時は次の順を守る。

1. 新しいセッションでEGMの7つの入口と、残す`to-prd`、`intent-handover-governance`を発見できることを確認する。
2. リンクされた各consumerが後継を読めることを確認する。起動時の検査だけで、Goldfish動作まで確認済みとはしない。
3. skills CLIで`to-spec`だけをglobal scopeから退役させる。例：`just skills remove -g to-spec -y -a universal`。CLIが停止する場合は中断し、storeや全skillの一括削除で代用しない。
4. merge後のmainから、各Claude homeでネイティブの`claude plugin update grilling@hironow-plugins`を行い、0.3.0と`grit-grill`の存在、古いhandover入口の不在を確認する。
5. consumerに古いコピーやdangling linkが残っていないか確認する。利用者が編集したコピーは自動削除せず報告する。

`egm-install`はこの退役を自動実行しない。
また、宣言更新のためにliveのlock全体をdumpして、無関係なhash driftを取り込まない。

## 検証範囲

テストは `tests/unit/test_egm_integration.py` と両installerの既存unit suiteにある。
宣言とpin、限定installerの副作用、cloneの拒否条件、contextの保存、profileの静的制約を検査する。

導入と7コマンドの発見、固定版とのファイル一致は、対話的な設計フローやレビュー分離の動作証明とは別である。
上流のv0.1.0 releaseも、配布ZIPそのものの全host動作を保証していない。
PRのCI、実機での質問と承認、native childの分離は、それぞれ実施した範囲だけを報告する。
