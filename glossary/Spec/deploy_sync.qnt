// 配布・同期・スキル配置（scripts/skills_lock.py, scripts/sync_agents.py）の状態機械モデル。
// 2つのエージェントホーム（h1, h2）と、ストア世代（1 -> 2）を扱う。
//
// preFix: 修正前コードの挙動。
//   - skills_lock.py#place は全ループ終了後にのみ _save_state を呼ぶ（PERSIST_PER_ITEM = false）。
//   - sync_agents.py#sync_mode は hook_session.apply_home より前に指示ファイルを書き込む（STAGE_HOOK_BEFORE_FILES = false）。
// codeAsIs: 修正後の現行コードの挙動。
//   - _swap_in ごとに .skills-lock-state.json を原子的リネームで永続化する（PERSIST_PER_ITEM = true）。
//   - hook_session.apply_home を先に実行し、停止時は指示ファイルも削除も書き込まない（STAGE_HOOK_BEFORE_FILES = true）。
module deploy_sync {
  const PERSIST_PER_ITEM: bool
  const STAGE_HOOK_BEFORE_FILES: bool

  pure val Homes = Set("h1", "h2")

  var stopped: bool                 // 配布・同期の中断（SyncStopped / 途中終了）
  var storeVer: int                 // ~/.agents/skills の世代（1 または 2）
  var placedVer: str -> int         // 各ホームにコピー配置された世代（0 = 未配置, 1, 2）
  var recordedVer: str -> int       // .skills-lock-state.json に永続化された世代（0 = 未記録, 1, 2）
  var inMemVer: str -> int          // place() ループ中のメモリ上の state（未永続化）
  var keptOrphan: Set[str]          // 未記録コピーのため更新拒否（kept）となったホーム
  var fileVer: str -> int           // 各ホームの指示ファイル世代（1 または 2）
  var hookVer: str -> int           // 各ホームのフック登録世代（1 または 2）

  action init = all {
    stopped' = false,
    storeVer' = 1,
    placedVer' = Homes.mapBy(_ => 0),
    recordedVer' = Homes.mapBy(_ => 0),
    inMemVer' = Homes.mapBy(_ => 0),
    keptOrphan' = Set(),
    fileVer' = Homes.mapBy(_ => 1),
    hookVer' = Homes.mapBy(_ => 1),
  }

  // scripts/skills_lock.py#place（コピーモード初回配置）:
  // _swap_in でホームへコピーを書き込む。PERSIST_PER_ITEM = true（修正後の現行コード）では
  // 直後に _save_state でディスクへ永続化する。
  action placeCopy(h: str): bool = all {
    not(stopped),
    placedVer.get(h) == 0,
    placedVer' = placedVer.set(h, storeVer),
    inMemVer' = inMemVer.set(h, storeVer),
    recordedVer' = if (PERSIST_PER_ITEM) recordedVer.set(h, storeVer) else recordedVer,
    stopped' = stopped, storeVer' = storeVer, keptOrphan' = keptOrphan,
    fileVer' = fileVer, hookVer' = hookVer,
  }

  // 修正前コードのループ末尾 _save_state(skills_dir, state)
  action finishPlace = all {
    not(stopped),
    inMemVer != recordedVer,
    recordedVer' = inMemVer,
    stopped' = stopped, storeVer' = storeVer, placedVer' = placedVer,
    inMemVer' = inMemVer, keptOrphan' = keptOrphan,
    fileVer' = fileVer, hookVer' = hookVer,
  }

  // 外部確認（bunx skills update）: システム外でストアが世代 1 -> 2 へ進む。
  action storeUpdates = all {
    storeVer == 1,
    storeVer' = 2,
    stopped' = stopped, placedVer' = placedVer, recordedVer' = recordedVer,
    inMemVer' = inMemVer, keptOrphan' = keptOrphan,
    fileVer' = fileVer, hookVer' = hookVer,
  }

  // 次回の scripts/skills_lock.py#place 再実行:
  // recordedVer == placedVer（own_copy）なら更新する。未記録なら kept に分類し更新を止める。
  action rePlace(h: str): bool = all {
    not(stopped),
    placedVer.get(h) != 0,
    placedVer.get(h) != storeVer,
    not(h.in(keptOrphan)),
    placedVer' = if (recordedVer.get(h) == placedVer.get(h)) placedVer.set(h, storeVer) else placedVer,
    inMemVer' = if (recordedVer.get(h) == placedVer.get(h)) inMemVer.set(h, storeVer) else inMemVer,
    recordedVer' = if (recordedVer.get(h) == placedVer.get(h) and PERSIST_PER_ITEM) recordedVer.set(h, storeVer) else recordedVer,
    keptOrphan' = if (recordedVer.get(h) != placedVer.get(h)) keptOrphan.union(Set(h)) else keptOrphan,
    stopped' = stopped, storeVer' = storeVer,
    fileVer' = fileVer, hookVer' = hookVer,
  }

  // 修正前コードのファイル先行書き込み（STAGE_HOOK_BEFORE_FILES = false のみ有効）
  action syncWriteFiles(h: str): bool = all {
    not(stopped),
    not(STAGE_HOOK_BEFORE_FILES),
    fileVer.get(h) == 1,
    fileVer' = fileVer.set(h, 2),
    stopped' = stopped, storeVer' = storeVer, placedVer' = placedVer,
    recordedVer' = recordedVer, inMemVer' = inMemVer, keptOrphan' = keptOrphan,
    hookVer' = hookVer,
  }

  // scripts/sync_agents.py#sync_mode のホーム処理:
  // 修正後の現行コード（STAGE_HOOK_BEFORE_FILES = true）では apply_home が先に実行され、
  // committed の場合のみ指示ファイルへ進むためホーム内で世代が分裂しない。
  action syncApplyHome(h: str): bool = all {
    not(stopped),
    hookVer.get(h) == 1,
    (STAGE_HOOK_BEFORE_FILES or fileVer.get(h) == 2),
    hookVer' = hookVer.set(h, 2),
    fileVer' = if (STAGE_HOOK_BEFORE_FILES) fileVer.set(h, 2) else fileVer,
    stopped' = stopped, storeVer' = storeVer, placedVer' = placedVer,
    recordedVer' = recordedVer, inMemVer' = inMemVer, keptOrphan' = keptOrphan,
  }

  // 配布中断（SyncStopped / ChangedSinceRead / プロセス終了）
  action stopRun = all {
    not(stopped),
    stopped' = true,
    inMemVer' = recordedVer,
    storeVer' = storeVer, placedVer' = placedVer, recordedVer' = recordedVer,
    keptOrphan' = keptOrphan, fileVer' = fileVer, hookVer' = hookVer,
  }

  // 復旧（just doctor / 再同期の開始）
  action recover = all {
    stopped,
    stopped' = false,
    storeVer' = storeVer, placedVer' = placedVer, recordedVer' = recordedVer,
    inMemVer' = inMemVer, keptOrphan' = keptOrphan,
    fileVer' = fileVer, hookVer' = hookVer,
  }

  action step = any {
    nondet h = Homes.oneOf()
    any { placeCopy(h), rePlace(h), syncWriteFiles(h), syncApplyHome(h) },
    finishPlace, storeUpdates, stopRun, recover,
  }

  // 不変条件1: dotfiles が配置したコピーが未記録のまま孤児（kept）にならない
  val noOrphanedCopy = keptOrphan.size() == 0

  // 不変条件2: 各ホームの指示ファイル世代とフック登録世代が分裂しない
  val noSplitHome = Homes.forall(h => fileVer.get(h) == hookVer.get(h))

  // 不変条件3: 全エージェントホームのフック登録世代が常に一致する
  val allHomesConsistent = Homes.forall(h1 => Homes.forall(h2 => hookVer.get(h1) == hookVer.get(h2)))
}

module preFix {
  import deploy_sync(PERSIST_PER_ITEM = false, STAGE_HOOK_BEFORE_FILES = false).*

  // 修正前の反例1: placeCopy 後に _save_state 前で中断し、ストアが更新されると次回 place で kept になる
  run orphanedCopyTest =
    init.then(placeCopy("h1")).then(stopRun).then(storeUpdates)
      .then(recover).then(rePlace("h1"))
      .expect("h1".in(keptOrphan))

  // 修正前の反例2: syncWriteFiles 後に apply_home 前で中断するとホーム内の指示とフックの世代が分裂する
  run splitHomeTest =
    init.then(syncWriteFiles("h1")).then(stopRun)
      .expect(fileVer.get("h1") == 2 and hookVer.get("h1") == 1)
}

module codeAsIs {
  import deploy_sync(PERSIST_PER_ITEM = true, STAGE_HOOK_BEFORE_FILES = true).*

  // 修正後の現行コード確認: 中断後にストアが更新されても、項目別永続化により次回 place で v2 へ更新される
  run perItemRecoveryTest =
    init.then(placeCopy("h1")).then(stopRun).then(storeUpdates)
      .then(recover).then(rePlace("h1"))
      .expect(placedVer.get("h1") == 2 and keptOrphan.size() == 0)
}
