# WSL の Ubuntu を上げるときの runner の手順

WSL の中で self-hosted runner が動く機体では、Ubuntu の版を上げると runner が静かに止まることがある。
systemd のサービスは `active` のままなので、`systemctl is-active` だけでは気づけない。

## 起きること

版を上げると、runner が使う .NET の実行に必要な ICU ライブラリ（`libicuNN`）が外れる。
listener は起動の直後に `Couldn't find a valid ICU package` で落ち、5 秒ごとに再起動を繰り返す。
GitHub 側では runner が offline になる。

## 上げる前

1. 実行中の job が無いことを確かめ、runner のサービスを止める（ADR-0035）。
2. `wsl --shutdown` の後に `wsl --export` で別のドライブへ写す。
   動作中は一貫した写しにならない。
3. 新しい版で運用して問題が出ないと確かめるまで、写しを消さない。

## 上げた後

runner のディレクトリで依存関係を入れ直し、サービスを再起動する。

```bash
sudo bash <runner-dir>/bin/installdependencies.sh
sudo systemctl restart actions.runner.<org>.<name>.service
```

次の三つで確かめる。
`systemctl is-active` だけで済ませない。

- `journalctl -u actions.runner.<org>.<name>.service` に `Connected to GitHub` と `Listening for Jobs` が出る。
- GitHub の runner 一覧で `online` になる。
- 最初の job が `Succeeded` で終わる。
