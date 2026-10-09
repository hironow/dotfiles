# Naming

Read this when you name a package, module, file, directory, type, function,
variable, or recipe.

A name says what the thing is or does in this domain. A specific name lets a
reader understand the code without opening it. A generic name forces them to.

## Do not use generic names

Do not use these words as a name, or as the meaningful part of a name:

- `Manager`, `Handler`, `Processor`, `Controller`, `Service`, `Helper`,
  `Util`, `Utils`, `Common`, `Misc`, `Base`, `Core` (as a type name), `Data`,
  `Info`, `Item`, `Object`, `Thing`, `Stuff`, `Wrapper`, `Engine`.
- Directories `utils/`, `common/`, `helpers/`, `misc/`, `shared/`, or a `lib/`
  that collects unrelated code.

These words are allowed when they are the established term of a framework or
protocol that you implement (for example, an `http.Handler` in Go, or a
Kubernetes controller). Then they name a real role.

## How to find a specific name

1. Say in one sentence what the unit does, in the words of the domain. For
   example: "It decides which subscriptions have expired."
2. Take the name from that sentence: `ExpiredSubscriptions`,
   `selectExpired`.
3. If no single name fits, the unit does more than one thing. Split it, then
   name each part.
4. Name by role, not by type or by technology. Write `invoices`, not
   `invoiceList`; `PaymentGateway` (a port), not `StripeClient`, unless the
   unit really is the Stripe adapter.

## Examples

| generic | specific |
| --- | --- |
| `UserManager` | `AccountRegistry`, `SignupFlow`, `SessionStore` (pick the job it does) |
| `processData(d)` | `normalizeAddresses(addresses)` |
| `utils/strings.go` | `slug/slug.go` with `slug.FromTitle` |
| `EmailService` | `ExpiryNotifier` (shell) and `ExpiryEmails` (core) |
| `handle()` | `rejectDuplicateOrder()` |
| `data`, `info`, `result` | `expiredUsers`, `quota`, `refundDecision` |

## Other rules

- Use the same name for the same concept everywhere: code, tests, docs, logs,
  and metrics.
- Name booleans as a statement that is true or false: `isExpired`,
  `hasQuota`.
- Keep abbreviations only when they are more common than the full word
  (`ID`, `URL`, `HTTP`).
- Follow the language's own naming style (Go: `MixedCaps`, short receiver
  names; Rust: `snake_case` functions, `CamelCase` types).
- When you rename, rename everywhere in one structural commit
  (`refactor:`), separate from any behavior change.
