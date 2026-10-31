# Design: functional core, imperative shell, ports and adapters

Read this when you design or change how code is split, when code talks to
anything outside the process, or when you add a fake.

Sources: "Functional Core, Imperative Shell" (Google Testing Blog, 2025-10,
https://testing.googleblog.com/2025/10/simplify-your-code-functional-core.html)
and "Hexagonal Architecture" (Alistair Cockburn,
https://alistair.cockburn.us/hexagonal-architecture).

## How the code is split

- **The core is pure.** It takes values and returns values. It does not read
  files, call the network, read the clock, make random numbers, or call a port.
  The shell passes in the current time and any random values.
- **The shell does the side effects.** It reads through ports, calls the core,
  and writes the core's result through ports. Keep it thin: no business
  decisions in the shell.
- **A port is an interface named for its purpose**, such as `Subscriptions` or
  `Mailer`, not `PostgresRepo`. Keep few ports, usually two to four per
  application.
- **An adapter connects one port to one technology.** One port has several
  adapters: the real one, a fake, and maybe a CLI or HTTP one. Changing the
  technology changes the adapter, never the port.
- **Driving adapters** (CLI, HTTP handler, job runner, test) start the work.
  **Driven adapters** (database, external API, mail, clock) are used by it.

```go
// core: pure values in, values out.
func ExpiredSubscriptions(subs []Subscription, now time.Time) []Subscription
func ExpiryEmails(subs []Subscription) []Email

// ports: named for the purpose.
type Subscriptions interface{ All(ctx context.Context) ([]Subscription, error) }
type Mailer interface{ SendAll(ctx context.Context, emails []Email) error }

// shell: read through ports, call the core, write through ports.
func (n ExpiryNotifier) Run(ctx context.Context) error {
	subs, err := n.subs.All(ctx)
	if err != nil {
		return fmt.Errorf("read subscriptions: %w", err)
	}
	return n.mailer.SendAll(ctx, ExpiryEmails(ExpiredSubscriptions(subs, n.now())))
}
```

## How each part is tested

| part | test with | external calls |
| --- | --- | --- |
| core | plain values in, assert the values out | none, and no fake needed |
| shell and wiring | fakes for every driven port | none |
| real adapter | the port's contract tests against a dedicated test account or local emulator | yes, to test targets only |
| whole system (e2e) | real dependencies only; no fakes, no mocks | yes, to a dedicated test environment |

Put most tests on the core. They are fast and need no setup.

## fake/: stand-ins for external services

Keep fakes in a `fake/` directory at the repo root, one package per driven
port (for example `fake/mailer`, `fake/payments`, `fake/clock`). A fake lets
you run and test the system with no external service, and it stops tests and
local runs from touching real systems by accident.

- **A fake is a small working implementation of the port, in memory.** It keeps
  state and behaves like the real service for the cases you use: an in-memory
  store, a mailer that records what it sent, a clock you set by hand.
- **A fake is not a mock.** It has no scripted expectations such as "expect
  `SendAll` called once". Tests assert on the fake's state ("the outbox holds
  these two emails"), not on the calls.
- **Write a fake for every external service** the code uses: payment, email,
  cloud APIs, LLM APIs, queues, the clock, and randomness.
- **Keep the fake honest with contract tests.** Write one test suite per port
  and run it against both the fake and the real adapter. Run the fake leg on
  every `just check`. Run the real leg against a dedicated test account or a
  local emulator, as an integration test. When the real service changes and the
  real leg fails, update the fake in the same change.
- **A fake may simulate failures** (timeouts, rate limits, rejected payments)
  through explicit settings, so tests can cover error paths.
- **Production never uses a fake.** Only start-up wiring and tests may
  import `fake/`. The wiring checks below reject every fake in production.

## Wiring rules that prevent accidents

Choose adapters in one place, at start-up, from explicit configuration.
Check the configuration before the first external call:

- **Tests and local runs use fakes by default.** Using a real adapter requires
  an explicit setting.
- **Stop when the choice is missing or contradicts itself.** Do not fall back
  to the real adapter.
- **Outside production, a real adapter must point at a dedicated test target**
  (a test account, a sandbox key, a local emulator). Refuse to start when it
  points at a production endpoint or a production credential.
- **Production refuses to start with any fake wired in.**
- Write a test for each of these checks.
