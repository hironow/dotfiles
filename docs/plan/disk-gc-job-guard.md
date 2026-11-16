# 計画: `just disk-gc` を job の実行中に止める

## なぜ

2026-11-16 01:33 JST、`just disk-gc` (`scripts/disk_gc.sh clean`) の WSL leg が、
WSL の runner で Rust の CI の job が build している最中に
`~/.cargo/registry/{src,cache}` を消した。
rustc は registry の crate (`darling`) を compile している途中で、自分の cwd を失って panic した。
cargo 1.95 は、registry の crate については rustc の cwd をその crate の展開先にする
(`util/workspace.rs` の `path_args`)。続く 13 件の `.d` のエラーは、
`fingerprint/dep_info.rs` の `try_canonicalize(pkg_root)` が ENOENT になったものである。
証拠は、`registry/src` と `registry/cache` の birth が 01:49 で `index` は 7/17 のままであること、
`disk_gc.sh` の 70〜71 行がちょうどこの 2 つを対象にしていること、そして PowerShell の履歴。

`runner_gc.sh` には job の検出があるが、`disk_gc.sh` には無い。
それなのに justfile は `just disk-gc` を「safe unattended」と説明している。

Windows の profile の cache (`~/.cargo`、uv、bun) も、Windows ネイティブの runner
(`actions-runner-win`、利用者 absin) の job と共有されているので、同じことが起きうる。

## 変えること

`scripts/disk_gc.sh` の `clean` に guard を入れ、`report` には判定を 1 行だけ足す。

1. その leg の runner の job の状態を 3 値で返す関数 `_runner_job_state` を作る (0 = 実行中、1 = idle、2 = 判定不能)。
   - Linux / WSL: `pgrep -x Runner.Worker` (`runner_gc.sh` と同じ。`-f` は自分自身に一致する)。rc 0 → 実行中、1 → idle、それ以外 (127 など) → 判定不能。
   - Windows (Git Bash): `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' tasklist /FI "IMAGENAME eq Runner.Worker.exe" /FO CSV /NH`。
     rc が 0 以外 → 判定不能。出力に `"Runner.Worker.exe"` があれば実行中、無ければ idle (該当なしの文言は言語で変わるが、image 名はそのまま出る)。
   - `set -eu` のもとでは、`_st=0; _runner_job_state || _st=$?` の形で受ける (idle の rc=1 で script が止まらないように)。
2. 削除の各段 (`mise prune`、`go clean -modcache`、`go clean -cache`、cache の 1 項目ごとの `rm -rf`) の直前で判定する。
   実行中なら `SKIP: a runner job is executing (Runner.Worker alive); rerun when idle` を出して、残りを消さずに exit 0。
   判定不能なら `SKIP: cannot tell whether a runner job is executing; nothing more deleted` を出して exit 2
   (fail-closed。WSL leg では呼び出し側の「WSL leg failed」が出る)。
   cache のループは今 `printf | awk | while` の pipeline で、中の `exit` が subshell しか終わらせないので、here-string に変える。
3. 上書きの鍵は `DISK_GC_ALLOW_BUSY=1` とする (runner-gc の `RUNNER_GC_ALLOW_BUSY` と同じ考え方。使用中の cache を消せば job は落ちる)。
   SKIP の行では上書きの方法を示さず、runbook に書く。値は 0/1 に正規化してから、
   Windows から WSL leg を呼ぶ `bash -lc` のコマンド行に埋め込む (`wsl.exe -e` は呼び出し元の環境を引き継がない)。
4. 判定は leg ごとに行う。WSL leg は distro の中で動く `disk_gc.sh` が WSL の runner を見る。
   Windows leg は Windows の runner を見る。一方の leg が SKIP しても、もう一方は続ける。
5. `report` に `runner job: busy|idle|unknown` を 1 行足す。何も消さずに、本物の検出を実機で確かめる経路になる。
6. justfile の `disk-gc` の説明の「safe unattended」と、`disk_gc.sh` の冒頭の注釈を直す。
   runbook `docs/runbook/runner-disk-gc.md` の §開発用キャッシュに guard の挙動を書く。§実行中のジョブの検出に次の規則を足す:
   「runner の job と共有する path を消す処理は、削除の各段の直前で job を判定する。『再生成できる』は『使用中に消してよい』ではない」。

## やらないこと

- 判定と削除の間に始まった job は防げない (判定は観測で、lock ではない。runner-gc と同じ限界)。各段の直前で判定して、その窓を最小にする。lock も、削除前の退避 (mv) も作らない。
- 対象の cache の一覧は変えない。ADR は変えない (runbook の規則で補う)。

## 独立レビュー (subagent、APPROVE WITH CHANGES) の扱い

指摘 6 件はすべて採用した。どれも実機かコードで確かめた。

1. fail-open: tasklist を MSYS 変換なしで実行すると `/FI` が `C:/…/FI` に書き換わり rc=1 になることを実測した。pipefail が無い `set -eu` (`disk_gc.sh:22`) では、これが「idle」と判定される。→ 3 値化、tasklist 行の静的検査、偽の argv の厳密照合。
2. 判定が 1 回だけ: `runner_gc.sh:262` と `:302` は項目ごとに再判定している。→ 各段の直前で判定。
3. 本物の検出がどこでも動かない。→ report に判定の行。
4. テストの隔離。→ env は白紙から組む、PATH は `test_podman_gc_simulation.py` と同じ、事前の検査、偽の `uname` で両分岐をパラメータ化。
5. `FORCE` の意味が repo の規則と食い違う。→ `DISK_GC_ALLOW_BUSY` に改名、値の正規化。
6. runbook。→ 上の 6。

## TDD

- **[Red]** `tests/unit/test_disk_gc_job_guard.py` を新しく作る。偽の `uname` で Linux と Windows の両分岐をパラメータ化する。
  - 偽の HOME と LOCALAPPDATA に cache を作る。偽の `pgrep`、`tasklist`、`mise`、`go` を置く。偽の検出は、argv が想定どおりでなければ exit 2 を返す。
  - env は白紙から組む。実行前に、偽の bin が使われていることと、`wsl.exe`、`powershell.exe`、`tasklist.exe` に届かないことを確かめる。
    さらに同じ env で `report` を実行し、候補の path がすべて tmp の下にあることを確かめる。
  - ケースは次の 5 つ。
    - idle (対照): cache が消え、`mise` と `go` が呼ばれる。guard が常に SKIP する、黙った故障を防ぐ。
    - 最初から実行中: 何も消えず、`SKIP` が出て、exit 0。
    - 判定不能 (偽が exit 3 / exit 1): 何も消えず、exit 2。
    - 途中から実行中 (最初の cache が消えた後に実行中と答える偽): 後ろの cache が残る。
    - `DISK_GC_ALLOW_BUSY=1`: 実行中でも消える。
  - report に `runner job:` の行が出ること。
  - 静的な検査: tasklist を呼ぶ論理行に `MSYS_NO_PATHCONV=1` と `MSYS2_ARG_CONV_EXCL` があること。WSL leg の dispatch 行に `DISK_GC_ALLOW_BUSY` があること。
- **[Green]** 上の「変えること」の 1〜5 を実装する。
- **[Refactor]** 6 (説明文と runbook)。

## 確かめ方

- `uv run pytest tests/unit/test_disk_gc_job_guard.py tests/unit/test_runner_gc.py` (Windows の native。Linux 分岐も偽の uname で通る)。
- `just ci` の lint (shellcheck、ruff、ty、markdownlint) と unit tests。
- 実機: `just disk-report` で、両 leg の `runner job:` の行が実際の状態と合うこと (WSL の job 中は busy、idle なら idle)。clean は実行しない。
