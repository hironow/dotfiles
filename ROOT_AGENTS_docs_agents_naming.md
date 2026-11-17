# Naming

Read this when you name a package, module, file, directory, type, function,
variable, or recipe, or when you choose a term for a concept in code, docs,
plans, or answers.

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

## Use established terms, not private ones

A term is the word for a concept. It appears in names, docs, plans, commit
messages, and answers. A term that only we use costs every new reader, human
or agent: they must learn it first, and a search for it finds nothing.

- **Do not coin a private term.** A private term is a word, or a new meaning
  for a word, that only this team, this repo, or this session uses.
- **Take the term from the field.** Use the word the industry or an
  open-source project already uses for the concept. Look in a standard or an
  RFC, in the documentation of the language, framework, or protocol, and in
  widely used open-source projects. Write "idempotency key", not "once-only
  ticket"; "circuit breaker", not "trip switch"; "backoff", not "retry
  spacing".
- When two established terms name the same concept, take the one the
  project's own stack uses, and keep to it.
- **In Japanese text, write the term in English when you are unsure which
  language to use.** Do not turn it into a coined word, a katakana
  transcription, or a forced Japanese phrase. Write 「worktree を作る」, not
  「作業木を作る」; 「squash merge する」, not 「スカッシュマージする」;
  「rate limit をかける」, not 「流量制限をかける」. Japanese prose with
  ordinary English terms in it is fine. A Japanese term that the field itself
  uses, and that you do not doubt, stays (「型」, 「関数」).
- **When no established term fits, stop and ask the human then and there**,
  before the term goes into code, a file name, or a doc. Say what the concept
  is, which established terms you checked and why each one does not fit, and
  the term you propose. Use the new term only after the human agrees, and
  define it where it first appears.
- **When many terms need deciding, or the thing you build is a field of its
  own, build a glossary first.** Do this before you define the terms one by
  one. Look for a glossary skill among the installed skills, and use it to
  choose better terms and write their definitions: the `domain-modeling`
  skill, the `ubiquitous-language` skill, or the `provable-glossary` skill.
  When none of them fits, the `find-skills` skill finds others.
- **An existing term is not exempt.** Follow a term already in the repo only
  when it is an established term, or one the human approved (a glossary or an
  ADR records it). When you meet a private term that nobody approved, ask the
  human then and there, and do not spread it into new names, docs, or answers.
  Leave existing identifiers and APIs as they are until the human decides: a
  rename can break callers.

## Keep names consistent

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
