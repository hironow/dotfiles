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
by itself: measure where the time goes first ("Measure before you optimise" in
docs/agents/go-tooling.md). When most of the end-to-end time is the network,
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

- `rust-lint`: `cargo fmt --all --check` and
  `cargo clippy --all-targets --all-features -- -D warnings`
- `rust-fmt`: `cargo fmt --all`
- `rust-test`: `cargo test --all-targets --all-features`

- Fix clippy findings. Do not add `#[allow(...)]` to hide one; if you must,
  write the reason on the line above.
- Use `unsafe` only when there is no safe way. Put a `// SAFETY:` comment
  on every `unsafe` block.
- Return errors with `Result`. Do not use `unwrap()` or `expect()` outside
  tests and `main` start-up code.

## Ship binaries

Ship one executable per supported OS and CPU. List each target and the linker
or SDK it needs in the root `justfile`, for example
`x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`,
`aarch64-apple-darwin`, `x86_64-pc-windows-msvc`. Build with
`cargo build --release --target <triple>`. Do not assume the result is fully
static: set the runtime linkage for each target (for example, the static C
runtime on MSVC), inspect the artifact, and run it on its target OS.
