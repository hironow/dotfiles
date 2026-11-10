# Rust tooling

Read this when you choose between Go and Rust for new code, or when you write
or change Rust. Go is the default for new code (docs/agents/go-tooling.md).
Choose Rust only when Go does not fit:

- you cannot accept a garbage collector (hard latency limits, real-time work).
  Judge this by deadline misses and tail latency (p99, the longest pause), not
  by averages;
- memory is very tight (embedded, small devices);
- the target is WebAssembly or another platform where Go output is too large or
  unsupported;
- you extend an existing Rust codebase.

These are constraints. Wanting more speed is a different reason, and not one
by itself: measure where the time goes first (docs/agents/performance.md, and
"Measure before you optimise" in docs/agents/go-tooling.md for the Go tools). When most of the end-to-end time is the network,
an exchange, a disk, or another service, a faster language changes little.

When Go does not fit, use Rust, never C++ or Java. Ownership and the borrow
checker turn use-after-free, data races, and many lifetime mistakes into
compile errors, and safety and correctness come before performance
(AGENTS.md).

Write the reason in the PR, or in an ADR when it starts a new codebase.

## Use the newest stable Rust

- Use the newest stable Rust and the newest edition it supports. Set
  `rust-version` and `edition` in `Cargo.toml`, and pin the toolchain in
  `rust-toolchain.toml` (`channel = "stable"` or an exact version).
- Rust is a Class 1 dependency (docs/agents/dependency-policy.md): move to new
  stable releases quickly and fix forward.

## Standard library first

- Use `std` before a crate. A crate needs a reason the standard library cannot
  meet, such as a protocol, a cloud client, or async I/O.
- Before you add a crate, check how many crates it pulls in
  (`cargo tree -p <crate>`). Prefer the crate with fewer dependencies.
- Turn off default features you do not use
  (`default-features = false`).
- Commit `Cargo.lock` for binaries.

## Quality gate

Add three recipes to the root `justfile`, and call them from `just check`:

- `rust-lint` (below): `cargo fmt --all --check`, and clippy once per target
  you ship.
- `rust-fmt`: `cargo fmt --all`
- `rust-test`: `cargo test --all-targets --all-features`

clippy checks one target, so code under `#[cfg(windows)]` or
`#[cfg(target_os = "macos")]` is linted only when you check that target. List
the targets once, in `rust_targets`, and use that list for the release builds
too (see "Ship binaries"). The recipe adds each target to the toolchain
itself: do not rely on `rust-toolchain.toml` to install them. Keep the
shebang and `set -euo pipefail`: in just's default `sh -cu`, a loop returns
only the last target's exit code.

```just
rust_targets := "x86_64-unknown-linux-musl aarch64-unknown-linux-musl aarch64-apple-darwin x86_64-pc-windows-msvc"

rust-lint *targets=rust_targets:
    #!/usr/bin/env bash
    set -euo pipefail
    cargo fmt --all --check
    for target in {{targets}}; do
      rustup target add "$target"
      cargo clippy --all-targets --all-features --target "$target" -- -D warnings
    done
```

- Pure Rust can be checked for every target from any machine: clippy does not
  link the target's code. Build scripts and proc-macros are built for the
  machine you run on, so they need its linker.
- A dependency whose build script compiles C for the target (for example
  `ring`, `aws-lc-sys`, `openssl-sys`, bundled `libsqlite3-sys`) is checked
  only on that target's OS. Then pass `just check` the targets this machine
  can check, and run `just rust-lint <triple>` for the others in that OS's CI
  job, next to its release build. Write in the `justfile` which job checks
  which target. Never drop a target silently.
- With `-D warnings`, a helper that only `#[cfg(windows)]` code calls is
  unused on the other targets. Give it the same `#[cfg(...)]`, or write the
  branch with `if cfg!(windows)` so every target type-checks it. Do not hide
  it with `#[allow(dead_code)]`.
- Lint finds errors in code. Only running the tests on an OS shows how the
  code behaves there.
- Fix clippy findings. Do not add `#[allow(...)]` to hide one; if you must,
  write the reason on the line above.
- Use `unsafe` only when there is no safe way. Put a `// SAFETY:` comment
  on every `unsafe` block.
- Return errors with `Result`. Do not use `unwrap()` or `expect()` outside
  tests and `main` start-up code.

## Ship binaries

Ship one executable per supported OS and CPU. List each target in
`rust_targets` (the same list `rust-lint` checks), and the linker or SDK it
needs, in the root `justfile`, for example
`x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`,
`aarch64-apple-darwin`, `x86_64-pc-windows-msvc`. Build with
`cargo build --release --target <triple>`. Do not assume the result is fully
static: set the runtime linkage for each target (for example, the static C
runtime on MSVC), inspect the artifact, and run it on its target OS.
