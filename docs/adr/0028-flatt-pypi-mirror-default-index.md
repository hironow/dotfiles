# 0028. Standardize on the Flatt Security PyPI mirror as the default uv index

**Date:** 2026-06-19
**Status:** Accepted

## Context

This repo's uv projects historically resolved from the implicit default index
`https://pypi.org/simple`, exposing the Python supply chain to the usual raw-PyPI
risks (typosquats, compromised releases, malicious new packages).

The local dev box already routes uv and pip through **Flatt Security's PyPI proxy
`https://pypi.flatt.tech/simple/`** (a malware-scanning mirror) via the
machine-local hardening config that `scripts/harden_env.sh` writes to
`~/.config/uv/uv.toml` (it also sets a personal `exclude-newer = "7 days"`). That
protection was **machine-local only**: CI and any other box still pulled from raw
pypi.org. The committed locks had drifted into an inconsistent state — `emulator/`
and `tools/rttm/` on raw pypi.org, `telemetry/examples/` accidentally on flatt
(the personal config leaking into a committed lock), and no `pyproject.toml`
declaring the index at all.

Key facts that de-risk adoption:

- The mirror is a **public, no-auth HTTPS endpoint** (verified `HTTP 200` on
  `/simple/`). Adoption needs **no secret distribution**.
- This repo has **no explicit non-flatt index** (no torch/CUDA wheel index), so
  the only registry a committed lock should reference is flatt.

## Decision

1. Add `[[tool.uv.index]]` with `name = "flatt"`,
   `url = "https://pypi.flatt.tech/simple/"`, `default = true` to the
   `pyproject.toml` of every uv project that ships a lock: `emulator/`,
   `tools/rttm/`, `telemetry/examples/`. The dependency-free root `pyproject.toml`
   is out of scope.
2. Regenerate `emulator/uv.lock` and `tools/rttm/uv.lock` through flatt so every
   package resolves from `pypi.flatt.tech`. `telemetry/examples/uv.lock` is
   already on flatt and is left untouched.
3. The invariant is the **absence of raw `pypi.org/simple`** in any committed
   lock — not the universal presence of flatt — so that an explicit non-flatt
   index could be added later without tripping the gate.
4. **`exclude-newer` stays exactly as each project declares it.** Unlike a sibling
   project that keeps `exclude-newer` personal, this repo treats it as
   **repo-authoritative**: `emulator/pyproject.toml` declares
   `exclude-newer = "7 days"`, so its lock keeps `exclude-newer-span = "P7D"`, and
   Dependabot's uv updater reproduces it. flatt adoption is **orthogonal** to that
   quarantine and must not disturb it. `tools/rttm/` declares no `exclude-newer`
   and stays span-less.
5. Lock regeneration runs the machine-local hardening config **out of the way** so
   a committed lock reflects only its project `pyproject.toml`. The mechanism is
   `XDG_CONFIG_HOME=$(mktemp -d) uv lock` (uv reads the user config from
   `$XDG_CONFIG_HOME/uv/uv.toml`; redirecting it to an empty dir drops the personal
   flatt default and personal `exclude-newer` while the project-level flatt index
   and the project's own `exclude-newer` still apply). This is wrapped in
   `just relock-uv` (`scripts/relock_uv.sh`) so nobody hand-types the env dance.

## Enforcement inventory

- `scripts/check_uv_flatt_index.sh` (`just check-uv-flatt-index`): for each of the
  three projects, assert the `pyproject.toml` declares the flatt index and the
  `uv.lock` carries no `registry = "https://pypi.org/simple"` line. Pure grep, no
  network. Wired into `just lint` and `just check` (local gate) and into the
  `Unit Tests` GitHub Actions workflow (the CI gate — this repo's CI runs
  individual jobs, not `just check`).
- The flatt **install** path in CI is implicit: `test-emulators.yaml` runs
  `uv sync --all-extras --frozen`, which reads the flatt-routed `emulator/uv.lock`
  and therefore pulls distributions from the mirror.
- Dependabot's uv updater (configured for `/emulator` and `/tools/rttm`) reads the
  declared flatt index and keeps re-locks on flatt; any regression to pypi.org is
  caught by the gate above.

## Consequences

### Positive

- Every CI and local uv install for these projects is malware-scanned through the
  mirror; the committed locks are consistent and intentional.

### Negative

- The mirror becomes a single point of failure: a flatt outage turns any CI job
  that runs `uv sync`/`uv lock` red. Accepted as a supply-chain-safety tradeoff;
  the endpoint is public and has been reliable.
- This reverses an earlier operational assumption that uv locks must stay on
  `pythonhosted`/`pypi.org` to keep CI green; with flatt as the declared default,
  the desired state is the opposite, and the gate enforces it.

### Neutral

- `exclude-newer` quarantine is unchanged; flatt and `exclude-newer` are
  independent knobs.
