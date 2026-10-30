# tools/

開発やテストで使う補助ツール。

- [ca-doctor](../docs/runbook/ca-doctor.md)：CA設定の健全性とレビュー済みのCA事故を診断するGoツール
- [kernel-doctor](../docs/runbook/kernel-doctor.md)：実行中または報告されたLinuxカーネル版を、レビュー済みのCVE修正床と突き合わせるGoツール（判定ではない）
- [rttm](./rttm/README.md)：RTTM ファイルを ELAN（EAF）形式に変換し、可視化する Python のツール
- [simple-server](./simple-server/README.md)：localhost の https を確かめる Go の簡易サーバー
- [tmux](./tmux/CHEATSHEET.md)：tmux のキー操作の早見表

使い方は、各ディレクトリの README かソースコードにある。
リポジトリ全体の構成は [`../README.md`](../README.md) にある。
