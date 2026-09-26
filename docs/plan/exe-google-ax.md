# exe を Coder から google/ax へ全面移行するプラン

**Date:** 2026-09-26
**Status:** Approved v3 (grilling Round 1-3 の決定、独立レビュー #1 / #2、GCP の事実確認を反映。2026-09-26 運用者承認)
**Branch:** `feat/exe-google-ax`

## 0. 要約

- exe の実行基盤を Coder (旧 project の GCE VM + Cloud SQL + Cloudflare Tunnel/Access + Tailscale) から
  **google/ax v0.3.1 + Agent Substrate v0.1.0 on GKE** へ置き換え、Coder 系は全撤去する。
- 新基盤は旧 exe とは**別の private GCP project** に作る。その識別子は git に一切入れない (§1.1)。
- GKE Standard の **zonal クラスタ 1 つ** (Rapid チャネル、1.37 系)。管理費 $0.10/h は GKE 無料枠 ($74.40/月、
  請求先アカウント単位) で相殺される。無料枠は空いていることを確認済み。
- ノードは **on-demand e2-standard-4 の 1 台だけ**で、使う時だけ起こす。台数は**リース方式の自動休眠**が持つ (§3.2)。
  休眠し忘れても 1 回あたり既定 ≈ ¥87、最悪 ≈ ¥266 で止まり、**24 時間つけっぱなしは構造的に起きない**。
- **保存先は全部、上限を宣言して CI で強制する** (§3.3)。Artifact Registry や snapshot がじわじわ溜まるのを防ぐ。
- 公開面ゼロ: private nodes + Cloud NAT、IP endpoint 無効 + DNS endpoint (Google IAM 必須)、Service は ClusterIP のみ。
- 構築は dotfiles 配下の OpenTofu: `tofu/exe-platform` (GCP 基盤) + `tofu/exe-cluster` (クラスタ内) + `tofu/tailnet` (ACL 移管)。
  上流 Substrate の installer (`ate-setup`) は、pin した版を build モードで `terraform_data` から呼ぶ。
- 概算 (東京のカタログ価格、2026-09-26): **休眠中 ≈ ¥450/月、起動中 ≈ ¥30/時** (Q22 の推奨どおりなら)。
- ちりつも対策は、あとで個人アカウント側の GCP にも横展開できるよう、再利用できる形 (spoke + 監査ツール + 後続計画) で残す (Q18)。
- 最大のリスクは上流が pre-1.0 で頻繁に breaking change すること。版を pin し、実機 e2e で互換を実証してから先へ進む。

## 1. 優先順位と設計への効き方

| 優先 | 要求 | 効いている設計判断 |
|---|---|---|
| 1 | google/ax を完全に利用 | 実行単位は AX `Task` のみ。`Workspace` (git + goal による自動セットアップ) / `Model` / suspend・resume / `ax ssh` を使う。task image は上流の runner 契約どおり |
| 2 | 低コスト | 無料枠で管理費 $0 の zonal クラスタ、ノードはリース中だけ、自動休眠の 4 層、保存先の上限、PVC は必要な性能の最小構成、GCS soft delete 無効、Managed OTel / GMP は使わない (必要性は spike で確認)、JPY の予算アラート |
| 3 | dotfiles 配下の OpenTofu のみ・非公開 | 3 stack とも tofu。上流は版 + commit SHA で pin。private nodes + DNS endpoint (IAM) + ClusterIP のみ。LB / NodePort / Ingress は作らない (テストで禁止)。private project の値は git 外 (§1.1) |
| 4 | シンプル | Cloudflare / Tailscale (exe 用) / Cloud SQL / cdr 系 5 スクリプト / Coder template 2 種 / public の devcontainer publish を撤去。上流 installer は再実装しない。独自コードは Go の `exe-reaper` 1 本 + bash ラッパー 2 本 |

## 1.1 機密性の制約 (運用者指定、2026-09-26)

- 本リポは public。新基盤の GCP project の識別子と、それに紐づく組織・アカウントの情報は
  **tracked file、commit message、PR の題名・本文、ADR、テストの fixture、public な GitHub Actions のログ**
  のいずれにも出さない。文中では「private project」とだけ書く。
- 値の置き場は gitignore 済みのファイルだけ: 各 stack の `terraform.tfvars` と partial backend 設定
  (`backend.hcl`、`tofu init -backend-config=backend.hcl`)。各新 stack に `.gitignore` を置き、`terraform.tfvars`、
  `backend.hcl`、`*.tfplan`、`.terraform/` を無視する。HCL の変数には既定値を持たせない。
- 機械的なガード (Phase 1):
    - 禁止トークンの一覧は repo 外のローカルファイル (例: `~/.config/dotfiles/forbidden-tokens`) に置く
    - commit する generic な検査スクリプトがそれを読み、staged の内容と commit message を検査する
    - prek の hook は pre-commit と **commit-msg の両方**を実際に install させる (`default_install_hook_types` と `just install-hooks` を直す)
    - `*.tfplan` / `*.tfstate*` など中身を検査できないバイナリは staging 自体を拒否する
    - `just ci` はブランチ上の**全 commit message** (`git log <base>..HEAD`) を再検査する
    - PR 本文はファイルに書いて同じ検査を通してから `gh pr create` する (recipe 化)
    - 検査スクリプトとそのテストには本物のトークンを書かない
- tofu の plan 出力には識別子が大量に出る。PR や docs に貼らない (runbook に明記)。
- public な CI は private project に一切触れない。イメージの build と push は private project 内の Cloud Build
  (または運用者の端末) で行う。
- 旧 exe (既に公開済みの旧 project) の撤去は、その project のオーナー ID で運用者が実行する (Q6)。
- 既存の露出 (tracked file 6 個、commit message 9 件、public PR 9 件) の掃除は別 work unit (Q12)。

## 2. 調査で確定した事実 (2026-09-26 時点、上流ソースと実環境で確認)

### 上流

- **google/ax** (Apache-2.0, v0.3.1 = 2026-09-25): stable 前に major な breaking change が入ると明言。
  `ax` CLI (kube context で `ax-system/svc/ax-server:8080` に自動 port-forward) / `ax-server` (stateless gRPC、Redis を読み書きするだけ) /
  `ax-controller` (Redis Streams を消費し、Substrate の `SuspendActor` / `ResumeActor` を呼ぶ唯一のコンポーネント) /
  `ax-task-runner` (各 task の PID 1)。上流の `deploy/redis.yaml` は**永続化も認証も無い**。
- AX は task ごとに gVisor の ActorTemplate (`gvisor-default` SandboxConfig、snapshot 先は `AX_SNAPSHOTS_BUCKET`) を作る。
  ActorTemplate の名前は image と env のハッシュから決まる (env が変わると別 template になる)。
  **WorkerPool も EgressPolicy も作らない**。**`Task.spec.resources` は読まれない** (actor の大きさは WorkerPool の limits だけで決まり、
  gVisor の既定は無制限)。資格情報の経路は `GEMINI_API_KEY` (atespace と同名 namespace の Secret `gemini-api-secret`、Gemini 専用) と
  `Task.spec.env` (平文。Redis と Substrate の Postgres に残り、`ax get task` で見える) の 2 つだけ。
- `ax ssh` はリモートの exit code をそのまま返す (`os.Exit(exitCode)`)。経路は `ate-system/svc/atenet-router:80` への port-forward。
  **v0.3.1 の `ax ssh -- cmd` は stdin を転送しない** (ExecOptions は Command / Stdout / Stderr のみ)。
- atenet router は、宛先の actor が suspend 中なら**自分で resume してから転送する** (Substrate の機能。ax-controller を経由しない)。
- 公開イメージは無い (`gcr.io/ax-substrate/...` は匿名 pull 不可、release asset 無し)。**全イメージを自前で build する**。
  ActorTemplate の image は digest 固定必須 (CEL `self.contains('@')`)。
- **Agent Substrate** (v0.1.0 = 2026-09-10、v0.2.0 = 2026-09-25): AX v0.3.1 の `go.mod` は commit `672533541dbf` を pin しているが、
  これは **v0.1.0 tag と系統が分岐** (`compare`: diverged, ahead 49 / behind 3)。本計画は **tag `v0.1.0` に統一**し、
  互換は spike S1 で実証する。v0.2.0 は「EgressPolicy の無い actor は egress ゼロ」で AX 未対応のため使わない。
- **v0.1.0 の制約**:
    - worker pod が消えると、起きている actor は **約 60 秒**以内に suspend されないと `ACTOR_STATE_CRASHED`
    (終端、状態消失、復旧手段なし)。**serving 中の WorkerPool を編集・縮小するのも同じ経路**で actor を殺す。
    (30 分に延びたのは v0.2.0 以降の話)
    - **actor 1 つが worker pod 1 つを丸ごと占有**する → 同時に起こせる task 数 = WorkerPool の replicas。
    - `WorkerPool.spec.workerImage` は必須で、ActorTemplate と同じ namespace に置く。**install 用のマニフェストは worker image を参照しない**
    (参照するのは ateapi / atecontroller / atelet / atenet / podcertcontroller だけ)。worker image は `ate-setup publish worker-images` が
    build して ref を出力する。
    - ノード 1 台だとローリングアップグレードは無い (上げる時は全停止)。
    - 同梱 Postgres の既定は requests cpu 2 / PVC 500Gi (コスト罠)。外部 DSN (`ATE_API_POSTGRES_CONNECTION_STRING`) で回避できる。
    - install は `go run ./cmd/ate-setup deploy ate-system`。CA / JWT pool の Secret 生成、ノードへの `ate.dev/substrate-version`
    付与まで行う。`KO_DOCKER_REPO` と `VERSION` を渡せば、image は ko で build され、ラベル値は `VERSION` で固定される。
    - gVisor の SandboxConfig は **nightly の GCS パス**と `registry.k8s.io` の pause image を参照する → 自前の SandboxConfig に差し替える。
    - atelet は hostPath と hostPort を使う → **Autopilot は不可**。E2 は nested virtualization 非対応 → **microvm は使えない (gVisor のみ)**。
- **GKE**: no-channel (static) は非推奨で新規顧客は作れず、2027-06-14 に Stable へ強制移行される。
  **1.37 は Rapid チャネルにだけある**。1.37 なら Substrate に必要な beta API が既定で有効になり、
  「作成時に beta API を有効化し損ねたら作り直し」の罠が消える。ノードのアップグレードは node pool の
  maintenance exclusion (`NO_MINOR_OR_NODE_UPGRADES`、minor の EOS まで) で止められる。auto-repair は node pool 単位で無効化できる。
  node pool には実行時の台数変更を無視する専用フィールド `ignore_node_count_changes` がある。
- **Artifact Registry の cleanup policy**: KEEP と DELETE の両方に当たるものは KEEP が勝つ。`most_recent_versions` は保護するだけで
  何も消さない (floor であって cap ではない)。**条件付き KEEP と「最新 N 版」を 1 つの policy に混ぜられない**。`tag_prefixes` は
  `tag_state = "TAGGED"` と組にする。dry-run は repository 単位の `cleanup_policy_dry_run`。適用は約 1 日遅れ。
- **Persistent Disk**: pd-standard の性能は容量比例 (10 GiB だと読み 7.5 IOPS / 書き 15 IOPS / 1.2 MiB/s)。pd-balanced は容量によらず
  基礎性能が高い。
- 価格 (Cloud Billing Catalog API、東京、2026-09-26): E2 vCPU $0.0280264/h、E2 RAM $0.00373911/GiB·h、
  Balanced PD $0.13/GiB·月、Standard PD $0.052/GiB·月、GCS Standard $0.023/GiB·月、GKE zonal $0.10/h、
  Cloud NAT IP $0.005/h、JPY 換算はカタログのレート ¥159.375/$。

### private project (値は書かない)

- 権限: 運用者は project の Owner、請求先アカウントの billing.admin。ADC は運用者のユーザー資格情報。
- **GKE 無料枠は空いている** (請求先アカウント配下の全 project で zonal / Autopilot クラスタ 0)。**請求通貨は JPY**。
- 無効な API が多い → 必要な API を列挙して tofu で有効化し、その集合をテストで固定する (Phase 2)。
- 組織ポリシー:
    - デフォルト SA への自動 IAM 付与は無効 → **node / Cloud Build / 各ジョブに専用 SA** を作る
    - 外部 IP は許可リスト方式 → **private nodes + Cloud NAT が必須**
    - OS Login 必須、シリアルポート無効
    - ドメイン制限付き共有あり → Workload Identity の principal 付与が通るかは spike で確認
    - bucket は UBLA + public access prevention が必須
    - リージョン・LB・NAT・VPC peering の制限は無し。`container.*` やカスタム制約も無し
- 同じ project に他の OpenTofu stack とその state bucket が 2 つある → 名前と state prefix は必ず `exe-` 系で分け、既存と被らせない。
- 東京に既存の subnet / router / NAT は無い。新しい VPC を作る (quota に余裕あり)。

## 3. 目標アーキテクチャ

```
 operator Mac (just exe-wake / ax / kubectl)
    |                                   |
    | lease.json write                  | HTTPS + Google IAM (DNS endpoint only)
    v                                   v
 +------------+     +------------- GKE zonal cluster "exe" (Rapid, 1.37) -------------+
 | GCS: ops   |<----| node pool "main": 0..1 x e2-standard-4 on-demand                |
 | lease.json | L1  |   (node count owned by the lease loop, ignored by tofu)         |
 | drain.json |     |   ns ax-system : ax-server | ax-controller | redis (PVC)         |
 | enforce.   |     |   ns ate-system: substrate control plane | atelet | workers x2   |
 |   json     |     |   ns exe-store : postgres (PVC)                                  |
 +------------+     |   ns exe-ops   : exe-reaper CronJob (L1, every minute)           |
    ^               +-----------------------------------------------------------------+
    | L2 reads             ^ setSize(0)          |                        |
 +------------+            |                     v                        v
 | Cloud Run  |------------+               GCS: snapshots      Artifact Registry
 | job        |                                                (platform, task)
 | enforcer   |                                                         ^
 +------------+                                                         |
    ^ every 10 min                                            Cloud Build (task image)
 Cloud Scheduler --- 04:00 JST daily: setSize(0) (L3) ---> GKE API
```

Legend / 凡例:

- operator Mac: 運用者の Mac (唯一の操作元)
- lease.json: 起動期限 (リース)。書くのは運用者だけ
- drain.json: L1 の片付け状況と heartbeat。書くのは L1 だけ
- enforce.json: L2 の判断記録。書くのは L2 だけ
- DNS endpoint only: IAM 認証必須の DNS 形式 API エンドポイントのみ (IP 形式は無効)
- node pool: ノードプール / on-demand: 通常課金 (spot ではない)
- node count owned by the lease loop: ノード台数は自動休眠の仕組みが持ち、tofu は無視する
- substrate control plane: Substrate の制御系 / workers: actor を載せる作業 Pod (gVisor)
- PVC: 永続ボリューム
- exe-reaper CronJob (L1): クラスタ内で丁寧に休眠させるジョブ (毎分)
- Cloud Run job enforcer (L2): クラスタの外からリース切れを強制するジョブ (クラスタの認証情報は使わない)
- Cloud Scheduler (L3): 毎日決まった時刻にノードを 0 にする最後の砦
- snapshots: task の suspend 時スナップショット
- Artifact Registry (platform, task): 基盤用と task 用のイメージ置き場
- Cloud Build: task image を private project 内で build する

図に無い周辺: VPC / subnet / Cloud Router + NAT、Cloud Monitoring のアラート、JPY の billing budget (L4)。

### 3.1 所有境界

| 層 | 所有者 | 仕組み |
|---|---|---|
| GCP 基盤 (API 有効化、VPC、NAT、GKE、node pool の設定、GCS、AR、IAM、Scheduler、Cloud Run job、budget、alert) | 自前 | `tofu/exe-platform` |
| **node pool の台数** | **リース方式の自動休眠** | tofu は `node_count` を書かず、`initial_node_count` は固定の定数、`ignore_node_count_changes = true`。台数を変えるのは `exe-reaper` (wake / enforce) と L3 だけ。IaC ドリフト規約の明示的な例外として spoke に書く |
| Substrate 本体 (ate-system の全オブジェクト、CRD、CA / JWT Secret、image) | 上流 installer | `tofu/exe-cluster` の `terraform_data` → pin した `ate-setup deploy ate-system` (build モード: `KO_DOCKER_REPO` = 自前 AR、`VERSION` = pin) |
| worker image | 上流 installer | `ate-setup publish worker-images` が出力する digest 付き ref を記録し、WorkerPool の `workerImage` に渡す |
| 自前の SandboxConfig (gVisor asset を private project の GCS に mirror、pause image は `gcr.io/gke-release`) | 自前 | `tofu/exe-cluster` |
| Postgres (Substrate store) / AX (server, controller, redis) / WorkerPool / NetworkPolicy / `exe-reaper` CronJob / Gemini Secret | 自前 | `tofu/exe-cluster` (`kubectl_manifest` + `ko_build`) |
| Task image (上流 `Dockerfile.task-runner` ベース + agent CLI) | 自前 | `docker/exe-task.Dockerfile` を `just exe-image` から Cloud Build で build |
| tailnet ACL | 自前 | `tofu/tailnet` (旧 stack から移管) |
| Task / Workspace / Model の実体 | 運用者と agent | `ax apply` (実行時データ。IaC の対象外) |
| 版の pin | 自前 | `exe/versions.json` を各 stack が `jsondecode(file(...))` で読む (plan / apply / test で同じ仕組み) |

境界の原則: 自分が所有するものは宣言的に持つ (tofu plan で drift が見える)。上流が所有するものは上流 installer を版固定で呼ぶ。
実行時にしか決まらないもの (ノード台数、task) は、それを持つ仕組みを 1 つに決めて明文化する。

### 3.2 自動休眠 (リース方式、4 層)

| 層 | どこで動く | 何をするか | 保証 |
|---|---|---|---|
| L0 リース | `just exe-wake [2h]` / `exe-extend` / `exe-sleep` (手元で `exe-reaper` を実行) | 起動には必ず期限が付く。既定 2h、1 回の起動・延長で最大 8h。**期限は 03:00 JST を越えられない** (下の算式)。延長に成功すると、それ以前の `drained` は無効になる。`exe-sleep` は期限を今にして L1 に片付けさせる | 期限なしの起動は作れない |
| L1 丁寧な休眠 | クラスタ内の CronJob `exe-reaper reap` (**毎分**、ノードが起きている間だけ動く) | 条件: 期限切れ、または **Running の task が 30 分連続で 0**、またはリースの読み取り失敗。手順: ① drain.json に `draining` と heartbeat → ② **atenet-router を 0 台にする** (router 経由の自動 resume と `ax ssh` を止める) → ③ AX の `SuspendTask` で Running の task を全部 suspend (AX の状態と実体を一致させる) → ④ Substrate 上で全 actor が SUSPENDED になるまで確認 (その間 heartbeat を更新、上限 30 分) → ⑤ `drained`。上限を超えたら `drain-failed`。期限内に戻ったら router を 1 台に戻す | 状態を失わずに寝かせる |
| L2 期限の強制 | Cloud Scheduler (10 分ごと) → Cloud Run job `exe-reaper enforce` | 期限切れ後の判定: `drained` なら 0 にする / `draining` で heartbeat が 2 回分以内なら待つ / heartbeat が止まった・`drain-failed`・**期限 + 45 分**を過ぎた・リースが **3 回連続**で読めない、のどれかなら強制的に 0 にして通知。1〜2 回の読み取り失敗では何もしない (L1 が片付けに入る) | Mac が閉じていても、クラスタ内が壊れていても止まる |
| L3 日次の強制停止 | Cloud Scheduler (毎日 04:00 JST) → GKE API `setSize(0)` を直接呼ぶ | 判断ロジックなし。正常時は空振りする (下の算式で保証)。**このジョブ自体の失敗は L4 が通知する** | 全部壊れても 24 時間には届かない |
| L4 検知 | Cloud Monitoring + JPY の budget | ① Compute Engine の稼働時間でノードが 9h を超えたら通知 (GKE の監視設定に依存しない) ② Scheduler ジョブ 2 つの失敗を通知 ③ 予算 ¥3,000/月の 50 / 90 / 100% | 抜けた時と、止める仕組みが壊れた時に気づける |

- **期限の上限の算式** (定数と Quint の不変条件は同じ場所から出す): 利用上限時刻 = L3 時刻 04:00 −
  (L1 の周期 1 分 + 片付けの上限 30 分 + L2 の周期 10 分 + 余裕 19 分) = **03:00 JST** (Q21)。
  これで、正常時に L3 が起きている actor を巻き込むことはない。
- 最悪額: ノードが起きている時間は「期限 + 45 分 + L2 の周期 10 分」以内。休眠し忘れは既定リースで ≈ ¥87/回、最大リースで ≈ ¥266/回。
- L2 は GCS と `nodePools.setSize` しか使わない。**クラスタの認証情報に依存しない** (クラスタ側が壊れていても止められる)。
  この性質を崩す変更 (kubectl を使うなど) はしない。
- L1 の追加の仕事 (§3.3): 生きている task が参照する task image に `inuse-` タグを付け、不要になったタグを外す。
  resume されないまま 30 日経った task は削除する (7 日前から `exe-status` で予告、`keep` ラベル付きは対象外、Q15)。
- `ax-job` / `ax-exec` は、リースが `draining` 以降なら新しい task を起こさない。

#### サブコマンド、実行場所、ID、書き込み先

| サブコマンド | 実行場所 | ID | 書き込む対象 |
|---|---|---|---|
| `wake` / `extend` / `sleep` / `status` | 運用者の Mac | 運用者の ADC | `lease.json`、node pool の台数 (wake のみ 1 に) |
| `reap` (L1) | クラスタ内 CronJob | reaper 用の KSA (Workload Identity) | `drain.json`、atenet-router の replicas、AX の suspend、task image のタグ、TTL 切れ task の削除 |
| `enforce` (L2) | Cloud Run job | enforcer 用の SA | `enforce.json`、node pool の台数 (0 のみ) |
| L3 | Cloud Scheduler | scheduler 用の SA | node pool の台数 (0 のみ) |

- 1 つのオブジェクトの書き手は 1 つだけ。読み取り側が組み合わせて判断する。書き込みは GCS の世代条件付き。
- `exe-status` は休眠中でも固まらない: リース、ノード数、各保存先の容量、当月の請求額、Scheduler 2 ジョブの最終結果は GCP API から出す。
  task 数など起きていないと取れない項目は「休眠中」と表示する。

#### formal-methods の対象

L1 / L2 / L3 は「自分で止める・消す」処理で、運用者・ax-controller・atenet router が同時に resume しうる。`exe/spec/lease.qnt` で次をモデル化する。

- 遷移: worker pod の除去 → 60 秒の窓 → CRASHED、運用者の `ax resume`、router 経由の自動 resume、任意の時点でのノード消失、
  lease / drain / enforce の各オブジェクトへの書き込みと読み取り失敗
- 不変条件: 強制でない休眠では worker pod の除去時に起きている actor は無い。L3 は正常時に起きている actor と重ならない (算式)。
  ノードは有界時間内に必ず 0 になる。延長に成功した直後に L2 が止めることはない
- 失敗する instance として残すもの: pool を先に縮める素朴な順序、書き手が 2 つある lease、ax-controller を止めて router を開けたままにする案
- Go 実装の seeded simulation を用意し、`just spec-check` を `just check` に組み込む

### 3.3 保存先の上限 (ちりつも対策)

| 溜まる場所 | 上限 (policy / lifecycle は明示的に列挙) |
|---|---|
| AR `exe-task` (task image) | KEEP#1 `condition { tag_state = "TAGGED", tag_prefixes = ["inuse-"] }` (L1 が付け外し)、KEEP#2 `most_recent_versions { keep_count = 2 }`、DELETE `condition { older_than = 14 日 }` |
| AR `exe-platform` (Substrate / AX / reaper image) | KEEP#1 `most_recent_versions { keep_count = 10 }`、DELETE `condition { older_than = 30 日 }`。untagged の即時削除はしない (稼働中の install が digest で参照しているため) |
| 両 AR 共通 | `cleanup_policy_dry_run = false`。適用は約 1 日遅れるので、`exe-status` は実際の容量を表示する |
| Cloud Build | 既定の無期限 bucket は使わない。source は `exe-build` bucket (7 日で削除)、ログは `CLOUD_LOGGING_ONLY` |
| GCS `exe-snapshots` | Substrate が参照の無い snapshot を GC する。**削除系の lifecycle は付けない** (参照中を消すと resume 不能)。上限は task の寿命 (30 日) |
| GCS `exe-ops` (lease / drain / enforce) | 古い世代は 5 個まで |
| tofu state bucket | 古い世代は 10 個まで |
| PVC | Postgres は pd-balanced 10Gi、Redis は pd-standard 10Gi (Q22、S7 で性能を実測) |
| Cloud Logging | 既定の 30 日保持 (無料枠内) |
| 旧 project の AR / Cloud SQL / 残骸 | 撤去で消える (Phase 7) |

- **CI で強制**: 全 stack の `google_artifact_registry_repository` と `google_storage_bucket` について次を検査する。
    - AR: DELETE policy があり、KEEP policy もある
    - AR: 条件付き KEEP と `most_recent_versions` を 1 つの policy に混ぜていない
    - AR: `cleanup_policy_dry_run = false`
    - bucket: snapshot 以外は削除 lifecycle か世代の上限がある
    - snapshot bucket: 削除 lifecycle が**無い**
    - repository あたりの policy 数が上限内
- **再利用 (Q18)**: ここで得た手順は、全エージェント共通の spoke `docs/agents/gcp-cost-guardrails.md` と
  読み取り専用の監査ツール `just gcp-cost-audit <project>` にまとめる。個人アカウント側への横展開は後続の
  `docs/plan/gcp-cost-guardrails-rollout.md` として残す (実施は今回の移行の後)。

## 4. 置換マッピング (Coder → AX)

| 現行 (Coder) | 移行後 (AX) | 備考 |
|---|---|---|
| `cdr create` + `cdr ssh` (対話ワークスペース) | `just exe-wake` → `ax apply` (Task, `debug: true`) → `ax ssh` | SSH サーバではなく guest process service |
| `cdr-job` (使い捨て 1 コマンド) | `ax-job`: リース確認 → Task 作成 → resume → Ready 待ち → `ax ssh -- cmd` (exit code 伝播) → delete (trap) | AX は command の exit code を返さないので `ax ssh` 経由で実行する |
| `cdr-exec` (常駐ワークスペース再利用) | `ax-exec`: resume → `ax ssh -- cmd` → suspend (既定) | warm resume は snapshot 復元 |
| 同じ VM で複数 project を同時に | **同時に起こせる task は 2 本** (WorkerPool replicas、Q17) | v0.1.0 は 1 actor = 1 worker |
| `cdr-project up/down` / runops 連携 | 切り離し (Q1) | 必要になったら AX Task 前提で別 work unit |
| `cdr-header` / Coder Web UI | 無し (Q4) | CLI のみ |
| Tailscale `tag:agent` | GKE IAM + k8s RBAC (v1 は運用者のみ) | |
| Cloud SQL (Coder DB) | in-cluster Postgres (Substrate) + Redis (AX) | |
| uptime check + alert | 自動休眠の L4 アラート + budget | |
| task 内 docker | 不可 (Q4) | docker 前提の作業は Mac / CI |
| public の devcontainer publish | 退役 (Q11) | devcontainer 自体はローカル / CI 用に残る |

## 5. フェーズ計画 (manager-loop の 10 フェーズ、Q19)

原則: 各フェーズは **[Red] 失敗するテスト → [Green] 最小実装 → [Refactor]**。structural と behavioral は別 commit。
**お金を止める仕組みを、お金がかかり始めるより先に入れる** (L3 と budget は Phase 2、L2 は Phase 3、ノードを長く起こすのは Phase 4 から)。
旧 Coder スタックの撤去は後半 (それまで旧 stack は mothballed のまま巻き戻し先として残す)。
新しい recipe は旧 stack と名前が被らないようにする (`exe-platform-apply` / `exe-cluster-apply` / `exe-e2e` など)。
旧 recipe 名への統一は撤去フェーズで行う。各フェーズの終わりに `just check` を緑にし、ノードを 0 に戻す。

### Phase 1 — 足場: 漏れ止めガードと版の固定 (クラウド操作なし)

- **[Red]** `tests/unit/test_check_forbidden_tokens.py`: 合成トークン (本物は使わない) で次を先に書く。
    - staged の内容や commit message に入っていれば失敗する
    - `*.tfplan` / `*.tfstate*` は staging 自体を拒否する
    - ローカル一覧が無ければ何もせず通る
- **[Green]** `scripts/check_forbidden_tokens.py`、prek の pre-commit と commit-msg、`default_install_hook_types`、`just install-hooks`、
  `just ci` でのブランチ全 commit message の再検査、PR 本文の検査 recipe。
  **[Red]** install された hook の種類に commit-msg が含まれることのテスト。
- `exe/versions.json`: AX `v0.3.1`、Substrate tag `v0.1.0` + SHA、GKE チャネル Rapid + minor 1.37、`ate.dev/substrate-version` の値
  (**node pool のラベルと `VERSION` の唯一の出どころ**)。**[Red]** pin の一貫性テスト (substrate の ref は 1 つだけ、SHA と一致、
  ラベル値が label として有効、両 stack が同じオブジェクトを読む)。
- ツールの pin: `ax` CLI、`ko`、Go (Substrate の build に必須)、Quint。OpenTofu provider の `ko-build/ko` は 0.0.x なので Class 2 (cooldown + changelog)。
- 仕上げ: `just check` 緑。

### Phase 2 — `tofu/exe-platform` と、お金を止める最初の仕組み

- state bucket は bootstrap スクリプトで作る (UBLA、PAP、versioning、古い世代 10 個)。新 stack ごとの `.gitignore`。
- **[Red]** `tofu/exe-platform/tests/*.tofutest.hcl` (plan + `mock_provider`、import ブロックは置かない) で不変条件を先に書く:
    - クラスタ: zonal、Rapid、1.37 系、Workload Identity、Dataplane V2、private nodes、IP endpoint 無効 + DNS endpoint 有効、HTTP LB addon 無効、Managed OTel / GMP 無効
    - node pool: on-demand、auto_repair 無効、maintenance exclusion `NO_MINOR_OR_NODE_UPGRADES` とメンテナンス時間帯 04:00〜08:00 JST、
    `node_count` を書かない、`initial_node_count` は定数、`ignore_node_count_changes = true`、ラベル値は pin 由来
    - 有効化する API の集合が列挙リストと一致する (run / cloudscheduler / monitoring / logging / compute / iam / iamcredentials / sts / storage / container / artifactregistry / cloudbuild / secretmanager / billingbudgets / cloudresourcemanager ほか、実装時に確定させて固定)
    - L3 の node pool 名と `setSize` の URI が node pool リソースと同じ値から作られている
    - NAT あり、bucket は UBLA + PAP + soft delete 0、§3.3 の上限
    - あわせて repo 全体の保存先上限テストを置く
- **[Green]**: API 有効化、VPC / subnet / Cloud Router + NAT、専用 SA (node、Cloud Build、reaper の Workload Identity、
  enforcer、Scheduler) と最小権限、GKE と node pool (e2-standard-4、boot disk は spike の実測まで 50GB)、
  bucket (`exe-snapshots`、`exe-ops`、`exe-build`)、AR (`exe-platform`、`exe-task`) と cleanup policy、
  Substrate の Workload Identity principal への権限 (上流が列挙する 6 種。project 番号で組み立てる。どれを絞るかも明記する)、
  **L3 (毎日 04:00 JST の `setSize(0)`)、Scheduler 失敗のアラート、ノード稼働時間のアラート、JPY の budget**。
- apply (新規 stack なので Q6 により implementer が実行)。作成直後にノードが残る場合は、L3 のジョブを手動実行して 0 にする
  (これで L3 が実際に効くことも確認できる)。`just exe-ctx` で DNS endpoint の kubeconfig を作り、IAM だけで繋がることを確認。
- この時点で自動で止める仕組みは L3 だけ。止め忘れの保険は人間しかいないことを、フェーズの閉じる時に確認する。
- 仕上げ: 2 回目の `tofu plan` が差分なし、ノード 0、テスト緑。

### Phase 3 — 自動休眠の本体 (L0 / L2) をノードを長く起こす前に入れる

- `tools/exe-reaper/` (Go 1.27、stdlib 優先、golangci-lint v2 + gofumpt、テストは同じ場所): `wake` / `extend` / `sleep` / `enforce` / `status`。
- **[Red]** Go の判定表テスト:
    - 期限: 最大 8h、03:00 JST を越えない
    - L2 の三分岐: drained / heartbeat あり / 強制
    - 読み取り失敗: 3 回連続で初めて強制、1 回目は何もしない
    - 延長に成功すると以前の `drained` が無効になる
    - 無操作の判定: Running の task が 30 分連続で 0 の時だけ
- **[Red]** `exe/spec/lease.qnt` (L0 / L2 / L3 と、書き手 2 つの lease を失敗する instance として) と、Go 実装の seeded simulation。
  `just spec-check` を `just check` に配線。
- **[Green]** 実装。Cloud Run job と Scheduler (10 分ごと) を `tofu/exe-platform` に追加 (image は ko_build)。
- **e2e (mock なし)**:
    - `just exe-wake 5m` から何もしなければ、上限時間内にノードが 0 になる
    - `lease.json` を消しても、3 回分の後に 0 になる
    - `exe-status` が休眠中にも固まらない
- 仕上げ: e2e 緑、ノード 0。

### Phase 4 — Substrate + AX のインストール (spike 前半)

- `tofu/exe-cluster`: Postgres (pd-balanced 10Gi、上流と同じ digest の `postgres:18-alpine`) → `terraform_data` で
  `ate-setup deploy ate-system` (build モード、`KO_DOCKER_REPO` = `exe-platform`、`VERSION` と DSN は env で渡す、DSN は sensitive) →
  `ate-setup publish worker-images` の出力から gVisor worker の digest 付き ref を記録 (**[Red]** `@sha256:` を含むこと) →
  自前の SandboxConfig → AX (`ko_build`、自前の `.ko.yaml` でベース image を digest 固定、`ax-server` の build 定義も明示) →
  Redis (StatefulSet、AOF、`requirepass`、pd-standard 10Gi) → atespace `exe` と同名 namespace に WorkerPool
  (replicas 2、`workerImage` は記録した digest、limits で cpu と memory を必ず指定) → NetworkPolicy (redis と postgres だけを守る) → Gemini Secret。
- WorkerPool の変更は serving 中の actor を殺すので、tofu 側に「起きている actor がいたら apply を止める」前提条件を入れる。
  変更は「新しい pool を作って切り替える」手順を runbook に書く。
- spike (全て実機、mock なし):

| # | 検証 | 合格条件 |
|---|---|---|
| S1 | 互換 | AX v0.3.1 + Substrate v0.1.0 + GKE 1.37 で Task が `Running` / `Ready=True` |
| S2 | ssh | `ax ssh <task> -- echo ok` が exit 0 で `ok` |
| S3 | 永続 | `/workspace` のファイルが suspend → resume 後も残り、**snapshot object が GCS に実際に書かれている** |
| S10 | 組織ポリシー | Workload Identity principal への権限付与が通る (ドメイン制限付き共有との相性) |
| S11 | OTel | Managed OTel 無しで install が完走する (駄目なら有効化し、費用を再見積もり) |

- 失敗時の回復経路 (仮説を変えて再試行する):
    - S1 失敗 → 1.37 の API 差 (PodCertificateRequest v1 化など) を確認 → Rapid の 1.36 + beta API 有効化で再作成 → それでも駄目なら運用者に判断を仰ぐ
    - S10 失敗 → GSA 経由の Workload Identity に切り替え、それも不可なら運用者に判断を仰ぐ
- 仕上げ: S1 / S2 / S3 / S10 / S11 緑、ノード 0。

### Phase 5 — task image と spike 後半

- Cloud Build の既定 pool が外部 IP の組織ポリシーに引っかからないことを確認 (駄目なら private pool か手元 build に切り替える)。
- `docker/exe-task.Dockerfile` (上流 `Dockerfile.task-runner` ベース + Claude Code などの agent CLI + `ax-task-runner` v0.3.1、linux/amd64)、
  `exe/ax/cloudbuild.yaml` (専用 SA、`exe-build` bucket、`CLOUD_LOGGING_ONLY`)、`just exe-image`。**[Red]** amd64 と digest 固定の assert。

| # | 検証 | 合格条件 |
|---|---|---|
| S4 | egress | task 内から `git ls-remote` と model API への HTTPS が通る |
| S5 | 隔離 | task 内から redis / postgres / ax-server に繋がらない。**NetworkPolicy 適用後も `ax get tasks` が port-forward で通る** |
| S7 | 容量 | CPU / メモリ / **ephemeral-storage** の実測で、基盤一式 + worker 2 が e2-standard-4 と boot disk に収まる。Postgres が 60 秒以内に Ready、Redis の AOF で遅延が出ない |
| S8 | image | task image で `claude --version` / `node -v` / `git` が gVisor 下で動く |
| S9 | 資格情報 | Q20 の方式で Claude が認証できる。対話ログインは suspend / resume 後も残る |

- S7 不足 → worker を 1 に減らすか e2-standard-8 にし、費用差を出して判断を仰ぐ。Redis が遅ければ pd-balanced に上げる。
- 仕上げ: S4 / S5 / S7 / S8 / S9 緑、ノード 0。

### Phase 6 — L1 (丁寧な休眠)、保存先の上限、ラッパー

- **[Red]** Quint モデルに L1 と競合を足し、§3.2 の失敗する instance を固定する:
    - 競合: 運用者の `ax resume`、router 経由の自動 resume、任意時点のノード消失、60 秒の窓
    - 失敗する instance: 素朴な順序、ax-controller を止めて router を開けたままにする案
    - Go の seeded simulation も拡張する
- `exe-reaper reap` (CronJob、毎分、専用 KSA、AX gRPC と Substrate API のクライアント): §3.2 の手順どおりに実装する。
  heartbeat、`drain-failed`、期限内に戻った時の router の復帰。`inuse-` タグの付け外し、task の寿命 (30 日、予告、`keep`)。
- `exe/scripts/ax-job` / `ax-exec` (bash): **[Red]** stub の `ax` を PATH 先頭に置く pytest で次を先に書く。
    - exit code の伝播
    - 失敗時も delete (`KEEP_ON_FAILURE` で保持)
    - `spec.image` 必須、タイムアウト
    - リース残りが足りなければ拒否、`draining` 以降は拒否
    - Q20 の資格情報の渡し方
- e2e (`tests/e2e/exe/`、mock なし、`EXE_E2E=1` の時だけ、`just exe-e2e`):
    - S6: 起きている task がある状態でリースを切らす → L1 が suspend → L2 がノードを 0 に → wake 後の resume で S3 のファイルが残る
    - 強制経路: L1 を止めた状態でリースを切らす → L2 が上限内に強制し、通知が出る
    - 片付け中の `ax resume`: 片付けの途中で resume を投げても、最終的にノードは 0、actor は SUSPENDED
- 仕上げ: 上記 e2e 緑、`just spec-check` 緑、保存先の上限テスト緑、ノード 0。

### Phase 7 — 旧 Coder スタックと tailnet の後始末 (破壊操作は運用者が実行)

1. 旧 project の棚卸し (運用者が旧 project のオーナー ID でログインし、読み取りコマンドを実行): Coder が作った VM / disk の残骸。
2. `tofu/tailnet` を新設: `tailscale_acl` を `import` し、exe 系タグと規則を消した ACL を saved plan → 運用者が apply。
   旧 stack 側は `removed { lifecycle { destroy = false } }` を**先に apply してから**、`exe/tailscale/acl.hujson` を動かす (`file()` 参照があるため)。
3. Cloud SQL: 30 日保持のコピー (export か final backup の安い方) → deletion protection 解除 → 削除 (Q3)。
4. 旧 `tofu/exe` を丸ごと destroy する saved plan を作る → 運用者が旧 project の ID で apply。
   Cloudflare の Tunnel / Access / DNS (`exe.hironow.dev`、`*.sandbox`) と Tailscale の auth key もここで消える。
5. GitHub の repo variables (`GCP_WIF_PROVIDER`、`GCP_PUBLISH_SA`) の削除 (運用者)。
6. repo から削除・更新する対象:
   - ディレクトリ: `exe/coder/`、`exe/cloudflared/`、`exe/tailscale/`
   - 旧 `exe/scripts/*`: cdr 系、bootstrap / smoke / teardown / project-* / fetch-projects-env
   - テスト: `tests/exe/`、`tests/test_cdr_wrapper.py`、`tests/test_vm_bootstrap.py`、`tests/test_actor_type_injection.py`、
     `tests/test_mise_data_dir_relocation.py` の Coder 参照、`tests/test_publish_workflow.py`、`tests/test_justfile_env_checks.py` の CF/TS 部分、
     `tests/unit/test_exe_stack_mode.py`、`tests/docker/ExeStartup.Dockerfile`、`tests/README.md` の索引
   - CI と hook: `.github/workflows/publish-devcontainer.yaml`、`iac-test.yaml` の Coder job、`.pre-commit-config.yaml` の Coder hook
   - 設定: `pyproject.toml` の `exe` marker、justfile の旧 `exe-*` / `test-iac` の Coder 部分 (新 recipe の名前もここで整理)、`config/mise/config.toml` のコメント
   - 運用者の端末: `~/.local/bin` の cdr symlink (`just` に掃除 recipe を用意)

- **[Red]** 列挙に頼らない汎用テスト: `docs/adr/` と `docs/plan/` 以外に `cdr` / `coder` / `cloudflare` / `exe.hironow.dev` / 旧 stack 固有名が
  残っていたら失敗する。
- commit 例: `feat(exe)!: remove coder control plane and cdr wrappers` (footer `BREAKING CHANGE: cdr commands are gone; use ax / ax-job / ax-exec`)
- 仕上げ: 残骸テスト緑、旧 project の棚卸し結果 (運用者提供) に exe の資源が無い。

### Phase 8 — ドキュメント、ADR、グローバル規約

- ADR **0045** `replace-coder-exe-with-google-ax` (基盤選定、所有境界、版 pin、公開面ゼロ、private project の扱い、資格情報の経路と影響範囲)。
- ADR **0046** `exe-lease-auto-sleep-and-storage-bounds` (自動休眠の 4 層、期限の算式、ノード台数の実行時所有、保存先の上限、Quint)。
- 旧 ADR の status 更新 (この repo の慣習どおり本文と `docs/adr/README.md` の表の両方): 0002 / 0004 / 0007 / 0008 / 0009 / 0010 /
  0011 / 0012 / 0013 / 0034 を、全部または一部 Superseded に。
- `exe/README.md`、`exe/docs/{architecture,runbook,usage}.md`、各 stack の README、root `README.md`、`install.sh` のコメントを現状の記述に。
- グローバル規約 (ROOT_* を編集して `just sync-agents all`):
    - `ROOT_AGENTS.md` の「Coder VMs」
    - spoke `iac-drift-policy`: `cdr` の記述を消し、ノード台数を実行時の仕組みが持つ例外を追記
    - spoke `enforcement`
    - hook `block-prohibited-commands.py`: `cdr workspaces update|edit` を、exe の namespace (`ax-system|ate-system|exe-store|exe-ops`) に対する
    `kubectl edit|patch|scale|set` と、exe の node pool への `gcloud container clusters resize` に置き換え
    (**[Red]** `tests/unit/test_agent_hooks.py` を先に)
- `docs/handover.md` 更新 (ローカル)。
- 仕上げ: 残骸テスト緑、docs に古い参照が無い、spoke 配布済み。

### Phase 9 — 再利用できるちりつも対策 (Q18)

- spoke `ROOT_AGENTS_docs_agents_gcp-cost-guardrails.md` + ROOT_AGENTS のトリガー表に 1 行
  (「GCP の保存先・build・無人で動く compute を作る / 触る時」)。中身:
    - 原則: 溜まるものには上限を、無人で動くものには自動で止まる仕組みを
    - AR cleanup policy の意味論と落とし穴 (KEEP が勝つ、`most_recent_versions` は floor、条件付き KEEP と混ぜられない、`tag_state` と組、dry-run は repo 単位、約 1 日遅れ)
    - bucket lifecycle、Cloud Build の既定 bucket、state bucket の世代、snapshot の寿命
    - 自動休眠のリース方式 (期限の算式、書き手 1 つ、heartbeat と上限、判断ロジックの無い最後の砦とその失敗検知)
    - 読み取り専用の監査手順と、直すのは IaC 経由で行うこと
- **[Red]** 単体テスト → `scripts/gcp_cost_audit.py` + `just gcp-cost-audit <project>` (読み取り専用)。列挙するもの:
    - 上限の無い AR repo、dry-run のままの cleanup policy
    - lifecycle の無い bucket、Cloud Build の既定 bucket
    - 停止中でも課金される disk / IP / SQL
    - budget の有無、GKE クラスタとノードプールの台数、Scheduler ジョブの最終結果
    - ID は引数で渡し、repo に書かない
- `docs/plan/gcp-cost-guardrails-rollout.md`: 個人アカウント側の project への横展開 (手順、完了条件、IaC 化の方針)。実施は今回の後。
- 仕上げ: 監査ツールが private project に対して読み取り専用で動く (レポートはローカル)、`just sync-agents all` 済み。

### Phase 10 — 検証

- クリーンな checkout から `just check` / `just ci` 緑。
- 実機: `just exe-e2e` 緑 (S1〜S6、強制経路、片付け中の resume)、L3 の最終実行が成功、アラートと budget が有効。
- 漏れ止め: ブランチの全 commit message と全差分に禁止トークン 0 件。public な workflow が private project に触れていない。
- 再現性: 前提知識ゼロの subagent に spoke と監査ツールだけを渡し、private project の監査レポートを作らせる (レポートはローカル)。
- 公開面ゼロの実機確認 (IP endpoint 無効、private nodes、LB / NodePort / Ingress 無し)。
- PR 本文を検査してから draft → ready にして CI 全緑。`manager-loop/OUTCOME.md` を書く (ローカル)。

## 6. コスト見積り (東京、カタログ定価、2026-09-26)

### 単価

| 項目 | USD | JPY | いつ課金されるか |
|---|---|---|---|
| e2-standard-4 (4 vCPU / 16 GiB) | $0.1719/h | ¥27.4/h | ノードが起きている時だけ |
| boot disk 50 GiB (pd-balanced) | $0.0089/h | ¥1.4/h | 同上 |
| Cloud NAT (VM 1 台 $0.0014/h + IP $0.005/h) | $0.0064/h | ¥1.0/h | 起きている時 (IP の休眠中の扱いは spike で実測) |
| GKE 管理費 (zonal) | $0.10/h | ¥15.9/h | クラスタが存在する限り。**無料枠で相殺 (確認済み)** |
| PVC: Postgres 10 GiB pd-balanced + Redis 10 GiB pd-standard | $1.82/月 | ¥290/月 | 常時 |
| GCS snapshot (Standard) | $0.023/GiB·月 | ¥3.7/GiB·月 | 常時 (task の寿命 30 日で上限) |
| AR (無料枠 0.5 GB 超) | ≈ $0.10/GiB·月 | ≈ ¥16/GiB·月 | 常時 (§3.3 で上限) |
| Cloud Scheduler 2 ジョブ / Cloud Run job / Cloud Build | ほぼ $0 | ほぼ ¥0 | 無料枠内の見込み |

### 月額

| 使い方 | 月額 |
|---|---|
| 休眠のみ | **≈ ¥450** (¥380〜630) |
| 月 20 時間 | ≈ ¥1,050 |
| 月 40 時間 | ≈ ¥1,650 |
| 月 80 時間 | ≈ ¥2,850 (予算アラートの 90% 付近) |
| 休眠し忘れ | 1 回あたり既定 ≈ ¥87、最悪 ≈ ¥266 (24 時間つけっぱなしは起きない) |

- PVC を両方 pd-balanced にすると休眠中 ≈ ¥570、両方 pd-standard だと ≈ ¥320 (ただし Postgres が遅すぎる恐れ、Q22)。
- 移行作業中 (Phase 2〜6) はクラスタが 20〜40 時間起きて ≈ ¥600〜1,200 の見込み。
- 旧スタックの撤去で、旧 project の維持費 (推定 ¥500〜1,500/月、要確認) が消える。
- 同時 3 本以上が要る場合は e2-standard-8 (≈ ¥57/h) か 2 台目 (Q17)。

## 7. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| 上流 pre-1.0 の breaking change | 版上げで壊れる | 版を 1 ファイルで pin。Class 2 扱い。版上げは「全 task を suspend → 上げる → `just exe-e2e`」の全停止手順 (ノード 1 台なのでローリングは無い) |
| AX v0.3.1 と Substrate v0.1.0 / GKE 1.37 の互換 | 起動しない | S1 と回復経路 |
| 起きている actor を残したままの worker 除去 (休眠、WorkerPool 編集、eviction) | CRASHED (終端) | L1 の手順を Quint で検証、期限の算式、heartbeat と上限、WorkerPool の apply を止める前提条件、limits の必須化、disk の実測 (S7) |
| 休眠し忘れ | 課金継続 | 4 層の自動休眠 (§3.2)。L3 は判断ロジックなしで毎日止め、その失敗も通知する |
| 止める仕組みが黙って壊れる | 24 時間保証の喪失 | Scheduler 失敗のアラート、`exe-status` に最終結果、L3 の URI と node pool 名を同じ値から作るテスト |
| 保存先の肥大 | じわじわ課金 | §3.3 の上限と CI の強制、`exe-status` での見える化 |
| AX の Redis が揮発 | Task 記録の全消失 | StatefulSet + PVC + AOF + requirepass |
| 同梱 Postgres のサイズ罠 / 遅い disk | ノード逼迫と PD 費 / control plane の不調 | 外部 DSN で自前の Postgres、pd-balanced、S7 で性能を実測 |
| Claude の資格情報 | 漏洩時の影響範囲 | Q20 の方式。`Task.spec.env` を使う場合は Redis の PVC、Postgres の PVC、ActorTemplate、`ax get task` の出力に平文で残ることを ADR に明記 |
| gVisor asset が nightly の URL | 休眠明けに取得できない | private project の GCS に mirror した自前の SandboxConfig |
| ドメイン制限付き共有 | Workload Identity の付与が通らず snapshot が 403 | S10、GSA 経由への切り替え |
| private project の識別子の漏洩 | 組織所属の露出 | §1.1 のガード (commit-msg を実際に install、バイナリ拒否、ブランチ全体の再検査、PR 本文の検査)、public CI を使わない |
| 旧 tailnet ACL の誤 destroy | tailnet 全体の ACL 破壊 | `removed { destroy = false }` → `tofu/tailnet` へ import |
| Coder 管理外リソースの取り残し | 課金継続 | Phase 7 の棚卸し |
| DNS endpoint はインターネットから到達可能 | IAM が唯一の防壁 | 運用者以外に `container.*` を付与しない |
| 同時実行は 2 本まで | 並列作業の制約 | 必要になったら機種か台数を上げる (Q17) |

## 8. 決定事項 (grilling、全て運用者が承認)

| # | 論点 | 決定 |
|---|---|---|
| Q1 | runops / phonewave 連携 (ADR 0011 / 0012 / 0013) | 今回は切り離す。3 本とも新 ADR で Superseded。必要になったら AX Task 前提で別 work unit |
| Q2 | ノードの課金形態 | on-demand (spot / preemptible は使わない) |
| Q3 | 旧 Coder DB (Cloud SQL) | 30 日間コピーを保持してから削除 |
| Q4 | IDE 接続 | v1 は `ax ssh` と `ax-job` / `ax-exec` のみ。task 内 docker は使えない前提 |
| Q5 | タスク内エージェントの認証 | Claude は長期 OAuth トークンを private project の Secret Manager に置き、渡し方は Q20。Gemini は k8s Secret |
| Q6 | 無人実行で任せる範囲 | 新規 stack への apply は implementer (フェーズ末に必ずノード 0)。既存リソースの削除・置換は saved plan まで作り、実行は運用者。gcloud での手動変更はしない。merge は運用者 |
| Q7 | state と名前 | 新 stack を private project に新 state で作る。旧 `tofu/exe` は撤去まで無傷で残し最後に丸ごと destroy。名前は `exe` 継続、`exe.hironow.dev` は廃止 |
| Q8 | tailnet ACL | ACL 専用の `tofu/tailnet` に移管。exe 系タグと規則は削除、owner / break-glass / steiner は維持 |
| Q9 | 予算とスペック | 予算 月 ¥3,000 の 50 / 90 / 100% (JPY、自動停止なし、値は tfvars のみ)。東京。e2-standard-4 から開始 |
| Q10 | 実行の予算と停止条件 | 実時間 12 時間 (チェックポイント、Q19)。stall 閾値 45 分。implementer の再生成は無確認で可。フェーズ上限は Q19 |
| Q11 | task image | 上流 `Dockerfile.task-runner` ベース + agent CLI。ツールチェーンは Workspace `goal` 任せ。build は private project の Cloud Build。public の devcontainer publish は退役 |
| Q12 | 既存の露出 | 今回はガードだけ。掃除は別 work unit |
| Q13 | 自動休眠の数値 | 既定リース 2h、最大 8h、task が 30 分動いていなければ休眠、日次の強制停止 04:00 JST、L2 の猶予 20 分。**利用上限時刻は Q21、猶予の扱いはレビュー #2 で精緻化** |
| Q14 | L1 が失敗した時 | 強制停止を優先 (コストの上限を守る)。発生時は通知。**レビュー #2 により、heartbeat がある健全な片付けは期限 + 45 分まで待つ形に精緻化** |
| Q15 | task の寿命 | resume されないまま 30 日で自動削除。7 日前から予告、`keep` ラベルは対象外 |
| Q16 | GKE のバージョン方針 | Rapid チャネル + 1.37 系。node pool の maintenance exclusion でアップグレードを止め、メンテナンス時間帯は 04:00〜08:00 JST |
| Q17 | 同時実行数 | 2 本 (e2-standard-4、1 本あたりメモリ 4GiB 前後、spike で調整) |
| Q18 | ちりつも対策の再利用 | 全エージェント共通 spoke + 読み取り専用の監査ツール + 後続計画を今回の run で作る (Phase 9)。前提知識ゼロの subagent で再現を検証 |
| Q19 | 実行の予算 | フェーズ上限は 10。12 時間は止まって中間報告するチェックポイント (続行は `/goal` の打ち直し) |
| Q20 | Claude の資格情報の渡し方 | 実行のたびに `ax-job` が Secret Manager から取り出し、`ax ssh` のコマンド引数で渡す。クラスタの DB と snapshot には残さない。task の起動コマンド自体をエージェントにする場合は対話ログイン |
| Q21 | 夜の利用上限時刻 | 03:00 JST (L3 は 04:00 のまま、算式は §3.2) |
| Q22 | PVC の disk 種別 | Postgres は pd-balanced、Redis は pd-standard (S7 で実測し、遅ければ pd-balanced に上げる) |

## 9. 完了条件 (Definition of Done)

1. 空の状態から just recipe だけで `exe-platform-apply` → `exe-wake` → `exe-cluster-apply` → `just exe-e2e` (S1〜S6) が緑。
2. 自動休眠:
   - L1 経由の休眠で状態が保持される
   - L1 を止めても L2 が上限内に強制する
   - 片付け中の resume でも最終的にノードは 0
   - L3 の最終実行が成功し、その失敗アラートがある
   - ノード稼働時間のアラートと JPY の budget が有効
3. 保存先の上限テストが緑 (§3.3 の全項目)。
4. 漏れ止め: pre-commit と commit-msg の hook が実際に install されている。ブランチの全差分と全 commit message に禁止トークン 0 件。
   バイナリの staging は拒否される。PR 本文は検査済み。public な workflow が private project に触れていない。
5. 旧 stack: `tofu/exe` は destroy 済み (運用者が apply)、Coder の残骸なし、Cloud SQL のコピーを 30 日保持、tailnet ACL は `tofu/tailnet` へ移管、残骸テスト緑。
6. 公開面ゼロを実機で確認 (IP endpoint 無効、private nodes、LB / NodePort / Ingress 無し)。
7. ADR 0045 / 0046、docs、グローバル規約を更新し `just sync-agents all` 済み。
8. 再利用できるちりつも対策 (spoke、監査ツール、後続計画) があり、前提知識ゼロの subagent で再現できた。
9. `just check` / `just ci` 緑、PR を ready にして CI 全緑。
10. 移行後 1 週間の実請求が §6 の見積り内。

## 10. レビュー記録

### レビュー #1 (独立 subagent、codex はクレジット切れで使用不可、2026-09-26)

26 件の指摘。検証の上で次のとおり扱う。

| # | 重さ | 要旨 | 扱い | 確認方法 |
|---|---|---|---|---|
| 1 | CRITICAL | v0.1.0 の suspend 猶予は約 60 秒、pool の縮小も actor を殺す | 採用 (§2、§3.2、Quint) | 上流 `tools/setup-gcp/README.md@v0.1.0:102`、`docs/upgrade.md@v0.1.0:56-68` |
| 2 | CRITICAL | no-channel は新規顧客不可・2027-06 に廃止 | 採用 → Rapid + 1.37 (Q16) | GKE release channels の公式ドキュメント |
| 3 | CRITICAL | 旧 stack に同居させると apply できない | 解消済み (Q7 で新 stack) | ADR 0034、justfile |
| 4 | HIGH | import ブロックと mock_provider の panic、`.tofutest.hcl` | 採用 (新 stack は import なし、拡張子を合わせる。tailnet は pytest) | ADR 0034、`.pre-commit-config.yaml` |
| 5 | HIGH | 1 actor = 1 worker | 採用 (Q17、§4) | 上流 `docs/api-guide.md@v0.1.0:66,140` |
| 6 | HIGH | `Task.spec.resources` は無視される | 採用 (WorkerPool の limits 必須) | AX `internal/substrate/client.go@v0.3.1` の `BuildActorTemplate` |
| 7 | HIGH | `workerImage` 必須、namespace の対称性 | 採用 (レビュー #2 の 3 で方式を修正) | 上流 `workerpool_types.go@v0.1.0:86-89`、`api-guide.md:419` |
| 8 | HIGH | boot disk と ephemeral-storage | 採用 (S7) | 実測で確定 |
| 9 | HIGH | WorkerPool の apply が actor を殺す | 採用 (前提条件と切り替え手順) | `docs/upgrade.md@v0.1.0:56` |
| 10 | HIGH | Substrate の pin が 2 系統 | 採用 (tag v0.1.0 に統一) | `compare v0.1.0...672533541dbf` = diverged |
| 11 | HIGH | 撤去の依存漏れ 9 件 | 採用 (列挙 + 汎用の残骸テスト) | Phase 7 で実物確認 |
| 12 | HIGH | Quint の不変条件と敵対者 | 採用 (§3.2) | AX の reconcile ループ、上流 upgrade.md |
| 13 | MEDIUM | バージョンラベルの出どころが 2 つ | 採用 (pin ファイルに 1 本化) | Phase 1 のテスト |
| 14 | MEDIUM | NetworkPolicy と port-forward | 採用 (自前資源だけを守る、S5 で確認) | S5 |
| 15 | MEDIUM | gVisor の nightly asset | 採用 (mirror + 自前 SandboxConfig) | 上流 `sandboxconfig-gvisor.yaml` |
| 16 | MEDIUM | snapshot bucket の削除 lifecycle 禁止 | 採用 (§3.3 のテスト) | — |
| 17 | MEDIUM | IAM 6 種、project 番号 | 採用 (Phase 2、S3、S10) | 上流 `tools/setup-gcp/README.md@v0.1.0` |
| 18 | MEDIUM | budget の前提 | 採用。権限と JPY は事実確認で確認済み | GCP の事実確認 |
| 19 | MEDIUM | kubectl provider の認証と tool pin | 採用 (Phase 1、Phase 2) | — |
| 20 | MEDIUM | ko のベース image が `:latest` | 採用 (自前 `.ko.yaml`) | AX `.ko.yaml@v0.3.1` |
| 21 | MEDIUM | ADR の漏れ (0008 / 0009) と status の書き場所 | 採用 (本文と README 表の両方) | Phase 8 で慣習を確認 |
| 22 | MEDIUM | Managed OTel の要否 | 採用 (S11)。GKE のシステムログは残す | S11 |
| 23 | MEDIUM | ノード 1 台はローリング無し | 採用 (§7 の全停止手順) | `docs/upgrade.md@v0.1.0:97` |
| 24 | LOW | node_count 0 での作成 | 採用 (レビュー #2 の 11 で解消: `initial_node_count` 定数 + L3 の手動実行) | Phase 2 |
| 25 | LOW | E2 は microvm 不可 | 採用 (§2 に明記) | — |
| 26 | LOW | amd64 | 採用 (Cloud Build はネイティブ amd64、テストで assert) | Phase 5 |

レビュー時点の文脈ファイルの誤り 2 件 (suspend 猶予 30 分、既定 snapshot bucket の値) は、上流ソースを優先して修正済み。

### レビュー #2 (同じ subagent に v2 を再レビューさせた、2026-09-26)

23 件の指摘。検証の上で次のとおり扱う。

| # | 重さ | 要旨 | 扱い | 確認方法 |
|---|---|---|---|---|
| 1 | CRITICAL | 04:00 の L3 が正常時にも片付け中の actor を巻き込みうる | 採用。期限の上限を算式で導出 (03:00、Q21)、L1 を毎分に、Quint の性質に | §3.2 の周期と猶予から算出 |
| 2 | CRITICAL | L2 が片付け中のノードを消す | 採用。heartbeat と上限 (期限 + 45 分)、判定表テスト | — |
| 3 | CRITICAL | prebuilt モードでは `workerImage` が得られず、bootstrap もできない | 採用。build モード + `publish worker-images` の ref を記録 | 上流 `cmd/ate-setup/internal/cmd/publish.go@v0.1.0:23-33`、install マニフェストの ko 参照に ateom が無いことを確認 |
| 4 | CRITICAL | resume を止める方式が未定。ax-controller を止めると suspend も止まる | 方式を今決めることは採用。ただし提案の「ax-controller を 0 にする」は却下: router の自動 resume は Substrate 側の機能で ax-controller を経由しない。採用案は「router を 0 → AX 経由で suspend → Substrate で確認」+ 片付け中の resume の e2e | AX `docs/networking.md@v0.3.1` (router は suspend 中の actor を resume してから転送)、AX の controller が suspend も resume も担うこと |
| 5 | HIGH | lease の書き手が 2 つ、読み取り失敗で即強制 | 採用 (書き手 1 つずつ、延長で drained を無効化、3 回連続で初めて強制) | — |
| 6 | HIGH | commit-msg の hook が install されない、plan ファイルは検査できない | 採用 | `justfile:724-725` は `prek install` のみ、設定に commit-msg 無し |
| 7 | HIGH | `exe-platform` の DELETE が稼働中の digest を消しうる | 採用 (keep 10、untagged の即時削除なし) | ate-setup は digest で pin する |
| 8 | HIGH | AR cleanup policy の意味論 | 採用 (policy を明示列挙、テストで検査) | 公式ドキュメント、provider ドキュメント |
| 9 | HIGH | Claude トークンを `Task.spec.env` に置くと平文で残る | 採用 → Q20。v0.3.1 の `ax ssh` は stdin を転送しないため、残らない経路はコマンド引数のみ | AX `cmd/ax/main.go@v0.3.1` の ExecOptions (Command / Stdout / Stderr) |
| 10 | HIGH | pd-standard 10 GiB は Postgres には遅すぎる | 採用 → Q22 (Postgres を pd-balanced) | PD の性能表 |
| 11 | HIGH | `ignore_changes` ではなく `ignore_node_count_changes` | 採用 | provider ドキュメント `container_node_pool.html.markdown:128` |
| 12 | HIGH | L3 の失敗を検知できない | 採用 (Scheduler 失敗のアラート、URI と名前の一致テスト、DoD を「動く」に) | — |
| 13 | HIGH | 8 フェーズでは余裕ゼロ、Phase 4 が大きすぎる | 分割は採用 (Phase 4 / 5)。Q18 を後回しにする提案は却下 (運用者が今回の成果物として明示的に依頼) → Q19 でフェーズ上限を 10 に | 運用者の依頼 |
| 14 | MEDIUM | L3 を Phase 2 へ | 採用 | — |
| 15 | MEDIUM | pin ファイルの読み込み方 | 採用 (`exe/versions.json` + `jsondecode(file())`) | — |
| 16 | MEDIUM | recipe 名とテストの衝突 | 採用 (新名で作り、撤去フェーズで整理) | `justfile:1453,1593`、`tests/unit/test_exe_stack_mode.py:170-171` |
| 17 | MEDIUM | 有効化する API の列挙 | 採用 (列挙してテストで固定) | — |
| 18 | MEDIUM | 新 stack の `.gitignore` と plan 出力の漏れ | 採用 | — |
| 19 | MEDIUM | L4 の metric の出どころ | 採用 (Compute Engine の稼働時間を使う) | — |
| 20 | MEDIUM | 無操作の定義、ID と書き込み先 | 採用 (§3.2 の表) | — |
| 21 | MEDIUM | 休眠中の `exe-status` | 採用 | — |
| 22 | LOW | cleanup policy 数の上限 | 採用 (apply 時とテストで確認) | — |
| 23 | LOW | L2 がクラスタの認証情報に依存しない性質 | 採用 (§3.2 に明記) | — |
