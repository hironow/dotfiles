# gcloud の Python 仮想環境の権限を復旧する

Google のインストーラーでユーザーのホーム配下に導入した Cloud SDK が対象。
システムやパッケージマネージャーが管理する SDK、共有設定、native Windows にはこの手順を使わない。

## 対象と所有者を確認する

通常ユーザーのシェルで実行する。
`CLOUDSDK_CONFIG` を指定している場合は、その設定ディレクトリを調べる。

```sh
config_dir="${CLOUDSDK_CONFIG:-"$HOME/.config/gcloud"}"
venv="$config_dir/virtenv"
gcloud info --format='value(installation.sdk_root,config.paths.global_config_dir)'
printf 'config: %s\nvenv: %s\n' "$config_dir" "$venv"
ls -ld "$config_dir" "$venv" "$venv/update_module.log"
```

表示された SDK が自分で管理するインストールであり、設定ディレクトリが `config_dir` と一致することを確認する。
`config_dir` と `venv` の親ディレクトリも確認し、共有先やシンボリックリンクなど想定外の場所を指していたら中断する。
`venv` 自体がシンボリックリンクの場合も中断する。

`virtenv` やその中の `update_module.log` が root 所有で書き込めないと、gcloud の Python 依存更新で `PermissionError` が出る。
Python が起動することや `pip check` が通ることだけでは、更新先の書き込み権限は確認できない。

## 確認した仮想環境だけを修復する

その仮想環境を使う gcloud や pip が動いていないことを確認してから、operator が次を実行する。
`sudo` を付けるのは所有権の修復だけで、gcloud 自体は通常ユーザーで実行する。

```sh
# 上で確認した venv だけが対象。リンク先の Python 本体には適用しない。
test -d "$venv" && test ! -L "$venv" &&
  sudo chown -h -R -P "$(id -u):$(id -g)" "$venv"
```

`-P` はディレクトリのシンボリックリンクをたどらず、`-h` はリンク先ではなくリンク自身の所有権を変更する。
対象をホーム全体、gcloud 設定全体、SDK 本体へ広げない。
設定ディレクトリ内の過去の root 所有ログなど、この仮想環境の外にあるファイルは変更されない。

## 通常ユーザーで更新を確認する

```sh
ls -ld "$venv" "$venv/update_module.log"
"$venv/bin/python3" -m pip check
just update-gcloud
```

エラーが残る場合は、その時点のエラー本文を確認する。
この手順は仮想環境の権限不整合を修復するもので、通信障害や別の依存問題まで解決するものではない。

`just add-gcloud` と `just update-gcloud` は sudo なしで使う。
`just update-all` は gcloud、Homebrew の順に実行し、gcloud が失敗すると Homebrew 以降には進まない。
Homebrew 単体の切り分けには `brew update --verbose` を使う（tap 情報は更新されるが、パッケージの upgrade や cleanup は行わない）。
