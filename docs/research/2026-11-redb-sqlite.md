# redb versus SQLite: evidence checked on 2026-11-08

## Finding

Consider cberner/redb when a database is needed. Prefer it only when evidence
matches the required version, workload, API, storage backend, durability and
concurrency and demonstrates an advantage. Otherwise compare SQLite case by
case. The inspected sources establish neither general in-memory superiority
nor multiprocess performance superiority.

This research concerns the Rust project [cberner/redb](https://github.com/cberner/redb),
not the similarly named .NET RedBase product. No benchmarks were executed for
this investigation. Published measurements below are other authors' results.

## November comparison: file-backed key/value operations

KvSQL v0.2.0, released November 3, contains a comparison at immutable commit
`ce154932d028937d4df3249c1f33e98cc2088098`. It uses redb **4.4.0**, SQLite
**3.50.2** and rusqlite **0.37.0**, not redb 4.5's new shared-file modes.
See the [release](https://github.com/softdevstudio/kvsql/releases/tag/v0.2.0),
[pinned results](https://github.com/softdevstudio/kvsql/blob/ce154932d028937d4df3249c1f33e98cc2088098/test/results/latest/neighbours.md)
and [lockfile](https://github.com/softdevstudio/kvsql/blob/ce154932d028937d4df3249c1f33e98cc2088098/bench/neighbours/Cargo.lock).

Conditions: Linux x86-64, Xeon 2.10 GHz, two reported hardware threads but one
benchmark thread, ext2/ext3 temporary files, 100,000 eight-byte keys with
13-byte values and 8 MiB configured caches. Reads are warm and shuffled.
Five interleaved rounds report medians and ranges; bulk load is timed once.
These are **real files**, not in-memory backends.

| Operation | redb 4.4.0 | SQLite 3.50.2 |
| --- | ---: | ---: |
| Key lookup | 1.32 µs | 2.29 µs |
| Scan 100 consecutive keys | 6.52 µs | 22.9 µs |
| Single-key synced transaction | 328.4 µs | 161.3 µs |
| Load 100,000 keys in one transaction | 75.46 ms | 66.23 ms |

Lower is better. These results favor redb reads but SQLite durable single-key
writes and bulk load under the measured conditions. They do not establish an
overall winner.

The [benchmark code](https://github.com/softdevstudio/kvsql/blob/ce154932d028937d4df3249c1f33e98cc2088098/bench/neighbours/src/main.rs)
uses a new redb read transaction/table per lookup, versus a reused prepared
SQLite statement. redb returns borrowed values while SQLite materializes owned
byte vectors. The comparison therefore includes API and conversion costs.
SQLite uses a `WITHOUT ROWID` key/value table, WAL and `synchronous=FULL`;
redb uses `Durability::Immediate`. The synced phase performs 200 commits per
round. A separate redb 0.78 µs open-snapshot result has no equivalent SQLite
snapshot measurement. The article's prepared-SQL headline compares **KvSQL**
with SQLite, not redb executing SQL.

Reported file sizes are not comparable because the stores contain different
data. The results also caution that shared-cloud numbers vary by 20–30%.
Durability comparisons on macOS need separate attention to SQLite's
`fullfsync` setting; the Linux results do not settle that question.

## October comparisons are not November or engine-only evidence

Tiramemsu's [October 27 article](https://www.tiramemsu.com/articles/making-redb-faster.html)
describes its own redb-backed application, with changes to query planning,
filter pushdown, decoding and allocations. It reports wins on some cyclic
queries and concurrent reads, but losses on selective joins, variable-length
paths, space and some writes. Its group-commit redb route and SQLite WAL/NORMAL
route are not per-transaction synced-commit tests. Threaded application results
do not demonstrate multiprocess behavior.

The dated article is also preserved in its [first-party repository](https://github.com/Volland/tiramemsu/blob/ed603855ddd50871acd335fe8ba49f35689e549d/site/articles/making-redb-faster.html).
These findings are useful workload leads, not evidence that replacing SQLite
with redb alone reproduces the application-level gains.

## In-memory storage and multiprocess files are separate configurations

| Configuration | Supported behavior |
| --- | --- |
| redb 4.5.0 `InMemoryBackend` | Process-local `RwLock<Vec<u8>>`; its range-lock operations are unsupported. It is not a cross-process shared-memory database. |
| redb 4.5.0 `ExclusiveWriter` | Default exclusive writer access, excluding other processes. |
| redb 4.5.0 `SingleWriter` | One writer process plus reader processes, using a backend with the required byte-range locks. |
| redb 4.5.0 `MultiWriter` | Several write-capable processes, with one write transaction at a time; not simultaneous write transactions. |
| SQLite `:memory:` | Private to each connection. Named/shared-cache in-memory connections can share within one process, not between processes. |
| SQLite file-backed WAL | Concurrent readers and a writer across processes on the same host, with one writer at a time. Standard WAL does not support network filesystems. |

Primary sources:

- redb [tagged in-memory implementation](https://github.com/cberner/redb/blob/v4.5.0/src/tree_store/page_store/backends.rs).
- redb [4.5.0 changelog](https://github.com/cberner/redb/blob/v4.5.0/CHANGELOG.md)
  and [backend contract](https://github.com/cberner/redb/blob/v4.5.0/src/db.rs).
- SQLite [in-memory databases](https://sqlite.org/inmemorydb.html)
  and [WAL concurrency](https://sqlite.org/wal.html#concurrency).

redb 4.5.0 was released November 5. Its shared write modes reject
`Durability::None` and require two-phase durable commits; see the
[tagged transaction implementation](https://github.com/cberner/redb/blob/v4.5.0/src/transactions.rs).
The 4.4 single-process read/write timings above therefore do not prove shared
mode performance. Version 4.5's locking is incompatible with the experimental
multiprocess locking in 4.3/4.4. Shared locking also depends on platform and
backend support; it is not a property of any arbitrary storage backend.

## Applicability limits

A database comparison must distinguish private memory, warm file-backed reads,
threads, processes, transaction lifetimes, value-copy costs and durability.
An advantage on one read workload is not overall database superiority.
No inspected source provides a matched in-memory or multiprocess superiority
test for current redb versus SQLite.

redb's own [tagged README comparison](https://github.com/cberner/redb/blob/v4.5.0/README.md)
also reports mixed file-backed results. Its published table does not identify
the measurement date and exact SQLite build, so it is not November-specific
evidence and does not justify blanket priority.

These findings do not call for Rust or FFI solely to obtain redb. They preserve
the existing Go-first policy, plain maps when sufficient, in-memory port fakes
for unit tests and real databases for database end-to-end tests.
