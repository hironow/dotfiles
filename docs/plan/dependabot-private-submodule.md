# Dependabot の clone で private の submodule を飛ばす

**Date:** 2026-11-17
**Status:** #633 で merge したが、merge 後の Dependabot は `protocols/UTCP` の壊れた入れ子で全 job が止まった。`docs/plan/dependabot-skip-all-submodules.md`（すべての submodule を飛ばす）で置き換えた
**Scope:** dotfiles のみ。worktree `../dotfiles-dependabot-submodule`、branch `fix/dependabot-private-submodule`。

## 所有者の依頼

3 リポの「最新に追従できていない領域」の調査で、dotfiles の週 1 回の Dependabot PR が出ていないと分かった。
所有者はこの修理を選んだ（2026-11-16、「1」）。

## 何が起きているか（確認済みの事実）

- dotfiles の Dependabot の `github_actions` の実行は、2026-07-28 から毎回失敗している（それ以前も 06-07〜06-30 に失敗）。最後の成功は 07-21。
  `gh run list --workflow 'Dependabot Updates'` で確認した。
- PR #596（2026-11-11）で全エコシステムを 1 つの `weekly` グループにまとめた。11-10、11-11、11-16 の実行では、`github_actions` の失敗で週 1 の PR が出ていない。最後の Dependabot PR は 11-08。
- 失敗の流れ（11-16 の実行ログ `job_1709041729` で確認）:
  1. Dependabot は `git clone --no-tags --depth 1 --recurse-submodules --shallow-submodules https://github.com/hironow/dotfiles` で clone する。
  2. private の `hironow/knowledge-work-plugins` は `Repository not found` で clone できない（`Failed to request additional scope: 403`）。
  3. git は submodule の clone を途中でやめるので、残りの 32 個の submodule は空のまま残り、`git status` に `modified content` と出る。
  4. Dependabot は更新ごとに `git status --short .` が空でなければ `git add -- <repo>` と `git commit` をする（dependabot-core `common/lib/dependabot/workspace/git.rb` の `store_change`）。1 件目（actions/checkout）は commit できたが、2 件目（11-16 は astral-sh/setup-uv、それ以前は actions/deploy-pages）で `git commit` が exit 1 になり、ジョブ全体が失敗する。
- 手元で同じ clone を再現した（scratchpad の `subrepro`、`file://` の 3 つのリポ、1 つを消して unreachable にする）。消したリポの clone の失敗で残りの submodule が空になり、`git status` に `m good1` `m good2` が出た。その後の `git add` と `git commit` は `no changes added to commit` で exit 1 になった。
- 個人アカウントの repo には、Dependabot に private repo へのアクセスを与える設定がない。この設定は組織にしかない（GitHub Docs「Managing security and analysis settings for your organization」の「Allowing Dependabot to access private dependencies」）。
- 所有者の git には `submodule.recurse` の設定がない（global も local も）。

## 直し方の比較

| 案 | 内容 | 判断 |
|---|---|---|
| A | `.gitmodules` の `knowledge-work-plugins` に `update = none` を付ける | **採用**。秘密情報が増えない。元に戻すのも 1 行 |
| B | fine-grained PAT を Dependabot secret に置き、`dependabot.yaml` の `registries` に `type: git` を足す | 不採用。長期の認証情報が増え、期限切れでまた止まる。submodule の clone に効くかも未確認 |
| C | `knowledge-work-plugins` を submodule から外す、または public にする | 不採用。所有者の構成の判断で、この修理の範囲を超える |
| D | 全 submodule に `ignore = dirty` を付ける | 不採用。所有者の手元の dirty も隠れる。原因（clone の失敗）は残る |

案 A を手元で確認した結果:

- Dependabot と同じ clone は `Skipping submodule 'private'` を出して exit 0 になり、`git status` は空になる。ほかの submodule は中身まで取れる。
- 副作用として、所有者の checkout でも `git submodule update` と `git submodule update --remote --force` がこの submodule を飛ばす。
    - 変更前に init した checkout: ローカルの `submodule.<name>.update` は無く、`.gitmodules` の `none` が効く。
    - 変更後に init した checkout: `git submodule init` が `none` をローカルの `.git/config` に写す（再現で確認。`fresh2` と `c2` は `none`）。
- `--checkout` を付けると、どちらの場合も `update = none` を上書きして更新できる（`--remote --force --checkout` で新しい commit まで進んだ）。
- 新しい機体では `git submodule update --init` がこの submodule を飛ばす。`--init --checkout` なら取れる。

## 変更

1. **[Red]** `tests/unit/test_private_submodule_clone.py` を足す。手元の再現を `tmp_path` の中で自動にする。
   - 準備: `tmp_path` に公開役の 2 つのリポ、private 役の 1 つ、それらを submodule に持つ superproject を作る。private 役の submodule の設定は、**本物の `.gitmodules` の `knowledge-work-plugins` の節から読んで写す**（`update` の値）。正規表現の読み方は `tests/unit/test_claude_md_excludes.py` に合わせる。git は `GIT_CONFIG_GLOBAL=os.devnull`、`GIT_CONFIG_NOSYSTEM=1`、`-c protocol.file.allow=always`、`-c commit.gpgsign=false` で所有者の設定から切り離す。
   - 対照: `update` を写さない superproject では、private 役を消すと、Dependabot と同じ clone（`--no-tags --depth 1 --recurse-submodules --shallow-submodules`）が失敗し、`git status --short` が空でない。これで再現の仕組みが本物の障害と同じだと示す。
   - 本題: 本物の設定を写した superproject では、同じ clone が exit 0 で、`git status --short` が空で、公開役の submodule の中身がある。
   - 所有者の更新: private 役に新しい commit を足し、`justfile` の `update-all-submodules` から取り出した `submodule update --remote` の行をそのまま実行すると、変更後に init した checkout（ローカルが `none`）でも private 役が新しい commit まで進む。
   - 新しい機体: README の手順から取り出した `submodule update --init ...` の行を HTTPS 役の素の clone で実行すると、private 役の中身が取れる。
   `justfile` と README から行を取り出すので、文言を戻すとテストが落ちる。
   取り出した行は `shlex.split` で分け、`submodule` から後ろの引数だけを使う（README の `-C ~/dotfiles` と recipe の `-c ...` は捨てる）。実行は必ず `["git", "-C", <tmp_path の中の checkout>, *その引数]` の形で、`shell=False` にする。テストは実行の前に、`-C` の先が `tmp_path` の中にあることを assert する。こうして、テストが所有者の本物の checkout に触れないようにする。
2. **[Green]**
   - `.gitmodules`: `[submodule "knowledge-work-plugins"]` に `update = none` を足す。
   - `justfile`: `git -c submodule.recurse=false submodule update --remote --force` に `--checkout` を足し、recipe の上のコメントに理由を 1 行足す。ほかの submodule は `update` を設定していないので、既定の checkout と同じ動きのまま。
   - `README.md`: `git -C ~/dotfiles submodule update --init` を `--init --checkout` にし、private の submodule は Dependabot の clone のために既定で飛ばす、と 1 文足す。
   - `.github/dependabot.yaml`: 先頭のコメントの「Out of scope」の近くに、private の submodule に `update = none` を付けた理由を書く。この編集で、merge 後に Dependabot が再実行される。
3. この計画を `docs/plan/` に置き、Status を更新する。

commit は 1 つ（`fix(dependabot): skip the private submodule in Dependabot's clone`）。構造の変更はない。

## 確認（完了の定義）

- `just ci` が完走して成功する。このホストだけの理由で落ちる leg があれば、比べるだけで合格にはしない。原因を直すか、所有者に報告して止まる。
- PR の CI が green。所有者の常設の許可（自分の PR は CI が green なら squash merge）に従って merge する。
- merge 後:
    - 手元の main を pull し、`git submodule status knowledge-work-plugins` が変わらないこと、`just update-all-submodules` がこの submodule を取りに行くことを確認する（ネットワークの都合で全体を回せないなら、`git -c submodule.recurse=false submodule update --remote --force --checkout knowledge-work-plugins` で代わりに確かめる）。
    - Dependabot の次の `github_actions` の実行が success になり、週 1 の PR が開くこと。`dependabot.yaml` の編集で再実行されなければ、次の定時（水曜 15:39 UTC）まで待って確認する。
- 失敗したとき: この修正の squash commit を丸ごと revert する PR を出す（新しいテストも一緒に消える。テストだけ残すと、本物の設定を読むので revert の CI が落ちる）。あわせて、変更後に init した各 checkout で `git config --get submodule.knowledge-work-plugins.update` を見て、`none` なら `git config --unset submodule.knowledge-work-plugins.update` で消す（init が写した値は revert では消えない）。Dependabot がまだ失敗するなら、ログで別の原因を探す（このとき案 B を所有者に相談する）。
- 復旧の手順は git の動作そのものなので、テストは作らない（このリポのコードの検査にならない）。

## 範囲外

- Dependabot が出す PR の中身（setup-uv v8→v10、setup-python v6→v7 などのメジャー更新）の確認。PR が出たら別に扱う。
- Mac の main tree（`/Users/nino/dotfiles`）は pull だけで反映される。この submodule の更新は `just update-all-submodules` を使う限り変わらない。

## レビューの記録

### Codex 1 回目（2026-11-17）

| # | 指摘 | 判断 | 確認したこと |
|---|---|---|---|
| 1 | 文字列の検査だけでは障害を防げたと言えない。再現を自動テストにする | 採用 | 変更 1 を再現テストに書き直した。行は `justfile` と README から取り出す |
| 2 | 変更後に init した checkout には `none` がローカルに写るので、1 行戻すだけでは復旧しない | 採用（復旧のテストは不採用） | 再現で `fresh2` と `c2` のローカルが `none` になるのを確認した。rollback に `git config --unset` を足した。復旧のテストは git の動作の検査なので作らない |
| 3 | 「main と比べて増えていない」は失敗を残す commit を許す | 採用 | 完了条件を `just ci` の完走と成功に直した |

### Codex 2 回目（2026-11-17）

| # | 指摘 | 判断 | 確認したこと |
|---|---|---|---|
| 1 | README の行には `git -C ~/dotfiles` があり、そのまま実行すると本物の checkout を触るおそれがある | 採用 | `submodule` から後ろだけを使い、`-C` を `tmp_path` の中に固定して assert する、と変更 1 に書いた |
| 2 | rollback で 4 ファイルだけ戻すと新しいテストが残り、revert の CI が落ちる | 採用 | squash commit を丸ごと revert する手順に直した |
