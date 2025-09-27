# https://just.systems

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# デフォルト: ヘルプを表示
default: help

# ヘルプ: 利用可能なレシピを一覧表示
help:
	@just --list --unsorted


# ------------------------------
# Project Management
# ------------------------------

# インストール: mise でツールをインストール
install:
	# Install tools via mise (versions are managed in mise.toml)
	mise install

# デプロイ: dotfiles をホームに配置（.zshrc の symlink）
deploy:
	@echo "==> Start to deploy dotfiles to home directory."
	ln -sf ~/dotfiles/.zshrc ~/.zshrc

# クリンナップ: 配置した dotfiles を削除（.zshrc）
clean:
	@echo "==> Remove dotfiles in your home directory..."
	rm -vrf ~/.zshrc

# ダンプ: Homebrew のバンドルを dump/ に出力
dump:
	# Dump current brew bundle
	rm -f ./dump/Brewfile && (cd ./dump && brew bundle dump)

# フリーズ: Python 依存を requirements.txt に固定（uv）
freeze:
	# Freeze current python packages using uv
	uv pip freeze | uv pip compile - -o requirements.txt


# ------------------------------
# Tests
# ------------------------------

# テスト: サンドボックスを準備して pytest 実行（詳細表示）
test:
	@echo '🧪 Preparing Docker sandbox (if available)...'
	@if command -v docker >/dev/null 2>&1; then \
		echo '→ docker detected; building sandbox image'; \
		docker build -t dotfiles-just-sandbox:latest -f tests/docker/JustSandbox.Dockerfile . || echo '⚠️ sandbox build failed (tests may skip)'; \
	else \
		echo '⚠️ docker not found; tests may skip'; \
	fi
	@echo '🧪 Running pytest (verbose with skip reasons)...'
	uvx pytest -v -ra tests/test_just_sandbox.py
	@echo '✅ Tests finished.'


# ------------------------------
# Formatting
# ------------------------------

# 整形: ruff の format を uvx で実行
ruff-format path="." opts="":
	@echo '🔧 Formatting with ruff via uvx...'
	uvx ruff format '{{path}}' {{opts}}
	@echo '✅ Formatting done.'

# 静的検査: ruff の check を uvx で実行
ruff-check path="." opts="":
	@echo '🔍 Checking with ruff via uvx...'
	uvx ruff check '{{path}}' {{opts}}
	@echo '✅ Check done.'


# ------------------------------
# Add sets
# ------------------------------

# 追加(一括): gcloud/brew/pnpm のセットを導入
add-all:
	just add-gcloud
	just add-brew
	just add-pnpm-g

# 追加: Homebrew バンドルを導入
add-brew:
	# Install brew bundle
	(cd ./dump && brew bundle)

# 追加: gcloud コンポーネントを導入
add-gcloud:
	# Install gcloud components
	sudo gcloud components install $(awk '{ORS=" "} {print}' ./dump/gcloud)

# 追加: pnpm のグローバルパッケージを導入
add-pnpm-g:
	# Install pnpm global packages
	pnpm add --global $(awk '{ORS=" "} {print}' ./dump/npm-global)


# ------------------------------
# Update sets
# ------------------------------

# 更新(一括): gcloud/brew/pnpm と各種ツールを更新
update-all:
	just update-gcloud
	just update-brew
	just update-pnpm-g
	@echo "◆ mise..."
	mise up
	mise plugins up
	@echo "◆ gh..."
	gh extension upgrade --all
	@echo "◆ tldr..."
	tldr --update
	@echo "◆ gitignore..."
	git ignore --update
	@echo "◆ vscode extensions..."
	code --update-extensions

# 更新: Homebrew を更新・掃除
update-brew:
	@echo "◆ homebrew..."
	brew update && brew upgrade && brew cleanup

# 更新: gcloud コンポーネントを更新
update-gcloud:
	@echo "◆ gcloud..."
	sudo gcloud components update --quiet

# 更新: pnpm のグローバルパッケージを更新
update-pnpm-g:
	@echo "◆ pnpm..."
	pnpm update --global


# ------------------------------
# Check sets
# ------------------------------

# 確認: PATH を1行ずつ表示
check-path:
	# Check PATH
	@echo $${PATH//:/\\n}

# 確認: ローカルIPアドレスを表示
check-myip:
	# Check my ip address
	@ifconfig | sed -En "s/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p"

# 確認: Docker コンテナの公開ポートを一覧
check-dockerport:
	# Check docker port
	@docker ps -q | xargs docker inspect | jq '.[] | {name: .Name, ports: .NetworkSettings.Ports}'

# 確認: Homebrew のインストール済みパッケージ
check-brew:
	brew list

# 確認: gcloud コンポーネント一覧
check-gcloud:
	gcloud components list

# 確認: npm グローバルパッケージ一覧
check-npm-g:
	npm ls --global --depth 0

# 確認: pnpm グローバルパッケージ一覧
check-pnpm-g:
	pnpm list -g --depth=0

# 確認: rustc の cfg を出力
check-rust:
	rustc --print cfg


# ------------------------------
# Validation
# ------------------------------

# 検証: PATH 内の重複コマンドを検出（影響のある順で表示）
validate-path-duplicates:
	#!/usr/bin/env bash
	set -euo pipefail
	echo '🔎 Validating duplicate commands in PATH...'
	IFS=':' read -r -a dirs <<< "$PATH"
	shopt -s nullglob
	lines=()
	i=0
	for dir in "${dirs[@]}"; do
	  [[ -d "$dir" ]] || continue
	  i=$((i+1))
	  for f in "$dir"/*; do
	    [[ -f "$f" && -x "$f" ]] || continue
	    name="$(basename "$f")"
	    lines+=("$name $i $f")
	  done
	done
	shopt -u nullglob
	if (( ${#lines[@]} == 0 )); then
	  echo "✅ No duplicate command names across PATH"
	  exit 0
	fi
	printf '%s\n' "${lines[@]}" | LC_ALL=C sort -k1,1 -k2,2n | awk '
	{
	  name=$1; idx=$2;
	  $1=""; $2="";
	  sub(/^  */,"",$0);
	  if (NR==1) { prev=name; n=0 }
	  if (name!=prev) {
	    if (n>1) {
	      print "command: " prev;
	      for (i=1;i<=n;i++) print "  " rec[i]
	      dup++
	    }
	    n=0; prev=name
	  }
	  n++; rec[n]=idx ":" $0
	}
	END{
	  if (n>1) {
	    print "command: " prev;
	    for (i=1;i<=n;i++) print "  " rec[i]
	    dup++
	  }
	  if (dup>0) {
	    print "⚠️  Found " dup " command(s) shadowed by PATH order"
	    exit 2
	  } else {
	    print "✅ No duplicate command names across PATH"
	  }
	}'


# ------------------------------
# Connect sets
# ------------------------------

# 接続: Cloud SQL (cloud_sql_proxy) へトンネル接続
connect-gcloud-sql:
	# Requires env: GCLOUD_SQL_INSTANCE, LOCAL_SQL_PORT
	[[ -n "${GCLOUD_SQL_INSTANCE:-}" ]] || { echo 'ERROR: environment variable GCLOUD_SQL_INSTANCE not set'; exit 1; }
	[[ -n "${LOCAL_SQL_PORT:-}" ]] || { echo 'ERROR: environment variable LOCAL_SQL_PORT not set'; exit 1; }
	cloud_sql_proxy -instances=${GCLOUD_SQL_INSTANCE}=tcp:${LOCAL_SQL_PORT}

# 接続: Azurite をローカル起動
connect-azurite:
	azurite --silent --location .azurite --debug .azurite/debug.log


# ------------------------------
# Cloud sets
# ------------------------------

# 一覧: gcloud のコンフィグ一覧
gcloud-list:
	gcloud config configurations list

# 一覧: Azure アカウント一覧
azure-list:
	az account list --output table

# 一覧: AWS プロファイル一覧
aws-list:
	aws configure list-profiles

# 一覧: Dataform(BigQuery) テーブル一覧
elt-list:
	dataform listtables bigquery


# ------------------------------
# Version checks
# ------------------------------

# バージョン確認: NVCC のバージョンを検証
check-version-nvcc expected:
	# Usage: just check-version-nvcc <EXPECTED_NVCC_VERSION>
	version=$(nvcc --version | sed -n 's/.*release \([0-9.]*\).*/\1/p' | head -n1); if [ "${version}" != "{{expected}}" ]; then echo "ERROR: Expected NVCC version {{expected}}, but found ${version}"; exit 1; fi

# バージョン確認: PyTorch のバージョンを検証
check-version-torch expected:
	# Usage: just check-version-torch <EXPECTED_TORCH_VERSION>
	version=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || true); if [ -z "${version}" ]; then echo "ERROR: PyTorch is not installed"; exit 1; elif [ "${version}" != "{{expected}}" ]; then echo "ERROR: Expected PyTorch version {{expected}}, but found ${version}"; exit 1; fi


# ------------------------------
# TLS checks
# ------------------------------

# 確認: HTTPS ローカルサーバーを起動（Go）
check-localhost-tls:
	# Serve TLS on localhost using the Go simple-server
	mise x -- sudo go run tools/simple-server/main.go
