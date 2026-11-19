# Protocol Changelog

Last updated: 2026-10-13

Summary of key changes across protocol and Google Cloud submodules.

"Current version" indicates the public release, and "Checkout state" indicates the local reference commit.
Entries verified on 2026-10-13 represent the diff since the previous submodule update and include commits dated earlier.
Unreleased changes are marked as HEAD to distinguish them from public release features.

---

## Protocols

### A2A (Agent-to-Agent)

**Current version**: v1.0.1 (2026-05)

**Checkout state**: `7c861a59` (HEAD 2026-10-12. No new release tag; v1.0.1 remains latest)

#### Verified 2026-10-13 (7 commits, docs only; no spec incompatibility)

[Diff for this update](https://github.com/a2aproject/A2A/compare/7295b180...7c861a59). Public release remains v1.0.1.

- **Spec example fix**: Updated section 8.4.1 canonicalization example to a valid Agent Card (#2319)
- **docs**: Replaced removed `A2AStarletteApplication` and v0.3 `TaskState` names in streaming tutorial (#2267); added MusedIn / Agent Commerce Gateway / ADEXTO to partners and a2a-php-sdk / a2a-php to community SDKs (#2294 / #2299 / #2303 / #2275 / #2263)

#### 2026-09-16 to 2026-09-22 Updates (1 commit, docs only)

- **Roadmap update**: Updated roadmap page based on TSC meeting discussions (#2237). No spec changes

#### 2026-09-01 to 2026-09-15 Updates (docs only, 4 commits; no spec incompatibility)

- **Docs readability**: Refined wording in `what-is-a2a` (#2223) / `a2a-and-mcp` (#2224) / `key-concepts` (#2225) / `life-of-a-task` (#2226). No changes to spec text or version

#### 2026-08-01 to 2026-08-31 Updates (docs / governance / build only, 14 commits; no spec incompatibility)

- **Added blog post announcing A2A joined AAIF** (#2186) — notable governance topic
- **build: Introduced JSON Schema generation** (#2074, resolves issue #2073) — machine-readable schema generation infrastructure for the spec (build change only; spec text unchanged)
- **docs(spec): Renamed `PushNotificationConfig` → `TaskPushNotificationConfig`** (#1981) — docs updated to match the type name consolidated in v1.0.1
- **docs(spec): Clarified Hybrid Agents section in Life of a Task** (#2154); fixed pagination field names in migration docs (#2165)
- **Partners list**: Added FAF (#2136) / TiEQi-A2A (#1900) / OpenAgents (#2168); fixed broken links (#2139, #2193)
- **governance / chore**: Added Rust and repo maintainers (#2175); promoted Todd Segal to Distinguished Engineer (#2147); updated ServiceNow representative (#2142); added Discord links (#2146)

#### 2026-07-28 to 2026-07-31 Updates (mainly docs; no spec incompatibility)

- **docs(spec): Clarified in-task authorization scope semantics** (#2081) — clarification of existing semantics; no incompatibility
- **Migrated vulnerability reporting to GitHub Security Advisories** (#2086, operational change)
- docs: Fixed grammar in hybrid agent docs (#2077); fixed failing PR links workflow (#2091)

#### Updates as of 2026-07-27 (docs / CI only; no spec changes)

- **No spec/version changes**: All 4 commits from v1.0.1-24 → -28 are docs/CI with zero behavioral changes
- **Added daily docs link check workflow** (#2059)
- **Fixed gRPC URL example**: Corrected gRPC URL example in AgentInterface (#1997)
- **Fixed Agent Card security requirement sample** (#2046); **added A2A meeting / agenda links** (#1993)

#### Updates as of 2026-07-18 (no spec changes; community SDK additions only)

- **No spec/version changes**: All commits from v1.0.1 to HEAD are docs/ci/chore with zero behavioral changes
- **Community SDK expansion**: Added Rust SDK (a2a-rs) (#1863) and C++ SDK (a2a-cpp) to community SDKs (#2034)
- **Partners list updates**: Added AlgoVoi / Auto Agent Protocol / Lumika; removed broken links

#### 2026-07-01 to 2026-07-07 Updates (docs / CI only; no spec changes)

- **Added AlgoVoi to partners list**: Docs-only change (#1994)
- **Removed broken partner links**: Removed broken link entries for OIXA / Pinchwork (#2017)
- **Migrated CI to buf-action**: Migrated away from deprecated buf-setup-action (#1999)
- **Batch-updated 3 GitHub Actions dependencies** (#2035)

#### 2026-06-22 to 2026-06-30 Updates (docs / CI only; no spec changes)

- **partners**: Added Auto Agent Protocol / Lumika (#1907)

- **Added docs build CI trigger**: Triggered docs build on build inputs changes (#1967)
- **Aligned `llms.txt` with v1.0 spec**: Updated llms.txt to match v1.0 spec and site navigation (#1943)
- **Updated homepage banner**: Updated A2A homepage banner (#1971)

#### Updates after v1.0.1 Release (2026-05)

- **Reorganized homepage information** (#1874, 2026-06-12): Restructured protocol overview homepage info and added missing sections

- **v1.0.1 release**: Official release from v1.0.0 → v1.0.1 (#1749)
- **Added Rust SDK (a2a-rs) reference**: Added Rust SDK (a2a-rs) reference to README and updated linter workflow (#1863)
- **Added multi-tenancy guide**: Added multi-tenancy guide and clarified tenant field semantics (#1848)
- **Aligned push notification auth**: Aligned push notification authentication examples with protocol behavior (#1793)
- **Updated SDK count to 6**: Updated official SDK count to 6 after adding Rust (#1778)
- **Fixed Tutorial 8 import path**: Fixed AgentExecutor import path (#1884)
- **Clarified MCP reference**: Clarified MCP reference in A2A overview (#1873)

#### Changes after v1.0.0

- **Fixed TaskStatus values spec**: Corrected specification description for TaskStatus values (#1801)
- **Removed deprecated stateTransitionHistory references**: Removed deprecated stateTransitionHistory references from spec (#1834)
- **Renamed to "Send Streaming Message"**: Replaced legacy method name "Stream Message" → "Send Streaming Message" (#1784)
- **Recommended HTTP binding MIME**: Preferred `application/a2a+json` for HTTP binding (#1753)
- **Custom protocol bindings docs**: Added official documentation for custom protocol bindings (#1619)
- **New logo & mascot**: Refreshed branding (#1719)
- **Added Community SDKs**: Added Community SDK section separate from official SDK list (#1698)
- **Officialized Rust SDK**: Added Rust SDK to official SDK list (#1729)
- **TSC member addition process**: Added documentation on adding TSC members to GOVERNANCE.md (#1571)
- **Spec fix**: Fixed transcoding-related errors (#1627)
- **Expanded partners list**: Added OIXA Protocol (#1692), Strale (#1702), WritBase (#1634)
- **Fixed tutorial host**: Used `127.0.0.1` in tutorial (#1783)
- **Updated Python helloworld tutorial**: Updated for a2a-sdk v1.0 (#1775)
- **Local build instructions**: Added local build instructions to Contributing Guide (#1726)

#### Key Changes in v1.0.0

- **Official release**: Promoted from v1.0.0-rc to v1.0.0
- **Spec refactor**: Separated application protocol definition from transport mapping
- **Push Notification consolidation**: Merged `TaskPushNotificationConfig` and `PushNotificationConfig` (#1500)
- **Field rename**: `SendMessageConfiguration.blocking` → `return_immediately` (#1507)
- **HTTP error mapping**: HTTP+JSON error mapping compliant with `google.rpc.Status` (AIP-193) (#1600)
- **LF package prefix**: Added LF package prefix (#1474)
- **Extension governance**: Added Extension governance documentation
- **In-Task Authorization**: Expanded details on in-task authorization
- **SDK backward compatibility**: Designed SDKs to support backward compatibility

#### Breaking Changes (v0.3.0 → v1.0.0)

| Change | Impact |
|---|---|
| Simplified ID format: composite ID → simple UUID/literal (#1389) | Request ID format changed |
| Enum format: `lowercase` → `SCREAMING_SNAKE_CASE` (#1384) | All enum values changed |
| Simplified HTTP URLs: removed `/v1/` prefix | Endpoint URLs changed |
| Well-Known URI: `agent.json` → `agent-card.json` (#841) | Endpoint URLs changed |
| Removed OAuth implicit/password flows (#1303) | Auth flows changed |
| Consolidated Push Notification Config (#1500) | Structure changed |

#### Reference Links

- [A2A Specification](https://github.com/a2aproject/A2A)

---

### A2UI (Agent-to-User Interface)

**Current version**: production **v0.9.1** (stable v0.9 series patch). **v1.0 spec is Release Candidate** (Status: Candidate, 2026-06-08). Lightweight tags `v0.8`/`v0.9` both point to old commit 19919ef4 and do not represent spec versions (actual specs live in `specification/{v0_8,v0_9,v0_9_1,v1_0}/`) / Python `a2ui-agent-sdk` **v0.8.0** + `a2ui-core` **v0.3.0** (2026-10-08). TS public releases are `@a2ui/angular` **0.12.0**, `@a2ui/lit` / `@a2ui/react` / `@a2ui/web_core` **0.13.0**, `@a2ui/markdown-it` **0.2.1** (verified latest on npm registry on 2026-10-13; version bump commit is #3105, 2026-10-09)

**Checkout state**: `3eafe0baf` (HEAD 2026-10-12. Spec release tags remain `v0.8`/`v0.9`; SDK tag is `python/a2ui-agent-sdk/v0.8.0`)

#### Verified 2026-10-13 (v1.0 implementation expansion: Python / TS / Dart / Swift / web)

[Diff for this update](https://github.com/google/A2UI/compare/3b28510f...3eafe0baf). Python releases and HEAD changes are distinguished below.

- **Python public release**: `a2ui-agent-sdk` v0.8.0 / `a2ui-core` v0.3.0 (2026-10-08). Introduced model return types for parser, multi-catalog support, and strict schema validation. See breaking changes below for details
- **Python HEAD (unreleased)**: `CatalogProvider` / `CatalogConfig` / transformer null allowlist in blueprint (#3072); aligned parser / prompt generator / inference format APIs (#3074); implemented `A2uiGenerator` / `A2uiRequestProcessor` and updated samples (#3075). Fixed validation error emission on chunks closing invalid v1.0 components (#3109)
- **TS agent**: Per-component catalog resolution and buffering until v1.0 component close (#3091); validated Direct JSON parser output (#3092); removed name-based child inference (#3090)
- **Dart**: Added v1.0 validator rules / composition constraints / built-in common types to a2ui_core (#2994); added resolution context with `@index` and parent chain plus missing-binding warnings (#2999)
- **web / Swift**: Added DateTimeInput time-only and min/max, Image `scaleDown`, and List align support (#3106); fixed Swift v1.0 adapter, catalog resolution, and conformance (#3079)
- **spec / test (HEAD)**: Resolved prose and schema inconsistencies in v1.0 (#3087); ported Express TS unit tests to language-agnostic YAML conformance suite (#3093)

##### Breaking Changes and Migration Verified in This Update

- **Python v0.8.0 / core v0.3.0 (public release)**: Requires `a2ui-core>=0.3.0,<0.4.0`. Parser return value changed from dict to a list of `AgentToRendererMessage`, so convert with `to_message_models` / `to_message_dicts`. Pass a single catalog as a list like `DirectJsonParser([catalog])`. Removed `schema_modifiers` / `remove_strict_validation`; conform payloads to the public schema. Component tree type key changed from `type` to `component`
- **Python HEAD (unreleased)**: Removed stream-parser classes and `create_stream_parser`. Use `parse_chunk` on the parser returned by `create_parser()`. Migrate `InferenceFormat.parser` to `create_parser()` as well. Move `CatalogConfig` from `a2ui.schema` to `a2ui.processor` and replace `A2uiCatalogProvider` with `CatalogProvider`
- **TS public release (Angular 0.12.0, Lit / React / web_core 0.13.0, #3105)**: Angular / Lit / React package roots now expose version-agnostic APIs; import legacy v0.8 APIs from `/v0_8` of each package. Migrate React v0.9 basic catalog to `@a2ui/web_core/v0_9/basic_catalog`. `web_core` component trees read `tree.component` instead of `tree.type`

Sources: [Python agent SDK CHANGELOG](https://github.com/google/A2UI/blob/3eafe0baf/python/a2ui_agent/CHANGELOG.md), [Python core CHANGELOG](https://github.com/google/A2UI/blob/3eafe0baf/python/a2ui_core/CHANGELOG.md), [TS version bump commit](https://github.com/google/A2UI/commit/0ba991341).

#### 2026-09-16 to 2026-09-22 Updates (16 commits: web_core recursion guard SECURITY + MCP catalog functions + Swift/Dart/Angular fixes)

- **SECURITY (web_core)**: Guarded against excessive recursion in DynamicValue resolution by introducing `MAX_DYNAMIC_VALUE_DEPTH = 20` (#2432) — prevents CWE-674 where 20,000-deep nested function calls crash the renderer process
- **MCP catalog**: Added jmespath / split / regexCapture / regexReplace / updateDataModel functions to process MCP results (#2650)
- **Swift**: Stopped invalid paths from deleting write targets (data model conformance) (#2626); constrained swift-json-schema to 0.13.x (#2656)
- **Dart**: Added payload entry-point types to a2ui_core (#2683); relaxed preact_signals dependency constraint (#2667); scoped validator to a single catalog (#2538)
- **Angular**: Guarded v0.8 icon component against non-string names (#2608)
- **conformance**: Added agent SDK parser suites and ran them in Python SDK (#2713)
- **samples/mcp**: Executed filesystem sample startup action declaratively from A2UI payload (#2711); fixed mcp demo (#2687); improved mcp docs (#2682)
- **docs**: Updated a2ui_agent module blueprint (#2718); used valid basic catalog icon names in canonical examples (#2703); clarified spec (#2677); moved Flutter adapter placeholder from renderers to dart (#2588)

#### 2026-09-01 to 2026-09-15 Updates (web_core / lit **0.11.0** BREAKING + a2ui_agent 0.6.0 + SECURITY hardening + SkillGenerator)

- **web_core 0.11.0 (BREAKING, v0.9 track)**: Invalid numeric literals (`${1.2.3}`) now throw `A2uiExpressionError` instead of `NaN` (#2497); calling unimplemented catalog functions raises the same exception (#2077); enforced expression parser nesting depth guard (#2492); moved basic catalog Web Components to `@a2ui/web_core/v0_9/basic_catalog` entrypoint (#2190)
- **lit 0.11.0 (BREAKING, v0.9)**: Moved basic catalog implementation to web_core (#2190); aligned DOM/behavior/styling with Angular reference implementation (#2205); **migrated Shadow DOM → Light DOM** (#2204; 0.10.4 was unpublished due to accidental breaking changes in a patch release)
- **a2ui_agent 0.6.0**: Keyword arguments for Express DSL + multi-version output (v0.9 / v0.9.1 / v1.0) (#2131); `surface()` / `deleteSurface()` directives (#2163)
- **SECURITY (web_core)**: Prototype chain traversal fix on v0.8 read path (#2355); hid V8 stack traces from DataContext errors (#2429); added `MAX_ARRAY_INDEX` limit + array signal clone optimization (#2430); capped dynamic ChildList at `MAX_DYNAMIC_CHILD_LIST_SIZE` (#2431); capped expression parser template length and parts count (#2433)
- **MCP catalog**: UI resource resolution + A2UI message handling inside `callMcpTool` (#2644); tool name / databinding / callback handler support (#2555)
- **Swift**: Extracted `NodeResolver` from `SurfaceViewModel` (#2487); wired Basic Catalog into sample gallery (#2455); marked DataModel / SurfaceComponentsModel as MainActor (#2502)
- **skills / eval**: `SkillGenerator` API to compile inference rules and catalogs into `SKILL.md` (#2516); cross-language conformance suite for expression parser (#2497); evaluated Express format with Gemma (#2549)
- **HEAD additions**: Universal markdown fallback for Text component (#2272)

#### 2026-08-01 to 2026-08-31 Updates (Full Swift SDK implementation + web_core node layer / `Catalog.fromJson` + v1.0 `allowedCallers` rename BREAKING)

- **BREAKING (v1.0 dev track): Renamed `callableFrom` to `allowedCallers` in spec** (#2238) — incompatible field rename for function caller control in v1.0 schema; production v0.9.1 users unaffected
- **Major Swift SDK progress**: Basic Catalog component schemas + registry (#2377); SwiftUI component implementations (#2400); core validation rules / reactivity / type coercion; **conformance test harness** (#90157ec1); Basic Catalog functions (#453bfa07); introduced `DataContext` type (#6bffecb3); validated surface theme against catalog `themeSchema`; atomic two-pass validation and single-action mutual exclusivity enforcement in message decoder; binding resolution for top-level path/call objects
- **web_core**: **Introduced node layer** (#2077) + React renders `A2uiSurface` via node layer (#2393); **`Catalog.fromJson` schema ingestion engine** (#9f000841); enhanced schema inference for generic binder (#d9086fb7); resolved `DynamicValues` inside function arg arrays (#2016)
- **lit**: **Migrated basic catalog components to light DOM rendering** (#b4eebcdc)
- **skills**: Added `a2ui-swift-development` skill (#2436); `a2ui-remediate-problem` skill + copyable verification (#57491139); glossary respect instructions (#2405)
- **explorers**: Collapsible sidebars + j/k keyboard navigation (#48874ecc)
- **eval / docs**: Preserved solver prose and normalized format version (eval/parser); Python 3.10/3.11 compatibility for reporter.py (#2199); fixed broken relative specification links; added Flutter sample to quickstart guide (#2107)
- **CI**: Switched GitHub Actions runners to ubuntu-latest family; remediation PAT token / quoted `/fix` support

#### 2026-07-28 to 2026-08-01 Updates (Removed surfaceProperties from v1.0 spec BREAKING + iframe component + Kotlin DSL engine)

- **BREAKING (v1.0 dev track): Removed `surfaceProperties` from v1.0 spec** (#2126 / #2129) — incompatible field removal from v1.0 schema
- **Renamed transport format term to `direct_json`** (#2130); restricted default input/output modes to valid MIME types (#2097)
- **feat(spec)**: Mixable catalogs and per-component `catalogId` resolution (spec-v1.0, #2079); specification version field in catalog definition metadata (#2111); **added A2UI web app iframe component spec (v0.9)** (#2123)
- **SDK**: Performance improvements to A2UI Express DSL (#2131) + **Kotlin SDK engine** (#2132); Swift `SurfaceGroupModel` / `MessageErrorMapper` (#2058); Angular `provideA2Ui` helper (#2061)
- **eval**: Standardized dataset schema, messages format, and multi-turn benchmark (#2078)
- **fix**: Message processor validates component properties against catalog schema (#2142, #2145); v0.9 TS compile / schema path resolution (#2109); aligned v0.9 slider schema with spec (#1487). perf: validator caching on `A2uiCatalog.validator` (#1972)
- deps: 5 items in npm_and_yarn group (#2119); `pyasn1` 0.6.4 (#2087). No direct security fixes

#### Updates as of 2026-07-27 (v1.0 RC continued + Swift SDK implementation + web_core prototype pollution fix SECURITY)

- **v1.0 spec fine-tuning**: Required `value` in `updateDataModel` + enforced explicit `null` deletion (#2068); restored `svgPath`/`DataBinding` support for `Icon.name` (#2070); renamed v1.0 schema/code references to agent/renderer names (#2076); MCP spec allows multiple data paths in data binding (#2073)
- **Added Atom Inference Format** + Express/Elemental InferenceFormat implementations (#2056 / #1982)
- **Swift SDK implementation progressing**: SurfaceViewModel core engine (#2052); component catalog protocols (#2005); A2UICore error types / JSONValue path (#1999); v0.9.1 common type schemas (#1994)
- **SECURITY: Protected `DataModel` in web_core against prototype pollution (#2085)**
- **Implemented host-driven container dimension management** via Resize (#2057); added community renderers (generative-mui #2082 / boteai #1674 / agenui #1912 / Ink #2032); documented release cadence in release.md (#2101)

#### Updates as of 2026-07-18 (v1.0 RC drafting accelerated; all breaking changes are v1.0(RC) vs v0.9 diffs, production v0.9.1 users unaffected)

- **v1.0 spec (RC) drafting**: Synchronous client→server RPC (`actionResponse`+`actionId`); server→client `callFunction`/`functionResponse` RPC; validated execution boundary via runtime catalog rather than wire
- **Bulk createSurface generation**: Allowed defining `components` and `dataModel` directly inside createSurface payload; added `@index` builtin and UAX #31 identifier rules
- **package release**: `@a2ui/web_core` v0.10.4 / `@a2ui/angular` v0.10.3 / Python `a2ui-core` v0.1.1 / `a2ui-agent-sdk` v0.4.0. Added A2UI Elemental (compact HTML layout) (#1952); moved Swift SDK to production layout

| Breaking Change (v1.0 RC vs v0.9) | Impact |
|---|---|
| Renamed `theme` → `surfaceProperties`, removed `primaryColor` | Separated layout and branding; updates needed in both createSurface and catalog |
| MIME type `application/json+a2ui` → `application/a2ui+json` | Media type update required at transport layer |
| Catalog `functions` changed from list → map (key=function name) | Existing catalog definitions require structural conversion |
| Icon `svgPath` → `path`; identifiers must follow UAX #31 | Updates needed for custom icons and naming |

#### 2026-07-01 to 2026-07-07 Updates (catalogId clarification + web_core type exports + Python tooling setup)

- **Spec clarification: `catalogId` is an arbitrary string identifier**: Clarified across v0.9 / v0.9.1 / v1.0 specs that it is "not a resolvable URI" and well-known IDs assume prior agreement between client and server (#1924)
- **web_core: Exported `UserAction` as `ClientEventUserAction` in v0.8**: Added type export for 1P usage (#1942)
- **API rename**: `indexSystemFunction` → `IndexSystemFunction` (#1811)
- **Angular fixes**: Fixed to use Angular signals directly (#1733); updated Angular MCP Apps demo to A2UI v0_9 (#1786)
- **Python tooling setup**: Converted to uv workspace (#1814); standardized PEP 420 namespace packages (#1815); enabled type checking for `a2ui_core` (#1816); centralized pyink config (#1911, #1932); unified Python CI (#1910)

#### 2026-06-29 to 2026-06-30 Updates (v0.9.1 validator fix + file-system decoupling of Express compiler + Python 3.10 support)

- **web_core: JSON Pointer escaping (RFC 6901) support**: TypeScript `DataModel.parsePath` now unescapes `~1`→`/` and `~0`→`~`, matching Python SDK parity (#1796)
- **Express compiler suite support for in-memory Catalog / A2uiCatalog**: Made `CatalogSchemaHelper` polymorphic so it accepts and crawls structured `Catalog`/`A2uiCatalog` models directly alongside physical file paths and raw JSON dicts; propagated to compiler/decompiler/prompt generator/`parse_express_response` (#1774)
- **eval: Fixed v0.9.1 catalog schema resolution**: Fixed `catalog.json` references from `common_types.json` failing to resolve during `v0.9.1` evaluation by registering the catalog schema relative to `common_types_schema` `$id` (#1789 fixed, #1792)
- **v1.0 spec: Fixed Button sample to use `child`**: Corrected Button example in `specification/v1_0/docs/a2ui_protocol.md` to use the proper `child` property (#1790)
- **Lowered minimum Python requirement to 3.10**: Relaxed `pyproject.toml` across all SDKs / eval / samples to `>=3.10` for broader compatibility; also refactored `tools/build_catalog/assemble_catalog.py` (#1808)
- **Consolidated dependencies/lockfiles into single workspace `uv.lock`**: Removed per-package `uv.lock` files and consolidated at root; switched package source from internal registry to PyPI; simplified CI (#1804)
- **Consolidated release automation scripts**: Removed `a2ui_agent/release.sh` and centralized release automation for a2ui-core / a2ui-agent-sdk (#1634)
- **CI/triage housekeeping (chore)**: Added needs-triage labeling (#1781); added auto-flag workflow for actionable issues/PRs (#1801); fixed duplicate triage labeling (#1803); removed noisy notification comments (#1805)

No breaking changes (Python 3.10 support and lockfile consolidation are both backward-compatible / internal build changes).

#### 2026-06-22 to 2026-06-27 Updates (web_core 0.10.3 / angular 0.10.2 / v1.0 spec reorg / Express compiler / Swift renderer)

- **web_core 0.10.3 / angular 0.10.2 release** (#1722): Added `setSignalImplementation` (to swap signal implementations) to web_core; aligned angular with signal changes
- **web_core signal swapping** (#1714): Made signal implementation swappable
- **v1.0 validation support** (#1718): Added support for A2UI v1.0 validation and nested reference path checks
- **Fixed streaming top-level objects** (#1541): Fixed top-level object streaming without list wrapping
- **Implemented A2UI Express compiler / decompiler / parser** (#1726, robustness fix #1741): Implemented full compiler suite for Express format
- **Structured SDK validation diagnostics** (#1738): Introduced structured validation details and unified diagnostic taxonomy
- **Initial Swift renderer commit** (#1711): Added new Swift renderer
- **v1.0 spec reorg: separated pure A2UI protocol from A2A transport extension** (#1725): Reorganized `specification/v1_0/` along the boundary between "pure protocol" and "A2A transport extension"
- **spec docs split** (#1608): Split `renderer_guide.md` into `core_sdk_spec.md` / `framework_adapter_spec.md` / `sdks_spec.md` (v0.9.1 / v1.0)
- **Integrated Express + v1.0 into eval suite** (#1740): Added Express and v1.0 to the Inspect-ai evaluation suite
- **Exported angular testing utils via `@a2ui/angular/testing`** (#1737)
- **lit/vite8 compatibility**: Fixed shell sample to compile with vite8 (#1753)
- **Restored MCP Apps demo (Angular)** (#1780): Restored MCP Apps demo for Angular

#### 2026-06-18 Updates (web_core 0.10.2 release / openUrl protocol restriction / minimal catalog cleanup)

- **web_core 0.10.2 release** (#1708): Bumped web_core package to 0.10.2
- **`openUrl` restricted to http/https only** (#1707): Restricted `openUrl` to accept only https/http protocol links (blocks unsafe schemes, security)
- **Removed minimal catalog from renderers** (#1497): Deleted minimal catalog from renderers while keeping it on the spec side; added simple basic samples (refactor)
- **Adjusted `publish_npm.mjs` for yarn** (#1703): Fixed CI npm publish script to match yarn setup

#### 2026-06-17 Updates (v1.0 strict catalog schema / Text heading variants removal BREAKING / 0.10.1 release prep)

- **spec(v1.0): Strict Catalog JSON Schema Restrictions and Consolidation** (#1629): Tightened and consolidated catalog JSON Schema restrictions
- **BREAKING (v1.0): Removed redundant heading variants from Text component** (#1668, `spec(v1.0)!`): Removed duplicate heading variants from Text component (backward-incompatible spec change)
- **0.10.1 release prep**: CI for 0.10.1 release prep (#1679); moved recipes to community and removed 0.8 example (#1677)
- **angular: Exported MarkdownRenderer in v0.8 public API** (#1658, CHANGELOG entry #1670)
- **react: Added basic catalog integration tests** (#1625); minor component tweaks (#1624)
- **Clarified in docs that a2ui metadata lives on message** (#1557); **lit: stopped testing harness from mutating a2ui messages** (#1623); **lit: fixed a2ui_explorer dev mode** (#1666)
- **Fixed all links + set up CI/VSCode link validation** (#1693); expanded samples list and contribution callout (#1697); fixed individual sample READMEs (#1687, #1685, #1686, #1684, #1683)
- **docs**: Added Lynx to renderer roadmap (#1630); aligned protocol version status labels (#1603)
- **Applied 1P compatibility transformations** (#1655); **dependency bumps**: uv group (#1662); lodash-es 4.17.23 → 4.18.1 (#1665); pyjwt 2.12.1 → 2.13.0 (#1664); 13 npm_and_yarn group updates (#1654)

#### 2026-06-13 Updates (eval inference strategies)

- **Introduced inference strategies in eval**: Added inference strategies to the A2UI evaluation framework (#1602)

#### 2026-06-12 Updates (Full a2ui_core SDK implementation / v0.10 → v1.0 spec promotion)

- **Promoted v0.10 → v1.0 spec**: Next spec directory moved from `specification/v0_10` equivalent to `specification/v1_0`, driving v1.0 updates
- **BREAKING (v1.0): Inlined catalog instructions as Markdown + removed `instructions.md`** (#1590): Changed Catalog schema (`client_capabilities.json`) to accept plain Markdown strings instead of relative file URIs; removed external `instructions.md` and inlined into catalog.json
- **a2ui_core SDK: Introduced reactive Signal / ComponentNode primitives**: Also added text-based layout renderer for testing (#1579)
- **a2ui_core SDK: Implemented component state models / message processing / rendering** (#1578)
- **a2ui_core SDK: Implemented catalog with component validation** (#1577)
- **Refactored Python SDK Catalog architecture for Web Core parity** (#1612)
- **Refactored `a2ui_agent` to depend on `a2ui_core`** (#1582); **added custom cuttable keys config support** (#1581)
- **Decoupled / deprecated core locale**: Switched to plumbing locale through catalog factory (#1610)
- **Added Lynx ecosystem renderer** (#1601); **added AGenUI v0.9 renderer to ecosystem** (#1450)
- **Reorganized samples**: Deleted some and moved others to `samples/community` (#1628)
- **Clarified AG-UI / CopilotKit A2UI guidance** (#1619)
- **CI overhaul**: Refactored GitHub Actions into composite actions + unified CI workflow (#1621); added browser-based integration tests to a2ui_explorer (#1607); added lint enforcement presubmit (#1600); moved Playwright screenshot regression to `test:visual` target (#1635)
- **Dependency bumps**: Updated yarn packages (#1616); 12 uv group updates across 9 directories (#1593)
- **Updated legacy/stable/candidate references on docsite** (#1419)

#### 2026-06-09 Updates (a2ui_core SDK launch / v0.10 spec follow-up)

- **Initialized a2ui_core SDK**: Created `a2ui_core` SDK with schema definitions and basic UI catalog components (Python implementation / web_core `basic_catalog` export, CatalogInterface for v0.9)
- **BREAKING (v0.10): Renamed `theme` → `surfaceProperties` + removed `primaryColor`** (#1525)
- **v0.10 spec: `surfaceId` globally unique per client session** (#1543); **added optional `instructions` field to Catalog schema + removed rules.txt** (#1522)
- **spec: Built-in `@index` function for list templates** (#1572); **defined catalog entity naming rules using Unicode UAX #31** (#1573)
- **Refactored FunctionCall wire schema** to align with protocol specification (#1518)
- **Migrated monorepo to Yarn v4 workspaces** (#1054)

#### 2026-06 Updates (v0.10 spec initialState / MIME convention change / Angular checks type)

- **BREAKING: Changed IANA MIME to `application/a2ui+json`**: Updated mime type to `application/a2ui+json` per IANA convention (POTENTIALLY BREAKING, #1493)
- **Optional `initialState` on v0.10 CreateSurfaceMessage**: Added optional initialState to CreateSurfaceMessage in v0.10 (#1524)
- **Exposed Angular `checks` type on ExtendedProps**: Exposed checks type on ExtendedProps (#1523)
- **Added migration notice**: Added migration notice (#1512)
- **Excluded GeneratedPluginRegistrant**: Ignored/deleted generated GeneratedPluginRegistrant files (#1530)

#### Late 2026-05 Updates (v0.10 spec / A2UI-over-MCP enhancements / Angular ComponentBinder)

- **Fixed Angular ComponentBinder children prop bug**: Fixed children prop bug in v0.9 Angular ComponentBinder; improved unit tests to use real models (#1472)
- **v0.10 spec: Added `steps` property to Slider**: Added `steps` property to Slider in v0.10 basic catalog (#1462)
- **Cleaned up basic_catalog.json refs**: Removed all remaining references to basic_catalog.json (#1463)
- **A2UI-over-MCP: Added static resources / dynamic tools support**: Supported static resources and dynamic tools in A2UI-over-MCP integration (#1471)
- **Reorganized v0.9 / v0.10 catalog files**: Reorganized v0.9 and v0.10 catalog files into dedicated structure (#1452)
- **Aligned web-core formatString with spec**: JSON-stringified objects/arrays in formatString per spec (#1430)
- **Refactored Angular dataModel computed property**: Removed redundant `version()` call in dataModel computed property (#1475)
- **Added v0.8 support to Angular explorer**: Supported v0.8 in Angular explorer app (#1436)

#### Second Half of 2026-05 Updates (v0.10 spec drift + v0.9 streaming/MCP setup)

- **v0.9 streaming parser suite**: Added streaming parser suite for v0.9 (#1394)
- **Organized v0.9 integration tests**: Moved integration tests to `tests/v0_9` directory (#1435)
- **v0.10 spec: Removed Video `posterUrl`**: Removed `posterUrl` from v0.9 Angular and added it to v0.10 spec (#1373)
- **v0.10 spec: `placeholder` parity handling**: Consolidated parity handling into v0.10 spec (#1372)
- **v0.10 spec: Removed Icon `color` prop**: Removed `color` prop from Icon component (#1371, fix #1303)
- **Restored A2UI×MCP sample**: Restored A2UI-over-MCP sample functionality + updated guide and diagrams (#1076, #1439)
- **Added Icon snake_case support**: Updated Icon internals to accept snake_case (#1433)

#### Changes after v0.9 (including web_core 0.9.2+, 2026-05 activity)

- **DataValueSchema recursion depth override**: Allowed overriding recursion depth on v0_8 `DataValueSchema` (refactor, web_core) (#1431)
- **web_core locale support + pluralize fix**: Implemented locale support in web_core and fixed `pluralize` behavior (#1427)
- **Removed Icon `color` prop**: Removed `color` prop from Icon component (#1371, fix #1303)
- **Moved CatalogComponentInstance to web_core**: Structural cleanup (#1426)
- **Modernized A2UI local uploader dashboard**: Integrated workspace_settings sample and refreshed dashboard (#1381)
- **Video links registry for examples**: Created registry of examples with videos (#1407)
- **Fixed AgentExtension parameter order**: Fixed bug where parameter order was reversed when creating AgentExtension (#1393)
- **Renamed Icon `path` → `svgPath`**: Renamed Icon path property to resolve type collision (#1347)
- **Accept/Reject CTAs / MCP tool allowlisting / model selection / dependency linking**: Multiple improvements to A2UI and editor app (model selection, MCP tool allowlist, dependency linking, etc.) (#1363)
- **Android / Jetpack Compose v0.9 renderer**: Added Android/Jetpack Compose v0.9 renderer to ecosystem docs (#1352)
- **Cloud Run deploy gcloud auth prerequisites**: Added gcloud authentication prerequisites to Cloud Run deployment guide (#1341)
- **Excluded React SVG from CSS reset**: Excluded SVG elements from React CSS reset (#1252)
- **Optimized Angular CI workflow**: (#1357)
- **Enforced Python formatting**: Enforced formatting across all Python files (#1340)
- **Renamed Standard Catalog → Basic Catalog**: Unified naming in docs and updated v0.9 status (#1302)
- **Vue3 renderer support docs**: (#873)
- **Added A2UI Inspect AI evaluation framework**: Introduced comprehensive A2UI evaluation framework using Inspect AI (feat(eval))
- **Improved renderer publishing scripts**: Cleaned up renderer publishing scripts via CI (#1317)
- **Fixed restaurant sample streaming duplicate surfaces**: Fixed duplicate surfaces error during streaming in restaurant sample app (#1322)
- **Completely removed C++ Agent SDK**: Deleted all C++ sources and build configs (#1335)
- **Removed Java Agent SDK**: Removed Java agent SDK and referenced Kotlin implementation instead (#1336)
- **Dynamic aria-label for Slider**: Added null checks for component properties and dynamic aria-label on Slider (#1345)
- **Suppressed automatic prettier install**: Stopped prompting to install prettier during formatting (#1342)
- **Enforced repo-wide formatting**: Applied automatic formatting across entire repository (#1338)
- **Fixed non-deterministic Kotlin tests**: Added Kotlin format check and fixed non-deterministic test failures (#1339)
- **Removed `any` from Surface model**: Removed `any` from surface model generic fallback and updated Angular component host (#1314)
- **Added node property null check**: Null check on node properties to prevent runtime errors (#1334)
- **Added strict type for Catalog components**: Added strict types enforcing required property implementations (#1320)
- **Renamed Checkbox value property**: `checked` → `value` (#1332)
- **Resolved module name collision**: Resolved module name collision via explicit qualified names (#1329)
- **Published Markdown-it to npm**: Initial release of markdown-it package (#1304)
- **Pinned markdown-it dompurify to 3.3.1**: Resolved install issue for enterprise proxy environments (#1313)
- **JSON Schema validation via jsoncons**: Integrated jsoncons for robust JSON schema validation (#1274)
- **A2uiCatalog glob pattern support**: Added glob pattern support for file path matching and enabled conformance tests (#1273)
- **Improved Angular catalog component props typing**: (#1265)
- **Migrated Python unit tests to conformance tests**: Converted remaining Python unit tests to conformance tests (#1266)
- **Migrated Kotlin unit tests to conformance tests**: Migrated remaining Kotlin unit tests (#1301)
- **Reorganized MCP samples directory**: Added a2ui-in-mcpapps sample project (#1323)
- **Created AnyDuringSchemaAlignment alias**: Added alias to track Angular `any` issues (#1310)
- **Removed untested platforms**: Deleted unsupported/untested platforms (#1308)
- **URL hash navigation for Angular explorer**: Implemented URL hash navigation in Angular explorer (#1269)
- **Fixed sandbox iframe origin/Vite module pathing**: Resolved sandboxed iframe origin and Vite module path issues (#1318)
- **Added Dart restaurant finder**: Added Dart restaurant finder sample (#1280)
- **Removed Angular Types namespace**: Deleted Types namespace from v0.8 renderer (#1292)
- **Integrated React typechecking**: Added type checking to the build process (#1284)
- **Integrated Kotlin SDK conformance tests**: Integrated Kotlin SDK with A2UI conformance tests (#1129)
- **Migrated React shell to v0.9**: Migrated React shell sample to A2UI v0.9 (#1262)
- **Dart SDK AI workflow**: Added AI-assisted test workflow and initial test definitions (#1251)
- **A2UI Examples live JSON editing**: Added live message JSON editing support (#1243)
- **Angular primaryColor propagation**: Propagated primaryColor to components in basic catalog (#1242)
- **Initial C++ port**: Initial C++ port of Python agent SDK (#1254)
- **Added License fix command**: Added command/UI config for license fixes (#1281)
- **Reorganized MCP guides**: (#1286)
- **Released web_core 0.9.2**: Released web_core package 0.9.2 (#1212)
- **Added obscured enum type**: Added missing `obscured` enum type to v0_8 common types Zod (#1264)
- **Fixed private index URL CI failure**: Fixed CI failure caused by private index URL in uv.lock (#1261)
- **Fixed Gemini Enterprise Agent Engine**: Fixed deployment failure to Cloud Run/Agent Engine (#1256)
- **Fixed `try_activate_a2ui_extension`**: Fixed bug in extension activation (#1234)
- **Clarified createSurface error spec**: Clarified that createSurface on an existing surface returns an error (#1238)
- **Styled React widgets with CSS variables**: Styled widgets using CSS variables in React renderer (#1205)
- **Supported React weight property**: Honored `weight` property in basic catalog (#1215)
- **Fixed Angular Tabs component**: (#1218)
- **Aligned Angular restaurant sample styling**: (#1220)
- **Updated Node.js / publishing scripts**: Improved scripts including Angular tests (#1177)
- **Added AG-UI guide**: Added feature quickstarts and AG-UI guide (#1229)
- **Bumped Python google-adk to 1.28.1 (security)**: (#1219)
- **Split personalized_learning sample**: Split into agent and client (#1244)
- **v0.9 renderer icon override**: (#1146)
- **Ported Angular Restaurant Sample to v0.9**: (#1189)
- **Fixed server error propagation**: (#1203)
- **Bumped renderer packages to alpha.3**: (#1178)
- **A2UI Theater**: Interactive JSONL playback and streaming viewer (#987)
- **A2A SSE streaming**: (#1049)
- **Concurrent surface support**: (#1037)
- **MCP Apps integration**: (#748)

#### Key Changes in v0.9

- **Prompt First design**: Shifted philosophy from structured-output-first to prompt-embedding-first
- **Web Renderers Data Model**: Full data model implementation for Web renderers (#606)
- **Revamped message types**:
    - `beginRendering` → `createSurface`
    - `surfaceUpdate` → `updateComponents`
    - New: `updateDataModel`, `deleteSurface`
- **Simplified component structure**: Moved from key-based wrapper to flat structure
- **Modular schemas**: Split into `common_types.json`, `server_to_client.json`, `standard_catalog.json`
- **Theme property**: Renamed `styles` → `theme`
- **Unified catalog**: Merged components and functions into a single catalog
- **Standardized Enum Case**: Unified to `lowerCamelCase` (#639)

#### Reference Links

- [A2UI Specification](https://github.com/google/A2UI)

---

### ADP (Agent Data Protocol)

**Current version**: v1.3.1 (2026-06)

**Checkout state**: `v1.3.1-33-g040a279` (v1.3.1 + 33 commits, HEAD 2026-08-17)

**Maintainer**: CMU NeuLab

#### 2026-08-17 Updates (1 commit, fix only)

- **fix: Fixed sample-limited dataset extractors** (#307) — fixed sample-limiting handling in dataset extractors. No schema or breaking changes

#### 2026-06-14 to 2026-07-05 Updates (Dataset expansion + consistency audit tools)

- **Added new datasets**: OpenThoughts-Agent / Finch (#274), SWE-ZERO 12M (#258), enterpriselab (#271)
- **Added cross-dataset consistency audit** (#305); **added sample fixture drift checker** (#302)
- **Separated LiteCoder terminal prompts**: Separated from tasks (#293) and extracted helpers (#301)
- **Fixed role normalization**: AndroidControl (#286), Android in the Wild (#285), OmniAct initial task order (#287)
- **Adapted to OpenHands SDK `<SOUL>` tag system prompt wrapping** (#272); native async condenser generation (#264)
- **Removed placeholder / empty system messages**: Toucan (#291), ORCA AgentInstruct (#290), OpenResearcher (#289), Nebius SWE-agent (#288)

#### 2026-06-13 Updates (ATIF conversion pipeline)

- **Added ATIF conversion pipeline**: Added conversion pipeline to Agent Trajectory Interchange Format (ATIF) (#256)

#### v1.2.0 / v1.3.0 / v1.3.1 Releases (2026-05 to 06)

- **Expanded SFT datasets**: Added LiteCoder Terminal SFT (#255), NVIDIA SWE-Zero OpenHands trajectories (#246), hybrid-gym trajectory (#248)
- **OpenHands SDK condenser SFT**: `openhands-sdk` emits condenser prompt SFT data (#244); added SDK-backed OpenHands SFT converter (#241)
- **Condenser replay / identity**: Condenser replay on in-memory event history (#252); emit identity trajectory when condensation is unnecessary (#251)
- **Hugging Face chat-template compatibility**: Made SFT samples compatible with HF chat-template (#242)

#### v1.0.0 / v1.1.0 Releases (2026-05)

- **v1.1.0**: Formalized promoting "available APIs" to trajectory fields (#212)
- **v1.0.0**: Introduced standardized schema versioning — formalized schema version, switching from implicit to mandatory explicit versioning (#211)
- **Optional OpenHands browser tools**: Made OpenHands browser tools optional for non-web datasets (#213)

#### Breaking Changes

| Change | Impact |
|---|---|
| Jump to v1.0.0 (explicit schema versioning required) | Legacy implicit schemas now require explicit version declarations |

#### Recent Changes (Pre-1.x)

- **Catalog dataset guidelines**: Added Catalog dataset guidelines and PR review workflow (#186)
- **Added per-step reward field**: Added optional `reward: float | None` field to Action / Observation schemas. Supports carrying per-step reward signals in RL training data. Inherited by all 6 concrete action/observation types. Defaults to None, leaving existing datasets unaffected (#183)
- **Added CoderForge-Preview dataset**: Coding trajectory dataset (#167)
- **Added Nemotron Terminal Corpus dataset**: Terminal corpus dataset (#165)
- **Added Toucan dataset**: (#163)
- **Added comprehensive documentation**: Completed README/LICENSE for all supported datasets and agents, plus mini-coder integration (#162)
- **Added SWE-Playground Trajectories dataset**: (#161)
- **Implemented Toucan-1.5M dataset**: (#154)
- **mini-coder trajectory dataset**: (#155)
- **TextObservation `name` field**: Added optional `name` field (#150)
- **MCP integration / SWE Agent conversion cleanup**: Added MCP, fixed SWE Agent conversion, cleaned up agent conversions (#148)
- **SWE Agent `std_to_sft` conversion script**: (#140)
- **Converted `send_msg_to_user` actions → `MessageAction`**: (#145)
- **Nnetnav fixes & Go-Browse filter**: (#144)

#### Key Changes

- **Dataset support**: SWE-Playground Trajectories, Toucan-1.5M, mini-coder trajectories, CoderForge-Preview, Nemotron Terminal Corpus, Toucan
- **MCP integration**: Agent tooling integration
- **Multi-agent support**: OpenHands, SWE-agent, AgentLab
- **Pydantic type safety**: Strengthened schema validation

#### Reference Links

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**Current version**: protocol / spec **1.0**, TS SDK (`@ag-ui/core/client/encoder/proto`) **1.0.2** (2026-10-05), Python protocol **1.0.0**, .NET SDK (`AGUI.*`) **1.0.1** (2026-10-12). Adapters verified in this update: **@ag-ui/claude-agent-sdk@0.0.6** / **ag-ui-claude-sdk@0.2.1** / **@ag-ui/mastra@2.0.1** (2026-10-12)

**Checkout state**: `704b190e4` (HEAD 2026-10-12 = `@ag-ui/claude-agent-sdk@0.0.6` + 5 commits)

#### Verified 2026-10-13 (AG-UI 1.0 follow-up releases: Claude Agent SDK / Mastra / .NET 1.0.1)

[Diff for this update](https://github.com/ag-ui-protocol/ag-ui/compare/903a9ab9...704b190e4). The adapters and .NET versions below are released; LangGraph and adk-middleware fixes are on HEAD.

- **@ag-ui/claude-agent-sdk 0.0.5 / 0.0.6**: Requires AG-UI 1.0 (`@ag-ui/core` / `@ag-ui/client` >=1.0.0); `RUN_STARTED` declares `protocolVersion`. 0.0.6 defaults `settingSources` to `[]` so runs do not load host `~/.claude` settings or working-directory `CLAUDE.md` (mitigation for claude-agent-sdk 0.2.x). Python `ag-ui-claude-sdk@0.2.1` does the same
- **@ag-ui/mastra 2.0.0 / 2.0.1**: Migrated to AG-UI 1.0; interrupts use only the `RUN_FINISHED` interrupt outcome and `RunAgentInput.resume` (2.0.0). 2.0.1 fixes `selectNewMessages` to forward the contiguous tail after the first unsaved message
- **fix**: Kept LangGraph A2UI subagent on the caller's event loop and separated the recovery worker (#3041); persisted adk-middleware processed message ledger alongside run input (reloaded on each run)
- **.NET**: `AGUI.*` 1.0.1 fixes 1.0 conformance (non-breaking). New tags: `@ag-ui/claude-managed-agents@0.0.2` / `@ag-ui/a2a-middleware@0.0.4`

##### Breaking Changes and Migration Verified in This Update

- **Mastra 2.0.0 / 2.0.1**: Requires `@ag-ui/core` / `@ag-ui/client` >=1.0.0 and optional peer `@copilotkit/runtime` ^1.76.0. Removed legacy CUSTOM `on_interrupt`, `forwardedProps.command`, and `emitInterruptOutcome`; migrate to `RUN_FINISHED` interrupt outcome and `RunAgentInput.resume`. Also removed legacy binary content parts and `registerCopilotKit`; re-verify wire output because tool-result URL formatting and capability declarations changed. Tool approvals accept `true` / `{ approved: true }` and reject cancel / `{ approved: false }`; any other value triggers a run error

Sources: [Mastra CHANGELOG](https://github.com/ag-ui-protocol/ag-ui/blob/704b190e4/integrations/mastra/typescript/CHANGELOG.md), [Claude adapter CHANGELOG](https://github.com/ag-ui-protocol/ag-ui/blob/704b190e4/integrations/claude-agent-sdk/typescript/CHANGELOG.md).

#### 2026-09-16 to 2026-09-22 Updates (**AG-UI 1.0 Release**: spec freeze + 1.0.0 SDKs + Java Spring integration)

- **spec 1.0 freeze** (#2783): Froze draft spec as 1.0. Schema is the single source of truth; all SDK protocol types generate from it, and behavioral rules are normative (BCP 14). `PROTOCOL_VERSION` is "1.0"
- **1.0.0 SDK release** (2026-09-17): @ag-ui/core@1.0.0 / @ag-ui/client@1.0.0 / @ag-ui/encoder@1.0.0 / @ag-ui/proto@1.0.0, ag-ui-protocol@1.0.0 (Py), AGUI.Abstractions/Formatting/Protobuf/Client/Server@1.0.0 (.NET)
- **Major 1.0 protocol changes (diff from 0.x)**:
    - `RUN_FINISHED.outcome` (success/interrupt/cancelled) + Interrupt + resume entry
    - Subagent events (SUBAGENT_STARTED/FINISHED/ERROR + subagentRunId)
    - Deprecated `THINKING_*` → replaced with `REASONING_*` family (translated at compatibility boundary)
    - ACTIVITY_SNAPSHOT / ACTIVITY_DELTA structured progress events
    - Normative distinction between unknown and malformed
    - HTTP + Protobuf binary wire spec
    - Moved AgentCapabilities to schema definition
    - `TOOL_CALL_RESULT.content` accepts content parts (renamed InputContent → ContentPart; wire unchanged)
- **Backward compatibility**: 0.x agents work with 1.0 clients (always-on compatibility boundary + version-gated middleware; shims documented in DEPRECATIONS.md with 12-month expiry)
- **Java Spring integration** (#2147): Spring AI integration (ag-ui-4j)
- **Protocol version declaration**: Clients declare the protocol version they speak and determine producer version (Py/.NET)
- **1.0 migration guide** (docs/migrating-to-1-0.mdx)
- **fix**: LangChain JSON decode error (#2681), watsonx lazy fastapi (#2747), typed runagent state (#2752), crewai uvicorn cap (#2769), optional copilotkit peer (#2763), license metadata publishing (#2761), client snapshot ordering (#2709)

#### 2026-09-01 to 2026-09-15 Updates (release/2026-09-08 to 09-14: New MCP Apps middleware + mastra 1.1.4 + strands 0.4.0 + Java 0.1.1)

- **@ag-ui/mcp-apps-middleware 0.1.0 / 0.1.1**: Added middleware connecting MCP Apps to AG-UI; advertises standard HTML MIME type (#2722)
- **@ag-ui/mcp-middleware 0.0.2**: Fixed peer client in MCP middleware (#2689)
- **@ag-ui/mastra@1.1.4**: Preserved terminal retry tripwire reason; dropped replayed tool call results; preserved developer instruction semantics; retained streamed tool args during background activity; prevented triple TOOL_CALL emission after resume
- **aws-strands**: **ag_ui_strands@0.4.0** / **@ag-ui/aws-strands@0.3.0** — preserved attachments and reported dropped media; stopped forwarding template-bound management tools
- **langgraph**: Preserved arguments across streamed text termination and tool call boundaries (#2607)
- **a2ui-middleware**: Kept action tool IDs within provider limits + action retry (#2712)
- **Java SDK 0.1.1** (java-client / java-core / java-server), **ag-ui-crewai@0.3.1** (fixed context field), **ag-ui-langgraph@0.0.45**
- **adk**: Accepted non-object JSON for frontend tool results
- No breaking changes to core / protocol event specs (TS SDK stayed at 0.0.59)

#### 2026-08-01 to 2026-08-31 Updates (521 commits: Added subagent lifecycle to protocol + metadata on every event + Java SDK 0.1.0 + aws-strands security hardening)

**Protocol additions (additive)**:

- **Added subagent lifecycle events + `subagentRunId` attribution to protocol** (#2350): Propagated across core / client / Python / protobuf (PNI-197) / .NET / langgraph. Typed `SubagentFinished` outcome (success | suspended), per-interrupt attribution, version-gated backward-compat shim for pre-subagent agents. LangGraph supports subagent attribution / lifecycle / HITL suspension / `subagent_visibility` (#2528)
- **Added metadata to all events / messages** (PNI-198, #2349 + review #2535): Core metadata and merge primitives, Python / protobuf (binary wire) / .NET, metadata on resume entries (PNI-317, #2458)

**BREAKING (integration boundary)**:

- **Made CORS opt-in in aws-strands TypeScript for auth parity with Python** (`fix(aws-strands)!`) — no longer allows CORS with credentials by default. No protocol event spec incompatibility

**aws-strands hardening (largest area of work in August)**:

- **URL fetch security**: Restricted fetch schemes, rejected redirect downgrades, **prevented DNS rebinding**, enforced URL fetch ceilings on redirect hops, blocked zero-net URL targets, contained hostile HTTP responses, validated server-side URL sources
- **Closed auth fail-open paths** (multiple); decided CORS credentials per-request instead of via policy; rejected credentials for null origins
- **Native frontend waits**: Delegated frontend waits to native interrupts; added `frontend_tool_call` interrupt reason to core/client; rejected unsafe native frontend identities; protected parked orchestrators; rejected second concurrent run on one thread (Py)
- **Citations**: Emitted Bedrock metadata as raw events; surfaced model citations on annotated messages; citations demo (TS/Py)
- **Multi-agent**: Driven multi-agent orchestrators from Python bridge; invocation state forwarding; per-thread agent config route

**langgraph (TS/Py)**: Boundary checkpoint durability fixes (snapshot pinning / state cache / expiry / root-scoping), documented malformed-input contract and applied to both runtimes, multimodal hardening (MIME-less data URL / subclassed media / attachment modality recovery / nameless attachment extensions), raw event emission toggle, defined `exit` custom event as advisory (PNI-386)

**SDK / Integrations**:

- **Released AG-UI Java SDK 0.1.0** (java-client / java-core / java-server)
- **New TS integrations**: @ag-ui/crewai (0.0.4) / @ag-ui/ag2 (0.0.2) / @ag-ui/agno (0.0.6) / @ag-ui/llamaindex (0.2.0, multimodal) / @ag-ui/pydantic-ai (0.0.3) / @ag-ui/langchain (0.0.3)
- **ag-ui-crewai@0.3.0 (Py)**: Ended empty streams on conversational runs; bounded/contained abandoned Conversational Flow workers; simplified OpenAI Responses handling
- **mastra**: Preserved segment identity (buffered text); propagated cancellation from Observable teardown (#2288)
- **adk**: Escaped state JSON pointer paths
- **.NET**: 0.0.5 → 0.0.6 (multimodal / metadata / media type handling fixes, subagent events)
- **Release infra**: Generated reviewed changelog entries from git history and published to release PRs / GitHub Releases

#### 2026-07-28 to 2026-07-31 Updates (Added Claude Managed Agents integration + full crewai 1.x support; published release/2026-07-28 and 07-31)

- **Added Claude Managed Agents integration** (TypeScript / Python / .NET, #2247). Published `AGUI.ClaudeManagedAgents@0.0.1` to NuGet. Hardened by rejecting lone surrogate entities and blank thread IDs, bounding/cancelling gated operations, and isolating session store keys
- **Full overhaul for crewai 1.x** → **`ag-ui-crewai@0.2.1`**: Drove crewai 1.6+ flows via StreamFrame path (CPK-7719), runtime capability probe, emitted reasoning as `REASONING_*` events (PNI-128), emitted backend tool / MCP tool calls as `TOOL_CALL_*` events (PNI-138 / PNI-130), async HITL interrupts + `RUN_FINISHED.outcome` (PNI-133), opt-in flow checkpointing / thread persistence (PNI-134), shared-state streaming (PNI-132), multimodal input passthrough (PNI-135), hierarchical multi-agent attribution (PNI-131)
- **A2UI generative-surface support in crew-ai** (all 4 pillars) + dojo demos (PNI-137, #2276)
- **Integration compatibility boundary change (note)**: Pinned crewai to `>=1.0,<2`, moved `crewai-tools` to optional `[tools]` extra, migrated Poetry → uv (CPK-7716). **No incompatible changes to protocol event spec**

#### Updates as of 2026-07-27 (Published release/2026-07-22 + Java core client/server + strands session reconcile)

- **Tagged release/2026-07-22** + released **ag_ui_strands@0.2.3 (Py)**
- **Added AG-UI Java (ag-ui-4j) core client/server** (#2057) + pinned to Java 17 (#2221)
- **strands-py session reconcile** (OSS-563, #2231), **mastra responses msg-id sanitize** (OSS-381, #2227), **raw event opt-out** (OSS-607, #2244), fixed ADK tool-call thought signatures (#2073)
- **Fixed CORS credentialed wildcard** (#2204), cleaned schema `oneOf`→`anyOf` (#2027), fixed request-state flush delegation (#2209)

#### Updates as of 2026-07-18 (Published release/2026-07-15 + .NET SDK docs)

- **release/2026-07-15**: Published new release tag
- **.NET SDK docs/fixes**: Fixed dotnet reasoning text message-id collision (#2200); added docs for .NET client/server verification and package parity notes (#1971)
- **Other**: Updated GitHub Actions dependencies (renovate); made go-dojo the default Go example (#2047). No breaking changes

#### 2026-07-02 to 2026-07-06 Updates (mastra 1.1.0/1.1.1 release + .NET NuGet release support)

- **@ag-ui/mastra@1.1.0 / 1.1.1 release** (2026-07-02 / 07-03): Officially tagged Mastra interrupt/resume work from the prior window. 1.1.1 includes fast-json-patch default import fix (#2115)
- **Mastra: Surfaced Observational Memory as AG-UI activity events** (OSS-92)
- **Mastra: Remote parity + write-back for shared-state streaming**: Shared state delivery and client edit sync via `STATE_DELTA` (OSS-414)
- **Mastra: Exposed `tracingOptions` passthrough and execution traceId** (#2083)
- **dotnet: NuGet release support**: Added NuGet release to AG-UI workflow; bumped sdk-dotnet AGUI.\* from 0.0.2 → 0.0.3 (including package trimming and signing fixes)
- **Added A2UI integration demos**: Local+remote A2UI demo and fixed-schema demo
- **CI: Migrated to Renovate config** (#1782, #1790); removed Java GitHub Actions (#2090)
- **fix: Skipped missing-payload chunks without aborting the stream** (#1635)

#### 2026-07-01 Updates (Mastra interrupt/resume overhaul + .NET SDK package name fix, all unreleased)

> No new package release tags were cut in this window (`677dfca1` 2026-06-26 → `b91f32ea` 2026-07-01). All items below are unreleased changes on `main`, and current package versions remain unchanged from the previous update. The main theme is aligning Mastra interrupt (suspend/ask/resume) behavior with LangGraph.

- **Mastra: native `useInterrupt` suspend/resume**: Implemented full suspend→ask→resume flow on top of Mastra's `tool-call-suspended`→`on_interrupt` bridge (aligned in *behavior* with LangGraph; payload shape remains unaligned). Fixed resume to round-trip the runId returned by Mastra's suspend chunk (`chunk.payload.runId ?? chunk.runId`) instead of using the AG-UI runId, which failed with "No snapshot found". Added local-only "interrupt" demo to dojo (#2040, OSS-88)
- **Mastra: Enabled standard interrupt-outcome by default (breaking change)**: `emitInterruptOutcome` now defaults to TRUE (opt-out). Uses structured `RUN_FINISHED.outcome` as the canonical interrupt signal and consumes the standard `RunAgentInput.resume` channel. Encodes snapshot runId into interrupt id as `${runId}::${toolCallId}`. **Requires CopilotKit client >= 1.61.2** (older clients leave runs stranded). Legacy `on_interrupt` CUSTOM event still fires as before (#2059, OSS-380). Preceded by introducing the opt-in standard RUN_FINISHED interrupt-outcome path (#2060, OSS-379)
- **Mastra: Remote agent resume-after-interrupt support**: Round-tripped suspend state and resume command via `@mastra/client-js` and removed the "unsupported" error path. Unified `on_interrupt` payloads and resumed-run event sequences between remote and local. Added capability-guard with a clear upgrade error for older client-js without `resumeStream()` (#2064, OSS-380)
- **Mastra: Mapped background tasks to AG-UI activity events**: Mapped `background-task-*` chunks to `ACTIVITY_SNAPSHOT` + `ACTIVITY_DELTA` (activityType `mastra-background-task`, round-tripping taskId in messageId). Suppressed normal tool rendering. Bumped `@mastra/core >= 1.29` and added dojo "Background Agents" demo (real LLM) (#2055, OSS-93)
- **Mastra: Progressive streaming for tool-call args**: Previously buffered tool calls and emitted a single `TOOL_CALL_ARGS`, rendering generative UI all at once. Now consumes `tool-call-delta` and forwards individual `TOOL_CALL_ARGS` (wrapped in `TOOL_CALL_START`/`END`) for progressive rendering. Older `@mastra/core` 1.0.x falls back to single flush (#2066, OSS-393)
- **Mastra: Fixed thread history duplication in multi-turn runs**: Stopped duplicating thread history across multi-turn runs; preserved message identity while syncing to CopilotKit (#2054, OSS-105 / #1556)
- **Mastra: Ensured `input.context` propagates to tools**: Resume paths (local/remote) previously reused `RequestContext` verbatim and silently dropped new `input.context` on resumed runs. Consolidated all paths into a single `applyInputContext()` and set it under the `"ag-ui"` key (idiom-equivalent to LangGraph's `state["ag-ui"].context`) (#2065, OSS-392)
- **Mastra: Allowed CopilotKit 1.x runtime peer** (#1730)
- **.NET SDK docs: Renamed hosting package to actual name `AGUI.Server`**: Corrected `AGUI.Hosting.AspNetCore` in docs to the actual published name `AGUI.Server` (namespaces, install commands, usings, nav groups). Fixed dependency note to clarify it is a "framework-agnostic Microsoft.Extensions.AI adapter with no dependency on Microsoft.AspNetCore.App". Also changed .NET logo hover CSS to suffix match (`6f33b409`)
- **langgraph (test-only, no behavioral changes)**: Added tests for opt-in interrupt outcome + `resume[]` round-trip; fixed stale comment (`copy`→`model_copy`) (#2053). Verification of existing structured interrupt/resume only
- **build/deps misc**: Pinned hono to a single version to fix dojo build; aligned `@mastra/*` in `client-cli-example` to 1.47 to match bridge; bumped Mastra to latest for remote resume (OSS-380)

#### 2026-06-26 Updates (New AG-UI .NET SDK / langgraph structured interrupt/resume / ag_ui_adk 0.7.0 / aws-strands 0.2.3)

- **New AG-UI .NET SDK integration (0.1.0-preview)** (#1963): Added full SDK for C#/.NET. Includes wire-format `AGUI.Abstractions`, SSE `AGUI.Formatting`, IChatClient-based `AGUI.Client` / `AGUI.Server`, protobuf transport, OpenTelemetry tracing, dojo e2e, and TS-client ↔ C#-server cross-language test harness. Configured for NuGet 0.1.0-preview (no release tag yet)
- **Package releases**: Bumped ag_ui_adk to 0.7.0, @ag-ui/aws-strands (TS) to 0.2.3 (via 0.2.2), and ag_ui_strands (Py) to 0.2.2 (tagged in release/2026-06-23 and 2026-06-24)
- **langgraph: Structured interrupt/resume support** (#1945, issue #700): Added structured interrupt/resume (opt-in, default off). **Requires `langgraph>=0.6.0`** for `Interrupt.id`
- **langgraph: DeepSeek `reasoning_content` support** (#1256): Handled DeepSeek-format `reasoning_content` inside `additional_kwargs`
- **langgraph: Stable messageId reuse** (#1317): Reused stable messageId across text→tool→text runs (node-scoped rather than run-scoped)
- **langgraph: Deprecation-warning cleanup** (#1215): Backward-compatible fallback for `context_schema` / `get_config_jsonschema`; non-deprecated jsonschema API
- **langgraph misc**: Detected content edits with same id (#1748); handled non-string dict keys (UUID) in `dump_json_safe` (#1741); stripped trailing slash on `/health` path (#700)
- **aws-strands robustness**: Drained stranded tool calls before `RUN_FINISHED` on halt; emitted non-empty tool result for empty content; forced `render_a2ui` turn to complete dynamic A2UI; added a2ui_fixed_schema demo (#2021, #2023)
- **Agno feature expansion** (#1895): Expanded AG-UI feature set and bumped agno to `>=2.6.19`
- **A2UI integration skill (docs)** (#1993, #2043): Added AG-UI A2UI integration skill; updated for middleware API + automatic catalog-forwarding injection DX
- **Clarified optional RunAgentInput fields** (#2028): Clarified client-provided run tools and optional `run_agent_input` fields

#### 2026-06-20 Updates (langgraph/aws-strands/middleware releases / ADK A2UI sub-agent rendering OSS-158 / agent resolver / strands HITL fix)

- **Package releases**: Bumped @ag-ui/a2ui-middleware to 0.0.10, @ag-ui/aws-strands (TS) + ag_ui_strands (Py) to 0.2.1, and @ag-ui/langgraph (TS) + ag-ui-langgraph (Py) to 0.0.42 (tagged in release/2026-06-19)
- **Ported A2UI sub-agent rendering tool to ADK (OSS-158)**: Added A2UI sub-agent rendering tool with recovery loop, auto-injected `generate_a2ui` tool (Strands parity), reconstructed prior A2UI surface on intent="update", surfaced hard-failure envelope when recovery is exhausted, included fixed-schema A2UI dojo demo + Gemini-shaped aimock fixtures. Declared google-adk floor at 1.28.1 and allowed `<3.0` (removed `<2.0` cap)
- **langgraph: Progressive A2UI paint**: Streamed inner `render_a2ui` deltas for progressive rendering (both TS and Py); streamed A2UI render via native `OnChatModelStream` and removed custom-event relay; used shared `split_a2ui_schema_context`; required `ag-ui-a2ui-toolkit>=0.0.4`
- **aws-strands: A2UI catalog parity + streamed catalogId stamp** (both TS and Py); **strands HITL fix**: Forwarded HITL tool results on resume instead of discarding them
- **a2ui-middleware: Deduplicated final-envelope paint per surfaceId**
- **Added minimal ADK agent resolver**: Resolved agent from assistant message history; scoped tool result history routing; preserved adk author on assistant messages; added example for tool-result resolver pinning
- **adk-middleware CI**: Added google-adk 2.x test leg as allowed-to-fail (informational/green) (#1947); re-resolved uv.lock to latest google-adk 1.x (#1946)

#### 2026-06-17 Updates (a2ui-toolkit 0.0.4 / a2ui-middleware 0.0.9 / schema-context split / licensing)

- **Bumped a2ui-toolkit to 0.0.4**: Bumped @ag-ui/a2ui-toolkit (TS) / ag-ui-a2ui-toolkit (Py) to 0.0.4 (via pyproject toolkit version revert)
- **Bumped a2ui-middleware to 0.0.9**: Bumped @ag-ui/a2ui-middleware to 0.0.9
- **a2ui-toolkit: Added A2UI schema-context split + catalog resolver (both TS and Py)**: Split schema and context and introduced catalog resolver
- **a2ui-middleware: Fallback to frontend-registered catalog id**: Fell back to frontend-registered catalog id when catalog id is unresolved
- **aws-strands fixes**: Strands hello injection fallback (#1761); centralized tool snapshot predicate; avoided phantom tool-call parents without snapshots
- **dojo: Stabilized chat e2e sends**
- **Licensing cleanup (#1624)**: Bundled LICENSE in ag-ui-protocol Ruby gem; aligned @ag-ui/spring-ai to Apache-2.0, @ag-ui/langchain to MIT, and @ag-ui/mastra to Apache-2.0 upstream; completed LICENSE + license-field coverage across publishable packages; reordered `license-files` after `version` in adk/aws-strands pyproject

#### 2026-06-15 Updates (aws-strands integration 0.2.0)

- **Bumped aws-strands integration to 0.2.0**: Bumped integration-aws-strands-ts (@ag-ui/aws-strands@0.2.0) and integration-aws-strands-py (ag_ui_strands@0.2.0) to 0.2.0 (minor bump following A2UI subagent architecture port). Tagged in release/2026-06-15

#### 2026-06-13 Updates (TS SDK 0.0.57 / aws-strands A2UI subagent / langgraph fixes)

- **Bumped TS SDK suite to 0.0.57**: Bumped @ag-ui/core / client / encoder / proto / create-ag-ui-app to 0.0.57
- **Ported A2UI subagent architecture to aws-strands**: Ported A2UI subagent architecture to both Python and TypeScript adapters. Aligned default CORS origin to literal `"*"` matching the Python adapter
- **client: Bound default fetch on HttpAgent**: Bound default fetch on HttpAgent to prevent "Illegal invocation" in browsers
- **a2ui-toolkit: Child-reference cycle detection**: Validated singular children and detected child-reference cycles (de-flaked deep child-chain cycle test; documented ref-field scope for child adjacency builders #1948)
- **langgraph fixes**: Used ToolMessage id (with tool_call_id fallback) in TOOL_CALL_RESULT; preserved runtime config in `prepare_regenerate_stream` (#1749); forwarded runtime context via kwargs; losslessly round-tripped reasoning content across turns
- **dojo: Adopted CopilotKit 1.60.1** (via 1.60.0); disabled langchain agent due to langchain-core version conflict; made weather demo tools deterministic under test
- **Multiple merged fixes**: Multi-LRO resume gating, duplicate terminal events, reasoning dedup in messages snapshot, ADK session read cache, LLMAgent HITL confirmation, ADK LRO duplicate tool call, client subscriber clone OOM, SSE drop recovery regression test, canary publish action, proto license metadata

#### 2026-06-09 Updates (TS SDK 0.0.56 / A2UI toolkit)

- **Bumped TS SDK suite to 0.0.56**: Bumped @ag-ui/core / client / encoder / proto / create-ag-ui-app to 0.0.56
- **Published @ag-ui/a2ui-toolkit 0.0.3**: Published A2UI integration toolkit, used by langgraph TS integration (@ag-ui/langgraph@0.0.40). Includes A2UI dynamic schema params fix
- **Bumped langgraph integrations**: ag-ui-langgraph@0.0.41 (Py) / @ag-ui/langgraph@0.0.40 (TS)
- **adk-middleware**: Updated default live-test model to gemini-3.5-flash

#### Early 2026-06 Updates (TS SDK 0.0.55 / protocol 0.1.19 / mcp-middleware)

- **Preserved client run_id in RUN_FINISHED**: Retained client's run_id in RUN_FINISHED event (#1582)
- **integration-langgraph-ts 0.0.36**: Bumped langgraph TS integration to 0.0.36
- **sdk-py protocol 0.1.19**: Bumped Python SDK protocol to 0.1.19
- **Batch release of TS SDK packages 0.0.55**: Bumped client / core / encoder / proto to 0.0.55
- **event reducer: Fixed tool result ordering**: Placed tool results after their corresponding tool calls (client)
- **langgraph TS createAgent inner graph export**: Exported inner graph
- **Added @ag-ui/mcp-middleware**: Added mcp-middleware release scope

#### Key Changes in release/2026-04-22

- **State Snapshot/Delta compaction**: Compacted STATE_SNAPSHOT and STATE_DELTA events per run into a single final state, applying deltas via fast-json-patch (RFC 6902) (#1535)
- **Idempotent release-python tag creation**: Made release-python tag creation idempotent on retries (#1548)
- **Expanded interrupt-aware run lifecycle draft**: Extended documentation proposal (#1555)
- **Python SDK 0.1.18**: Released Python SDK 0.1.18
- **Added AgentCapabilities to Python SDK**: Added AgentCapabilities type to Python SDK (#1307)
- **LangGraph orphan tool message preservation**: Preserved orphan tool message fix in `langgraph_default_merge_state` (#1494)
- **Strands template hooks forwarding**: Forwarded template hooks to per-thread `StrandsAgentCore` (#1561)
- **Mastra resourceId forwarding**: Always forwarded `resourceId` in working-memory sync Memory calls (#1560)
- **Multiple LangGraph empty string/fallback fixes**: `resolve_message_content`, `handle_reasoning_event`, `handle_node_change`, etc. (langgraph family)
- **LFS migration**: Tracked `test-image.png` with LFS; added pre-commit hook to detect raw binaries bypassing LFS
- **Talk to Us form**: Added "Talk to Us" form to documentation sidebar (#1554)
- **Fixed `prepareRegenerateStream` config forwarding**: Properly merged `assistantConfig` and forwarded config (#1509)
- **Reverted Python wheel permissions fix**: Reverted commit that broke wheel builds (#1508)

#### Key Changes in release/2026-04-15

- **AWS Strands package bump**: Updated AWS Strands package versions (#1531)
- **AWS Strands kwargs forwarding fix**: Forwarded all template kwargs to per-thread agents via signature introspection (#1529)
- **LangGraph package bump**: Updated LangGraph integration package versions (#1530)
- **CVE-2026-25528 security fix**: Fixed security vulnerability via dependency version bump (#1527)
- **Fixed state streaming across sequential tool runs**: Fixed issue where state failed to stream when tools ran consecutively (#1526)
- **A2UI middleware v0.9 support**: Supported v0.9 inline catalog schema format
- **Implemented ADK `getCapabilities`**: Added `getCapabilities()` and `/capabilities` endpoint to ADKAgent (#1475)
- **ADK Dependabot vulnerability fixes**: Fixed critical/high vulnerabilities in adk-middleware (#1517)
- **Eliminated redundant ADK session scans**: Removed redundant session scans and fixed stale tool-call cleanup (#1514, #1515, #1516)
- **Multi-instance session cache hydration**: Fixed multi-instance cache (#1484)
- **Kotlin Ktor 3.2.4 upgrade**: Ktor 3.1.3 → 3.2.4 (#1520)
- **reasoning/thinking events**: Multi-agent support and event throttling middleware (#1427)
- **BinaryInputContent backward-compat middleware**: Added legacy BinaryInputContent compatibility middleware (#1422)
- **Strands.py v0.1.5**: Released Strands.py

#### Key Changes in release/2026-03-28

- **Release automation**: Consolidated release automation pipeline
- **ADK middleware O(1) optimization**: Improved lookup performance in ADK middleware

#### Previous Key Changes

- **Claude Agent SDK integration**: Added Claude Agent SDK integration (#916)
- **Langroid integration**: Integrated Langroid framework and Dojo demo app
- **Bedrock Converse API compatibility**: Fixed Bedrock Converse API compatibility in LangGraphAgent (#1300)
- **Reasoning Spec**: Added reasoning specification (#1050)
- **Multimodal spec**: Added multimodal spec (#1084)
- **Ruby SDK**: Full protocol implementation (#865)
- **Dart SDK v0.1.0**: Full protocol implementation
- **Framework integrations**: Support for LangGraph, Mastra, CrewAI
- **State management**: JSON Patch delta (RFC 6902) support

#### Reference Links

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**Current version**: Continuous deployment (no version tags)

**Checkout state**: HEAD `38a2ff8` (2026-07-09, no tags)

**Maintainer**: Anthropic

**As of 2026-07-18**: No changes to the spec itself in this period. Commits since early July are only client showcase / docs additions (`docs/specification.mdx` was last meaningfully updated in June or earlier). No breaking changes

#### 2026-07-01 Updates (Logo asset adjustment only)

- **Adjusted square client logo scaling** (#446): Image asset change only. No spec or code changes

#### 2026-06-12 to 2026-06-30 Updates (Client showcase addition only)

- **Added Deep Code to client list**: Added Deep Code entry and dark/light SVG logos to `docs/snippets/clients.jsx`. Does not touch spec (#421)

More than a month has passed since the previous record (`5d4c1fd`, 2026-05-21), but this was the only upstream activity. No spec/schema changes, and still zero version tags.

#### Second Half of 2026-05 Updates

- **Fixed name field character range (allowed digits)**: Updated spec name field character range to allow alphanumeric + digits (#384)
- **Added bub client**: Added bub to client list (#340)
- **Added Superconductor client**: Added Superconductor to ClientShowcase (#377)
- **Added Vita logo**: Added Vita logo to Agent Skills logo carousel (#332)
- **Added Tabnine client**: Added Tabnine to ClientShowcase (#349)
- **Expanded README.md content**: Pulled home.mdx content into README.md to make README standalone

#### Recent Changes

- **Refreshed landing page**: Added "What are Agent Skills?" and "How do Agent Skills work?" sections to home.mdx; merged Why/What sections; restructured Adoption
- **Added fast-agent client**: Added fast-agent to client list and adjusted logo size (#327, #328)
- **Added Google AI Edge Gallery**: Added to Agent Skills client list with source code URL
- **Added Workshop.ai client**: (#314)
- **Added nanobot client**: (#315)
- **Simplified LogoCarousel**: Extracted shared `clients.jsx` and margin overrides
- **Reduced Get Started cards**: Condensed "Get started" in home.mdx to 2 cards: Quickstart and Specification
- **Consolidated Progressive disclosure links**: Unified links to specification.mdx
- **Deleted `what-are-skills.mdx`**: Removed redundant documentation
- **Client Showcase page**: Web-based client showcase page (#291)
- **Shuffle/alphabetical toggle**: Added toggle to ClientShowcase

#### Key Changes

- **Added Discord links**: Added Discord links to README and docs
- **Added Kiro logo**: Added Kiro logo
- **Runtime version examples**: Added runtime version examples to compatibility field
- **Quickstart guide**: Added quickstart guide for skill authors
- **Best practices guide**: Added best practices guide for skill authors (#224)
- **Apache 2.0 license**: Added top-level LICENSE (#122)

#### Reference Links

- [AgentSkills](https://agentskills.io)

---

### MCP (Model Context Protocol)

**Current version**: **2026-07-28 (GA, 2026-07-28 tag issued)**

**Checkout state**: `3778656b` (HEAD after 2026-07-28 tag, HEAD 2026-10-12. Spec GA tag remains 2026-07-28)

#### Verified 2026-10-13 (docs only; no spec changes)

[Diff for this update](https://github.com/modelcontextprotocol/modelcontextprotocol/compare/0a11bf68...3778656b). Public specification remains 2026-07-28.

- **Inspector docs**: Updated all pages to match v2/main. Updated security page, mcpdo client, secret storage, Docker, and monitoring sidebar display for MRTR conversations (also includes 2026-10-06 commit)
- **community**: Added Governance Working Group charter and FSIG participant
- **docs**: Started TypeScript quickstart server with `serveStdio` (#3427); added Linux to supported platforms for Claude Desktop (#3426)

#### 2026-09-16 to 2026-09-22 Updates (4 commits, docs only: Skills extension published)

- **Skills extension published**: SEP-2640 reached Final; Skills Over MCP WG maintains official Skills extension (`io.modelcontextprotocol/skills`) — docs now reflect published status (#3372)
- **docs**: Tracked Skills work via extension issues; repaired Skills SEP links after ext-skills archive move (#3366)

#### 2026-09-01 to 2026-09-15 Updates (**SEP-2640 Skills Over MCP Finalized** + Skills WG / Filesystems WG)

- **SEP-2640 (Skills Over MCP) Accepted → Final** (#2640): Formalized the SEP integrating Agent Skills as an MCP extension. Added backward-compatibility requirements and aligned discovery / loading / selection / activation docs with spec language. **No version bump to 2026-07-28 spec text itself** (extension spec finalized)
- **Skills WG**: Added Sambhav Kothari as Skills Over MCP WG lead (#3360); focused extension overview and support matrix on Skills
- **Filesystems WG**: Added Daniel Temesgen as lead and updated membership (#3282)
- **docs**: Added MCP Apps demo (Excalidraw) to apps overview; tracked near-term Tasks extension support

#### 2026-08-01 to 2026-08-31 Updates (55 commits: Next spec release roadmap published + community governance; no spec text changes)

- **Published roadmap for next specification release** (#3290): 5 priority areas — (1) agentic messaging primitives, (2) HTTP-native transport consolidation and hardening, (3) agent identity and enterprise-ready security, (4) improved primitives, and (5) improved SDK developer experience. Listed maintainers and deliverables per area and defined impact on SEP prioritization. Also added roadmap blog post (#3291) and Looking back section (#3298)
- **Added Enterprise Interest Group charter** (#2626); **added transports working group charter**; re-chartered Authorization IG into a single venue
- **Promoted Rust SDK to Tier 1** (SDK listing); documented Cargo (Rust) packages in registry package types
- **Migrated Node floor from EOL 20 to 24**; **patched 2 high-severity advisories** in dev dependencies (881ee655)
- **docs**: Clarified subscription completion results (71f7c162); hardened icon MIME type documentation; clarified SEP finalization requirements; organized WG/IG creation process
- Dependency bumps (typescript-eslint 8.68.0 / eslint 10.9.1, etc.). No changes to spec text or schema after 2026-07-28 spec GA

#### 2026-07-28 to 2026-07-30 Updates (**2026-07-28 spec official release (GA)** — stateless protocol generation)

**Notable**: The stateless spec previously tracked as RC/draft reached **GA on the `2026-07-28` tag (5f5440bb)**, became the default docs version (7732aa68), and was listed as current version on the versioning page (#3173). Breaking changes previously marked "unconfirmed" are now **finalized**.

- **Rewrote spec around stateless protocol + `server/discover`** (17bbea97 and #3069 series). Removed session lifecycle; switched to per-request version declaration and per-request `_meta` capabilities (c7b6fc0d, ba7d0d20)
- **Replaced `resources/subscribe` → `subscriptions/listen`** (5710d7c5). Aligned `subscriptions/listen` envelope compliance on schema side and **renamed `MetaObject`** (271ecc9a, f7e99af6)
- **Explicitly deprecated HTTP+SSE transport** (91dcd516); migrated Java quickstart to Streamable HTTP (faf8afe0)
- **Added caching guidance (`ttlMs`, `cacheScope`)** to architecture / client concepts (a80d01b2, ad3b0c0f)
- **SEP status**: Reclassified SEP-2663 (Tasks) as a protocol extension (395f8c5e) + fixed `MISSING_REQUIRED_CLIENT_CAPABILITY` error code (9b44c6b4); consistently used extensions for SEP-2575 capability exchange (#2830); froze SEP-1686 code examples as historical record (72aeea4e, #3166)
- **schema erratum**: Fixed `NumberSchema` min/max/default to number type in 2025-06-18 / 2025-11-25 (#3139); corrected error codes (#3116)
- **security**: Consolidated guidance into dedicated "security best practices" page (#3099); scoped session hijacking guidance to cover state handles (0d0ef033). No code CVE fixes
- Updated examples to SDK v2 (`mcp 2.0.0`) (#3066 series); versioned Documentation section alongside spec (#2990)

#### Updates as of 2026-07-27 (docs / deps only; no substantive spec changes)

- **No substantive spec changes**: Additions from -243 → -266 are mainly dependabot (typescript-eslint 8.65.0 / typescript-json-schema 0.68.0 / npm groups / actions/setup-node 7) and docs merges
- **Disabled SEP reminder bot**; merged minor docs fixes around structured content / SEP-2243 header mismatch / SEP-2575 error codes (#3106 / #2992 / #3092)

#### Updates as of 2026-07-18 (2026-07-28-RC draft: major breaking changes for statelessness landed)

**Note**: Items below are at RC/draft stage and unconfirmed. Once finalized, they fundamentally change MCP's connection model.

- **Stateless mode (removed handshake)**: Removed `initialize`/`notifications/initialized`; all requests carry protocol version and client capabilities in `_meta`. Version mismatch returns `UnsupportedProtocolVersionError` (SEP-2575)
- **Removed sessions**: Removed `Mcp-Session-Id` from Streamable HTTP; state passes via server-minted handles in tool arguments (SEP-2567)
- **Added `server/discover`**: Servers MUST implement an RPC advertising supported versions, capabilities, and identity (SEP-2575)
- **Introduced `subscriptions/listen`**: Replaced HTTP GET and `resources/subscribe`/`unsubscribe` with a single long-lived POST-response stream (SEP-2575)
- **MRTR pattern + `resultType`**: Replaced server-initiated `roots/list`/`sampling`/`elicitation` with returning `InputRequiredResult`. Required `resultType` on all results (SEP-2322)
- **Extracted tasks to extension** (`io.modelcontextprotocol/tasks`), removed `ping`/`logging/setLevel`, changed resource not-found error code `-32002`→`-32602`

| Breaking Change | Impact |
|---|---|
| Removed initialize handshake, moved to per-request meta | Full rewrite of client/server connection setup flow |
| Removed sessions (`Mcp-Session-Id`) | Requires migration to server-minted handles |
| Removed server-initiated requests → MRTR | Sampling/elicitation/roots implementations incompatible |
| Removed `ping`/`logging/setLevel`/SSE resumability | Calls to these features no longer work |

**Notable**: SEP activity in this window focused on post-Final errata for already-Final **SEP-2243 (HTTP header standardization)**, landing two normative behavior fixes: separating TTL from `Mcp-Param-*` header emission logic and inverting uppercase prefix handling for base64 sentinels. In-flight standards-track SEPs — SEP-2567 (Sessionless MCP) / SEP-2575 (Make MCP Stateless) / SEP-2596 (Feature Lifecycle/Deprecation) / SEP-2577 (Deprecate Roots/Sampling/Logging) / SEP-2106 (Tools schema JSON Schema 2020-12) / SEP-2164 (resource-not-found error code) / SEP-2468 (Issuer iss param) / SEP-2484 (Conformance Tests for Standards Track SEP) / SEP-2663 (Tasks Extension) — all remained in draft with no status transitions in this window.

**Correction**: A previous entry noted "Withdrew SEP-2243 (HTTP Standardization) (#2914)", but the current checkout (`docs/seps/2243-http-standardization.mdx`) confirms SEP-2243 Status is **Final / Standards Track**. Either the previous reading was incorrect or the SEP was withdrawn and resubmitted to Final. Subsequent notes treat "SEP-2243 is Final" as authoritative.

#### 2026-07-01 to 2026-07-07 Updates (2026-07-28 release prep announcements + dependency bumps only; no substantive spec changes)

- **Added SDK beta announcement blog for 2026-07-28 release** (#2988, text correction #2997): RC/release prep progressing on docs side
- **Added appeals channel to Code of Conduct** (#2993)
- **workflows: Enabled Dependabot auto-approve via slash-commands** (#3018)
- **Dev dependency bumps**: typedoc 0.28.20 (#3014) / typescript-eslint 8.62.1 (#3013) / prettier 3.9.4 (#3012) / tsx 4.23.0 (#3015)
- **Note**: Large diffs appear in `docs/specification/*/schema.mdx`, but these are regenerated HTML from the typedoc bump rather than spec changes. No status transitions for in-flight SEPs in this window

#### 2026-06-30 Updates (SEP-2243 HTTP header standardization Final errata / minor fixes)

- **Decoupled `Mcp-Param-*` header emission from schema TTL**: Redefined client behavior for `Mcp-Param-*` custom headers. The old wording ("omit if cached `inputSchema` is stale") caused an infinite loop when `ttlMs: 0` (always stale → always omit → server reject → re-fetch tools/list → stale again). The new wording states: "build using last fetched `inputSchema`, omit only if never fetched, and refresh-and-retry on reject (covering both missing header and body mismatch)." Clarified that TTL governs tools/list refresh pacing, not header emission gating. Also applied to draft Streamable HTTP transport spec (**normative behavior change**, #2972)
- **Inverted uppercase prefix handling for base64 sentinels**: Fixed a contradiction in the SEP-2243 conformance table. `=?BASE64?...?=` (uppercase prefix) changed from "Server MUST accept (case-insensitive prefix)" to "Server treats as literal value, not Base64". Confirmed that the base64 sentinel prefix is **only valid in lowercase `base64` (case-sensitive)** (**normative behavior change**, #2937)
- **Fixed sort order of deprecated features table**: Sorted `specification/draft/deprecated.mdx` in "descending order of spec version when first deprecated". Content (deprecation items from SEP-2596 / SEP-2577 / PR #2858) was already present; row order only (368e013c)
- **Dependency bumps only (no spec impact)**: prettier 3.8.4→3.9.3 (#2987), eslint 10.5.0→10.6.0 (#2986), typescript-eslint 8.61.1→8.62.0 (#2985)

| Change | Kind | Impact |
|---|---|---|
| Base64 sentinel uppercase prefix → treated as literal (#2937) | Normative behavior change (Final errata) | Legacy case-insensitive implementations become non-compliant; prefix must be lowercase `base64` only |
| Decoupled Mcp-Param-* header emission from TTL (#2972) | Normative behavior change (draft) | Eliminates reject loop at `ttlMs: 0`; clients build headers from latest schema |

#### 2026-06-25 Updates (subscriptions/listen response / security best practices / IG charters / SEP-2243 withdrawal)

- **`subscriptions/listen` graceful end response** (#2953): Added empty `SubscriptionsListenResult` so servers can distinguish graceful subscription completion (such as shutdown) from transport drops. Carries `subscriptionId` in `_meta`; includes schema/draft regeneration and subscriptionId backfill in stream-notification examples (non-breaking additive optional)
- **Recommended SSE keep-alive on listen streams** (#2954): Recommended SSE comment-line keep-alives on listen streams in `streamable-http.mdx` / subscriptions pattern
- **Organized `server/discover` version selection** (#2955)
- **Added Security best practices tutorial** (#1554): Added `tutorials/security/security_best_practices.mdx` + `docs/community/security.mdx`
- **Expanded SECURITY.md** (#2973): Added SDK vulnerability disclosure process and stdio trust-boundary guidance
- **Enterprise Managed Authorization**: Completed account-linking guidance and fixed broken spec links (#2945, #2960)
- **Added Financial Services Interest Group charter** (#2979); **added Primitive Grouping Interest Group charter** (#2942)
- **Split AI contribution policy into `AI_POLICY.md`** (#2965)
- **Moved Kotlin SDK to Tier 3** (#2513); added Lead to Interceptors WG
- **Withdrew SEP-2243 (HTTP Standardization)** (#2914): Deleted stale proposal doc (SEP withdrawal, not a wire protocol break)

#### 2026-06-20 Updates (error code allocation / client-matrix & extension support expansion / enterprise-managed auth docs)

- **Organized error code allocation** (#2907): Structured JSON-RPC error code allocation (fweinberger/error-code-allocation)
- **Added Microsoft 365 Copilot to extension support matrix + updated MCP Apps client list** (#2637)
- **Expanded client-matrix**: Added PostHog Code to client-matrix (#2946); marked Archestra.AI as supporting OAuth Client Credentials (#2950)
- **enterprise-managed authorization docs**: Updated links to stable enterprise-managed authorization spec (#2949); added enterprise-managed auth blog post (#2944)
- **Added `build-rust-mcp-client` doc** (#2864): Build documentation for Rust MCP client
- **Dependency bumps**: npm_and_yarn group (#2957). No impact on spec text

#### 2026-06-17 Updates (EMA / Security Interest Group charters / MRTR & elicitation draft cleanup / deps)

- **Added EMA Interest Group charter**: Created EMA IG charter and formatted with prettier; added Lead Maintainer sponsor and fixed facilitator name; listed Discord channel and invite link
- **Added Security IG charter + reorganized charters**: Added Security Interest Group charter and moved all charters under `working-groups/` and `interest-groups/`
- **MRTR (Multi-Round Tool Result) draft cleanup**: Added changelog entries for required `resultType` and SSE resumability removal; restricted caching requirements to complete results and defined cache keys; restored request timeout guidance for transport-specific cancellation; aligned server / client feature pages with `_meta` / resultType / per-request capabilities
- **Elicitation draft cleanup**: Removed `elicitationId` from URL mode elicitation request; removed `notifications/elicitation/complete` from draft; added `elicitationComplete` to `subscriptions/listen` filter; clarified that core client notifications do not occur over Streamable HTTP
- **`subscriptionId` spec**: Defined `subscriptionId` to carry JSON-RPC ID verbatim as string / number; simplified explanation to request ID only
- **`x-mcp-header` cleanup**: Deduplicated x-mcp-header rules, restricted to statically reachable properties, and extended Base64 sentinel encoding to `Mcp-Name` header
- **discover.mdx**: Replaced Response Fields table with Data Types section
- **Dependency bumps**: esbuild (#2911, #2910), eslint 10.4.1 → 10.5.0 (#2916), typescript-eslint 8.60.1 → 8.61.0 (#2917), prettier 3.8.3 → 3.8.4, markdown-it. No impact on spec text

#### 2026-06-13 Updates (dependency bumps only)

- **Bumped esbuild**: Bumped esbuild in deps / deps-dev (#2911, #2910). No changes to spec text

#### 2026-06 Updates (message patterns reorg / stdio legacy-fallback / Server Card WG)

- **Reorganized Authorization spec docs**: Split AS discovery into a standalone doc and consolidated client registration onto one page (promoted normative wording from tables into body text; 2026-06-04 to 05 localden/auth-spec series)
- **Schema fix: `ElicitationCompleteNotificationParams`**: Extracted to inherit from NotificationParams (#2866)
- **Added repository links to Registry / Server Card / Triggers & Events charters** (#2887)

- **Reorganized message patterns page**: Moved and reorganized message patterns page from `utilities/` and updated links
- **Fixed stdio legacy-fallback rules + compatibility matrix**: Fixed stdio legacy-fallback rules and added compatibility matrix (#2844)
- **Cleaned up draft spec overview**: Removed deprecated features and added extensions section
- **Renamed Server Identity WG → Server Card WG**: Renamed WG and added Sam Morrow to IG/WG (#2827)
- **build(deps) group**: Bumped vitest / typescript-eslint / tsx / eslint / actions packages

#### Major SEPs Introduced Between 2025-06-18 and 2025-11-25 (Supplement)

- **SEP-973 Icons metadata**: Metadata exposing icons on tools/resources/prompts
- **SEP-835 Incremental scope consent**: Incremental scope consent via `WWW-Authenticate`
- **SEP-1036 URL mode elicitation**: Standardized `ElicitResult` / `EnumSchema` and URL mode elicitation
- **SEP-1330 titled / multi-select enum elicitation**: Titled and multi-select enums
- **SEP-1577 Tool calling in Sampling**: Added `tools` / `toolChoice` to sampling
- **SEP-1686 Tasks (Experimental)**: Polling and deferred result retrieval for long-running requests
- **SEP-991 OAuth Client ID Metadata Documents**: Added as recommended client registration mechanism (PR #1296)
- **SEP-1613 JSON Schema 2020-12 as default dialect**: Explicitly fixed schema dialect
- **OpenID Connect Discovery 1.0 support**: Extended authorization server discovery to support OIDC Discovery (PR #797)

#### Breaking Changes in 2025-11-25 Release

| Change | Impact |
|---|---|
| HTTP 403 for invalid Origin (PR #1439) | Streamable HTTP transport now requires 403 for invalid Origins — affects client behavior |
| Aligned OAuth Protected Resource Metadata with RFC 9728 (SEP-985) | `WWW-Authenticate` header optional with fallback to `.well-known` — review existing implementation behavior |
| Return input validation errors as Tool Execution Errors (SEP-1303) | Changed from Protocol Error to Tool Execution Error |

#### Changes after 2025-11-25 (Draft for Next Release)

- **Added SEP-2575 unsupported protocol error code**: Introduced custom error code for unsupported protocol errors to support SEP-2575 stateless MCP
- **SEP-2596: Specification Feature Lifecycle and Deprecation Policy**: Documented spec feature lifecycle and deprecation policy (#2596)
- **SEP-2577: Deprecate Roots / Sampling / Logging**: Progressed deprecation of these three features (#2577)
- **SEP-2106: Tools `inputSchema`/`outputSchema` JSON Schema 2020-12 compliance**: Standardized tools schema to JSON Schema 2020-12 dialect (#2106)
- **SEP-2164: Standardized resource not found error code**: Standardized error code as -32602 (#2164)
- **SEP-2468: Recommended Issuer (iss) param in MCP Auth Response**: Recommended `iss` in auth responses (#2468)
- **SEP-2484: Standards Track SEPs require Conformance Tests for Final**: Required conformance tests to promote standards-track SEPs to Final (#2484)
- **SEP-2663: Tasks Extension**: Promoted tasks extension SEP to Final and reformatted (#2663)
- **Promoted SEP-2260 to Final**: Marked SEP-2260 as Final
- **MRTR (Multi-Round Tool Result) schema bugfixes**: Clarified required `resultType` and reframed absent fields as backward-compatible; clarified `notifications/message` is request-scoped; resolved ambiguity in HTTP backward-compat fallback inspecting 400/404 bodies
- **Added GitHub Copilot CLI / CIMD clients**: Added CIMD to ChatGPT MCP Client support list and GitHub Copilot CLI to clients list (#2741, d1b92de)
- **SEP-2575: Make MCP Stateless**: Proposal to make MCP stateless, positioned as a complement (init removal) to SEP-2567 (#2575)
- **SEP-2567: Sessionless MCP via Explicit State Handles**: Proposal for sessionless MCP via explicit state handles. Promoted to Final / Accepted status; spec language applied to draft. Clarified stdio SHOULD NOT, list endpoints varying by request authorization, and added `connect_database` example and Future Work
- **Redefined SEP-2567 ↔ SEP-2575 relationship**: Reframed SEP-2567 as complementary (init removal) rather than an opt-in predecessor to SEP-2575
- **MRTR schema cleanup**: Renamed `IncompleteResult` to `InputRequiredResult`; fixed Multi-Round Tool Result `draft/schema.mdx`
- **Augmented Tool Call extension**: Updated docs for tasks-augmented tool call flow
- **Updated elicitation/roots diagrams**: Refreshed elicitation diagrams and roots page
- **Revised `requestState` spec**: Updated `requestState` handling requirements
- **Removed `URLElicitationRequired` error**: URL Elicitation itself remains supported via MRTR; removed the error
- **Regenerated SEPs**: Applied prettier and regenerated SEPs
- **Moved Core Maintainers to Emeritus**: Moved Che Liu and Basil Hosmer to Core Maintainer Emeritus
- **SDK Working Group charter**: Added SDK WG charter (#2662) and organized work items into spec implementation and tiering
- **Designated `#general-sdk-dev` Discord channel**: Assigned Discord channel for SDK WG
- **vm2 3.11.3 security bump**: Mitigated GHSA-vwrp-x96c-mhwq (#2711)
- **TypeScript 6.0.3 / eslint 10.3.0 / typescript-eslint 8.59.1-8.59.3**: Dependency bumps (#2610, #2676, #2677)
- **typescript-json-schema 0.67.1 pin**: Reverted pin from 0.67.2 → 0.67.1 (#2714)
- **fast-uri 3.1.2**: Bumped fast-uri in dev deps (#2715)
- **Explicit connect in Ruby client sample**: Updated Ruby client sample to connect explicitly (#2685)

#### Key Changes in 2025-11-25

- **Interceptors WG charter**: Created Interceptors Working Group charter (#2619)
- **MCP client best practices**: Added MCP client best practices to docs (#2582)
- **Added Runbear client**: Added Runbear to Example Clients (#2572)
- **`.well-known/agent-skills/` discovery endpoint**: Exposed MCP skills via `.well-known/agent-skills/`
- **Mintlify directory symlink fix**: Fixed Mintlify indexing for draft-sep / search-mcp-github skills (#2597, #2604)
- **Clarified single Core Maintainer approval**: Clarified single Core Maintainer approval for WG charter PRs (#2592)
- **First-class fork-based contributions**: Made fork-based contributions a first-class path
- **TypeScript 6.0.3**: TypeScript 6.0.2 → 6.0.3 (#2610)
- **HTTP Standardization (SEP-2243)**: Merged HTTP transport standardization
- **Deterministic `tools/list` ordering**: Added deterministic ordering specification for tool lists
- **Tool-name disambiguation**: Clarified tool-name disambiguation
- **Skills Over MCP IG**: Created Skills Over MCP Interest Group charter
- **Inspector V2 WG**: Created Inspector V2 Working Group charter
- **Updated mcpc CLI client**: (#2576)
- **SEP-2207 OIDC refresh token guidance**: (#2207)
- **Ruby SDK docs**: Added Ruby SDK example to build-client documentation (#2486)
- **SEP-2350 Client-side scope accumulation**: (#2350)
- **TypeScript 6.0.2**: TypeScript 5.9.3 → 6.0.2 (#2503)

#### Key Changes

- **Top-level Extensions tab**: Promoted Extensions to a top-level tab with dedicated pages (#2263)
- **SDK tier ratings**: Python SDK Tier 1, C# SDK Tier 1, Go SDK Tier 1, Java SDK Tier 2, Swift SDK Tier 3, PHP SDK Tier 3
- **OIDC / Enterprise Managed Authorization**: Updates for OIDC and enterprise managed authorization
- **Experimental tasks feature**: Application-driven task architecture with polled status tracking
- **Extensions framework** (SEP-2133, Final): Added schema for extension capabilities
- **Expanded MCP Apps support**: Claude Desktop, ChatGPT, MCPJam, Postman, VSCode, goose, Copilot

#### Reference Links

- [MCP Specification](https://modelcontextprotocol.io/specification/2026-07-28)

---

### MCP-Apps

**Current version**: **v2.0.3 (2026-09-25)**

**Checkout state**: `82221c0c` (HEAD 2026-09-25 = v2.0.3 tag)

#### 2026-09-23 to 2026-09-25 Updates (**v2.0.1 to v2.0.3**: patches only)

- **v2.0.1**: Fixed example servers crashing on startup below Node 20.11; aligned dependency isolation check with `@modelcontextprotocol/client` 2.1
- **v2.0.2 / v2.0.3**: Pinned `pdfjs-dist` to 5.4.530 and `@cantoo/pdf-lib` to 2.6.5 in pdf-server; updated dependencies flagged by npm audit (#792 / #793)

#### 2026-09-01 to 2026-09-15 Updates (**v2.0.0**: Migrated to MCP TypeScript SDK 2.x; wire compatible, TS API / peer breaking)

- **v2.0.0 release** (#720 / #768): Replaced `@modelcontextprotocol/sdk@^1` with **split SDK 2.x peers** (`client` / `server` / `core` / `node` / `express`, all `^2.0.0`), required Node.js 20+, and **dropped zod 3 for `zod@^4.2.0` (Standard JSON Schema) only**
- **Wire compatibility**: `ui/*` iframe messages are byte-identical to 1.x; 2.x View ↔ 1.x host interoperate. Added cross-version interop tests against published 1.7.5 (#770)
- **TS API breaking changes**: `App`/`AppBridge` now extend `Protocol` from `@modelcontextprotocol/client` (removed `ProtocolWithEvents`); handler context moved from `extra.signal` → `extra.mcpReq.signal`, etc.; `setRequestHandler` takes method name argument (1.x `(Schema, handler)` kept as deprecated overload, to be removed in 3.0); errors are `ProtocolError` / `SdkError` (dropped `MCP error N:` prefix)
- **Minor host-side wire diffs**: resource-not-found changed `-32002` → `-32602`; unknown tool changed `result.isError` → JSON-RPC `-32602`
- **Kept 1.x handler signature as deprecated overload** (#769 / #771); added migration guide `docs/migrate-to-2.md`

| Breaking Change (v1.7.5 → v2.0.0) | Impact |
|---|---|
| MCP SDK 1.x single package → 2.x split peers | Run `npm uninstall @modelcontextprotocol/sdk` and install role-specific client/server/node/express packages |
| Dropped zod 3 + deprecated raw shapes | Upgrade to `zod@^4.2.0` and wrap with `z.object({...})` |
| Handler context / `setRequestHandler` args | Migrate to `extra.mcpReq.*` and method-name args (1.x overload removed in 3.0) |
| Error types (`McpError` → `ProtocolError`/`SdkError`) | Update numeric code checks and message prefix handling |

#### Updates as of 2026-07-27 (v1.7.5 release)

- **Tagged v1.7.5** (2026-07-23, #724): Bumped ext-apps to 1.7.5
- **Fixed preservation of experimental capability settings** (#721)
- **Reduced npm audit findings from 15 → 3** (#725)

#### Updates as of 2026-07-18 (draft spec additions; SDK remains at v1.7.4)

- **Spec additions (unreleased)**: Added missing `HostCapabilities` fields (#653); synced spec `object-src` with `default-src` (#715)
- **Note**: npm SDK versions (1.7.x) and spec versions (`RELEASES.md` 0.3.0) are versioned separately. Tracked tags follow SDK versions (v1.7.4 is latest)

#### 2026-07-07 Updates (draft spec: added missing HostCapabilities fields)

- **spec: Added missing `HostCapabilities` fields** (#653): Updated `specification/draft/apps.mdx` (additive fields only, no breaking changes). Only spec change in this window
- **docs: Added mcp-use inspector badge to supported clients list** (#650)
- **docs: Added API Docs link for ext-apps/server** (#697)

#### Changes after v1.7.4 (docs only)

- **Fixed map-server readme / code of conduct links** (#657): Fixed broken doc links. No spec or implementation changes

#### Key Changes in v1.7.4 (2026-06-04)

- **SECURITY: Required PKCE + `redirect_uri` binding in lazy-auth-server token exchange** (#681)
- **Supported mounting lazy-auth-server under a base path**: Enabled mounting under a base path (#683)
- **Bumped ext-apps to 1.7.4** (#685)

#### Key Changes in v1.7.3

- **Added lazy-auth-server example**: Added example lazy auth server (#679)
- **Bumped ext-apps to 1.7.3**: Bumped ext-apps to 1.7.3 (#680)

#### Key Changes in v1.7.2

- **Bumped example transitive dependencies**: Bumped transitive dependencies under examples to latest patches (#658)
- **Switched pdf-lib → `@cantoo/pdf-lib` fork**: Switched pdf-server to maintained `@cantoo/pdf-lib` fork due to unmaintained upstream (#651)

#### Key Changes in v1.7.1

- **PDF Server lazy form extraction**: Lazy form extraction via range transport and incremental viewer scans (#639)
- **PDF Server cache sharing**: Shared cache across server instances and deduplicated form parsing (#637)
- **qr-server FastMCP host/port support**: Passed host/port for Docker compatibility (#372)
- **PostMessageTransport source validation**: Added unit tests for PostMessageTransport source validation (#536)
- **`buildAllowAttribute` unit tests**: (#541)
- **Updated CONTRIBUTING.md guide**: Updated contributing guide for package previews (#601)

#### Key Changes in v1.7.0

- **Tool registration spec (WebMCP-style)**: Added spec for registering App tools called by Host (#72)
- **MCP app sampling support**: Added MCP app sampling support via stock SDK types (#530)
- **Zod jitless by default**: Defaulted Zod to jitless with `allowUnsafeEval` opt-out for strict CSP environments (#618)
- **Unified pre-handshake guards**: Standardized on `console.warn` and guarded requests before handshake (#620, #630)
- **One-shot handler registration warning**: Warned when registering one-shot handlers after `connect()` (#629)
- **React StrictMode cleanup**: Fixed StrictMode cleanup and relaxed late-handler guard re-registration (#631)
- **React autoResize forwarding**: Forwarded `autoResize` from `useApp` to `App` (#622)
- **Tightened types**: Disallowed csp/permissions on `McpUiToolMeta` with `never` (#624); removed stale resourceUri JSDoc (#626)
- **Patch version bumps for dependencies**: Bumped vite, hono, and @hono/node-server to patch versions (#616)

#### Key Changes in v1.6.0

- **Progress-based timeout reset**: Supported progress-based timeout reset in `callServerTool` (#600)
- **Hardened E2E tests**: Stabilized tests by polling initial shrink-to-fit zoom (#607)

#### Key Changes in v1.5.0

- **PDF Server annotation rasterization**: Rasterized imported annotations (#593)
- **PDF Server form field save hardening**: Improved robustness of saving form fields (#591)
- **PDF Server highlight/underline/strikethrough import**: Imported highlights, underlines, and strikethroughs from existing PDFs (#592)
- **PDF Server `get_viewer_state`**: Added `get_viewer_state` to interact actions (#590)
- **PDF Server zoom-out improvement**: Allowed zooming out below fit (#589)
- **PDF Server fullscreen / pinch-zoom**: Fullscreen fit-to-page and pinch-zoom (#583)

#### Key Changes in v1.4.0

- **PDF Server `save_as` action**: Added `save_as` to interact actions (#580)
- **Fixed path-to-regexp ReDoS CVE**: v8.3.0 → v8.4.1 (#576)
- **addEventListener/removeEventListener**: Added DOM-model `on*` semantics (#573)

#### Reference Links

- [MCP-Apps](https://github.com/modelcontextprotocol/ext-apps)

---

### MCP-UI

**Current version**: `@mcp-ui/client` v7.1.1 (2026-05) / `@mcp-ui/server` v6.1.0 (2026-02)

**Checkout state**: `client/v7.1.1-2-g2b10490` (v7.1.1 + 2 commits, HEAD 2026-07-08. Repo migrated to `MCP-UI-Org/mcp-ui`; per-package tags `client/v*` and `server/v*` are the current scheme. Root `CHANGELOG.md` is stale from old `idosal/mcp-ui` and not referenced)

**As of 2026-07-18**: Unreleased post-v7.1.1 change emits a CJS build so `require('@mcp-ui/client')` exposes exports (#211). No breaking changes

#### Key Changes in v7.1.1

- **Cancel sandbox proxy iframe timeout**: Cancelled sandbox proxy iframe timeout on effect cleanup to prevent unhandled rejections in StrictMode (#190)

#### Key Changes in v7.1.0

- **`hostInfo`/`hostCapabilities` props**: Added `hostInfo` and `hostCapabilities` props to `AppRenderer` (#179)

#### Key Changes in v7.0.0

- **Removed legacy spec**: Completely removed legacy specification (**breaking change**) (#185)
- **Fixed major bump**: Fixed previous commit where semantic release failed to trigger major bump (#187)

#### Breaking Changes

| Version | Change |
|---|---|
| v7.0.0 | Complete removal of legacy specification |
| v6.0.0 | Removed deprecated content types, changed MIME types |
| v5.0.0 | `delivery` → `encoding`, `flavor` → `framework` |

#### Reference Links

- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)

---

### NLIP (Natural Language Interaction Protocol)

**Current version**: 1st edition (Ecma approved 2025-12-10)

**Maintainer**: Ecma TC56 NLIP (Ecma International)

**Notable**: Industry standard for an **application-layer communication protocol** between AI agents and between humans and AI agents. Officially approved by Ecma International on 2025-12-10 and submitted to ISO on 2026-01-25. A Claude Skills-compatible reference implementation is scheduled for release on 2026-02-28 (on the reference implementation side).

#### 1st Edition Structure (6 Documents Total)

| Standard | Title | Role |
|---|---|---|
| **ECMA-430** | Natural Language Interaction Protocol (NLIP), 1st edition | Core protocol spec (agent-to-agent / human-to-agent application-level) |
| **ECMA-431** | NLIP over HTTP/HTTPS binding | HTTP/HTTPS binding |
| **ECMA-432** | NLIP over WebSocket binding | WebSocket binding (CBOR + UTF-8 JSON fallback, RFC 8949) |
| **ECMA-433** | NLIP over AMQP binding | AMQP binding |
| **ECMA-434** | Security profiles for NLIP | Agent Security Profiles (mandatory requirements for NLIP-compliant implementations) |
| **ECMA TR/113** | Explanatory guide to NLIP | Informative explanatory guide (design philosophy / use-cases / sample exchange) |

#### Repository Layout (Tracked Targets)

- **`nlip-project/nlip_spec`**: README index of the Ecma-approved 1st edition (this submodule)
- **`nlip-project/ecma_draft` / `ecma_draft1`**: Feedback collection repos from the First Draft phase (historical)
- **`nlip-project/documents`**: TC-56 NLIP related documents
- **`nlip-project/security_guidelines`**: Companion to ECMA-434
- **`nlip-project/nlip_spec_swarm` / `nlip_web` / `nlip_agents` / `kivy-chat-mach2`**: Reference implementations

#### Key Features

- **Multi-transport support**: 3 binding families — HTTP/HTTPS, WebSocket, and AMQP (selectable per use case)
- **WebSocket × CBOR**: Compact, efficient binary encoding for multimodal communication with guaranteed JSON fallback
- **Standardized Security Profiles**: Compliance with ECMA-434 is **mandatory** for implementations claiming NLIP conformance
- **Royalty-free open source standard**: Royalty-free under Ecma International governance
- **Position relative to A2A / MCP**: A2A handles opaque agent-to-agent communication and MCP handles agent-to-tool/data communication; NLIP complements them by handling **natural-language application-level** communication for agent-to-agent and human-to-agent interactions

#### Reference Links

- [nlip_spec (GitHub)](https://github.com/nlip-project/nlip_spec)
- [NLIP Project site](https://nlip-project.org/)
- [Ecma International - ECMA-430](https://ecma-international.org/publications-and-standards/standards/ecma-430/)
- [Ecma International - ECMA-431 (HTTP)](https://ecma-international.org/publications-and-standards/standards/ecma-431/)
- [Ecma International - ECMA-432 (WebSocket)](https://ecma-international.org/publications-and-standards/standards/ecma-432/)
- [Ecma International - ECMA-433 (AMQP)](https://ecma-international.org/publications-and-standards/standards/ecma-433/)

---

### OpenResponses

**Current version**: Untagged (spec is date-versioned; latest CHANGELOG = `2026-04-24`)

**Checkout state**: `7078a8f` (remote HEAD, HEAD 2026-10-09)

#### Verified 2026-10-13 (3 commits: tooling / docs structure)

[Diff for this update](https://github.com/openresponses/openresponses/compare/21a5dbc2...7078a8f1). Untagged.

- **Migrated to TypeSpec**: Changed schema generation to TypeSpec-based (#83)
- **docs**: Redesigned API reference layout (#84); per-endpoint / per-object navigation (#85). These commits update schema generation and display infrastructure, not a new spec version release

#### Updates as of 2026-07-18 (WebSocket transport + Response compaction + spec versioning)

- **WebSocket transport**: Added WebSocket mode to `/v1/responses`. Starts turns with `response.create` and reuses the same semantic events as HTTP streaming. Defines sequential turns, `previous_response_id` continuation, 60-minute connection limit, and disconnect recovery (#71/#72)
- **Response compaction**: Added `POST /v1/responses/compact` endpoint and request/response schemas (#68)
- **Introduced Spec versioning**: Date-versioned specification/reference and added `llms.txt` (#77, 2026-07-06)
- **Added assistant-message `phase` field** (`commentary`/`final_answer`); made `logprobs` optional (#45)
- Breaking: Fixed `createResponse` operation ID — changes operation names in OpenAPI-generated clients (regeneration required)

#### Recent Changes

- **Response phase compaction**: Added assistant message phase parameter to source schema; aligned phase and compaction schemas, covered with compliance tests, and introduced neutral model descriptions (#68)
- **compact response endpoint**: Added compact response endpoint to spec and documented compaction endpoint (#68)
- **WebSocket mode support**: Implemented WebSocket mode in OpenResponses (major new feature) (#71)
- **WebSocket recovery compliance coverage**: Added WebSocket recovery compliance tests
- **WebSocket mode documentation**: Aligned WebSocket mode docs and validation
- **mise version bump**: Bumped `mise-bun` environment version (#72)
- **Composed schema fields rendering**: Rendered composed schema fields in reference docs
- **Added AWS partner**: Added AWS partner logo (#67)
- **Added Red Hat community**: Added Red Hat logo
- **Updated core maintainer list**: Improved maintainer management

#### Key Changes

- **Llama Stack integration**: Added Llama Stack integration (#29)
- **Added Databricks community**: Added logo to community section
- **Optional logprobs**: Made logprobs optional (#45)
- **CLI compliance tests**: Added `bin/compliance-test.ts`
- **Bun migration**: Switched package manager from Node to Bun

#### Reference Links

- [OpenResponses](https://github.com/openresponses/openresponses)

---

### UTCP (Universal Tool Calling Protocol)

**Current version**: v1.1 (spec, untagged tracking latest, last spec commit 2026-05-18)

**Checkout state**: `4a9ed93` (remote HEAD detached, HEAD 2026-09-16. Spec version remains v1.1)

#### 2026-09-16 to 2026-09-22 Updates (4 commits: 1.1 snapshot re-cut + API docs sync)

- **1.1 snapshot re-cut** (#66): Re-cut `versioned_docs/version-1.1` from current line before 1.2 lands — reflects 1.1.x docs (OAuth cache keying, MCP client reuse, socket protocols, security/protocol pages) in the 1.1 snapshot
- **Docs fixes (before re-cut)**: Stop redirects from non-loopback origins into loopback (python-utcp #109); clarify MCP checklist requires HTTPS/WSS anywhere + plain HTTP/WS only on loopback; clarify where `ws://` URLs are accepted; clarify no-request-body on SSE reconnection
- **API docs sync**: Synced from python-utcp@3730c46 (1.2 line)

#### 2026-09-01 to 2026-09-15 Updates (Clarified HTTP trust boundary in docs; no spec incompatibility)

- **docs: Documented client-enforced trust boundary and current OAuth2 / SSE behavior** (#65) — API docs sync with python-utcp 1.1.12. No breaking changes to implementation or schema
- Remaining commits are automated `chore: update contributors data` updates

**Maintainer**: Universal Tool Calling Protocol community (independent OSS)

**As of 2026-07-18**: No substantive changes. Current spec is **v1.1** (secure-by-default: added `allowed_communication_protocols` to all call templates; when unspecified, only tools of the same protocol can be registered/called). No breaking changes

**Notable**: A **structural alternative / complement** to MCP. While MCP "calls tools via a proxy", UTCP is designed so **agents call native endpoints (HTTP/gRPC/WebSocket/CLI) directly after discovery**, eliminating wrapper tax and latency while reusing existing auth/billing/security. Redesigned to a plugin-based architecture in v1.0, and made multi-protocol manuals secure-by-default in v1.1.

#### 2026-06-24 Updates (examples field on JsonSchema; others automated contributors updates)

- **Added optional `examples` field to JsonSchema**: Auto-synced docs from `python-utcp@ae4cebc` adding `examples: Optional[List[JsonType]]` (list of schema example values) to tool input/output JSON Schema models. Backward-compatible additive optional (commit d583734)
- The other 7 commits are automated `chore: update contributors data` updates with no spec changes

#### Changes from v1.0 → v1.1

- **New `allowed_communication_protocols` field**: Added optional field to call templates (manual configuration)
- **Secure by default**: When unspecified, a manual can only register/call tools of its own protocol type (HTTP manuals only HTTP tools, CLI manuals only CLI tools)
- **Explicit multi-protocol**: Manuals mixing multiple protocols must explicitly set `allowed_communication_protocols`
- **Clarified dual license**: Clarified licensing wording (commit `29bbc4e`)
- **API docs sync**: Re-synced API docs from `python-utcp@4ed0a48` (commit `6bd28ae`)

#### Breaking Changes in v1.1

| Change | Impact |
|---|---|
| Removed implicit permission for multi-protocol manuals | In v1.0, CLI tools could be mixed into an HTTP manual; in v1.1 they are filtered out unless explicitly listed in `allowed_communication_protocols`. Working configs may silently stop working |

#### Key Features of v1.0

- **Plugin Architecture**: Split core functionality into pluggable components, improving modularity, testability, and packaging
- **Multiple Protocol Support**: Supports HTTP / CLI / WebSocket / Text / **MCP** via plugins (subsuming MCP as a plugin)
- **Enhanced Data Models**: Standardized on Pydantic models with comprehensive validation
- **Advanced Authentication**: Extended authentication including API key, OAuth, and custom auth
- **Better Error Handling**: Specific exception types per scenario
- **Async/Await Support**: Fully asynchronous client interface
- **Performance Optimizations**: Optimized client and protocol implementations
- **OpenAPI extensions**: Added agent-focused enhancements (tags, `average_response_size`, multi-protocol, direct execution instructions) to OpenAPI
- **Dual license clarification**: Cleaned up dual licensing in recent commits

#### Related Repositories (Org Ecosystem)

| Repo | Role |
|---|---|
| `utcp-specification` | Spec itself (this submodule) |
| `python-utcp` | Official Python implementation |
| `typescript-utcp` | Official TypeScript implementation |
| `utcp-agent` | Ready-to-use agent calling APIs/native endpoints directly in under 5 lines |
| `code-mode` | Plug-and-play library calling MCP/UTCP tools via **code execution** |

#### Position Relative to MCP

| Aspect | MCP | UTCP |
|---|---|---|
| Invocation method | Via proxy server (wrapper) | Agent calls native endpoint directly |
| Latency | Wrapper hop present | No hop |
| Auth/billing | Re-implemented on MCP server | Reuses existing systems |
| Compatibility | Custom MCP protocol | Reuses existing APIs via OpenAPI extensions |
| MCP adoption | n/a | Subsumes MCP protocol as a plugin |

#### Reference Links

- [utcp-specification (GitHub)](https://github.com/universal-tool-calling-protocol/utcp-specification)
- [Universal Tool Calling Protocol org](https://github.com/universal-tool-calling-protocol)
- [www.utcp.io](https://www.utcp.io/)
- [python-utcp](https://github.com/universal-tool-calling-protocol/python-utcp)
- [typescript-utcp](https://github.com/universal-tool-calling-protocol/typescript-utcp)

---

### webmcp-tools

**Current version**: **v0.0.4 (2026-08-28)** (evals CLI also renamed to `webmcp-evals` v0.0.4)

**Maintainer**: Google Chrome Labs

**Checkout state**: `04732fb` (`v0.0.4-123-g04732fb` = v0.0.4 + 123 commits, HEAD 2026-10-12. No new tag issued)

#### Verified 2026-10-13 (docs / webmcp-skills / demo)

[Diff for this update](https://github.com/GoogleChromeLabs/webmcp-tools/compare/5a3be0f6...04732fb8). Changes are on HEAD; public release remains v0.0.4.

- **webmcp-skills**: Supported Interactive / Autonomous pacing across Stages 1–6 (#556); updated React patterns to `use-webmcp-tool` v0.3.0 (#555)
- **docs / demo**: Listed Nekuda SDK and standalone verification (#560); Smart home security demo (#544); added Agio Digital / VueUse `useWebMCP` (#547 / #548)

#### 2026-09-16 to 2026-09-22 Updates (17 commits: demo SECURITY hardening + BestPrice.gr production site)

- **SECURITY (demos)**: Sanitized innerHTML with DOMPurify in page-agent / french-bistro (#469), french-bistro modalDetails (#471), and ticket-booking movieGrid (#472); mitigated DOM XSS and DoS in pizza-maker (#468); nested webmcp-maze EvalTool Web Worker in a sandboxed iframe (#470)
- **New production site**: Added BestPrice.gr production WebMCP site (#395)
- **fix**: Resolved cross-demo tool name collisions (#474); updated webmcp demos (#476)
- **deps**: @babel/core 7.29.7, protobufjs 7.6.6, nanoid 3.3.19, etc.

#### 2026-09-01 to 2026-09-15 Updates (tool execution API options / inputObject + WebMCP Registry / demo expansion; v0.0.4 unchanged)

- **Tool execution API**: Added required callback options to `executeTool()` (#430), then passed **`inputObject` for backward compatibility** (#447); polyfill passes options to registered tool execution (#434); AbortSignal on EvalTool execute (#428)
- **docs**: Added **WebMCP Registry** description (#222); added WebMCP Agent Skill / Signett / DeepDeck / Timeline Studio / multiple Challenge demos to Awesome list
- **CI**: Improved Dependabot grouping + demo build verification (#454); mostly dependency bumps

#### 2026-08-01 to 2026-08-29 Updates (v0.0.4 release: evals-cli → `webmcp-evals` rename + tool abort support)

- **v0.0.4 release** (2026-08-28): Renamed evals-cli to **`webmcp-evals`** (#379) and tagged release
- **feat**: Added abort support for tool execution (agent / polyfill); populated trajectories for local evals (#396); included browser console errors in reports (#361); added imperative tool registration mode to french-bistro demo (#377); tool `inputSchema` supports both objects and strings
- **Hotel chain readonly tool** (#398); **added WebMCP Kit / WindTunnel** (#389)
- **docs**: Open for Agents Storefront (#383); added MCP Webcomic Site Server to Libraries & Tools (#392)
- deps: bumped `@hono/node-server` / `@modelcontextprotocol/sdk` / `@a2ui/*` and others. No schema incompatibility

#### 2026-07-28 to 2026-07-31 Updates (Evals CLI moved to Puppeteer WebMCP API; v0.0.3 unchanged)

- **Switched Evals CLI to use Puppeteer WebMCP API** (#326); manual form submission handling (#305); implemented evals report analyzer (#308)
- **feat**: Persisted agent open state via URL search parameters (#315)
- **fix**: Removed JSON parsing in `mapRawBrowserToolsToConfig` (#340); fixed react dependencies (#339). Refactored react demos to `use-webmcp-tool` package (#314)
- **docs**: Added `use-webmcp-tool` / `webmcpify` / `Latch` to Awesome WebMCP (#322, #286, #285)
- **deps (supply-chain bumps)**: `brace-expansion` 1.1.16 (#310, #312), `fast-uri` 3.1.4 (#311), marked / postcss / autoprefixer, 5 items in github-actions group (#327), added Dependabot config (#319). No schema incompatibility or direct security fixes

#### Updates as of 2026-07-27 (Code Mode follow-up + evals expansion; v0.0.3 unchanged)

- **Code Mode follow-up** (#309): Follow-up fixes around `execute_batch`
- **evals-cli expansion**: Added hotel chain eval (#299); detailed timestamps in eval reports (#300)
- **docs**: Standardized live demo URLs with trailing slashes (#281); brace-expansion bump (#307)

#### Updates as of 2026-07-18 (Code Mode / execute_batch + WebMCP Polyfill)

- **Code Mode / `execute_batch`**: Exposed `execute_batch` tool for Page Agent, introducing "Code Mode" (#287)
- **WebMCP Polyfill**: Added polyfill for browsers without native support and integrated into demos; improved cross-origin tool lookup/execution and same-origin checks (#276)
- **Added Gemini/Ollama to Backend contracts** (#294); **overhauled evals-cli** (fixed runs vs steps bug + full LLM trajectory support, #293, #298)
- **v0.0.3 NPM release** (#288/#290)

#### 2026-07-01 to 2026-07-06 Updates (Removed `navigator.modelContext` + major evals-cli enhancements)

- **Removed `navigator.modelContext`**: Removed references to this API across all demos and docs (`AWESOME_WEBMCP.md`, coffee-shop, doors, hotel-chain, etc.) (5944b1e). Impact limited to demos
- **evals-cli enhancements (main theme of this window)**: Multi-step local eval (98373e3); Chat Completions API for openai/ollama providers (ea21765); env var override for base URL (#249); optional tool calls in expected trajectories (e87b4fe); argument subset matching in `matchesRecursive` (3b0df45); preserved Gemini `thought_signature` in OpenAI-compatible multi-turn (4cfb73d); inline flags `(?flags)` support in `$pattern` (1b5ab2f); treated omitted `arguments` in `functionCallOutcome` as unconstrained (5bed009)
- **Demo updates**: AI Chat helper in Sport Shop (50a7852); in-page agent display on result page (#250); used view-transition auto (6b7223f)
- **deps**: js-yaml bump in analytics-dashboard demo (#255)

#### 2026-06-30 Updates (Promisified `registerTool`)

- **Changed `registerTool` to return a Promise**: Updated `document.modelContext.registerTool()` TypeScript signature from `(tool, options?) => void` to `(tool, options?) => Promise<void>`. Enables proper handling of rejected registration promises; updated all demos (explainer / hotel-chain / smart-home / shared types `webmcp.d.ts`) to `await` + try/catch, and updated explainer code examples and inspector descriptions to `await document.modelContext.registerTool({...})` (#228). Consumers checking the return type must adapt from `void` to `Promise<void>`, though existing unawaited calls work at runtime as before, so this is not treated as a breaking change (the only change is that previously silent registration failures can now be caught)

#### 2026-06-16 to 06-29 Updates (Dependency bumps only)

- **dependabot deps bumps**: sport-shop-angular undici 7.22.0 → 7.28.0 (#244), hono 4.12.24 → 4.12.25 (#241), @sigstore/core 3.1.0 → 3.2.1 (#248), leather-bag undici 7.22.0 → 7.28.0 / 6.26.0 → 6.27.0 (#245), evals-cli ws 8.20.1 → 8.21.0 (#239)

#### 2026-06-24 Updates (in-page agent iframe / SharedWorker fix / Stacktree demo)

- **iframe support for in-page AI agent** (#243): Enabled running the in-page AI agent inside an iframe
- **Fixed tool execution in SharedWorker**: Fixed tool execution when running under SharedWorker
- **Fixed iframe agent flow to call `getTools` before `executeTool`**
- **Added Stacktree to Demos** (#246)
- **Documented `document.modelContext` as primary surface** (docs)

#### 2026-06-19 Updates (WebMCP flag rename)

- **Renamed `enable-features` flag `WebMCPTesting` → `WebMCP`** (#242): Replaced `enable-features=WebMCPTesting` with `enable-features=WebMCP` across all demos and docs as Chrome's origin trial / feature flag name was finalized as `WebMCP`

#### 2026-06-16 Updates (shared worker support / dependabot batch)

- **Added shared worker support**: Added shared worker support to french-bistro demo (#224); cleaned up ports in shared worker (including refactor away from `delete`)
- **dependabot deps bumps**: leather-bag Angular suite (compiler / common / core / forms / platform-browser / router / build / compiler-cli) to 22.0.1 (#230, #232, #234), smart-home / hotel-chain vite 8.0.x → 8.0.16 (#235, #236), evals-cli/ui js-yaml 4.1.1 → 4.2.0 (#238), sport-shop-angular Angular packages (#234)

#### 2026-06-15 Updates (origin trial tokens / dependabot batch)

- **Backfilled origin trial tokens in demos**: Added missing origin trial tokens to demos (ot2, #229)
- **dependabot deps bumps**: Bumped esbuild / vite / @vitejs plugins in react-flightsearch (#227), evals-cli/ui (#226), webmcp-maze (#225); leather-bag hono 4.12.18 → 4.12.23 (#213); hotel-chain postcss 8.5.8 → 8.5.15 (#210)

#### 2026-06-10 Updates (leather-bag angular standards / referrer)

- **Updated leather-bag app to latest Angular standards**: Refactored leather-bag demo to modern Angular idioms
- **Referrer support**: Adopted `use-referrer` (#223)
- **Demo dependency bumps**: Bumped sport-shop-angular hono 4.12.24 and analytics-dashboard postcss 8.5.15 via dependabot (#216, #217)

#### 2026-06-09 Updates (Angular 22 / parametersJsonSchema / french-bistro agent)

- **Added in-page agent to french-bistro demo** (#214)
- **Migrated to `parametersJsonSchema`**: Used `parametersJsonSchema` instead of `parameters` in tool definitions (#220)
- **Updated leather-bag demo to Angular 22**: Exposed Angular-style WebMCP tools and added dynamic form behavior

#### 2026-06 Updates (Page Agent demo / Sport Shop evals / permission policy)

- **Tightened permission policy**: Tightened permission policy
- **Added Page Agent demo**: Added Page Agent demo
- **Sport Shop evals**: Added example evals for Sport Shop; added pickup / promos / extra cart tools to Sport Shop
- **Exposed Pizza-Maker tools for cross-origin testing**: Exposed Pizza-Maker tools for cross-origin testing
- **Improved eval reports**: Improved reports with eval names and improved sidecar UI
- **Added webmcp.cool to AWESOME_WEBMCP**: Added webmcp.cool to AWESOME_WEBMCP.md

#### Recent Changes

- **Made Search product globally available**: Promoted Search product to a globally available tool
- **Updated french-bistro tool descriptions**: Improved tool descriptions in french-bistro demo
- **Removed input schema**: Deleted unnecessary input schemas
- **Sport shop search results tool**: Added tool to read search results in sport shop
- **Removed "demo site" wording**: Removed "demo site" phrasing to improve product feel
- **More complex hotel example**: Increased hotel search complexity and fixed search logic
- **Added autocomplete values**: Added autocomplete values to name/phone form fields (#159, #160)
- **Fixed Leather Bag demo**: Fixed images in Leather Bag demo (#155)
- **registered-purchase feature**: Added registered-purchase feature (#149)
- **Removed `unregisterTool`**: Removed `unregisterTool` calls (#153)
- **Added `untrustedContentHint`**: Added `untrustedContentHint` to `shared/types/webmcp.d.ts` (#152)
- **Fixed Pizza toppings**: (#150)
- **Fixed Live demo link format**: Fixed live demo link formatting in README
- **Flight Search flexible routes**: Added flexible routes and one-way/round-trip support to Flight Search (#141)
- **Flight Search build fix**: Made return flight properties optional (#144)
- **Improved french-bistro demo Lighthouse**: Improved Lighthouse audit score
- **Morning ritual coffee demo**: Implemented with persistent state and index entry (temporarily reverted)
- **Fixed Maze player trail animation**: Fixed maze player trail animation (#133)
- **Optional `for` attribute on Label**: Accessibility improvement (#146)
- **Dependency updates**: Hono 4.12.14, basic-ftp 5.3.0, protobufjs 7.5.5, vite 8.0.5, vite 7.3.2, etc.

#### Key Changes

- **Order Tracking declarative demo**: Added declarative demo for order tracking
- **Ticket Booking support**: Added ticket booking support
- **webmcp-maze demo**: Added new maze demo project
- **WebMCP Flow**: Added architecture diagram builder
- **Vercel AI SDK migration**: Migrated to Vercel AI SDK with experimental multi-step tool execution
- **Sport Shop demo**: Improved Sport Shop demo

#### Reference Links

- [webmcp-tools](https://github.com/GoogleChromeLabs/webmcp-tools)

---

## Payments / Agentic Commerce

Payment and agentic commerce protocols and specifications. Managed separately from existing generic protocols (under `payments/`). Four main pillars:

1. **Commerce flow**: ACP / AP2 / UCP — business protocols for orders, carts, and payment handlers
2. **Crypto-native payment**: x402 — HTTP-native cryptocurrency payments
3. **Agent identity (cryptographic verification)**: Visa Trusted Agent Protocol, Mastercard Verifiable Intent — cryptographic proof standards for agent identity and authorization driven by major financial players
4. **Cross-industry partnerships**: Nearly all major players—Adyen, Worldpay, Fiserv, Checkout.com, Basis Theory, Amex, JCB, PayPal—converging around AP2 and Verifiable Intent

---

### ACP (Agentic Commerce Protocol)

**Current version**: API Version 2026-04-17

**Maintainer**: OpenAI & Stripe

**Checkout state**: `7fdd78d` (untagged continuous deployment, HEAD after v2026-04-17 API, HEAD 2026-07-17)

#### Updates as of 2026-07-27 (optional product URL on checkout Item)

- **SEP: Added optional product URL to checkout Item** (#281) — allows linking from cart items to product pages

#### Changes after v2026-04-17

- **Improved embedded examples for `IntentTrace` / `CancelSessionRequest`** (2026-06-15, #253): Improved 2 embedded examples
- **Unwrapped error envelope in `delegate_payment` OpenAPI examples** (2026-06-15, #266): Unwrapped error envelope in released `delegate_payment` OpenAPI example
- **Added 2026-01-16 changelog to readme listing** (2026-06-15, #251): Added missing 2026-01-16 entry to readme changelog list
- **Fixed `MessageInfo` / `MessageWarning` / `MessageError` examples** (2026-06-11, #262): Corrected examples for all 3 message types (`MessageInfo` / `MessageWarning` / `MessageError`)
- **SEP: Added Feed Update ID to Feed API Upsert Products Response** (2026-06-04, #260)
- **Fulfillment Details on Checkout Complete (SEP)**: SEP allowing fulfillment details to be returned upon checkout completion (#200)
- **Suggested Pricing on Checkout Create (SEP)**: SEP allowing suggested pricing when creating a checkout (#201)
- **Fixed `delegate_payment` OpenAPI examples error envelope**: Fixed `delegate_payment` OpenAPI examples to unwrap error envelope (#243)
- **Aligned refund amount example with schema**: Fixed type in spec/2026-01-30 refund amount example to match schema (#249)
- **Stale PR Reminder Workflow**: Added workflow sending reminders for stale PRs (#240)
- **Order Schema Post-Checkout SEP**: Post-checkout Order Schema alignment SEP (#232)
- **Added `UpsertProductsResponse` JSON Schema**: Added `UpsertProductsResponse` to feed JSON Schema bundle (#241)
- **Added Meta as TSC member**: Added Meta to TSC members (#236)
- **Fixed `Address.company` description**: Fixed copy-paste error (#193)
- **Added `intervention_required` documentation**: Added `intervention_required` to RFC error code docs (#143)
- **Intent traces examples**: Added intent traces examples for all reason codes (#151)
- **Agentic Commerce Inc. CLA signature**: Added Agentic Commerce Inc. as Corporate CLA signatory for Catalog (#226)

#### Key Changes in v2026-04-17

- **Cart Capability SEP**: Added Cart Capability (#188)
- **Product Feeds API SEP**: Added Product Feeds API (#190)
- **Marketing Consent SEP**: Added marketing consent flow (#199)
- **Markdown Content Specification (CommonMark)**: Defined Markdown content spec (#212)
- **Payment Intent (capture vs authorize)**: Payment intent including PaymentHandler `display_name` (#130)
- **Payment Handler display order**: Supported merchant-suggested display order (#133)
- **Mandatory Idempotency Requirements**: SEP mandating idempotency requirements and guarantees (#121)
- **Rich Post-Purchase Lifecycle Tracking**: Added post-purchase lifecycle tracking to Order schema (#106)
- **Discovery RFC seller terminology**: Restructured discovery RFC around seller terminology (#176)
- **TSC Operating Model**: Added TSC operating model doc (#184)
- **Added CLA signatories**: Meta Platforms, Affirm, PayPal, and Agentic Commerce (Catalog) signed CLA
- **Fixed `risk_signals` spec**: Allowed empty `risk_signals` in `delegate_payment` (#214)
- **Revised governance model**: Updated governance structure including TSC and DWGs (#173)
- **Hardened Webhook Signing Replay Protection**: Strengthened replay attack prevention (#160)
- **Delegated Authentication API**: API contract for merchant-specified authentication (#93)
- **Discovery Well-Known Document implementation**: (#137)
- **MCP Transport Binding**: MCP transport binding for Agentic Checkout (#139)

#### Key Changes in v2026-01-30

- **Capability Negotiation**: Capability negotiation between agents and sellers
- **Payment Handlers Framework**: Structured payment handlers (**breaking change**)
- **Extensions Framework**: Optional, composable extensions
- **Discount Extension**: Rich discount code support (first ACP extension)

#### Breaking Changes

| Change | Impact |
|---|---|
| Introduced Payment Handlers (v2026-01-30) | Must migrate from payment method IDs to structured handlers |
| `items` → `line_items` | Field rename in Create/Update requests |
| Required `currency` | Now mandatory on create requests |
| Removed `channel` field (#85) | Removed from `AuthenticationMetadata` |

#### Reference Links

- [ACP Protocol](https://agenticcommerce.dev)

---

### AP2 (Agent Payments Protocol)

**Current version**: v0.2.0 (2026-04-28)

**Maintainer**: Google Agentic Commerce

**Notable**: **v0.2.0 released** on 2026-04-28, reaching the official AP2 V2 spec release as `Release of V2 (#233)`. Cross-industry hub uniting 60+ partners including PayPal, Adyen, Amex, Mastercard, JCB, and Worldpay.

#### Changes after v0.2.0

- **Removed uvlock**: Excluded `uv.lock` from repository (#246)
- **Updated CHANGELOG.md**: Updated CHANGELOG for 0.2.0 release (#239)
- **Updated video title**: Fixed README video title (#238)
- **Updated CONTRIBUTING.md**: Updated contribution guidelines (#240)

#### Key Changes from v0.1.0 → v0.2.0

- **AP2 V2 Release**: Official release of V2 specification (#233)
- **PaymentReceipt**: Implemented transaction confirmation object (#110)
- **X402 Payments**: x402 payment method integration (Python sample) (#121)
- **Go Sample**: Standalone Go implementation example (#101)
- **Vertex AI Auth**: Added Vertex AI authentication support alongside Google API keys (#48)
- **X-A2A-Extensions Header Logging**: Header logging in server middleware (#29)
- **UCP Integration Docs**: Universal Commerce Protocol integration (#138)
- **Kite AI / Global Payments / Tether / Solana / OKX / Nexi**: Added numerous partners

#### Reference Links

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### UCP (Universal Commerce Protocol)

**Current version**: **v2026-08-25 (2026-08-25)**

**Checkout state**: `9756aa96` (`git describe` = `v2026-01-23-269-g9756aa96`, HEAD 2026-10-12. Protocol tag remains v2026-08-25)

#### Verified 2026-10-13 (5 commits; protocol version unchanged)

[Diff for this update](https://github.com/Universal-Commerce-Protocol/ucp/compare/f2206e68...9756aa96). Changes are on HEAD; public release remains v2026-08-25.

- **fix (cart)**: Omitted `cart_id` in `complete_checkout` request (#911)
- **docs**: Clarified `line_items` requirements for cart-to-checkout conversion (#910); added contributing guide to ucp.dev (#888); restored type recovery in bundled schemas (#919)
- **deps**: urllib3 2.8.0 (#923)

#### 2026-09-16 to 2026-09-22 Updates (5 commits; protocol version unchanged)

- **ci**: Hardened ucp workflows (#847)
- **fix**: Read docs as UTF-8; named missing `ucp-schema` binary (#840)
- **docs**: Restored specification overview section order (#823)
- **deps**: soupsieve 2.9 (#834), anyio 4.14.2 (#844)

#### 2026-09-01 to 2026-09-15 Updates (Payments Technical Council announced + dependency CVE fixes; protocol version unchanged)

- **docs: Announced Payments Technical Council members** (#809)
- **SECURITY**: **Updated js-yaml to 4.3.2 to resolve CVE-2026-84375** (#814); mitigated vulnerability via fast-uri override (#803); disallowed private registries in lockfiles (#806)
- **fix**: Required skipping all words + non-empty reason in example annotations (#767); handled off-site links externally in docs link checker (#772)
- **Note**: Old protocol tag `v2026-04-08` was rewritten on remote for **loyalty extension backport (#813)** (conflicts with local tags; requires `git fetch --tags --force`)

#### 2026-08-01 to 2026-08-27 Updates (**v2026-08-25 protocol release**: multi-vertical expansion + request constraints + 3DS2; 7 breaking changes)

**v2026-08-25 release** (2026-08-25 tag, release announcement #770): Major release including major protocol enhancements, structural refactoring for multi-vertical expansion, payments security (3DS2), structured request constraints, independent capability versioning, and grocery shopping readiness.

- **Added Location Search + Lookup capabilities** (#589, `feat!`); fulfillment behavior for location context (#671)
- **Request constraints**: Expressed instrument requirements via request constraints; **split PAN and Network Token credential types** (#424, `feat!`); `anyOf` constraint + payments example (#757); response-carried request constraints (#655)
- **Structural refactoring (multi-vertical expansion)**: Moved Payment constructs from `shopping/` to `common/` (#741, `refactor!`); moved common primitive types to `common/types` (#736, `refactor!`); reorganized specification hierarchy by domain verticals (Shopping / Payment / Common) (#723); moved shopping extensions into nested subfolders (#761)
- **Made token binding vertical-agnostic** (#746, `refactor!`)
- **Transition & deprecated schema cleanup + fulfillment fixes** (#763, `fix!`); made destination types explicit (#688, `fix!`)

| Breaking Change (v2026-08-25) | Impact |
|---|---|
| Location Search + Lookup capabilities (#589) | Profile structure changed with new capabilities |
| Request constraints + PAN/Network Token credential type split (#424) | Changed instrument requirements representation; explicit credential type required |
| Moved Payment constructs / common types to `common/` (#741, #736) | Extension namespaces and schema paths changed; consumers must update references |
| Made token binding vertical-agnostic (#746) | Binding definitions require migration |
| Transition & deprecated schema cleanup (#763) / explicit destination types (#688) | Users of deprecated schemas must migrate to new schemas |

**governance**: **Lodging TC formed** (2026-08-11: Amadeus / Booking.com / Expedia / Google / Hilton / Marriott / Trip.com). Second vertical-specific Technical Council after Food TC (2026-07-16: Block/DoorDash/Google/Toast/Uber Eats)

#### 2026-07-28 to 2026-07-31 Updates (Made `cart.id` optional; fix/docs only)

- **fix: Changed `cart.id` on update requests from required to optional (omitted)** (#633) — backward-compatible relaxation from required → optional
- **docs: Clarified response values set by business in identity-linked sessions** (#585)
- deps: `datamodel-code-generator` 0.64.0 (#654), `pymdown-extensions` 11.0 (#643). No breaking changes or security fixes

#### Updates as of 2026-07-27 (Added `policies[]` + extension-defined Actions + shopping permalink)

- **Added `policies[]` to cart / checkout / catalog / order** (#572) — unified field for referencing transaction policies
- **Extension-defined Actions primitive** (#582) — foundation allowing extensions to define custom Actions
- **Shopping permalink capability** (#523); added per-op example scaffold for catalog `get_product` (#616)
- **fix: Authority binding allows exact name-host match** (#627); updated signature example to spec-compliant raw `r||s` (#590); targeted fulfillment extension at checkout (#592)
- deps: js-yaml / fast-uri (#621), pillow 12.3.0 (#619)

#### Updates as of 2026-07-18 (`keys[]` promotion = breaking / governance workflow setup)

- **Promoted `keys[]` to canonical profile signing key field (#566, 2026-07-12, breaking)**
- **Added per-operation Requirement column to spec** (#542)
- **governance**: Added governance workflow and deleted CODEOWNERS (#583); redirected MAINTAINERS.md to central repo (#598); consolidated duplicate `merchant_fulfillment_config` into canonical business config (#581)

| Breaking Change | Impact |
|---|---|
| Promoted `keys[]` to canonical signing key field (#566) | Profile signing key lookup changed; consumers of old field must migrate |

#### 2026-07-02 to 2026-07-03 Updates (Web Bot Auth interop + normalized namespace authority binding)

- **Web Bot Auth (WBA) interoperability** (#483): Added **EdDSA (Ed25519, [RFC 8037](https://datatracker.ietf.org/doc/html/rfc8037)) as an optional algorithm** to signing key JWK schema and signature spec. Maintained ECDSA P-256 (ES256) as UCP baseline. Verifiers choosing WBA interoperability MUST support EdDSA (because WBA requires Ed25519). Backward-compatible
- **Defined namespace authority binding + extended RDNS grammar** (#530): Specified canonical procedure binding declared schema URLs to reverse-domain authority (using URL parser, requiring https, rejecting userinfo, requiring registered domain, reversing labels to form `authority_prefix`). Resolved prior contradiction between "MUST validate" and "SHOULD reject" — strengthened normative rules against namespace spoofing
- **docs: Fixed "Capabilities Incompatible" example to `capabilities_incompatible`** (#562)

#### 2026-06-30 Updates (Fixed array labels in schema ref tables / added catalog REST headers)

- **Added HTTP Headers section to catalog REST**: Added "HTTP Headers" section to catalog REST binding (`docs/specification/catalog/rest.md`). Specified `UCP-Agent` header as MUST across all operations, carrying the platform profile URI (`profile="https://platform.example/profile"`) using Dictionary Structured Field syntax ([RFC 8941](https://datatracker.ietf.org/doc/html/rfc8941)) (#548)
- **Schema reference tables: Labeled array elements with type names (fixed `Array[any]`)**: Fixed rendering bug where array properties whose element types could not be read inline due to `allOf` definitions or resolved `$ref` inlining rendered as `Array[any]` in reference tables. All 11 affected cells (`totals` across AP2 / buyer consent / discount / fulfillment / split payments extension capability tables, and `products` in catalog lookup) now render accurately as `Array[Total]` / `Array[Product]`. Schema definitions themselves are unchanged from base; fix is in reference table rendering (`main.py`) only (#552)

#### 2026-06-29 Updates (CI/tooling only)

- **Updated workflow path triggers & resolved conflicts**: Adjusted path triggers for docs / linter workflows; minor tweaks to cspell custom dictionary and pre-commit config. No spec or schema changes (#232)

#### 2026-06-26 Updates (Fulfillment methods into catalog — breaking / docs / Tech Council)

- **BREAKING: Expanded fulfillment methods to catalog surface** (#507, `feat!`): Composed `dev.ucp.shopping.fulfillment` not only into checkout but also catalog surfaces (search / lookup / get_product), letting variants advertise fulfillment options via `fulfillment.methods[]` (method-first discovery, making shipping/pickup peer methods). Opened checkout's closed `type` enum into an open string vocabulary (well-known: shipping / pickup; unknown values ignored) and restructured destinations into a single shape `{ id, name?, address?, availability }`
- **schema reference: Fixed inline `oneOf` branch rendering** (#549)
- **Error Handling docs: Added `message.path` field convention** (#397)
- **Wrapped embedded session error under `params.error`** (#494, fixed examples)
- **Linked common types to shared references section** (#536)
- **Added schema / documentation development instructions to README** (#452)
- **site nav**: Added announcements section (#529); moved overview to end of nav (#539)
- **Tech Council member change**: Naga Malepati → Uddhav Kambli (#541)

#### 2026-06-19 Updates (Unified path field descriptions / Booking.com logo / CI)

- **Unified `path` field descriptions across message schemas**: Harmonized descriptions of the `path` field across message schemas (#380, docs)
- **Updated Booking.com SVG logo to new branding** (#526, style)
- **Fixed `ucp-schema` caching** (#522, ci): Fixed CI `ucp-schema` caching bug

#### 2026-06-17 Updates (Catalog example validation refactor / docs / AGENTS.md)

- **Validated catalog examples by op + direction and removed `def=`** (#516): Refactored catalog example validation to operation + direction granularity and dropped `def=`
- **Added AGENTS.md**: Added AGENTS.md for coding assistants (#510)
- **docs**: Improved footnote rendering and table alignment in `signatures.md` (#291); cross-linked `cart_id` from Create Checkout (#439); qualified `get_product` catalog error severity note (#464); rendered Catalog response metadata on schema reference page (#465); added missing Discovery section to REST binding (#509)
- **ci**: Bumped GitHub Actions for Node 24 compatibility (#521)

#### 2026-06-15 Updates (Build script improvement)

- **Added serving instructions to build script output**: Appended serving instructions to end of build script output (#432)

#### 2026-06-12 Updates (Buyer consent per-segment breaking / delegated IdP)

- **BREAKING: Per-segment extensibility for buyer consent** (#451): Made buyer consent extensible per segment. Marked `feat!`, breaking backward compatibility
- **Added delegated identity providers + accelerated IdP flow** (#423): Added delegated identity providers and accelerated IdP flow
- **Added signature response headers to `get_order`**: Added missing signature response headers to `get_order` (#370)
- **Preserved required fields when rendering embedded schemas**: Preserved required fields during embedded schema rendering (#501)
- **Google TC member change**: Venu → Jing (#506)
- **docs fixes**: Removed unnecessary `fulfillment-option` entity from checkout (#284); fixed identity linking formatting (#505); corrected invalid UCP version in cart error response examples (#504)

#### 2026-06 Updates (Split payments extension / idempotency contract)

- **Added split payments extension**: Introduced split payments extension (following discount and loyalty extensions) (#409)
- **Documented idempotency payload-mismatch contract**: Documented contract for idempotency payload mismatches (#485)
- **Updated Amadeus logo**: Highlighted Amadeus logo in lodging section (#488); replaced legacy Amadeus SVG with updated version (#468)
- **stylelint / SVG formatting fixes**: Excluded `local_preview` and `site` directories from stylelint (#495); fixed pre-commit SVG formatting and trailing newlines (#491)

#### Changes after v2026-04-08

- **`feat`: Loyalty extension for catalog/cart/checkout capability**: Added loyalty extension to catalog / cart / checkout capabilities (2nd official extension after discount) (#340)
- **Schema-validated documentation examples**: Organized doc examples around schema validation (#359)
- **Added partner logos**: Added partner logos and configuration to documentation assets; cleaned up logo formats and layout (#453)
- **idna / pymdown-extensions dependency bumps**: idna 3.11 → 3.15 (#457), pymdown-extensions 10.21.2 → 10.21.3 (#456)
- **Fixed PR auto-labeler permissions**: Fixed permissions on PR auto-labeler (#454)
- **Schema refactor**: Organized schema references into common types (#436)
- **Fixed profile schemas validation (breaking)**: Fixed profile schemas to match validation and endpoint contracts; backward-incompatible schema correction (#429)
- **urllib3 v2.7.0 security bump**: urllib3 2.6.3 → 2.7.0 (#434)
- **Removed server startup from `build_local.sh`**: Removed server start from `build_local.sh` (#430)
- **Identity Linking OAuth 2.0 foundation**: Added OAuth 2.0 foundation for identity linking based on capability-driven scopes (**breaking change**) (#354)
- **Added `attribution` field**: Added attribution field for platform referral context (#391)
- **Expanded core-concepts**: Integrated comprehensive UCP protocol overview into `core-concepts` doc (#336)
- **Standardized glossary / acronyms**: Added centralized glossary and acronym standards (#241)
- **Fixed deprecated checkout id**: Omitted deprecated checkout id from playground payloads (#332)
- **Blocked corporate registries**: Blocked corporate registries (#411)
- **Fixed typos / formatting**: Fixed typos and formatting in index and versioning docs (#416)
- **Added Twum Djin to Governance Council**: Added Twum Djin to Governance Council (#395)
- **Extracted Configure Site URL as shared action**: Extracted CI step into composite action (#382)
- **Added extensibility & forward-compatibility guidelines**: Added extensibility and forward compatibility guidelines to docs (#290)
- **Fixed discounts extension schema**: Fixed mismatch between doc examples and discounts extension schema (#371)
- **Updated Tech Council maintainer list**: Updated maintainer list
- **Removed legacy PR template**: (#377)
- **Modernized `signatures.md` text diagrams**: (#331)
- **Fixed `create_cart` `ucp_agent` parameter**: Added missing `ucp_agent` parameter in REST operation (#362)
- **Fixed Total/Totals field rendering**: Fixed issue where Total/Totals were not rendered on schema reference page (#352)
- **Removed entity wrapper from MCP response examples**: Removed unnecessary entity wrappers from MCP response examples (#360)
- **Fixed documentation accuracy**: Fixed spec example inconsistencies and accuracy (#363, #365)
- **Fixed Profile examples**: Fixed profile examples inside Playground widget (#236)
- **Standardized lockfile package registries**: Standardized package registries in lockfiles (#368)
- **Upgraded super linter**: (#372)
- **Added PR auto-labeler**: (#366)
- **Differentiated line item ids**: Distinguished line item ids from item ids (#112)

#### Key Changes in v2026-04-08

- **Renamed `variant.selected_options` → `options`**: Renamed variant options field (#353) (**breaking change**)
- **Separated Webhook fields**: Split dangling webhook fields into headers; changed transports to reference base schemas only (#342) (**breaking change**)
- **Unified UCP error conventions**: Unified embedded protocol errors with UCP error conventions (#325) (**breaking change**)
- **Get Order operation**: Added Get Order operation with platform-auth (#276)
- **Required Order `currency`**: Made `currency` mandatory in Order schema (#283) (**breaking change**)
- **Updated Order Capability**: Updated Order capability (#254) (**breaking change**)
- **Used `signed_amount.json`**: Fixed total to use `signed_amount.json` (#299) (**breaking change**)
- **Order `label` field**: Added optional `label` field to Order (#326)
- **Reverted Identity Linking**: Reverted Identity Linking redesign (#329)
- **lodash security fix**: Updated lodash to fix Trivy vulnerability (#333)
- **Transition Schema cleanup**: Cleaned up transition schemas ahead of version cut (#341)
- **Extracted EP core**: Extracted shared EP core and grouped transports in navigation (#339)

#### Improvements after v2026-01-23 (Included in v2026-04-08)

- **Embedded Protocol Transport Binding**: Embedded protocol transport binding + re-auth mechanism for cart capability (#244)
- **Product Get Operation**: Added get product operation to `catalog.lookup` (#195)
- **Discount Capability extension**: Extended discount capability to carts (#246)
- **Eligibility Claims & Verification**: Eligibility claims and verification contract (#250)
- **Authorization & Abuse Signals**: Formalized authorization and abuse signals (#203)
- **Catalog Search & Lookup**: Catalog search and lookup for product discovery (#55)

#### Breaking Changes

| Change | Impact |
|---|---|
| Expanded fulfillment methods to catalog (#507, 2026-06-26) | Opened checkout's closed `type` enum to open vocabulary, composed fulfillment into catalog surfaces, restructured destinations to single shape. Migrate to method-first discovery |
| Fixed profile schemas validation (#429, post-v2026-04-08) | Backward-incompatible correction to profile schemas; existing implementations must re-validate |
| Identity Linking OAuth 2.0 foundation (#354, post-v2026-04-08) | Migrated to capability-driven scopes; redesign auth flows |
| `variant.selected_options` → `options` (#353) | Variant field rename |
| Separated Webhook fields to headers (#342) | Transport schema structure changed |
| Unified EP error conventions (#325) | Error response format changed |
| Required Order `currency` (#283) | `currency` mandatory when creating Orders |
| Updated Order Capability (#254) | Order capability structure changed |
| Used `signed_amount.json` (#299) | `total` format changed |
| Embedded Protocol Transport Binding (#244) | Transport + re-auth for cart capability |
| Authorization & Abuse Signals (#203) | Authorization signal structure changed |

#### Reference Links

- [UCP Protocol](https://github.com/Universal-Commerce-Protocol/ucp)

---

### x402 (Internet Native Payments)

**Current version**: Go v2.9.0 / Python v2.7.0 / TypeScript npm-@x402/\* v2.10.0 (including npm-x402@v1.1.0 legacy bundle)

**Notable**: Repository is moving to a foundation repo. Added repo move note to README (#40) and bumped main branch to align with foundation repo (#93).

#### Key Changes in Go v2.9.0

- **`SettleResponse`/`VerifyResponse` Extensions field**: Added Extensions field for TypeScript SDK parity (#1808)
- **`net/http` support docs**: Added `net/http` support to Go SDK docs (#1782)

#### Key Changes in TypeScript Core v2.10.0

- **Aptos support**: Added Aptos blockchain support
- **Stellar support**: Added Stellar blockchain support
- **Exported hook types**: Exported hook types (#1811)
- **Preserved MCP `structuredContent`**: Fixed preserving `structuredContent` in payment wrapper results (#1834)

#### Key Changes in Python v2.7.0

- **MCP `server_sync` test coverage**: Added test coverage for MCP `server_sync` module (#1733)

#### Unreleased Changes

- **Stable testnet support**: Added Stable testnet (chain ID 2201) support to EVM (#1786)
- **EVM contract deployment fix**: Fixed EVM contract deployment (#1880)
- **Added USDC**: Added USDC on Arbitrum One/Sepolia (#1877)
- **Fixed `HTTPFacilitatorClient` 308 redirects**: Fixed handling of 308 redirects (#1813)
- **Fixed Facilitator signer random selection**: Fixed randomization of signer selection (#1849)
- **Polygon mainnet**: Added default asset support on Polygon mainnet (chain ID 137) (#1791)
- **Repo move notice**: Added repository move note to README (#40)

#### Reference Links

- [x402 Protocol](https://github.com/coinbase/x402)

---

### Visa Trusted Agent Protocol

**Current version**: Initial spec + sample implementation (untagged, 6 commits, launched in 2026)

**Maintainer**: Visa Inc. (major credit card network)

**Notable**: Standardizes **agent identity / authorization** in agentic commerce. Positioned as an **identity complement layer** to existing payment protocols (ACP / AP2 / UCP / x402). One of the few agentic commerce identity standards driven by a major financial player (Visa).

#### Key Features

- **Cryptographic Identity Proof**: AI agents prove their identity and user-delegated authority to merchants using **cryptographic signatures**
- **Signed contents**: Includes timestamp, unique session identifier, key identifier, and algorithm identifier (replay prevention)
- **Context-Bound Security**: Every request is cryptographically locked to the merchant's **specific website + exact page being operated on**, preventing authorization reuse elsewhere
- **Replay Attack Prevention**: Time-sensitive elements make each request unique and valid only once
- **Standardized Customer / Payment Identifier Delivery**: Securely delivers consented consumer's **PAR (Payment Account Reference)**, verifiable consumer identifier, loyalty number, email, phone, etc., via query parameters to the merchant
- **Authorization for both Browse / Payment**: Signatures bound separately per action type (browsing and payment)
- **Anti-Fraud**: Clearly distinguishes authenticated agents from anonymous bots, reducing chargebacks and fraud

#### Repo Structure

- Spec + sample implementation (multiple components in Quick Start)
- **Added nonce validation sample code** (reference implementation for replay-prevention verification)

#### Reference Links

- [visa/trusted-agent-protocol (GitHub)](https://github.com/visa/trusted-agent-protocol)

---

### Mastercard Verifiable Intent

**Current version**: v0.1.0 (Draft), last push 2026-04-20, +4 commits since v0.1.0 tag

**Maintainer**: Mastercard (co-developed with Google)

**Notable**: Open-sourced on 2026-03-05. Major financial-player agent identity / authorization standard alongside Visa Trusted Agent Protocol. Proves "user-to-agent delegation scope" in a tamper-evident way using an **SD-JWT (Selective Disclosure JWT)-based** cryptographic credential chain. Explicitly designed to interoperate with AP2 / UCP (complementary rather than rival).

#### Key Features

- **SD-JWT credential format**: Selective Disclosure reveals only the minimum required information to each party (privacy-preserving)
- **Layered tamper-evident chain**: Cryptographically proves that an AI agent's commercial action is within the user's delegation scope
- **Two execution modes**:
    - **Immediate**: User confirms each time (user-confirmed)
    - **Autonomous**: Delegated to agent (agent-delegated)
- **Standards-based**: FIDO Alliance / EMVCo / IETF / W3C
- **Interoperable with AP2 / UCP**: Designed as a complementary standard
- **Reference implementation**: Includes official 100% Python reference implementation

#### Industry Commitments (at 2026-03-05 announcement)

| Company | Role |
|---|---|
| Google | Co-developer |
| Fiserv / IBM / Checkout.com / Basis Theory / Getnet | Endorsing supporters |
| Adyen / Worldpay (Global Payments) | Endorsing supporters |

#### Reference Links

- [agent-intent/verifiable-intent (GitHub)](https://github.com/agent-intent/verifiable-intent)
- [verifiableintent.dev](https://verifiableintent.dev/)
- [Verifiable Intent spec overview](https://verifiableintent.dev/spec/)
- [Mastercard - Verifiable Intent](https://www.mastercard.com/global/en/news-and-trends/stories/2026/verifiable-intent.html)

---

### Summary of Existing Commerce Protocols (Cross-Protocol Comparison)

| Protocol | Domain | Maintainer |
|---|---|---|
| **ACP** (Agentic Commerce Protocol) | Order / Cart / Payment Handler layer | OpenAI + Stripe |
| **AP2** (Agent Payments Protocol) | Payment Receipt / Payment method integration | Google + 60 partners |
| **UCP** (Universal Commerce Protocol) | Cart / Catalog / Order / Discount / Identity Linking | Universal Commerce Protocol community |
| **x402** | Crypto-native HTTP payment | Coinbase |
| **Visa Trusted Agent Protocol** | Cryptographic proof of agent identity / authorization (verified by merchant) | Visa |
| **Mastercard Verifiable Intent** | Verify user → agent delegation scope via SD-JWT chain (privacy-preserving) | Mastercard + Google |

---

## Google Cloud / ADK

### ADK Python

**Current version**: **v2.11.0 (2026-10-01)** / v1.39.1 (2026-08-27, stable lts)

**Checkout state**: `e8b019239` (HEAD of OSS mirror main, HEAD 2026-10-12. Due to Copybara, `git describe` outputs the `v1.15.0` series; treat explicit tags and CHANGELOG as authoritative for versions)

#### Verified 2026-10-13 (main after v2.11.0: Gemini continuation / rewind / live cleanup)

[Diff for this update](https://github.com/google/adk-python/compare/2f2243dc...e8b019239). The items below are unreleased changes on HEAD, not features of v2.11.0.

- **feat**: **Resume stopped Gemini generation with continuation token**, vmaas sandbox lifecycle helper, client label on `model_consult` advisor requests, Python 3.15 support
- **fix**: Prevent telemetry from retaining OTel context across async generator yields, call `before_run` / `after_run` plugin callbacks in `run_node_live`, record artifact version on rewind and avoid generating tombstone parts every time, skip credential exchange events when adding to Memory Bank, strictly decode url-safe base64 and reject invalid input, use `asyncio.sleep` in `PlaywrightComputer` async methods
- **refactor**: `AudioCacheManager` → `RealtimeCacheManager`, consolidated workflow interrupt event helpers into `events._interrupts`

#### 2026-09-23 to 2026-10-07 Updates (**v2.10.0 / v2.11.0**: execution cancellation / workflow tool confirmation / ModelConsultTool / SQLite memory)

- **v2.10.0 (2026-09-24)**: **Ephemeral Skills lifecycle and active skill limit** (experimental, `ADK_ENABLE_SKILL_LIFECYCLE=1`), **MongoDB toolset** (vector / hybrid search), **duration / token / model call count metrics in eval**, automatic request parameter adaptation and reasoning token reporting for OpenAI reasoning models
- **Breaking/behavioral changes (v2.10.0)**: BigQuery protected write mode dry-run only executes non-SELECT targeting session's anonymous dataset (multi-statement scripts / `CALL` / `EXPORT DATA` rejected); BigQuery protected mode sessions are held in process memory (do not persist across restarts or replicas); `OpenAIResponsesLlm` ignores `thinking_config` with a warning (use `OpenAIGenerateContentConfig.effort`); `AgentEvaluator.evaluate` / `evaluate_eval_set` raise `ValueError` on 0 eval cases; instruction templating preserves `${var}` and `\{var}` literally; old live-audio modules (under `google.adk.flows.llm_flows`) emit `DeprecationWarning` (migrate to `google.adk.live`)
- **v2.11.0 (2026-10-01)**: **Graceful cancellation of Runner / Workflow / Node via `abort_signal`** (`/run_sse` cancels runs on client disconnect), **Tool node pauses for tool confirmation with `RequestInput`** (same behavior as LlmAgent), **`ModelConsultTool`** (consult another model mid-task, bounded by turn / session budget), **SQLite memory service** (`sqlite://` URI), **opt-in modern-protocol connection path for MCP SDK 2.x**, `ToolCallIntegrityPlugin`, BigQuery tools usable in CMEK-required environments, Vertex project defaulted from GCP metadata
- **Breaking (v2.11.0)**: **Server serves Dev UI runtime config** (returns `/dev-ui/assets/config/runtime-config.json` per request instead of writing into package). Configure logo via `--logo-text` / `--logo-image-url` and fetch config from the server
- **HEAD (after v2.11.0)**: Unreleased changes on main (see CHANGELOG for details)

#### 2026-09-16 to 2026-09-22 Updates (**v2.9.1 / v2.9.2** + HEAD)

- **v2.9.1 (2026-09-15)**: Claude adaptive thinking — requests visible thoughts to expose step-by-step reasoning (ba0d542)
- **v2.9.2 (2026-09-18)**: Telemetry — preserved OTel event names on platforms outside Agent Engine (9110770)
- **HEAD (after v2.9.2)**: `OpenAILlm` `api_key`/`base_url` + per-request key resolution (56aabce2), honored `tool_config` mode and all tool declarations (ed758bba), robust parsing of Chat Completions responses (f28d28a3), `SkillToolset` detects skill changes (f848b7e3), workflow `DEFAULT_ROUTE` fan-out (ffc191bb), resolved interrupts resume without `rerun_on_resume` (307d0413), restored oldest-first order for Redis session list (68638424), `InvocationNotFoundError` on rewind (fc16a78a), artifact reference resolution depth limit (87b9f25b)

#### 2026-09-01 to 2026-09-15 Updates (**v2.9.0**: FallbackModel / LiveKit / YAML graphs / MCP SDK 2.x + 3 breaking changes)

- **v2.9.0 highlights**: **Automatic failover on primary model failure via `FallbackModel`**, **LiveKit runner for voice / telephony**, **load ADK 2.0 graphs from YAML**, **accept MCP SDK 2.x while staying 1.x compatible**
- **Breaking (v2.9.0)**: Failed workflow nodes re-execute on resume (no completion replay → make node bodies idempotent); GCS tool local paths restricted under `local_file_root` (rejected if unset); `InMemorySessionService` raises `SessionNotFoundError` when appending to an unowned session (aligned with DB backends)
- **MCP 2.x note**: When SDK 2.x is explicitly installed, undeclared fields fail validation (put vendor extensions under `_meta`); 1.x behaves as before
- **HEAD (after v2.9.0)**: MongoDB toolset (vector / hybrid search), `SkillDiscoveryMode`, optional `context_builder` on `RemoteA2aAgent`, BigQuery `default_project_id` / `default_dataset_id`, streaming partial function-call arguments, MCP ADC over https only

#### 2026-08-01 to 2026-08-31 Updates (v2.6.2 to v2.8.0 + lts v1.37.0 to v1.39.1: model capability declaration / media-returning tools / Model Armor / FallbackModel / HITL enhancements)

**Releases**: v2.6.2 (08-03) / v2.6.3 (08-07) / **v2.7.0 (08-13)** / v2.7.1 (08-17) / **v2.8.0 (08-25)**; stable lts: v1.37.0 (07-30) / v1.38.0 (08-07) / v1.39.0 (08-17) / v1.39.1 (08-27).

- **v2.7.0 (correctness release)**: **Models self-declare capabilities** (removed model ID inference; checks output schema × tools combinations by model capability), **tools can return media (images, etc.) in function responses** (Gemini / Anthropic / LiteLLM / Apigee / OCI), conversation history preserves thought signatures, server-side tool call parts, and parallel function call results across round-trips, **Jinja2 instruction templates** (`use_jinja2=True`, `{{ artifact("name") }}` helper, optional dependency), faster imports and eliminated O(n^2) Pydantic round-trips and streaming accumulation
- **Breaking (v2.7.0)**: **Moved `pyarrow` from `gcp` extra to new `bigquery-analytics` extra** — shrinks `pip install google-adk[gcp]` by ~50 MB. `BigQueryAgentAnalyticsPlugin` users must install `google-adk[bigquery-analytics]`
- **v2.8.0**: **Model Armor guardrail plugin**, **`FallbackModel` (automatic model failover)**, **load ADK 2.0 graph workflows from YAML config**, `RemoteA2aAgent` native task mode + `auth_scheme`/`auth_credential`, `data_agent` toolset CRUD tools, `ADK_MAX_LLM_CALLS` env, telemetry (per-invocation / per-workflow token spend, OTLP logs export, OTel log records for MCP HTTP exchanges), live (before/after model callbacks, VIDEO modality, direct user send for streaming tools, session resumption handle), eval (custom metrics, `asyncio.gather` parallelization for LLM-as-judge), Vertex AI API version config, `GcsArtifactService` signed/authenticated URLs, Antigravity client-side tool outcomes
- **SECURITY (main / included in releases)**: **SQL injection guard for BigQuery tools** (d6290a0), **fenced relayed agent output to prevent spoofing instructions** (9ffe8be), **blocked YAML / ruamel deserialization in agent-config code references** (924d802), **optional OIDC verification on Pub/Sub and Eventarc triggers** (73d9fe05), validated `app_name` before deploy Dockerfile interpolation (6eb1d35d), rejected transfers to forbidden parent/peer agents (b0503a03), stopped caching failed-verification remote agent cards (2685acd3)
- **workflow / HITL**: **Multi-turn nested HITL pauses and resumption across workflows and agent tools** (6d145180), aligned callback lifecycle for hallucinated tool calls (f842a15c), stabilized invocation resolution on resume (8db82ba2, ed1306f5), prevented duplicate user events on invocation retry (d06a7fed), scoped `ParallelAgent` early exit to direct sub-agent escalations (cd04c7a7)
- **Other**: Rebound callback methods on agent clone (f449bb70), forwarded generation config (temperature/top_p/…/media_resolution) to Live API (bd74c42b), coerced integral floats to int-typed tool parameters (adbee3cd), resolved all Claude model IDs rather than enumerating (01919b37), reported unknown tool names to the model (f3377937), stopped `ContainerCodeExecutor` atexit leak (04f8df11), labeled dynamic instructions so they are not misread as user turns (8cdbbb15), eliminated O(n^2) comparison in session rehydration (b8dd086)
- **v1 lts**: Fixed remaining v1 backport review items in v1.39.x; sent api registry credentials only to google api endpoints (#6889); restored accepting session resource names (#6888)

#### 2026-07-27 to 2026-07-31 Updates (v2.6.0 / v2.6.1 releases + 118 commits on main: CLI telemetry / OCI provider / supply-chain protection)

**Releases**: **v2.6.0 (2026-07-30)** and **v2.6.1 (2026-07-31)** tagged on the release branch and merged back to main (a5b5b468 / 82d5f988; CHANGELOG dates are 2.6.1=2026-07-30 / 2.6.0=2026-07-29).

- **Breaking (2.6.0)**: **Namespaced file artifacts per app** (f72f0db) — breaks compatibility with existing artifact paths. **Required patched async LangGraph runtime** and updated graph field types (551372b)
- **CLI telemetry**: Collected metrics for ADK CLI runs (2280f1c), consent checks / status command / interrupt safety (6bab08f), TTY connectivity capture (c12a025), parent terminal grouping + TTL pruning (2c6a7ff)
- **Models/providers**: LLM capability reporting system (2aff82c), **added OCI Generative AI provider** (#5069 / 625ef1a), `ReflectAndRetryModelPlugin` for self-healing (322f455)
- **A2A / MCP / tools**: Per-invocation auth headers for fetching agent cards (3dd1156), `elicitation_callback` on `McpToolset` (4824619), HTTP trace debugging for MCP Toolset (6d8045c), skill script execution inside Environment (fa31b6c)
- **realtime / eval / telemetry**: `audio_stream_end` on realtime input (0f738a5), public entrypoint for live/audio eval (5091f0a), request-driven metric export for Agent Engine (8930d9b), `gen_ai.agent.name` attribute on `execute_tool` spans (1a80962)
- **SECURITY / supply chain**: **Published `constraints-3.11/3.12.txt` with a 4-day buffer to protect transitive dependencies against supply-chain attacks** (75c773e), **excluded LangGraph releases containing unsafe checkpoint loading from dependencies** (1b12ee39), restricted A2A agent card RPC targets (SSRF mitigation, 16cbb7d), ignored A2A peer-supplied event actions metadata (0ba7d3c), stopped mounting cluster credentials into GKE code sandbox (8207880), stopped tracing credentials via `config.http_options` (761f1ac), validated skill names before building skill URLs (11101ac), killed runaway code on executor timeout (27548e3), moved synchronous OAuth2 token calls off the event loop (b0f52f0)

#### Updates as of 2026-07-27 (v1.36.2 stable lts release + 76 commits on main: security hardening / Eventarc toolset / audio user simulator)

- **Tagged v1.36.2 (2026-07-21)** (stable lts series). v2.x remains at v2.5.0
- **SECURITY: Prevented continuation forgery on tool confirmations** — blocks spoofing confirmed continuations
- **SECURITY: Rejected `base_url` / `extra_body` in `generate_content_config`** (closes accidental external exfiltration path); `http_options.extra_body` remains allowed
- **feat(eventarc): Added Eventarc Advanced toolset to ADK**; added **telemetry consent config endpoint** + local write utility
- **Audio-capable user simulator** (`LlmAudioUserSimulator` + Cloud TTS) and batch of eval samples (`user_simulation` / `rubric_criteria` / `llm_judge_match` / `custom_metric` / `basic_criteria`, etc.)
- **feat: Served `to_a2a` agents under a path prefix**, user labels support in RunConfig, `state_delta` on LiveRequest (live mode), forwarded ManagedAgent instructions to `system_instruction`
- **Fixes**: Prevented prompt cache invalidation with dynamic tools; AnthropicLlm `finish_reason` / thinking-block signatures; respected A2A `Message.role` / raw bytes base64 / preserved metadata; prevented `transfer_to_agent` loops; Windows path support; lazy imports for heavy dependencies

#### Updates as of 2026-07-18 (Tagged v2.5.0: ManagedAgent expansion / Skill Registry / pervasive mTLS)

- **v2.5.0 (2026-07-16)**: Updated from v2.4.0 → v2.5.0
- **ManagedAgent (Managed Agents API backed)**: `single_turn` mode, remote MCP server support, `node_input`→`user_content` bridging (2.4.0–2.5.0)
- **Workflow resumability / HITL**: State-based resumption for task-mode workflow nodes, HITL resumption for standalone nodes and NodeTool, resumability checkpoints (2.3.0–2.5.0)
- **Skill / Agent Registry**: Added `GCPSkillRegistry`, plus registries for searching agents and MCP servers (1.34.0, 2.5.0)
- **Pervasive mTLS + security fixes**: mTLS for Google API tools / `DiscoveryEngineSearchTool` / telemetry exporters; SSRF, artifact path traversal, tool confirmation continuation forgery, and starlette CVE fixes (2.4.0–2.5.0)
- **Breaking**: Removed event logger setup due to OpenTelemetry Events API/SDK deprecation (2.5.0) — telemetry configuration via Events API is disabled

#### 2026-07-02 to 2026-07-07 Updates (Tagged v2.4.0 / v1.36.1 + 67 commits on main: Workflow as Tool / ManagedAgent / security hardening)

**Releases**: **v2.4.0 (2026-07-07)** and **v1.36.1 (2026-07-06, stable lts)** were tagged on the release branch (CHANGELOG not yet mirrored to main, so full breakdown follows in the next window). Key changes in +67 commits on main (referenced by short hash as Copybara exports omit PR numbers):

- **Core Workflow as Tool feature**: Implemented core support for invoking workflows as tools (1263ed64)
- **ManagedAgent**: Added ManagedAgent via Managed Agents API (cf91b844) + sample
- **`model_input_context`**: Added ephemeral context for LLM requests (2aeb1e1b)
- **Expanded mTLS support**: GDA client / Google API tools (e85a7b28, 3466586b); used mTLS endpoint for OAuth2 token requests (ffe41f05)
- **DaytonaEnvironment**: Added remote sandbox workspace environment (df6baf4a)
- **McpToolset**: Exposed configurable parameters as properties (cca8c567)
- **BigQuery**: `LLM_REQUEST` logging of tool descriptions/parameter schemas (ecef5f85); exposed thinking / tool-use token columns in analytics views (c14258df)
- **Telemetry**: Added `gen_ai.invoke_agent.{inference,tool}_calls` metrics; `invoke_workflow` span in schema v2. **Note: `gen_ai.agent.workflow.steps` and `gen_ai.agent.{request,response}.size` were removed and duration metrics renamed to GenAI semconv names — may affect existing dashboards and alerts**
- **SECURITY**: **Path segment validation in `GcsArtifactService` / `InMemoryArtifactService` prevents cross-user artifact access** (8718aeff); **scoped artifact references to caller** (f8631500); **added DNS rebinding protection to `_OriginCheckMiddleware`** (9a4f479d); enabled Jinja2 autoescape in gepa sample (XSS mitigation, a721c1eb)
- Other: Exposed `SKIP_THOUGHT_SIGNATURE_VALIDATOR` constant (6aad10df); allowed setting OAuth prompt parameter (ac997706)

#### 2026-07-01 Updates (v2.3.0 dev mainline +43 commits: telemetry schema v2 / Anthropic effort / LiteLLM expansion / mTLS hardening)

43 commits from previous doc point `50c81ebf` (2026-06-27) to HEAD `17d5f389` (2026-07-01), concentrated in 2026-06-29 to 07-01. Because Copybara exports omit `#PR` from commit subjects, changes are referenced by short hash. Key items:

**[Features]**

- **telemetry: `invoke_agent` call count metrics**: Added `gen_ai.invoke_agent.inference_calls` / `gen_ai.invoke_agent.tool_calls` (semconv #336 compliant, counted per-span in TelemetryContext) (c6dec00a)
- **telemetry: schema version opt-in**: Introduced `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN` (1|2) env var. Defaults to 2 on Agent Engine (when `GOOGLE_CLOUD_AGENT_ENGINE_ID` is present) and 1 elsewhere (84bbb357)
- **Anthropic effort / thinking config (breaking change)**: Added `AnthropicGenerateContentConfig` to allow setting `effort` (low/medium/high/xhigh/max) directly. Automatically omits sampling parameters (`temperature`/`top_p`/`top_k`) when thinking/effort is enabled to avoid Anthropic API 400 errors. `temperature`/`top_p`/`top_k`/`stop_sequences`/`max_output_tokens`, previously ignored on Claude, now propagate to the client, and `max_output_tokens` overrides the default `max_tokens=8192` (4c862b96)
- **LiteLLM dynamic custom headers**: Added `RunConfig.http_options` to propagate per-request HTTP headers/timeout/retry down to the LiteLLM model layer (000d74da)
- **Relaxed `ToolNode` input**: Workflow `ToolNode` now accepts JSON strings and `types.Content` in addition to dict/None (4e446324)
- **Built-in tool resolution for managed agents**: Added `LlmRequest.is_managed_agent` flag so `google_search`/`url_context` resolve server-side config even without a Gemini model configured (f11d19d2)
- **Exposed `max_parallel_workers`**: Allowed controlling parallel worker concurrency via `@workflow.node` decorator and `Node` class (199d9548)
- **BigQuery Analytics plugin observability controls**: Added OTel correlation, `custom_metadata_allowlist`, and `payload_column_denylist` to `BigQueryAgentAnalyticsPlugin` (38d715cb)
- **Recovered `environment_id`**: Populated `LlmResponse.environment_id` from interactions stream so sandbox environments can be reused across turns (81f9f2ec)

**[Security / Hardening]**

- **Case-insensitive MCP mTLS header matching**: Made authorization header inspection case-insensitive to match httpx lowercase header key normalization (38700324)
- **Dynamic mTLS endpoint resolution in `ApplicationIntegrationTool`**: Replaced hardcoded URLs with `_mtls_utils.get_api_endpoint` to use `.mtls.googleapis.com` variants when presenting client certs (37ca6fbe)
- **Restored `auth_token` initialization in Secret/Parameter Manager client** (46a21817)
- **Restricted GitHub Actions to main/v1 branches and main repo**: Prevented workflow runs and merge blocks on forks (8c4173ee)
- **Hardened CI JSON passing**: Switched inline heredocs to environment variables to prevent script injection (8c7fcd1c)

**[Fixes]**

- **Applied custom Gemini connection logic to all 3_x models**: Extended logic previously limited to 3.1 across the 3_x family (8aff5141)
- **Parsed DeepSeek-V3 proprietary inline tool-call tokens**: Added fallback when LiteLLM does not convert them into structured `tool_calls` (c5b2caad)
- **Surfaced empty STOP turns as errors**: In non-streaming mode, surfaced `finish_reason=STOP` with no content as a `MODEL_RETURNED_NO_CONTENT` error event (932a9b56)
- **perf: Avoided deepcopying session contents when building LLM requests**: Removed full-event deepcopy in `_get_contents` (a non-LLM CPU sink accounting for ~4-7s of a ~30s profiled run) (400f512d)
- **refactor: dynamic scheduler**: Rebased static graph dispatch onto dynamic scheduler (196f7708); extracted transfer loop (7329f7d3)

#### 2026-06-27 Updates (Unreleased dev after v2.3.0: streaming deltas / OpenAI Responses labs / sandbox hardening)

main HEAD progressed to `50c81ebf` (81 commits after v2.3.0; no new release tag yet). Referenced by short hash as Copybara exports omit `#PR` from commit subjects. Key items:

**[Features]**

- **Interactions streaming deltas**: Streamed thought / media / code-exec / function-result deltas (b2dda6e); surfaced streamed grounding + final usage metadata (6a50b8d)
- **OpenAI Responses API support (labs)** (6b831d5)
- **Provider-prefixed Gemini model ID support** (816a87f)
- **Vertex AI session TTL / expiration support** (49d4441)
- **Vertex AI memory `load_profiles` tool** (fb2b3af); error handling in `VertexAiMemoryBankService.search_memory` (f3529e9)
- **mTLS support for `DiscoveryEngineSearchTool`** (8ba0e6a)
- **Skills state injection**: Injected session state into `SKILL.md` via `adk_inject_state` (3afdb08)
- **ADK CLI dev server refactor**: Nested agents support in dev mode and simplified API (35a3e4c)
- **MCP HTTP traces**: Added traces for server requests and errors (4c4f77a)
- **Exposed `branch` property on Context** (50c81ef)

**[Security / Hardening]**

- **Prevented path traversal in `AgentTool` `config_path` resolution** (171ae9e)
- **Hardened `ContainerCodeExecutor` sandbox by default** (0a9ce0f)
- **Module blocklist for YAML agent-config code references** (6a5be34)
- **Enforced agent-config args denylist on load under `adk web`** (e506fa6)

**[Fixes]**

- **Fixed Vertex AI Live API session replay**: Replayed on reconnect / modality switch (c007a87)
- **Preserved Anthropic thinking blocks + signatures across LiteLLM round-trips** (febb250); preserved streamed reasoning deltas (b9625bf)
- **Migrated AgentRegistry base URL from v1alpha → v1** (82432a3)
- **google-genai 2.9 SDK support**: Adapted interactions conversion (9f3aeef); **stripped tzinfo in MariaDB** (2f799d5)

#### 2026-06-19 Updates (v2.3.0 merge / Template Injection fix SECURITY / A2A serialize fixes / tuple tool params)

- **Merged v2.3.0 to main** (`chore: merge release v2.3.0 to main`): Next release in 2.x series
- **SECURITY: Fixed Code Generation Template Injection via Filenames** (`fix: Fix Code Generation Template Injection via Filenames`): Blocked template injection through filenames
- **A2A `_serialize_value()` fixes**: Recursed into JSON-native containers (`recurse into JSON-native containers`) and preserved JSON-native types (`preserve JSON-native types`)
- **tool tracing: Handled Pydantic models in `safe_json_serialize`** (`fix: handle Pydantic models in safe_json_serialize`)
- **feat(tools): Tuple tool parameters support**: Allowed tuple types in tool parameters
- **Fixed LiteLLM Claude thinking blocks**: Fixed bug where `display: "omitted"` thinking blocks were dropped
- **Used Modality enum for `RunConfig.response_modalities`**
- **feat: Supported `file_data` URI references in `GcsArtifactService`**
- **`instructions_utils` fixes**: Fixed placeholder matching regression, fixed matching invalid nested paths, rolled back instruction util refactor that broke internal customers
- **Respected ignore files in `adk deploy`** (`fix(cli): respect ignore files in adk deploy commands`)
- **Stripped datetime tzinfo for MySQL in `create_session`**; **applied `run_config` `custom_metadata` to user events in node runtime**

**Notable**: Following v2.0.0 GA (2026-05-19), **2.x releases hit their stride with v2.1.0 → v2.2.0 (2026-06-04)**. v2.2.0 focuses on observability and eval—**Google GenAI SDK v2.0.0 support**, **AutoTracingPlugin (OpenTelemetry auto-instrumentation)**, **RubricBasedMultiTurnTrajectoryEvaluator**, and native OTel `gen_ai.client.*` metrics—plus many security fixes (listed below). On the LTS side, **v1.35.0 (2026-06-10)** was released, backporting Gemini 3.1 Live fixes (input transcription handling, grounding metadata defaults, history config injection). On main after v2.2.0, work is underway on **E2BEnvironment (remote sandbox workspace)**, **GEPARootAgentOptimizer**, the ADK 2.0 producer cut of the BigQuery Agent Analytics plugin, and the `GOOGLE_GENAI_USE_ENTERPRISE` env var.

#### 2026-06-18 Updates (Gemma4 / cached token counts / DatabaseSessionService AsyncEngine reuse / Live stabilization)

main HEAD progressed to `73ecf8d7` (many commits since prior record). Key items:

**[Features]**

- **Supported Gemma4 in Gemini** (`feat(gemma4)`): Enabled Gemma4 models in the Gemini class
- **Added configuration options to Gemini class** (`feat(models)`): Expanded configuration options on Gemini class
- **`AsyncEngine` reuse in `DatabaseSessionService`**: Allowed reusing an existing SQLAlchemy `AsyncEngine`; added public `prepare_tables()` for eager initialization
- **Reported cached token counts**: Reported cached token counts for Anthropic / OpenAI models; added `create_http_options` to `ContextCacheConfig` for cache creation timeout
- **Live function response behavior control**: Added `response_scheduling` (`feat(tools)`)
- **Nested state access support in template injection** (`feat(utils)`); **exposed `parameter_binding` on `@node` decorator**
- **eval**: Exposed `user_simulator_config` in `generate_responses`; added `log_level` option to `adk run` CLI
- **Passed `invocation_id` to `_setup_invocation_context`**

**[Security / Hardening]**

- **Prevented ReDoS**: Prevented ReDoS in code block extraction (`fix: prevent ReDoS in code block extraction`)
- **auth: Safe handling of missing client-credentials scopes**: Safely handled missing client-credentials scopes
- **CLI: Improved operator safety for generated `.env` files**

**[Fixes]**

- **Live stabilization**: Reconnect on 1011 errors, forwarded thinking config, rejected `history_config` in Vertex / Enterprise Live sessions, excluded live HTTP clients from trace serialization, removed live event buffering in runner, extracted `grounding_metadata` from Live API `server_content`
- **sessions**: Prevented `MissingGreenlet` after `append_event` in asyncpg; additional `DatabaseSessionService` fixes; fixed `vertex_ai_session_service` crash when Agent Engine passes full resource name instead of short session ID
- **a2a**: Suppressed `part_metadata` in Vertex AI mode; rendered HITL interrupts when prompt is in data part; preserved execution metadata on final events; mapped `Message.role` to correct GenAI content role
- **artifacts**: Preserved `.text` on `GcsArtifactService` load; preserved empty GCS text artifacts; converted `image/svg+xml` to text in `LoadArtifactsTool`
- **models / planners**: Surfaced errors on STOP + empty content; preserved litellm function call id; sanitized union type schemas; preserved all leading parallel function calls; allowed `BuiltInPlanner` subclasses to override `process_planning_response`; surfaced `MALFORMED_FUNCTION_CALL` so `on_model_error` can recover
- **Other**: Verified transfer target is a sibling agent; persisted `output_key` on `before_agent_callback` short-circuit; prevented `VertexAiRagRetrieval` from blocking the event loop; JSON-serialized firestore session state; propagated grounding metadata; prevented history filtering loops via `isolation_scope` propagation
- **otel**: Added pure functions for building stable / experimental semconv logs; added telemetry functional test with MCP toolset

#### 2026-06-15 Updates (Compaction function response fix)

- **Fixed compaction orphaning function responses**: Fixed bug where compaction left function responses orphaned (preserving conversation history integrity)
- **CI: Installed `addlicense` tool in kokoro pre-commit presubmit**

#### 2026-06-13 Updates (enterprise parameter migration / mTLS / Agent Identity / Antigravity wrapper)

main HEAD progressed 67 commits (`ca8baf19...d3c21d71`). Key items:

**[Features]**

- **Migrated to `enterprise` parameters**: Migrated core and CLI to enterprise parameters; replaced `vertexai` naming with `enterprise` in samples and docs; set up `GOOGLE_GENAI_USE_ENTERPRISE` env var support
- **mTLS support**: Migrated `McpToolset` to `AsyncAuthorizedSession` for mTLS support; added mTLS to `AgentRegistry` client
- **Agent Identity auth provider**: Implemented auth provider based on Agent Identity Credentials service; added diversion logic based on auth provider resource name; added Remote Agents support to `gcp_auth` client UI
- **Antigravity SDK agent wrapper (experimental)**: Added experimental Antigravity SDK agent wrapper in labs
- **GCS first-party toolset**: Added GCS first-party toolset to ADK integrations
- **Live API enhancements**: Supported Live API translation config in `RunConfig`; propagated output token counts in live usage metadata; Gemini 3.1 live sends `grounding_metadata` only at the end of each turn
- **Per-request OpenTelemetry configuration**: Allowed configuring telemetry per request
- **Added request timeout to `load_web_page`**
- **Updated default model to `gemini-3.5-flash`** (including samples)

**[Breaking / Behavioral Changes]**

- **Changed telemetry metrics units from ms → seconds**: Changed agent / tool execution duration metrics from milliseconds to seconds (review existing dashboards)
- **Required `otel google-genai` instrumentor >=0.7b1**: Raised minimum instrumentor version for genai 2.x
- **Made `a2a` a required dependency for `agent_engine` deploy**; **moved `google-cloud-parametermanager` to optional dependencies**

**[Fixes]**

- **Workflow stabilization**: Prevented replay divergence hangs / sequence barriers; prevented branch mutation on shared `InvocationContext`; fixed silent dead ends on unmatched conditional routes; preserved explicit single-turn contents; prevented silent drain of routed nodes
- **Non-Latin text support in `InMemoryMemoryService` search**
- **CI security hardening**: Added repository check preventing workflow execution on forks; gated pr-triage secrets to same-repository `pull_request_target`; stopped shell interpolation of release analyzer workflow inputs
- **Adopted unused-import enforcement in ruff**

#### Key Changes in v2.2.0 (2026-06-04)

**[Security / Critical Fixes]**

- **Blocked path traversal in Agent Builder file tools** / **fixed Zip Slip in GCS skill extraction** / **restricted unpickling of v0 actions blobs** / **validated session ownership in `delete_session`** — strengthened agent execution defenses
- **CVE-2026-48710 mitigation**: Bumped starlette / fastapi

**[Features]**

- **AutoTracingPlugin**: OpenTelemetry auto-instrumentation plugin
- **RubricBasedMultiTurnTrajectoryEvaluator**: Rubric-based multi-turn trajectory evaluation
- **Enhanced A2A integration**: `to_a2a(Workflow)` support, preserved A2A message metadata, distinguished `input-required` vs `auth-required`
- **Added `BaseSessionService.get_user_state(app_name, user_id)`**; **included thoughts / tool calls in compaction summaries**

#### Changes after v1.34.0 / v2.0.0 GA (Mostly Included in v2.2.0)

**[Operations / Architecture]**

- **Repointed v2 release workflows to v1 branch**: Repointed v2 release workflows and manifests to `v1` branch and deleted main → v2 auto-sync workflow (operational shift to v1-led line)
- **Google GenAI SDK v2.0.0 support**: Added Google GenAI SDK v2.0.0 support in ADK for Interactions
- **Changed default model to `gemini-3-flash-preview`**: Updated default agent model to `gemini-3-flash-preview` (including samples)
- **Restored 1.x agent config wiring**: Restored 1.x agent config wiring for backward compatibility

**[Features]**

- **Standardized `request_input` tool**: Standardized `request_input` tool for proactive LLM confirmation
- **Live `turn_complete_reason` support**: Preserved `turn_complete_reason` in Live responses to capture safety info
- **Native OTel `gen_ai.client.*` metrics**: Emitted `gen_ai.client.*` metrics natively
- **Propagated `custom_metadata`**: Forwarded `custom_metadata` from run requests into run config
- **Creation from sandbox templates / snapshots**: Enabled creating sandboxes from templates / snapshots
- **Data agent chart generation / artifact loading**: Added chart generation and artifact loading to data agent
- **Telemetry expansion**: Attached `user.id` to `gen_ai.user.message` log records; fixed telemetry for tool call errors; preserved transcription event order
- **Skills**: Added adk-review skill / adk-issue skill; automated PR triage and CLA verification; removed experimental tag from `SkillToolset`
- **Aborted `api_server` on client disconnect**: Aborted runs when client drops to prevent leaks

**[Security / Hardening]**

- **Shell-escaped `ReadFileTool` commands**: Shell-escaped path and range in `ReadFileTool` commands (security)
- **Omitted `scope` from OAuth2 token requests**: Omitted scope from auth OAuth2 token requests
- **Checked non-mTLS hardcoded endpoints**: Detected non-mTLS hardcoded endpoints in `check-file-contents.yml`

**[Bug Fixes]**

- **Prevented MCP init hangs / task group leaks**: Prevented MCP initialization hangs and task group leaks, as well as session drops on MCP tool errors
- **Prevented Gemini 3.1 grounding metadata loss**: Fixed silent drops of grounding metadata and transcription finished events in Gemini 3.1 (including live)
- **Fixed graph chat agent wiring**: Prevented incorrect wiring of chat agents in graphs
- **Stopped infinite retries in `LoadSkillResourceTool`**: Stopped infinite retry loops on `RESOURCE_NOT_FOUND`
- **Fixed `AgentTool` sub-Runner plugins**: Stopped `AgentTool` sub-Runners from closing parent plugins; prevented breaking skill tool refs when prefix is set + added `tool_filter` support
- **state / live fixes**: Preserved `state_delta` on `NodeRunner` path; preserved transparent config on live session reconnect
- **Resolved circular imports**: Broke circular imports between `base_tool` / `llm_request`; lazy-loaded GCS evaluation managers / `google-cloud-storage`
- **perf(flows)**: Resolved agent tool unions in parallel

#### Key Changes in v2.0.0 GA (2026-05-19)

- **Reached General Availability**: Established production-grade foundations for multi-agent workflows and dynamic agent collaboration
- **Multi-Agent Workflow Engine**:
    - **Flexible Execution Graphs**: Model-agnostic orchestration engine for non-linear, conditional, and cyclic agent execution patterns
    - **Intelligent Task Delegation**: Modular workflow abstractions enabling parallel sub-agent workers, nested hierarchical teams, and resilient dynamic scheduling
- **Dynamic Agent Collaboration**:
    - **Native Inter-Agent Routing**: Seamless orchestration of inter-agent messaging, control state handoffs, and context variable propagation across multi-agent flows
- **Via v2.0.0 alpha/beta pipeline**: Staged release via v2.0.0a1 → v2.0.0a2 → v2.0.0a3 → v2.0.0b1 → v2.0.0 GA. Switched main branch to v2.0.0 GA (transition to v2).

#### Key Changes in v1.34.0 (2026-05-18)

**[Features]**

- **a2a persistent task stores support**: Added persistent task store support to a2a (cd78d87)
- **Gemini Live API in ADK evaluate**: Added Gemini Live API support to ADK evaluate; used `Runner.run_live()` in `evaluation_generator`; live mode support in local / base eval services (790c9be)
- **mTLS Google Cloud Telemetry exporter**: Added mTLS support to Google Cloud Telemetry exporter (cfe8d2c)
- **`A2aAgentExecutor` factory in `to_a2a()`**: Extended `to_a2a()` to accept a factory (115124c)
- **non-ADK input-required events support**: Supported input-required events generated outside ADK (6e53472)
- **User simulator conv history config**: Made inclusion of tool calls/responses in conversation history passed to user simulator configurable (baf7efb)
- **Implemented `GCPSkillRegistry`**: Implemented `GCPSkillRegistry` in ADK (88ebd42)
- **Implemented Skill Registry**: Implemented Skill Registry in ADK (380d261)
- **Improved Agent Skill description validation**: Made validation messages more informative (9f38973)
- **Simplified `ask_data_agent` / `ask_data_insights` data retrieval**: Simplified data retrieval handling (48f1b30)
- **`McpToolset` OAuth PKCE support**: Supported OAuth PKCE in `McpToolset` (e7316dc)
- **CI: Gemini auto review/invoke workflows**: Added Gemini-based auto review / invoke workflows to CI (fd8b492)

**[Bug Fixes]**

- **Fixed `output_key` state delta callback visibility**: Fixed agent `output_key` state deltas to be visible in callbacks (0524797)
- **Anthropic negative `thinking_budget` → adaptive thinking**: Mapped negative `thinking_budget` to adaptive thinking (03b915b)
- **Persisted refreshed OAuth2 credentials**: Persisted refreshed OAuth2 credentials to store in auth (218ea76, #5329)
- **Removed unused OAuth flows**: Removed unnecessary OAuth flows from auth (c35a579)
- **Prevented Interactions API double-escape**: Avoided pre-serialization of dict values (85f397d)
- **Enforced `CacheMetadata` active-state invariant + fingerprint-only metadata**: Enforced cache active state invariant and handled fingerprint-only metadata in performance analyzer (76b9f0b, 9c5de58)
- **Caught `OSError` on `AnthropicLlm` import**: Caught `OSError` when importing `AnthropicLlm` (91cb5c6)
- **`project_id` fallback**: Fell back to project id when credentials lack a quota project (e377cb5)
- **Fixed dynamically loaded tools in `SkillToolset`**: Fixed bug where tools dynamically loaded into `SkillToolset` within the same invocation were not found (f9097cb)
- **Isolated sub live agent session resumption handles**: Fixed sub live agents inheriting parent session resumption handles and interrupting conversations (8dd9147)
- **Preserved string content in Anthropic `tool_result` blocks**: Preserved string content in `tool_result` blocks for Anthropic models (9a1e75f, #5358)
- **Preserved `tool_use` ID on Anthropic session resume**: Preserved `tool_use` ID during session resume on Anthropic models (327c45f, #5074)
- **Handled empty `GenerateContentResponse` as success**: Treated empty `GenerateContentResponse` without prompt feedback as success (0cb9ae9)
- **Preserved `AgentTool` results**: Preserved `code_execution_result` and `executable_code` inside `AgentTool` (7e61b51, #5481)
- **Respected roles during A2A conversion**: Distinguished user / agent roles when converting events to A2A format (59f7347)
- **Eager raise on `AgentRegistry` import**: Raised eagerly on `AgentRegistry` import when `a2a-sdk` is absent (33cf6cb)
- **Prevented AnyIO `CancelScope` task boundary violations**: Prevented `CancelScope` violations when MCP session creation fails (4309159)
- **Prevented compaction of HITL events**: Prevented compaction of events involved in Human-in-the-Loop (bb2efb6)
- **Preserved `live_session_id`**: Preserved `live_session_id` during function call handling (07a9a01)
- **Suppressed `llm_response` serialization when excluded from trace**: Only JSON-serialized `llm_response` when included in trace (1284493)
- **Removed deprecated CLI flags & version-based service URI**: Removed deprecated CLI flags and version-based service URI handling (e04a468)
- **`gemini-3-flash-preview` model update**: Updated models in hello world / session state agent samples (6d89d21, 2d423e8)
- **Used `tool_responses` role for gemma4 LiteLLM**: Used `tool_responses` role in LiteLLM integration for gemma4 models (3d07960, #5650)

**[Performance]**

- **Lazy-load service registry**: Split `apps.app` and lazy-loaded service registry, reducing cold start by ~8% (bd062ec)
- **Guarded debug log evaluation with `isEnabledFor`**: Guarded debug log evaluation with `isEnabledFor` (57d8fc7)
- **Cached `find_context_parameter` introspection** (ec54bd4)

**[Code Refactoring]**

- **Extracted `a2a_metadata` as a constant**: Defined `a2a_metadata` string as a constant for extension developers (0821f2d)

#### Changes after v1.33.0 (Including Hotfixes Merged into v1.34.0)

- **Gemini Live API evaluation support**: Live API support in ADK evaluate, `Runner.run_live()` in `evaluation_generator`, live mode in local / base eval services
- **Implemented `GCPSkillRegistry`**: New `GCPSkillRegistry` implementation in ADK
- **mTLS Telemetry exporter**: Added mTLS support to Google Cloud Telemetry exporter
- **`A2aAgentExecutor` factory in `to_a2a()`**: Extended `to_a2a()` to accept a factory
- **Stabilized `SkillToolset`**: Removed experimental tag from `SkillToolset`
- **Lazy-load service registry**: Split `apps.app` and lazy-loaded service registry, reducing cold start by ~8% (perf)
- **Preserved `AgentTool` results**: Preserved `code_execution_result` / `executable_code` inside `AgentTool`
- **Respected roles during A2A conversion**: Distinguished user / agent roles when converting events to A2A format
- **Cleaned up OAuth flows**: Removed unused OAuth flows from auth (c35a5796)
- **Removed deprecated CLI flags & service URI**: Removed deprecated CLI flags and version-based service URI handling (e04a4683)
- **Fixed dynamically loaded tools in `SkillToolset`**: Fixed bug where tools dynamically loaded into `SkillToolset` within the same invocation were not found (f9097cbf)
- **`project_id` fallback**: Fell back to project id when credentials lack a quota project (e377cb5e)
- **Supported non-ADK input-required events**: Supported input-required events generated outside ADK (6e534723)
- **Gemini auto review/invoke workflows**: Added Gemini-based auto review / invoke workflows to CI (fd8b4929)
- **Preserved `tool_use` ID on Anthropic session resume**: Preserved `tool_use` ID during session resume for Anthropic models (327c45f9)
- **Implemented Skill Registry**: Implemented Skill Registry in ADK (380d261e)
- **a2a persistent task stores support**: Added persistent task store support to a2a (cd78d87b)
- **Enforced `CacheMetadata` active-state invariant**: Enforced cache active-state invariant (76b9f0ba)
- **Isolated sub live agent session resumption handles**: Fixed sub live agents inheriting parent session resumption handles and interrupting conversations (b4dab9a)
- **Persisted refreshed OAuth2 credentials**: Persisted refreshed OAuth2 credentials to store (af74b21)
- **`gemini-3-flash-preview` model update**: Updated models in hello world / session state agent samples
- **Eager error on `AgentRegistry`**: Raised eagerly on `AgentRegistry` import when `a2a-sdk` is absent
- **Extracted `a2a_metadata` as a constant**: Defined `a2a_metadata` string as a constant for extension developers
- **`CacheMetadata` fingerprint-only support**: Handled fingerprint-only metadata in performance analyzer
- **Caught `OSError` on `AnthropicLlm` import**: Caught `OSError` when importing `AnthropicLlm`
- **`McpToolset` OAuth PKCE support**: Supported OAuth PKCE in `McpToolset`

#### Key Changes in v1.33.0 (2026-05-08)

**[Features]**

- **`BufferableSessionService`**: Added new bufferable session service (0bc767e)
- **`LlmResponse` function call/response helpers**: Added `get_function_calls()` and `get_function_responses()` to `LlmResponse` (22fae7e)
- **`ApigeeLlm` credential injection**: Added option to inject credentials into `ApigeeLlm` (ce578ff)
- **Configurable truncation for ADK environment tools**: Made environment tools truncation limit configurable (83ae405)

**[Bug Fixes]**

- **Excluded inline video data from sessions**: Filtered video events with inline data from session storage (88421f8)
- **Fork detection / offload limits / response logging (BigQuery)**: Fixed BigQuery plugin fork detection, offload limits, and response logging (9d1bb4b)
- **Hot reload agents for `adk web`**: Added hot reload support for agents in `adk web` (740557c)
- **Skipped `state_delta` overwrite on `function_response`-only**: Skipped overwriting `state_delta` on `function_response`-only events (fc27203, 211e2ce)
- **Clarified unregistered `CustomAuthScheme` error**: Threw actionable error when AuthProvider is unregistered (83f9817)
- **Fixed `req.app_name` → `app_name`**: Corrected variable name (8286066)
- **`LlmBackedUserSimulator` empty response error**: Emitted explicit error message on empty response (fb92aad)
- **Agent Engine deploy auth**: Used project / location instead of API key (398f28f)
- **Caught `genai.ClientError` when sandbox is absent**: Caught `genai.ClientError` when sandbox does not exist (69fa777)
- **Converted to `asyncio.sleep`**: Replaced blocking sleep with `asyncio.sleep` to avoid blocking event loop (3a1eadc)
- **Prevented `ListSkillsTool` duplication**: Stopped appending skills to system instructions when `ListSkillsTool` is available (01f1fc9)
- **Fixed double append bug**: Fixed double append bug (f8b4c59)
- **Default API key on Express mode API calls**: Included default api key param in Express mode API calls (e833995)

**[Code Refactoring]**

- **Removed `input.type`/`output.type` attributes from adk metrics**: Cleaned up metrics definitions (9559968)
- **Adjusted `workflow.steps` metric calculation**: Adjusted `workflow.steps` calculation logic + added unit tests (03d6208)

#### Key Changes in v1.32.0 (2026-04-30)

**[Security]**

- **Fixed `load_web_page` SSRF / local-file access**: Fixed SSRF and local-file access vulnerabilities in `load_web_page` (0447e93)
- **Fixed nested YAML configs RCE**: Blocked RCE vulnerability via nested YAML configs in ADK (74f235b)
- **PubSub / Eventarc `user_id` sanitization**: Sanitized `user_id` originating from PubSub subscriptions / Eventarc sources (#5324, 0c4f157)
- **Credential isolation in auth context**: Isolated resolved credentials within auth context (prevents race conditions / data leaks) (5578772)
- **litellm floor >= 1.83.7**: Raised minimum litellm version to include CVE patch (6d2ada8)
- **Scoped Vertex RAG memory display names**: Scoped display names (784350d)

**[Core / Features]**

- **Anthropic thinking blocks support**: Added support for Anthropic thinking blocks format (16952bd)
- **`adk deploy` CLI express mode onboarding**: Added express mode onboarding to `adk deploy` CLI (2b04996)
- **Native OpenTelemetry agentic metrics**: Added native OpenTelemetry agentic metrics (6942aac)
- **Event compaction OpenTelemetry tracing**: Added OpenTelemetry tracing for event compaction (c65dd55)
- **`GcpAuthProvider` 2LO/3LO/API Key sample**: Added 2LO/3LO/API Key auth samples via `GcpAuthProvider` (909a8c2)
- **`ComputerUseToolset` predefined function exclusion**: Added support for excluding predefined functions (d760037)
- **`BigQueryAgentAnalyticsPlugin` credentials**: Added credentials parameter (34713fb)
- **Apigee LLM refusal messages**: Supported refusal messages in Apigee LLM (d6594a1)
- **`save_live_blob` parameter**: Added `save_live_blob` query parameter to `/run_live` endpoint (36ab8f1)
- **Graceful handling of MCP tool errors/transport**: Safely handled tool execution errors and transport crashes (7744cfe)
- **`McpToolset` `credential_key` option**: Supported user-defined `credential_key` (282db87, #5103)
- **`SaveFilesAsArtifactsPlugin` reference suppression option**: Added option to prevent attaching reference files to messages (987c809)
- **BigQuery LLM cache metadata logging**: Recorded LLM cache metadata in BigQuery (02deeb9)
- **Rubric-based eval `evaluate_full_response`**: Added full response evaluation option (#5316, 7623ff1)

**[Bug Fixes]**

- **Accumulated lists on `state_delta` merge**: Accumulated list values when merging `state_delta` from parallel tool calls (#5190)
- **Capitalized `GcpAuthProvider` Bearer scheme**: Fixed to capitalized `Bearer` (ad937fe)
- **Fixed `load_web_page`; bumped `google-genai` minimum**
- **Prevented `LoopAgent` sub-agent state reset**: Stopped resetting sub-agent state on pause (8846be5)
- **Fixed `VertexAiSessionService` list filters quoting**: Fixed `user_id` literal quoting (bdece00)
- **Caught `ValueError` in safe-JSON serializer**: Handled `ValueError` on circular references (#5412, 70a7add)
- **Disabled bound token `mcp_tool`** / **fixed web oauth flow and trace view** / **fixed schema `RecursionError`**
- **Fixed `ReflectRetryToolPlugin` exception ordering** / **raised minimum `mcp` version 1.24.0 → 1.25.x**

**[Performance]**

- **Lazy-loaded optional providers**: Improved cold start by ~25% by lazy-loading optional providers and auth chain (66bfedc)

#### Key Changes in v1.31.1 / v1.31.0

**[Core]**

- **Parameter Manager / Secret Manager user-agent**: Added Google user-agent
- **`VertexAiMemoryBankService` `memories.ingest_events`**: Added support
- **Vertex AI Agent Engine Sandbox integration**: Computer-use support
- **Added Firestore support**
- **Live `session_id` in `LlmResponse`**: Added live `session_id` to `LlmResponse`
- **Minimum MCP version 1.24.0**: Raised minimum MCP version from 1.23.0 → 1.24.0

**[Bug Fixes]**

- **Fixed CLI console URL path**: Fixed console URL path after CLI deployment (#5336)
- **Fixed `on_event_callback` ordering**: Fixed event processing order bug (#3990)
- **`FunctionDeclaration` `json_schema` fallback**
- **Resolved BigQuery plugin issues**

#### Key Changes in v1.30.0

**[Core]**

- **Auth Provider support**: Added Auth Provider support to Agent Registry
- **Parameter Manager integration**: Added Parameter Manager integration to ADK
- **Gemma 4 model support**: Added Gemma 4 model support in ADK (#5156)
- **Live avatar support**: Added Live avatar support in ADK
- **Live session resumption**: Exposed `live_session_resumption_update` as Event in `BaseLlmFlow` (#4357)
- **Promoted BigQuery tools to Stable**: Promoted BigQuery tools to stable
- **A2A artifact interceptor**: Sent A2A events containing artifacts using interceptor in `RemoteA2aAgent`

**[Security]**

- **Fixed credential leak vulnerability**: Fixed credential leak vulnerability in Agent Registry
- **Path traversal validation**: Added path traversal validation for `user_id` and `session_id` (#5110)

#### Key Changes in v1.29.0

**[Core]**

- **`EnvironmentToolset`**: Added `EnvironmentToolset` for file I/O and command execution
- **`LocalEnvironment`**: Added `LocalEnvironment` for local command execution and file I/O
- **Easy GCP support**: Added Easy GCP support to ADK CLI
- **Secret Manager regional endpoints**: Added regional endpoint support to `SecretManagerClient`
- **Auth Provider registration API**: Added public API on Credential Manager to register custom Auth Providers
- **Additional HTTP headers for MCP tools**: Supported additional HTTP headers on MCP tools

**[Tools]**

- **`BashTool` shell metacharacter blocking**: Added shell metacharacter blocking in `BashTool`
- **`BashTool` resource limits**: Configurable resource limits for subprocesses
- **`BashTool` process group management**: Robust process group management and timeouts
- **BigQuery ADK 1P Skills**: Added ADK 1P Skills to BigQuery toolset

**[Models]**

- **Vertex AI custom session IDs**: Supported custom session IDs in Vertex AI Session Service
- **Model endpoints in Agent Registry**: Supported model endpoints in Agent Registry

**[Optimization]**

- **Context propagation**: Context propagation to thread pools
- **`InMemorySessionService` shallow copy**: Optional shallow-copy sessions

**[Bug Fixes]**

- **Redacted credentials in BigQuery analytics**: Redacted credentials in BigQuery analytics plugin
- **`BaseToolset.get_tools()` caching**: Cached `get_tools()` within the same invocation
- **Prevented compaction of pending function calls**: Stopped compacting events with pending function calls (#4740)
- **Live session resumption/GoAway handling**: Handled Live session resumption and GoAway signals (#4996)

#### Key Changes in v1.28.0

- **A2A lifespan parameter**: Added A2A lifespan parameter support
- **BigQuery 1P Toolset migration**: Migrated BigQuery 1P toolset
- **Spanner Admin Toolset**: Added new Spanner Admin toolset
- **Slack integration**: Added Slack integration
- **SSE streaming**: Added SSE streaming support for conformance tests
- **Anthropic `thinking_blocks`**: Supported Anthropic `thinking_blocks` format in LiteLLM
- **MCP sampling callback**: Supported MCP sampling callbacks
- **Module import protection**: Added protection against arbitrary module imports (security)

#### Breaking Changes

| Change | Impact |
|---|---|
| Credential manager takes `tool_context` (v1.24.0) | Argument changed from `callback_context` to `tool_context` |
| `SecretManagerClient` package move (v1.29.0) | Moved to `google.adk.integrations.secret_manager` package |

#### Reference Links

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**Current version**: **v2.5.0 (2026-09-30)** (v1 series continues maintenance at v1.8.0)

**Checkout state**: `40d37cad` (HEAD 2026-10-12 = v2.5.0 + 64 commits. Due to lightweight tags, bare `git describe` diverges from actual state)

#### Verified 2026-10-13 (main after v2.5.0: Gemini fixes / experimental app-info endpoint)

[Diff for this update](https://github.com/google/adk-go/compare/44d41c9c...40d37cad). Below are unreleased changes on HEAD.

- **feat**: Experimental `/apps/{app_name}/app-info` endpoint (#1404)
- **fix (Gemini)**: Disabled automatic continuation in genai SDK (#1813); resumed `MAX_TOKENS` stops when `maxOutputTokens` is unspecified (#1759); guarded nil first candidate in streaming aggregator (#1802)
- **fix**: `LoopAgent` returns if there are no sub-agents (#1780); `agenttool` wraps errors from `runner.New` (#1803); aligned vertexai session service with other implementations via ADK REST API (#1571)
- **deps / docs**: grpc bump (#1814); 12 go-minor-patch bumps (#1798); fixed error behavior docs for agent callbacks, mcptoolset examples, and telemetry docs

#### 2026-09-23 to 2026-10-07 Updates (**v2.5.0 / v1.8.0** + ~78 commits: OpenAI Chat Completions / SECURITY hardening / Gemini continuation)

- **v2.5.0 (2026-09-30)**: **OpenAI Chat Completions API support** (#1642; split Chat Completions / Responses into sub-packages #1643), **daily time partitioning for BigQuery event logging table** (#1377), **guaranteed artifact version metadata** (#1440), `session/database` persists input/output transcriptions (#1662), base64-encoded `[]byte` fields in agentengine (#1387)
- **SECURITY**: Message size limit on adkrest `/run_live` WebSocket (#1664), checked Host / Origin on all web launcher routes (#1641), excluded session filenames from shared GCS listings (#1708 / #1673)
- **HEAD (after v2.5.0)**: **Resumed stopped Gemini generation with continuation tokens** (#1715), **per-request auth (`Config.Auth`) on A2A remoteagent** (#1150), 120s default SSE write timeout (#1686), `PubSubController` respects `MaxConcurrentRuns` (#1720), mcptoolset cancellation / close / config validation (#1717 / #1713 / #1687), vertexai sessions preserve `ExecutableCode` / `CodeExecutionResult` (#1729), kept `${var}` placeholders literal (#1682), re-evaluated toolsets at every step (#785)

#### 2026-09-16 to 2026-09-22 Updates (6 commits: web server SECURITY hardening + OpenAI model fixes)

- **SECURITY**: Bound web server to loopback by default (#1456); adkrest rejects DNS-rebinding hosts and cross-origin browsers (#1615)
- **OpenAI model**: Extracted streamed function names from `output_item.added` (#1616); pinned function tools to non-strict validation (#1389)
- **session/vertexai**: Stripped `temp:` keys before `AppendEvent` persistence (#1514)
- **web launcher**: Deferred telemetry shutdown and adjusted startup logging (#1469/#1470)

#### 2026-09-01 to 2026-09-15 Updates (**v2.4.0 / v1.7.0**: REST API auth + OpenAI stream / session hardening)

- **v2.4.0**: **Added authentication and authorization to adkrest** (#1561), provided endpoints called by ADK web UI (#1459), web launcher initializes artifact / memory services to serve UI properly (#1460)
- **OpenAI model**: Applied all generation config fields (#1392), surfaced server-side failures (#1359), preserved end-of-stream finish reason / logprobs / tool calls (#1373), preserved refusals and completed stream content (#1467), preserved caller-owned JSON schemas (#1451)
- **session / runner**: Reported missing sessions with `session.ErrNotFound` (#1458), snapshotted events under read lock on DB / VertexAI backends (#1559), stopped nil event loop after cancellation (#1479)
- **workflow / agent**: `ParallelWorker` fail-fast stops new dispatches even under `maxConcurrency` (#1239), agenttool `SkipSummarization` terminates parent loop (#908), preserved late tool completions in final content (#1428)
- **HEAD (after v2.4.0)**: Re-exposed `run_live` via API mount (#1533), stripped `temp:` keys from in-memory sessions (#1356), honored isolation scope in remoteagent (#1259)
- **SECURITY**: Removed consent URI from `ConsentRequiredError` message (#1519), removed caller identifiers from GCP auth service errors (#1520), validated deploy CLI values before Dockerfile interpolation (#1240)

#### 2026-08-01 to 2026-08-31 Updates (v2.2.0 / v1.6.0 / v2.3.0 releases: context compaction suite + credentials-service client + security fixes)

- **v2.3.0 centerpiece = context compaction suite**: Summarization of completed invocations as conversations grow (#1232), mid-invocation compaction when prompt exceeds threshold (#1234), reachable from all serving surfaces (#1235), compaction records on session events (#1231), **preserved durable facts across re-summarization** (#1431), tests against real model recordings (#1236)
- **telemetry**: Recorded opt-in `gen_ai` content attributes on `generate_content` spans (#1426)
- **auth/gcp**: **Added credentials-service REST client** (#1149)
- **SECURITY**: **Fixed unsafe use of A2A peer-supplied `transferToAgent` metadata** (#1226), rejected non-http(s) URL / path remote agent card sources (#1328, SSRF mitigation), **rejected conflicting tool confirmation requests** (#1369) and **rejected resume from non-agent-created events** (#1357)
- **Fixes**: Filtered thinking parts from agenttool results (#696), replayed OpenAI model assistant turns with `output_text` content (#1427), nil event guard (#1417), quoted `userId` in Vertex AI session AIP-160 filters (#1171), supported `load_artifacts` alongside other tool calls (#1320), preserved artifact deltas across multiple tool calls (#474), bounded consecutive thought-only turns in `llminternal` (#1290)
- **v2.2.0 (08-10)**: Supported both string and object for function call arguments + improved error reporting (#1254), enabled h2c on web launcher listener (#826)
- **chore**: Go 1.26.6 (#1339), migrated OTel logs to 0.21 (#1335), added Kotlin/TypeScript implementations to README, `.agents/skills` + examples authoring skill (#1331)

#### 2026-07-24 to 2026-07-26 Updates (Unreleased dev after v2.1.0: h2c / Vertex AI artifact delta)

- **Enabled h2c (HTTP/2 cleartext) on web launcher listener** (#826)
- **fix**: Preserved Vertex AI artifact deltas (#904), resumed confirmed tool calls in request order (#1169)
- **chore**: Expanded Dependabot scope + CODEOWNERS routing (#1199), `google.golang.org/genai` 1.65.0 (#1215), gcp detectors / grpc bump (#1219), `golang.org/x` updates (#1216)
- **docs**: Added Kotlin/TypeScript implementations to README (#1212). No breaking changes or security fixes

#### Updates as of 2026-07-27 (v2.1.0 / v1.5.1 releases: OpenAI support / BigQuery Agent Analytics Plugin)

- **Tagged v2.1.0 (2026-07-23) + v1.5.1 (2026-07-22)**
- **Added OpenAI support** (#1178)
- **BigQuery Agent Analytics Plugin** (#738)
- **Multi-module Go dev support in CI** + updated dev docs (#1155)
- **fix(parallelagent): Wait for sub-agent teardown before returning on early stop** (#1186); `golang.org/x` dependency updates (#1192)

#### Updates as of 2026-07-18 (24 commits after v2.0.0: agentregistry / provider auth / MCP per-request auth)

- **`agentregistry` package**: Added discovery / REST transport / RemoteAgent + McpToolset factories (#1122–#1148)
- **credential/provider auth**: Added core credential/provider auth package and supported per-request auth on MCP toolsets
- **Reference**: v2.0.0 (2026-06-30) itself brought Multi-Agent Workflow Engine GA (#1109, 548 files / +51k lines from v1.5.0→v2.0.0), matching adk-python 2.0's workflow GA theme

**Note**: Single-module repo (not monorepo multi-module tags). `v2.0.0` is an official major release with a Go major import path bump (`google.golang.org/adk` → `/v2`). Parent submodule's bare `git describe` prints `v0.1.0-255-g0f5cfa0` because **its default behavior only matches annotated tags** (not because tags are unfetched). In this repo only `v0.1.0` is an annotated tag, while v1.0.0–v2.0.0 (including v1.4.0/v1.5.0) are all lightweight tags; `git describe --tags` resolves properly to `v2.0.0-2-g0f5cfa0`.

**Notable**: **ADK Go 2.0 major release (2026-06-30)**. Centered on the new `workflow` package (scheduler-based goroutine-per-node execution engine, HITL pause/resume, handoff/re-entry, JoinNode fan-in, etc.), accompanied by breaking API changes including module path change, mandatory context on `session.NewEvent`, and ToolContext/CallbackContext unification. The 1.x series continues maintenance on the `v1` branch.

#### 2026-07-09 Updates (Added agentregistry client foundation)

- **Introduced `agentregistry` package**: Added `Config`/`Client`/`New` client foundation and authenticated REST Transport for `agentregistry.googleapis.com`. **Ported from adk-python for behavioral parity**: Application Default Credentials + mTLS endpoint selection, typed `APIError`, service wire types and list options, and resolution helpers (`connectionURI`/`cleanName`/transport-binding map). Standardized list-response types to AIP-158 `ListXxxResponse` naming (#1122)
- **test**: De-flaked `TestA2ACleanupPropagation` (#1131)

#### 2026-07-02 to 2026-07-08 Updates (Unreleased dev after v2.0.0: TaskRunner seam / LLM registry)

- **platform TaskRunner seam**: Added execution seam enabling caller-controlled tool fan-out (#1050)
- **name-based LLM registry**: Name-based model registration via `Register` / `NewLLM` (#1057)
- **Made `PackTool` public API** (#1055); **added `NewInMemory` convenience constructor to runner** (#1133)
- **Tool-confirmation alignment**: Emitted confirmation requests in model-response order (#1053); fixed confirmation wrapper to propagate `ProcessRequest` to underlying tool (#1130)
- **fix**: Shallow-copied input event when stripping temporary state deltas to prevent mutation (#1128)

#### 2026-07-01 Updates (v2.0.0 docs setup / v1 & v2 branch workflow)

- **Documented v1/v2 branch workflow in contributing**: Split `main` as the 2.x dev line and `v1` as the 1.x maintenance line for the 2.0 release. Clarified that `main` history is continuous (old clones can fast-forward) and 1.x fixes should branch from `origin/v1` (#1114 / 0f5cfa0)
- **Added per-example READMEs and index to workflow examples**: Documented sample apps for the new workflow subsystem (#1113 / c478319)

#### 2026-06-30 Updates (ADK Go 2.0 major release — introduced workflow subsystem)

- **ADK Go 2.0 release (v2.0.0, breaking change)**: Changed module path from `google.golang.org/adk` → `google.golang.org/adk/v2`. Massive 547 files / +51,635・-7,030 squash. Introduced new `workflow` package (scheduler-based goroutine-per-node execution engine, EdgeBuilder/NodeConfig, graph validation, HITL pause/resume and handoff/re-entry modes, JoinNode fan-in, AgentNode, retry config, state persistence in `session.State`) (#1109 / 893e4a4)
- **`session.NewEvent` now requires `context.Context` (breaking change)**: Signature changed to `NewEvent(ctx, invocationID)`. Obtains ID/timestamp via `platform` package (replay-safe). Removed old contextless form and interim `NewEventWithContext`
- **Unified ToolContext and CallbackContext into Context (breaking change)**: Existing mocks fail to compile due to missing new methods (`Actions`/`FunctionCallID`/`ToolConfirmation`/`RequestConfirmation`/`SearchMemory`, etc.). Embedding `agent.StrictContextMock` is the recommended migration path (unoverridden methods panic) (#945)
- **Removed `agent.InvocationContext.TriggeredBy()` (breaking change)**: Removed unused public API surface (`NodeState.TriggeredBy` field remains for resume) (#841)
- **v1.5.0 (final addition to 1.x maintenance line)**: Added table-driven tests for FunctionCall/Response mapping in `VertexAiSessionService` (#739 / caf798a)

| Change | Impact |
|---|---|
| Module path changed `google.golang.org/adk` → `/v2` (v2.0.0) | All import paths must be rewritten |
| `session.NewEvent` requires `context.Context` (v2.0.0) | Call signature changed; old `NewEventWithContext` removed |
| Unified ToolContext / CallbackContext into Context (v2.0.0, #945) | Existing mocks fail to compile; migrate to `agent.StrictContextMock` |
| Removed `agent.InvocationContext.TriggeredBy()` (v2.0.0, #841) | Call sites using this public API must be rewritten |

#### 2026-06-24 Updates (conformance harness only)

- **Added `system_instruction` keyNode handling to conformance harness** (#1075): Supported `system_instruction` keyNode handling in conformance test harness (test/conformance layer only, no API changes)

#### 2026-06-19 Updates (`load_memory` VertexAiSessionService compat / removed `context.Background` / linter)

- **Fixed built-in `load_memory` tool for `VertexAiSessionService` compatibility** (#793): Updated `load_memory` to work with `VertexAiSessionService`
- **Eliminated `context.Background`** (#1062): Removed `context.Background` usage across codebase and propagated caller context
- **Linter fixes** (#1068): Fixed linter findings on main

#### 2026-06-18 Updates (Gemini Enterprise AgentSpace streams / manual session ID)

- **Gemini Enterprise AgentSpace streams support** (#777, `fix(agentengine)`): Supported Gemini Enterprise AgentSpace streams in agentengine
- **Allowed manual session ID configuration** (#721): Enabled manual setting of session IDs
- **Added `StrictContextMock` test double** (#1019, `feat(agent)`): Added strict context mock for testing
- **Added AGENTS.md** (#1045): Added AGENTS.md for AI coding agents

#### 2026-06-15 Updates (deterministic event creation seams)

- **Added platform clock / UUID provider seams**: Added replacement seams for platform clock and UUID provider for deterministic event creation (improved testability) (#964)

#### 2026-06-10 Updates (govulncheck patch / Node 24 migration)

- **SECURITY: Bumped `x/net` and OTel OTLP exporters**: Bumped `golang.org/x/net` and OTLP exporters to patched versions for govulncheck advisory (#994)
- **Completed Node 24 migration in GitHub Actions**: Fully migrated GitHub Actions to Node 24 (#996)

#### Key Changes in v1.4.0 (2026-05-29)

- **Context unification (tool context → callbackContext)**: Internal context unification merging tool context into callbackContext (#871), unified agent/context + internal/context/callback_context (#868)
- **`adka2a` structured error propagation**: Propagated structured errors in `adka2a` (#874)
- **Migration to `a2a-go/v2` SDK**: Updated examples and CLI launcher to use `a2a-go/v2` SDK (#780)
- **Accepted metadata-only SSE chunks**: Prevented stream aborts in `StreamingResponseAggregator` by accepting metadata-only SSE chunks (#918)
- **Conformance test recording plugin**: Added plugin for recording conformance tests (#890)
- **Fixed `a2a` execution cleanup callback**: Fixed cleanup callback not firing (#903)
- **Preserved unrelated function events**: Fixed preservation of unrelated function events (#767)
- **Preserved Vertex AI function call IDs**: Preserved Vertex AI function call IDs (#762)
- **Yielded tool responses before confirmations**: (#765)
- **Copied `ThoughtSignature`**: Copied `ThoughtSignature` onto `adk_request_confirmation` parts (#763)
- **Fixed `replay_plugin`**: Normalized empty llmresponses and function formatting before comparison (#869)
- **Added transfer agent validation**: Added validation to transfer agent (#824)

#### Key Changes in v1.3.0 (2026-05-20)

- **Fixed user auth propagation (`adka2a` compat)**: Fixed user auth propagation not working in `adka2a` compat (#861)
- **Live audio cache for save artifact**: Added audio cache for save artifact in live (#838)
- **Live streaming tools**: Added streaming tools in live (#836)
- **Live session resumption**: Added session resumption to bidirectional Live streaming (#837)
- **Live bidirectional streaming core**: Added core bidirectional streaming (#833), sequential agent live run (#835), and live example (#834)
- **Nil deref guard (unimplemented `tool.Tool`)**: Prevented nil dereference when tools do not implement `tool.Tool` interface (#855)
- **Fixed `StateDelta` propagation for non-streaming agents**: Fixed `StateDelta` propagation for non-streaming agents (#854)
- **Fixed runtime request Decode errors**: Handled request Decode errors instead of ignoring them in runtime (#851)
- **Gemini model update**: Updated examples model to `gemini-3.1-flash-lite` (#839)
- **Added Dependabot config**: Added Dependabot config for automatic genai dependency updates (#843)
- **`a2a-go` nil part fix bump**: Bumped version to pick up `a2a-go` nil part fix (#827)
- **Parallel HITL function test**: Added parallel HITL function test (#817)
- **ADK Go LLM Request tagging support**: Updated ADK Go version for LLM Request tagging (#816)
- **Migrated `adka2a` public API to v2**: Fixed old `adka2a` public API to depend on new `a2a-go/v2` (#813)
- **VertexAI MemoryBank support**: Added VertexAI MemoryBank support (#801)
- **Fixed thought signature propagation**: Propagated thought signature to first function call in mixed responses (#788)
- **Renamed `gen_ai.usage` attributes**: Renamed experimental reasoning tokens attributes to `gen_ai.usage.*` (OTel semantic conventions alignment) (#779)
- **`a2a-go/v2` support**: Added `a2a-go` v2 support to ADK (#701)
- **`stream_query` simple text support**: Supported simple text in addition to full `genai.Content` (#773)
- **Update existing Agent Engine instances**: Added support for updating existing Agent Engine instances (#755)
- **Removed manual runner session ID & enabled auto-generation**: Removed manual session ID input in runner and enabled auto-generation (#754)

#### Key Changes in v1.2.0

- **Agent Engine integration**: Full support for Agent Engine deployment (#749)
- **Merged skill source proxy**: Implemented proxy merging multiple skill sources (#747)
- **Preload frontmatters skill source proxy**: Frontmatter preload proxy (#748)
- **Skill Source proxy for preloading skills**: Skill preloading proxy (#745)
- **`SkillToolset` implementation**: Provided Skills as a toolset (#733)
- **Toolsets `RequestProcessor`**: Allowed Toolsets to implement `toolinternal.RequestProcessor` interface (#730)
- **Fixed `traceCapacity` API config**: Added `traceCapacity` to API config (#731)
- **Fixed `adk-web` SSE error format**: (#734)
- **Fixed content processor**: Excluded `toolconfirmation.FunctionCallName` (#717)

#### Key Changes in v1.1.0

- **EventArc subrouter**: EventArc subrouter support and Cloud Run deploy script integration (#713, #716)
- **Pub/Sub trigger**: Pub/Sub trigger setup and subrouter (#704, #712)
- **Skills package**: Defined `skill.Source` interface and filesystem skill source implementation (#711)
- **Agent Engine deploy**: Added Agent Engine deployment to ADK Go CLI (#715)
- **Telemetry LRU cache**: Configurable LRU cache for debug telemetry (prevents memory leaks) (#687)
- **Cache read input token attribute**: Added cache read input token attribute to telemetry (#714)

#### Key Changes in v1.0.0

- **Official release**: v1.0.0 stable release

#### Key Changes in v0.6.0

- **Apigee model**: Added Apigee model support (#639)
- **RemoteAgent part conversion extension point**: Extension point for RemoteAgent part conversion (#627)
- **`pathPrefix` config**: Added `pathPrefix` setting to API launcher (#616)
- **Replay plugin**: Added replay plugin (#618)

#### Reference Links

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**Current version**: **v2.2.1 (adk-v2.2.1 / devtools-v2.2.1 / integrations-v2.2.1, 2026-10-06)** (v2.2.0 was 2026-09-30)

**Checkout state**: `14c9c3d5` (HEAD 2026-10-12 = v2.2.1 + many commits. Same caveat as above for bare `git describe` with lightweight tags)

#### Verified 2026-10-13 (expanded `adk-python` v0.1.0 parity)

[Diff for this update](https://github.com/google/adk-js/compare/9839754d...14c9c3d5). Items below are unreleased changes on HEAD; public release remains v2.2.1.

- **parity**: Aligned tools (#1046) / mcp_tool (#1047) / flows (#1048) / cli (#1049) with `adk-python` v0.1.0
- **fix**: Prioritized explicit `vertexai: false` over enterprise env vars (#1044)
- **dev / test**: Raised vitest coverage threshold to measured values (#1024); set worker heap limit from measurements (#1027); checked license headers on `.mjs` / `.cjs` in CI (#1022)

#### 2026-09-23 to 2026-10-07 Updates (**v2.2.0 / v2.2.1**: expanded `adk-python` parity + planners)

- **v2.2.0 (2026-09-30, #910)**: **Planner support** (`BasePlanner` / `BuiltInPlanner` / `PlanReActPlanner`, planner on LlmAgent #941/#948), `DebugLoggingPlugin` (#920), opt-in `autoCreateSession` (#967), construction-time validation in ExampleTool (#968), ADK tracking headers on MCP HTTP (#962), forwarded `MemoryEntry.id` to Vertex `memoryId` (#947)
- **v2.2.1 (2026-10-06)**: **`ToolCallIntegrityPlugin`** (#979), reserved `__adk_internal_` customMetadata key (#977)
- **SECURITY / fix**: Pinned fetched agent card RPC url to source origin (#829), required HTTPS for implicit Google API auth (#952), sealed interrupted invocations in session history (#976), kept `${...}` literal in instructions (#959)
- **HEAD (after v2.2.1)**: **Gemini continuation token resumption** (#985), models / telemetry parity with `adk-python` v0.1.0 (#981 / #963), defaulted `code_executors` to client-side execution (#1003), planner retains all leading parallel function calls (#991), `@google/genai` ^2.27

#### 2026-09-16 to 2026-09-22 Updates (**v2.1.0 release** + 13 commits)

- **v2.1.0 (2026-09-15, #792)**: Formally released the 90 commits after v2.0.0 (Chrome Prompt API BaseLlm, ContainerCodeExecutor, VertexAiRagMemoryService, PKCE S256, SSRF/DNS-rebinding hardening, typed-errors, ReflectAndRetry plugins, etc. — see previous section)
- **feat**: `openapi_tool` parity with `adk-python` v0.1.0 (#924), attached session metadata to A2A task/working/input-required events (#919), published code-execution skill on agent cards (#905)
- **fix**: Scanned all 2xx media types for return schema (#917), emitted body argument for schema-less media types (#907), prevented nested artifacts from leaking versions (#918), made `AdkApiServer.stop()` idempotent (#916), stripped null enum members in `toGeminiSchema` (#915), wired `--staging_bucket` to `adk deploy agent_engine` (#893), routed Gemini 3.x live audio by model family (#912), closed skill registry when closing skill toolset (#906), inlined reusable Zod v3 sub-schemas (#904), rendered empty text part on outputless code execution results (#903)

#### 2026-09-01 to 2026-09-15 Updates (90 commits after v2.0.0: Chrome Prompt API / RAG memory / ContainerCodeExecutor / SSRF & DNS rebinding hardening; no new tag)

- **feat**: **Chrome Prompt API BaseLlm (on-device)** (#843), **ContainerCodeExecutor (Docker sandbox)** (#541), **VertexAiRagMemoryService** (#543), ported python v0.1.0 retrieval tools (#854), `--min_instances` / `--max_instances` on Agent Engine deploy (#899)
- **SECURITY**: **Origin validation in dev server (DNS rebinding defense)** (#557), **prevented SSRF / silent file reads in A2A agent-card resolution** (#832), **PKCE S256 on OAuth2 auth URIs** (#820), stopped sending unauthenticated requests when OpenAPI HTTP credentials are unavailable (#816), removed `httpOptions` with credentials from telemetry (#815)
- **fix**: Honored isolation scope during compaction (#830), configured `VertexAiSessionService` from `vertexai://` URI (#898), switched to `GOOGLE_GENAI_USE_ENTERPRISE` (#897), bundled browser web build properly (#614), determined resume target agent for multiple function responses (#810)

#### 2026-08-01 to 2026-08-30 Updates (**v2.0.0 major release**: optional peers cut install to 172 packages + typed-errors + ReflectAndRetry plugins)

- **v2.0.0 (2026-08-21, #629)**: **Made situational subsystems optional peers, reducing `npm install` package count from 591 → 172** (#626). Included: **typed-errors module (`errors/`) ported from adk-python** (#583), **`ReflectAndRetryToolPlugin` / `ReflectAndRetryModelPlugin` (self-healing error recovery)** (#631), **graduated `RoutedAgent` / `RoutedLlm` from experimental** (#783)
- **Workflow hardening**: Handled node errors as failures rather than throwing (#776), resumed callers on awaited input (#760), rejected replies not answering an open interrupt (#777), unwound callers on dynamic child pause/fail (#709), child pending interrupts hold caller (#759), shared same destination across two route keys (#763)
- **SECURITY**: **Guarded dev server reads against DNS rebinding** (#744), **scrubbed credential material before forwarding to remote A2A peers** (#767), **closed 2 author-blind confirmation-resolution paths** (#755), **bound HITL confirmation to the approved action** (#771), redacted OAuth2 authorization codes in logs (#640), bound credential responses to requesters (#775)
- **Fixes**: Resolved built-in tools by name (#811), gracefully handled unregistered tool calls (#790), loaded artifacts / MCP resources alongside other tool calls (#639), preserved `EventActions` even on long-running no-response tools (#571), stopped live grandchild hang in code execution (#793), restored event round-trip in `VertexAiSessionService` (#565), stopped dropping piped stdin (#781), propagated A2A request metadata into agent execution (#752/#768)
- **dev / docs**: Explicit minimum Node.js version in README (#800). No breaking changes declared beyond package layout (optional peers)

#### 2026-07-24 to 2026-07-31 Updates (v1.5.0 release (#503) + follow-up dev: mandatory A2A auth / python parity tools)

- **Tagged v1.5.0 (2026-07-30)** (#503)
- **SECURITY**: Required authentication when mounting A2A server (#529), required confirmation before running inline skill scripts (#528), rejected zip-slip entries and non-bare skill names in zipped skills (python parity, #584), passed `-NoProfile` to PowerShell and `/D` to `cmd.exe` in `UnsafeLocalCodeExecutor` (#566), switched `randomUUID` to cryptographically secure source (#577)
- **CLI-level A2A authenticator**: For dev server / Cloud Run deploy (Part 1/2 `bearerTokenUserBuilder` #562, Part 2/2 #559)
- **Added `ttl` / `expireTime` options to `VertexAiSessionService.createSession`** (#561)
- **Python parity tools**: `getUserChoiceTool` / `requestInputTool` (#506), `EnterpriseWebSearchTool` (Gemini web grounding, #525), SSRF-safe `load_web_page` (#524), `ExampleTool` (#554), `LoadMcpResourceTool` (#542)
- **agents**: `BaseAgent.clone()` (#545), `RoutedAgent` clone (#556), tool callback response type validation and state event pollution prevention (#505)
- **Type change**: Made `streaming` / `stateDelta` optional on `RunAgentRequest` (#585) — backward-compatible relaxation with no API removals or renames

#### Updates as of 2026-07-27 (v1.4.0 release: Anchored Iterative Summarization / GlobalInstructionPlugin / LoopAgent live streaming)

- **Tagged v1.4.0 (2026-07-20)** (#452)
- **Implemented Anchored Iterative Summarization** in context compactor (#470)
- **Scoped global instructions with `GlobalInstructionPlugin`** (adk-python parity, #507)
- **Ported `LoopAgent` live streaming (`runLiveImpl`) to TS** (#504); switched `content_processor` branch matching to Trie lookup (#509)
- **fix: Replaced message parts & exposed to LLM on Artifact save** (#515), quoted `userId` in AIP-160 filters for vertexai sessions (#499), loaded `SKILL.md` with tables (#500)

#### Updates as of 2026-07-18 (28 commits after v1.3.0: Skills Registry / OpenAPI REST tool / Agent-Controlled Compaction)

- **Skills Registry**: Core interface + zip extraction + local toolset cache fallback, remote GCP Skills Registry integration, dynamic `SearchSkillsTool` for LLM Agents (#422–#424)
- **OpenAPI REST tool**: Auth helper / credential exchanger, spec operation parser, and REST API tool implemented in parts 1–3 (#384–#386)
- **Gemini Interaction API + Compaction**: Implemented Gemini Interaction API (#364), Agent-Controlled Compaction (#477), composite session keys (`appName/userId/sessionId`, #486)
- **Live models**: Gemini 2.5 / 3.x Live models support (#409), `--reload_agents` hot reload (#304)
- **Security**: Multiple SSRF / auth fixes (#465, #482)

#### 2026-07-01 to 2026-07-05 Updates (Gemini Interaction API + OAuth2 SSRF hardening)

- **Implemented Gemini Interaction API in adk-js** (#364)
- **SECURITY: Applied SSRF blocklist to OAuth2 token endpoint in `fetchOAuth2Tokens`** (#465)
- **streaming: Fixed suppression of empty part arrays** (#450)

#### 2026-06-30 Updates (Context compaction and session-scoped artifacts)

- **Added `TrajectoryThoughtPruningCompactor`**: New `BaseContextCompactor` implementation pruning only "thought" parts from older events in session history. Preserves causal history (action / observation) while cutting token usage. Trailing `eventRetentionSize` items are excluded from compaction. Also extracted `hasThoughts` / `pruneThoughts` into Event utilities and updated `database_session_service` (#451)
- **Introduced `SessionArtifactService` + refactored `ForwardingArtifactService`**: Added `SessionArtifactService` interface for session-scoped artifact operations bound to app / user / session, and `ScopedArtifactService` wrapper binding an existing `BaseArtifactService` to a specific session. Rebuilt `ForwardingArtifactService` on top of this structure (#455)

No new release tags, `SECURITY:` prefix commits, or breaking changes in this window.

#### 2026-06-22 Updates (v1.3.0 release / integrations package / Skills Registry / `--reload_agents`)

**Released v1.3.0 (adk-v1.3.0 / devtools-v1.3.0 / main-v1.3.0) on 2026-06-22**. Incorporated the following post-v1.2.0 work from main:

- **New `integrations` package** (#449): Created top-level integrations package
- **OpenAPI REST API tool (part 3)** (#386): Implemented REST API tool following v1.2.0 parser / auth handler (part 2, #385), completing OpenAPI toolchain
- **Skills Registry trilogy**: Core interface + zip extraction + local toolset cache fallback (#422), remote GCP Skills Registry integration + E2E (#423), dynamic `SearchSkillsTool` for LLM agents (#424)
- **`--reload_agents` flag** (#304): Watches agent files for hot-reload
- **Gemini 2.5 / 3.x Live Models support** (#409)
- **`LlmAgent` uses `AuthPreprocessor`** (#444)
- **Moved Agent Engine deploy target GCR → Artifact Registry** (#441): Bundled Reasoning Engine server-compatible routes + headers parser (#440)
- **Concurrent replacement + key dedup** (#432); **dynamic download + shared folder serve for ADK Web assets** (#427)
- **SECURITY: Fixed streaming prototype pollution** (#410): Prevented prototype pollution via model-controlled JSON paths
- **Fixes**: Resolved `outputSchema` + tools infinite loop (#412), suppressed trailing empty STOP chunks (#426), filtered temp state keys on session creation (#406), made session event keys MySQL index-safe (#437)
- **Breaking changes**: Changed default dev server port 8000 → 8080 (#439); changed Agent Engine deploy target GCR → Artifact Registry (#441, requires Artifact Registry setup)

#### 2026-06-18 Updates (OAuth2 SSRF hardening / `outputSchema`+tools infinite loop fix)

- **SECURITY: Blocked `127.0.0.0/8` and cloud-metadata hostnames in OAuth2 discovery SSRF check** (#431): Strengthened SSRF guard in OAuth2 discovery to block loopback ranges and cloud metadata endpoints
- **Resolved infinite loop when combining `outputSchema` + tools** (#412): Fixed infinite loop occurring when `outputSchema` and tools were used together (also added unit tests)

**Notable**: **v1.2.0 release (2026-06-03)** incorporated post-v1.1.0 security and robustness fixes (CORS vulnerability, OAuth2 SSRF prevention, abort on HTTP disconnect, `AdkApiServer` host restriction, etc.). Subsequent work on main—the **Skills Registry trilogy** (Core interface + Zip extraction + local Toolset cache → remote GCP Skills Registry integration → dynamic SearchSkillsTool for LLM Agents, #422-424), **OpenAPI spec operation parser + auth handler (part 2, #385)**, and **streaming prototype pollution fix (via model-controlled JSON paths, security, #410)**—was **released in v1.3.0 (2026-06-22)**, keeping pace with Python-side Skills Registry and GCP integrations.

#### 2026-06-17 Updates (Gemini 2.5/3.x Live Models / dynamic ADK Web assets DL / secure randomUUID)

- **Gemini 2.5 / 3.x Live Models support** (#409, `feat(core)`): Supported Gemini 2.5 / 3.x Live models in ADK JS
- **Dynamic download of ADK Web assets**: Dynamically downloaded ADK Web assets and served from shared folder (#427)
- **Enabled concurrent replacement + key dedup** (#432): Supported concurrent replacement with key deduplication
- **Suppressed trailing empty STOP chunks in SSE streaming** (#426, `fix(streaming)`): Suppressed trailing STOP chunks with zero parts
- **Used secure `randomUUID`** (#433, `refactor(core)`): Used secure `randomUUID` when available
- **Made session event keys MySQL index-safe** (#437): Adjusted session event keys to fit MySQL indexes
- **Fixed state mutation bad practice in `content_processor_utils`** (#430)
- **TSDoc / unit test expansion**: TSDoc + unit tests for LLM processors / summarizer / security plugin / a2a utils / compacted events (#413), unit tests for `OAuth2CredentialRefresher` (#403), TSDoc for `agent_transfer` / `tool_filter` / `context_compactor` / `content_request` / `agent_registry_mcp` processor (#414)

#### Changes after v1.1.0 (Included in v1.2.0)

- **Implemented Agent Registry**: Implemented Agent Registry in adk-js (#358)
- **Fixed CORS vulnerability**: Disabled `express.urlencoded` parser to resolve CORS vulnerability (security) (#378)
- **Prevented OAuth2 SSRF**: Blocked SSRF via IPv4-mapped IPv6 and fixed dead `172.16/12` check (security) (#354)
- **Removed hardcoded `*` from `run_sse`**: Removed hardcoded `Access-Control-Allow-Origin` wildcard from `run_sse` (security) (#360)
- **Aborted agent execution on HTTP disconnect**: Aborted agent run when HTTP connection drops (#382)
- **`AdkApiServer` host restriction**: Restricted `AdkApiServer` to listen only on the configured host (#383)
- **OpenAPI auth helpers / credential exchangers (part 1)**: Implemented auth helpers and credential exchangers for OpenAPI (#384)
- **`customMetadata` support**: Supported `customMetadata` in `runAsync` / `runEphemeral` (#363)
- **`listSessions` pagination / sorting**: Added pagination and sorting to `listSessions` (#331)
- **Closed MCP client sessions (Windows)**: Closed MCP client sessions after `listTools`/`callTool`, fixing Windows libuv assertions and process leaks (#333)
- **`AgentTool` fixes**: Stopped propagating `skipSummarization` to parent `EventActions` (#301); filtered `temp:` keys from sub-agent state deltas (#271)
- **Wrapped function tools array responses**: Wrapped array responses for Gemini API compliance (#347)
- **Externalized `agent_loader` esbuild deps**: Marked `lightningcss` / `jiti` external, fixing `adk web` failures when optional deps are absent (#319)
- **Agent Engine Sandbox Code Executor**: Added code executor running via Agent Engine Sandbox (#317)
- **Added `@param` TSDoc**: Added `@param` TSDoc to `BeforeA2ARequestCallback` and `AfterA2ARequestCallback` (#339)
- **`injectSessionState` unit tests**: Added unit tests for `injectSessionState` in instructions (#338)
- **`runWithRouting` `failover_utils` tests**: Added unit tests for `runWithRouting` (#336)
- **`file_extension_utils` tests**: Added unit tests for `file_extension_utils` (#337)
- **Vertex AI Memory Bank service**: Implemented Vertex AI Memory Bank service + tests (#291)
- **Agent Engine Sessions support**: Added Agent Engine Sessions support (#249)
- **Google Maps tool**: Added new Google Maps tool (#321)
- **`VertexRagRetrievalTool`**: Grounding retrieval tool using Vertex AI RAG Engine (#277)
- **`stringifyContent` / `AgentTool` thought parts filter**: Filtered thought parts from output (#323)
- **Windows compatibility**: Replaced unix `cp` with Node.js `fs.cp` in `dev/build.js` (#318)
- **Applied `toolFilter` in `MCPToolset.getTools()`**: Fixed `getTools()` to apply `toolFilter` (#312, #313)
- **Fixed `StreamingResponseAggregator.close()` drop**: Fixed drop when final chunk has no candidates (#289, #311)

#### Key Changes in v1.1.0

- **`UrlContextTool`**: Added `UrlContextTool` for Gemini 2+ URL context grounding (#303)
- **Vertex AI Search Tool**: Added Vertex AI Search tool (#296)
- **MCP prefix strip**: Fixed stripping prefix on tool execution (#299)
- **`AgentTool` session reuse**: Used `getOrCreateSession` for reuse within the same session (#302)
- **Fixed `adk web` UI source serving path**: (#309)
- **Used `js-yaml`**: Switched from `yaml` package to `js-yaml` (#293)

#### Key Changes in v1.0.0

**[Core / Features]**

- **Official release**: Promoted to v1.0.0 (#229)
- **Progressive model streaming processing**: Progressive model streaming processing (#258)
- **Skills system**: script execution (#276), loader part 3 (#256), toolset part 2 (#252), skills interface (#251)
- **Abort parameter support**: Supported abort parameter across runner / agent / model / tool / processors (#234)
- **`RoutedAgent` / `RoutedLlm`**: Routable agent and LLM (experimental) (#215)
- **Unsafe local code executor**: Unsafe local code executor (#257)
- **Plugin callbacks for context compaction and tool selection**: Plugin callbacks (#250)
- **Auth preprocessor**: Auth preprocessor (#227)
- **OAuth2 support**: OAuth2 classes (#225)
- **`AdkApiServer` export**: Exported from `@google/adk-devtools` (#245)
- **`Agent` type alias for `LlmAgent`**: Parity with Python ADK (#242)

**[Bug Fixes]**

- **Custom URL options for DB connections**: Client URL support (#284)
- **Fixed `thoughtSignature` propagation**: Propagation when streaming parallel function calls (#268)
- **ESM dynamic require support**: Preserved `__dirname`/`__filename`/`import.meta.url` in ESM builds (#254)
- **Fixed ESM dynamic require**: (#244)
- **Added invocation id**: Added invocation id when merging parallel tool responses (#253)
- **Moved otel dependency**: Moved from dev deps → deps (#243)

**[Security / Deps]**

- **Path traversal prevention**: `FileArtifactService` (CWE-22)
- **lodash / lodash-es security updates**: (#232, #230)
- **follow-redirects bump**: (#275)
- **vite bump**: `npm_and_yarn` group (#236)

#### Key Changes in v0.2.4

- **A2A integration**: Serving agents via A2A using CLI options (#188)
- **Token-based context compaction**: (#191)
- **Fixed session DB initialization**: (#195)
- **MikroORM refactoring**: Refactored session service

#### Reference Links

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**Current version**: v0.41.3

**Checkout state**: `v0.41.3-1-g659f047` (v0.41.3 + 1 commit, HEAD 2026-05-21)

**Notable**: README announced evolution into successor project `agents-cli` (#952), and recently **officially surfaced that it entered maintenance mode and pushed users to `agents-cli`** (#967). Google's agent dev tooling strategy has effectively migrated to `agents-cli`.

#### Changes after v0.41.3

- **Official maintenance mode announcement**: Surfaced maintenance mode in README / docs and pushed migration to `agents-cli` (#967)

#### Key Changes in v0.41.3

- **Version bump**: Version bump to v0.41.3 (#953)

#### Key Changes in v0.41.2

- **Regenerated uv lock + pinned `langgraph-prebuilt`**: Pinned `langgraph-prebuilt<1.0.9` (#948)
- **Announced `agents-cli`**: Announced `agents-cli` as next-generation evolution of Agent Starter Pack (#952)

#### Key Changes in v0.41.1

- **Version bump**: Version bump to v0.41.1 (#944)

#### Key Changes in v0.41.0

- **Default region change**: Changed default region to `us-east1`

#### Key Changes in v0.40.1

- **Fixed Vertex AI model name**: Used valid model name in connectivity check (#919)
- **Updated BQ analytics table name**: Updated to `agent_events` table name (#924)

#### Key Changes in v0.40.0

- **`adk-py@` shortcut**: Added shortcut for `google/adk-python` contributing samples (#918)
- **Gemini Enterprise app filter**: Added `appType` filter to `list_gemini_enterprise_apps` (#912)

#### Reference Links

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**Current version**: **v1.11.0 (2026-09-28)**

**Checkout state**: `18588d94` (HEAD 2026-10-08 = v1.11.0 + dependency bumps)

#### Verified 2026-10-13 (dependency bumps only, 6 commits)

[Diff for this update](https://github.com/GoogleCloudPlatform/cloud-run-mcp/compare/5dcae110...18588d94). Items below are unreleased changes on HEAD; public release remains v1.11.0.

- **deps**: `@modelcontextprotocol/sdk` 1.26.0 → 1.31.0 (#328), `brace-expansion` 5.0.12 (#324), `proxy-addr` 2.0.8 (#325), `fast-uri` 3.1.8 (#327), `@grpc/grpc-js` 1.14.5 (#326), `ip-address` 10.7.2 (#321). For next release

#### 2026-09-23 to 2026-10-07 Updates (**v1.11.0** + SECURITY fix)

- **v1.11.0 (2026-09-28, #319)**: Mainly dependency updates (`yargs` 17.7.3 / `qs` 6.16.0 / `hono` 4.13.7 / `protobufjs` / `fast-uri` / `js-yaml` 4.3.2). Moved npm publish to Node 24 (#320)
- **SECURITY (HEAD)**: Fixed cache-poisoning vulnerability (#322)

#### 2026-08-01 to 2026-08-20 Updates (1 commit, dependency bump only)

- **deps**: `js-yaml` 4.3.0 → 4.3.1 (#308). No functional changes; no tagged release issued

#### Updates as of 2026-07-27 (dependency bumps only; no substantive changes)

- **dependabot**: `fast-uri` 3.1.4 (#303) / `js-yaml` 4.3.0 (#302) / `body-parser` 2.3.0 (#301). No functional changes

#### Updates as of 2026-07-18 (Docker Compose → Cloud Run direct deploy features = unreleased)

- **Docker Compose deployment support**: Added `deployCompose` capability to deploy directly to Cloud Run from compose definitions (#252, #272)
- **`run-compose` integration**: Download/run `run-compose` binary for compose translation; parallel builds and translate (#244, #245, #253, #249)
- **Compose resource extensions**: Supported volume mounts (#254), Secret Manager (#256), and AI models (#258) in compose deployments
- **Cloud Build integration** (`cloudbuild.yaml` + BUILD_ID scheduled builds, #269, #275); **bundled Cloud Run skills** (#267)
- Breaking changes: None

#### 2026-06-29 Updates (archiver v8 migration)

- **Upgraded to `archiver` 8.0.0**: Updated internal zip/tar creation utility (`lib/util/archive.js`) for breaking API changes in `archiver` v7→v8. Removed old factory `archiver('zip'|'tar', …)` and switched to named class exports `new ZipArchive({ zlib })` / `new TarArchive({ gzip })`. Also added `test/local/archive.test.js`. User-facing behavior (source archive on deploy) is unchanged; upstream breaking changes absorbed internally (#297)

#### Changes after v1.10.0

- **Continued `hono` 4.12.x bumps**: Dependency patch bumps for `hono`, etc., continuing to latest HEAD (through #294)
- **Bumped `@protobufjs/utf8` 1.1.0 → 1.1.1**: Dependency patch bump (#282)
- **Bumped `fast-uri` 3.1.2 / `fast-xml-builder` 1.2.0 / `hono` 4.12.18**: Dependency patch bumps (#281, #280, #279)
- **Bumped `ip-address` / `express-rate-limit`**: Security patches (#277)
- **Docker Compose deployment support**: Enabled deploying docker compose configurations to Cloud Run (#272)
- **BUILD_ID-based cloudbuild**: Added BUILD_ID-based cloudbuild for scheduled builds (#275)
- **Fixed cloudbuild image location**: Fixed image placement location (#273)
- **Fixed README SKILL.md links**: (#276)
- **Cloudbuild config**: Added `cloudbuild.yaml` (#269)
- **Cloud Run skills**: Added cloud run skills (#267)
- **Fixed named/bind volume permissions**: (#262)
- **AI model support**: Supported AI models in run compose (#258)
- **Secrets Manager support**: Supported Secrets Manager in compose deployments (#256)
- **Volume mount support**: (#254)
- **Parallel builds**: Supported parallel builds in run compose (#253)
- **`deployCompose` capability**: (#252)
- **Translate functionality for run compose**: (#249)
- **More detailed service info**: Provided richer info in `getInfo` (#248)
- **Added SECURITY.md**: (#247)
- **`run-compose` binary integration**: Binary download and resource command execution (#244, #245)
- **Refactored artifact download logic**: Made reusable (#240)
- **Dependency updates**: Hono 4.12.14, fast-xml-parser 5.7.1, lodash 4.18.1, path-to-regexp 8.4.0, picomatch 4.0.4, etc.

#### Key Changes in v1.10.0

- **`cloud-run-mcp` client**: Added client for deploying from OSS Run MCP (#242)
- **Ingress policy env var**: Configured ingress policy via environment variable (#243)
- **Run v1 client**: Added `googleapis`-based Run v1 client (#236)
- **Expanded integration tests**: Added integration tests for Java, Node.js, and Python projects

#### Reference Links

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**Current version**: `gcloud-mcp-v0.5.3` / `storage-mcp-v0.6.0` / `observability-mcp-v0.2.3` / `backupdr-mcp-v0.1.0`

**Checkout state**: `release-please-422-19-g238728f` (19 commits ahead of `storage-mcp-v0.6.0` release-please branch, HEAD 2026-07-15. `release-please-NNN` is a bot tag, not semver)

#### Updates as of 2026-07-18 (breaking change in storage-mcp 0.6.0 + dependency bumps)

- **Breaking**: **Removed `download_object_safe` tool in `storage-mcp` 0.6.0 (#420)** — clients using this tool must migrate to alternatives. Moved `delete_object` from safe→destructive in 0.5.1 (#412)
- **`gcloud-mcp` 0.5.3**: Windows compatibility refactor (#342); repaired integration tests (#426)
- The 19 commits ahead of the pin are almost entirely dependency bumps (`js-yaml` / `hono` / `@grpc/grpc-js` / `googleapis` v172, etc.)

#### Changes after storage-mcp-v0.6.0

- **Standard dependency updates**: Standard dependency updates (#428)
- **Bumped `turbo` to v2.9.14 (security)**: Security update for `turbo` to v2.9.14 (#430)
- **Bumped `@tootallnate/once` 2.0.0 → 2.0.1**: Dependency patch bump (#431)
- **Bumped `qs` 6.15.0 → 6.15.2**: Dependency patch bump (#432)
- **Bumped `protobufjs` 7.5.6 → 7.6.1**: Dependency minor bump (#436)
- **Updated `googleapis` to v172**: Updated `googleapis` dependency to v172 (#433)
- **Bumped `brace-expansion` 5.0.5 → 5.0.6**: Dependency patch bump (#429)
- **Bumped `fast-uri` 3.1.0 → 3.1.2**: Dev deps bump (#427)
- **Standard dependency updates**: Standard dependency updates (#399)

#### Key Changes in storage-mcp-v0.6.0 (2026-05-06)

- **Removed `download_object_safe` tool (breaking change)**: Removed because despite being named "safe", its design allowed writing to sensitive destination paths like `~/.bashrc`. Must migrate to the destructive `download_object` path or `read_object_content` / `read_object_metadata` (#420, #422)
- **Repaired integration tests**: Fixed failures due to unreachable MCP connection (#421, #426)
- **Dependency bumps**: hono 4.12.12 → 4.12.18 (#425), ip-address / express-rate-limit (#423), protobufjs 7.5.4 → 7.5.6 (#417), postcss 8.5.6 → 8.5.12 (#416), fast-xml-parser 5.5.7 → 5.7.1 (#415), codecov-action v6 (#410)

#### Key Changes in storage-mcp-v0.5.1

- **Moved `delete_object` to destructive**: Moved from safe tools to destructive tools (security hardening) (#412)
- **`gemini mcp list --debug` flag**: Added debug flag to avoid output truncation (#405)

#### Key Changes in storage-mcp-v0.5.0

- **Safe object download tool**: Added safe download object tool; marked original as destructive (#403)
- **Custom User-Agent**: Set custom User-Agent on Storage client (#407)
- **Fixed `list_buckets`**: Used `project` instead of `userProject` (#408)

#### Key Changes

- **`backupdr-mcp` v0.1.0**: Added new Backup DR MCP server (#372, #380)
- **`storage-mcp` v0.3.3**: Updated storage component (#358)
- **`observability-mcp` v0.2.3**: Updated observability component (#357)
- **Windows compatibility**: Refactoring (#342)

#### Reference Links

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### Gemini Cloud Assist MCP

**Current version**: v0.8.0 (2026-04-21)

**Checkout state**: `v0.8.0-11-g54903e5` (v0.8.0 + 11 commits, HEAD 2026-10-12)

**Notable**: **Fully deprecated** local Node.js implementation (v0.2.0) and overhauled architecture to a Remote MCP Server setup. Currently in **Private Preview** via allowlist (access request required through Google Cloud account team).

#### Verified 2026-10-13 (3 commits)

[Diff for this update](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp/compare/04988915...54903e5b). Plugin addition is on HEAD; public release remains v0.8.0.

- **feat**: **Added Claude Code plugin** (157a1a2). Other commits are Internal Changes

#### 2026-09-16 to 2026-09-22 Updates (1 commit)

- **chore**: Removed deprecated Gemini CLI extension and instructions (e32393c)

#### Changes after v0.8.0 (For Next Release)

- **Updated skills**: Updated bundled skills (a0439a7)
- **Added Claude Code Instructions**: Added instructions for Claude Code to README/project docs (540474b, 22a2a18)
- **Updated README MCP Tool description**: Incorporated MCP Tool descriptions and Claude Code instructions into README (997bb4d, 8580afd)
- **GitHub workflows cleanup / fixes**: Cleaned up CI workflows (a8c60dc)

#### Key Changes in v0.8.0

- **Migrated to Remote MCP Server**: Full migration from local Node.js MCP server to **Remote MCP Server architecture** (**breaking change**) (d225f7b)
- **Fully deprecated local Node.js server**: Completely retired v0.2.0 local server (d5d860b)
- **Private Preview launch**: Officially launched Gemini Cloud Assist remote MCP Server in Private Preview
- **Added Skills**: Added 2 Skills: `designing-and-deploying-infrastructure` and `operating-google-cloud`
- **Added deprecation / Private Preview notices to README**: Documented local deprecation and remote access request steps

#### Key Changes in v0.2.0 / v0.1.x (Legacy Local Node.js)

- **Published npm package**: Published `@google-cloud/gemini-cloud-assist-mcp` to npm (e24e526)
- **`mcpName` / install instructions**: Added `mcpName` field and install instructions for Claude Desktop / npm package (831c72e, 4a7afda)
- **version sync script**: Added to tooling (94cc346)
- **npm publish workflow**: Automated npm publish via GitHub Actions (6b00fa5)

#### Breaking Changes

| Change | Impact |
|---|---|
| Local Node.js server → Remote MCP Server (v0.8.0) | Client configs must point to remote endpoint; local install flows are obsolete |

#### Reference Links

- [Gemini Cloud Assist MCP](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp)
- [Use the Gemini Cloud Assist remote MCP server (Cloud Docs)](https://docs.cloud.google.com/cloud-assist/use-gemini-cloud-assist-mcp)

---

### GKE MCP

**Current version**: **v0.15.0 (2026-07-28)**

**Checkout state**: `a3f1b45` (`v0.15.0-52-ga3f1b45`, HEAD 2026-09-21. No new tag issued)

#### 2026-09-16 to 2026-09-22 Updates (4 commits, dependency bumps only)

- **deps**: `google.golang.org/adk` 1.6.1 → 1.7.0 (#550), `anthropic-sdk-go` 1.73.0 (#551), `google.golang.org/api` 0.298.0 (#549), 7 `/ui` npm group updates (#552)

#### 2026-09-01 to 2026-09-15 Updates (dependency bumps only; no functional changes)

- **deps**: UI `@modelcontextprotocol/ext-apps` 1.7.5 → **2.0.0** (#548), `go-sdk` 1.8.0 (#546), `google.golang.org/adk` 1.6.1 (#536), `anthropic-sdk-go` / `genai` / npm group, etc. No substantive functional changes

#### 2026-08-01 to 2026-08-31 Updates (dependency bumps only; no substantive changes)

- **deps (all 17 commits)**: `goquery` 1.13.0 (#529), `anthropic-sdk-go` 1.68.0 (#528), `genai` 1.70.0 (#527), kubernetes group (#524, #519), protobuf-grpc group (#525), google-cloud group (#523), **`google.golang.org/adk` 1.6.0 (#518)**, multiple ui npm groups. No functional changes

#### 2026-07-28 to 2026-07-29 Updates (v0.15.0 release: `delete_cluster` safety checks)

- **v0.15.0 release (#494)**: Officially tagged previously recorded unreleased items (`query_prometheus` #471 / `query_traces` #467 / evals mock infra, etc.)
- **Added safety checks to `delete_cluster` tool** (#481): Strengthened guardrails for destructive operations
- **deps (most of 13 commits)**: `@hono/node-server` 1.19.13→2.0.12 (#495), 11 all-npm group updates (#493), 3 kubernetes group updates (#487), `google.golang.org/genai` 1.65.0 (#490), `adk` 1.5.1 (#489), `anthropic-sdk-go` 1.61.0 (#491). Security bumps: `brace-expansion` 5.0.7 (#483), `fast-uri` 3.1.4 (#485)
- fix(ci): Resolved MD013 line length in SKILL.md (super-linter) (#486). No breaking changes

#### Updates as of 2026-07-27 (Added `query_prometheus` PromQL tool + evals mock infra → included in v0.15.0)

- **feat(monitoring): Added `query_prometheus` tool for PromQL metric queries** (#471)
- **evals**: Mock routing for `query_prometheus` (#472), mock support for `monitoring_time_series_chart` / `mql_validator` + mock for `jobset-interruption` skill (#482), centralized MCP mock middleware + VBAR OOM eval mock (#468)
- deps: all-npm group / google-cloud group / genai 1.64.0 / anthropic-sdk-go 1.58.0, `actions/setup-node` 7 / `setup-go` 7, fixed presubmit formatting (#480)

#### Updates as of 2026-07-18 (post-v0.14.0, unreleased)

- **`query_traces` MCP tool**: Added tool for Google Cloud Trace (#467) — recent highlight
- **Eval suite expansion**: Multi-case evals for JobSet interruption (#458), GPU/TPU disruption (#460), and TPU vbar OOM (#457)
- Mostly dependency updates (`anthropic-sdk-go` / `google.golang.org/genai`, `api` / `adk`). No breaking changes

#### Key Changes in v0.14.0 Release (2026-07-06)

- **Added `verify_unused` cluster safety check skill** (#444)
- **Added GKE TPU dynamic slices monitoring/management skill** (#442)
- **Added View parameter (`BASIC|FULL`) to `query_logs`**: Supports compact log entry output (#449)
- **Dependency updates**: `google.golang.org/adk` 1.4.0 → 1.5.0 (#455), **`adk-anthropic-go` 0.1.18 → 1.0.0 (major, #454)**, `anthropic-sdk-go` 1.56.0 (#453), `google.golang.org/api` 0.287.0 (#452), 9 ui npm group updates (#456)
- Updated version to 0.14.0 (#451). No explicit breaking change markers (formally tagged skills already recorded after v0.13.0)

#### 2026-07-01 Updates (Added TPU metrics monitoring skill)

- **Added `gke-tpu-metrics-monitoring` skill**: Skill using GKE system metrics and PromQL to monitor and troubleshoot TPU workloads, nodes, and node pools. Diagnoses whether workload interruptions or performance degradation stem from underlying infrastructure. Bundles `EVAL.yaml` / `TEST.md` / `references/failure_signatures.md` / `scripts/validate_queries.sh` alongside `SKILL.md` (#443)

#### 2026-06-29 Updates (GPU/TPU disruption skill + UI vulnerability fix)

- **Added GPU/TPU host maintenance disruption skill**: Skill `gke-ai-troubleshooting-handle-disruption-gpu-tpu`. Diagnoses and predicts node disruptions on GPU/TPU workloads during Compute Engine host maintenance. Includes diagnostic workflow starting from scheduled maintenance checks (#430)
- **Fixed UI dependency vulnerabilities (security)**: Updated `ui/package-lock.json` to resolve UI dependency vulnerabilities, mainly bumping Babel toolchain transitive dependencies (`@babel/core` etc. to 7.29.x) (#448)

#### Dependency Bumps Only (2026-06-29, no substantive changes)

- `github.com/anthropics/anthropic-sdk-go` 1.50.1 → 1.51.1 → 1.53.0 (#434, #446)
- `google.golang.org/genai` 1.61.0 → 1.62.0 (#445)
- 10 batched all-npm group bumps (#447)
- (dev) `@types/node` 25.9.3 → 26.0.0 in `/ui` (#437)
- (ci) `actions/checkout` 6 → 7 (#432)

#### 2026-06-26 Updates (Developer Knowledge API docs / manifestgen mapping / DK 404 fix)

- **Added Developer Knowledge API env vars / setup docs** (#439)
- **manifestgen: Mapped `giq_fetch_model_server_versions` to gcloud command** (#428); **mapped `giq_fetch_model_servers` to gcloud command** (#427)
- **Fixed DK `SearchDocuments` HTTP method to GET to resolve 404** (#440)
- **Fixed duplicate manifestgen instructions + required Developer Knowledge usage** (#438)
- **Aligned `instruction.md` with registered MCP schema** (#405)
- **Dependency bumps**: hono 4.12.23 → 4.12.27 (#441), `google.golang.org/api` 0.284.0 → 0.286.0 (#433), genai 1.60.0 → 1.61.0 (#435), super-linter 8.6.0 → 8.7.0 (#431)

#### 2026-06-18 Updates (`gke-skill-creator` meta-skill)

- **Added `gke-skill-creator` meta-skill** (#419): Added meta-skill (a skill for creating skills) targeting GKE

**Notable**: **v0.13.0 released on 2026-05-28**. Following v0.12.0's Anthropic Claude ADK adapter and node pool management tools, v0.13.0 added a batch of k8s resource operation tools (apply / get / describe / patch / delete / logs / rollout status / auth check / api resources / cluster info / events). Also added install checksum verification and secure CI checks (preventing insecure `pull_request_target`). Post-v0.13.0 continues with dependency bumps (`google.golang.org/api`, `genai`, `anthropic-sdk-go`, kubernetes group, `esbuild`, npm group, etc.).

#### 2026-06-15 Updates (dependency bumps only)

NO_NEW_COMMITS — HEAD date only updated to 2026-06-15. `google.golang.org/api` 0.283.0 → 0.284.0 (#423).

#### 2026-06-13 Updates (Anthropic SDK / Kubernetes / esbuild bumps)

- **`anthropic-sdk-go` 1.48.0 → 1.50.1**: Bumped Anthropic SDK Go (#424)
- **3 kubernetes group updates**: Updated k8s dependencies (#422)
- **`esbuild` 0.28.0 → 0.28.1**: Updated UI esbuild (#421)
- **`google.golang.org/genai` 1.59.0 → 1.60.0**: Bumped genai SDK (#425)
- **9 NPM group updates (UI)**: Updated npm dependencies (#426)

#### 2026-06-10 Updates (skill evals moved to yaml)

- **Migrated skill evals from textproto → yaml**: Switched skill evals from textproto to yaml format to align with OSS (#420)

#### Key Changes in v0.13.0 (2026-05-28)

- **Expanded k8s resource operation tools**: Implemented `list_k8s_api_resources` (#378), `patch_k8s_resource` (#387), `get_k8s_rollout_status` (#386), `check_k8s_auth` (#385), `describe_k8s_resource` (#388), `get_k8s_cluster_info` (#379), `get_k8s_logs` (#370), `delete_k8s_resource` (#368)
- **Set default delete cascade policy to background**: Set k8s delete default cascade policy to background (#376)
- **Install checksum verification**: Added checksum verification during install (#398)
- **Insecure `pull_request_target` prevention check (CI)**: Added CI check preventing unsafe `pull_request_target` usage (#400)
- **Removed `eval-on-pr` workflow**: Disabled and completely removed `eval-on-pr` workflow (#397, #399)
- **Dependency bumps**: `google.golang.org/adk` 1.2.0 → 1.3.0 (#393), genai 1.57.0 → 1.58.0 (#392), `anthropic-sdk-go` 1.43.0 → 1.45.0 (#394), `adk-anthropic-go` 0.1.15 → 0.1.16 (#395), `go-sdk` 1.6.0 → 1.6.1 (#391), `api` 0.279.0 → 0.280.0 (#390), 7 all-npm group updates (#396), qs 6.15.0 → 6.15.2 (#382)
- **manifestgen developer knowledge instructions**: Added developer knowledge usage instructions to manifestgen (#371)
- **Implemented `apply_k8s_manifest` tool**: Added new MCP tool to apply k8s manifests (#358)
- **Integrated ADK Anthropic Claude Go library**: Integrated `Alcova-AI/adk-anthropic-go` (#356)
- **dk: Switched `SearchDocuments` / `GetDocuments` / `AnswerQuery` to real HTTP**: Promoted 3 Developer Knowledge tools from mocks to real HTTP calls (#344, #345, #346)
- **Removed Baseline Evaluation Label Requirement**: Removed mandatory label requirement for Baseline Evaluation (#369)
- **Bumped `anthropic-sdk-go` 1.42.0 → 1.43.0** (#364)
- **Bumped `google.golang.org/genai` 1.56.0 → 1.57.0** (#363)
- **7 all-npm group updates (UI)** (#365)
- **`get_k8s_version` tool**: Added K8s version retrieval tool (#353)
- **Cluster operations support**: Added cluster operations support and improved unit tests (#328)
- **DK real HTTP connection**: Switched `SearchDocuments` from mock implementation to real API calls (#344)
- **Updated OWNERS / automatic reviewers**: Updated owners and automatic reviewer settings (#355)
- **Removed eval skips**: Deleted evaluation skip logic (#354)
- **Implemented `list_k8s_events` tool**: Added new k8s event listing tool (#329)
- **Triggered baseline evals on feature branches**: Ran baseline evaluation on feature branches as well (#352)
- **Switched `eval-on-pr` to `pull_request_target`**: Ran eval CI on `pull_request_target` (#347)
- **Defined `dk_get_documents` tool**: Defined Developer Knowledge get-documents tool (#324)
- **`get_k8s_resource` MCP tool**: MCP tool retrieving k8s resources using client-go (#327)
- **Defined `dk_search_documents` tool**: Defined Developer Knowledge search-documents tool (#326)
- **Defined `dk_answer_query` tool**: Defined Developer Knowledge answer-query tool (#325)
- **DeepEval CI/CD integration**: Implemented DeepEval tests for PRs and CI/CD workflows (#323)
- **Integrated Developer Knowledge API client**: Integrated developer knowledge api client (#319)
- **`giq_fetch_model_servers` instructions**: Added `giq_fetch_model_servers` usage instructions to manifestgen (#307, #308)
- **UI dependency bumps**: hono 4.12.14 → 4.12.18 (#322), ip-address / express-rate-limit (#320), fast-uri 3.1.0 → 3.1.2 (#331)
- **Go / NPM dependency bumps**: `anthropic-sdk-go` 1.39.0 → 1.42.0 (#342), genai 1.55.0 → 1.56.0 (#339), gkerecommender 0.5.0 → 1.0.0 (#340), google-cloud group (#337)
- **CI action bumps**: `google-github-actions/auth` v2 → v3 (#336), `actions/checkout` v4 → v6 (#335), `setup-go` v5 → v6 (#334), `setup-python` v5 → v6 (#333)

#### Key Changes in v0.12.0

- **Implemented ADK Anthropic Claude adapter**: LLM abstract factory + ADK adapter for Anthropic Claude (#280, #303)
- **Added Node Pool management tools**: Tools for GKE node pool create/list/update, etc. (#282)
- **New cluster tools + GKE remote MCP features**: New cluster operation tools and GKE remote MCP integration (#281)
- **giq `fetch_model_servers` / `fetch_profiles`**: Implemented fetch tools for model servers and profiles and wired them to manifest agent (#284, #285, #290, #293, #279)
- **manifestgen rename**: `giqTool` → `generateManifestTool` (#306)
- **GKE AI TPU connectivity troubleshooting skill**: (#267)
- **GKE AI troubleshooting skill authoring guide**: (#268)
- **Dependency bumps**: google-cloud groups (#296), `modelcontextprotocol/go-sdk` 1.5→1.6 (#298), `google.golang.org/api` (#297), genai 1.54→1.55 (#299)
- **Added auto-request-review**: (#305)

#### Changes after v0.11.1

- **GIQ tool manifest agent integration**: Integrated `giq_generate_manifest` into manifest agent (#253)
- **Separated GIQ core logic from MCP transport**: (#251)
- **ADK framework integration (manifest agent)**: Integrated ADK into manifest agent (#247)
- **Skills installation instructions**: Added Skills install steps to README (#252)
- **backend vertex pool abstraction**: Separated agent mocks (#240)
- **Strengthened `gke-productionize` skill guidelines**: (#242)
- **Fixed `gke-workload-security` skill pathing**: (#248)

#### Key Changes in v0.11.1

- **Used `go-version-file`**: Used `go-version-file` in release process; version bump to v0.11.1 (#238)
- **Embedded rich instructions in manifestgen**: (#218)
- **Updated Hono dependency**: UI Hono 4.12.12 → 4.12.14 (#237)

#### Key Changes in v0.11.0

- **Updated MUI dependencies**: Updated Material-UI dependencies to latest versions (#233)
- **Updated NPM dependencies**: Updated `globals`, `typescript`, etc. (#234)
- **Fixed CI markdownlint/Prettier conflict**: Resolved CI conflict between markdownlint rules and Prettier formatting (#232)
- **Dependabot NPM config**: Added dependabot config for NPM (#220)
- **Updated CI actions**: `actions/checkout` v6, `actions/setup-node` v6, `actions/setup-go` v6 (#223-#225)

#### Key Changes in v0.10.0

- **Golden Image Finder skill**: Added golden image search skill
- **Docker image support**: Added Docker image support (#183)
- **GKE Workload Scaling skill**: Added workload scaling skill
- **ComputeClasses skill**: Added ComputeClasses creation skill
- **Fixed Shell Command Injection**: Fixed shell command injection vulnerability in `ui/scripts/build.ts` (security)

#### Reference Links

- [GKE MCP](https://github.com/GoogleCloudPlatform/gke-mcp)

---

### Google Analytics MCP

**Current version**: **0.7.0 (2026-07-29)**

**Checkout state**: `0.7.0` (the tag commit itself, HEAD 2026-07-29)

#### Key Changes in 0.7.0 (2026-07-29)

- **v0.7.0 release (#202)**: Functional changes bundled into the release commit (no separate feat commits in range; no `CHANGELOG.md`)
- **fix(deps): Added upper bound to `mcp` dependency** (#200)
- CI: Updated `actions/checkout` digest (#193), `actions/setup-python` v7 (#194). No breaking changes or security fixes

#### 2026-06-29 Updates (dependency patch update)

- **Bumped `google-analytics-admin` to 0.30.1**: Patch bump of pinned `google-analytics-admin==0.30.0` → `0.30.1` in `pyproject.toml` (Renovate automated PR). No breaking changes (#188)

#### 2026-06-25 Updates (CI/build chore only)

- **CI: Pinned `actions/checkout` to v7** (#181, Renovate)
- **build: Fixed zizmor findings** (#183): Resolved GitHub Actions static analysis zizmor findings

#### 2026-06-11 Updates (setup instructions for Claude Code)

- **Added Claude Code section**: Added Google Analytics MCP setup section for Claude Code to README (#174)

#### Key Changes in 0.6.0 (2026-05-21)

- **Prevented subprocess stdio handle inheritance**: Prevented stdio handle inheritance in subprocesses, resolving follow-up deadlock from v0.4.0 #151 fix (#154)

#### Key Changes in 0.5.0

- **Added conversions schema/spec tools**: Added new tools for conversions schema / spec (#161)
- **`google-analytics-data` v0.22.0**: Dependency bump (#159)
- **`google-analytics-admin` v0.29.0**: Dependency bump (#158)

#### Key Changes in v0.4.0

- **Fixed tool call deadlock / stdout corruption**: Resolved tool call deadlocks and stdout protocol corruption (#151)

#### Key Changes in v0.3.0

- **Added `run_funnel_report` tool**: Funnel report tool using GA Data API v1alpha (#127)
- **Added Skills for ADK development**: Bundled ADK development Skills with Google Analytics MCP (#148)

#### Changes after v0.2.0

- **Updated minimum `google-adk` version (security)**: Updated minimum `google-adk` version to 1.28.1, mitigating vulnerability GHSA-rg7c-g689-fr3x (#137)
- **Improved MCP schema compatibility**: Improved MCP schema compatibility and LLM guidance
- **ADK migration**: Migrated to use Google ADK
- **Updated `google-analytics-admin`**: Updated to v0.28.0
- **Updated `google-analytics-data`**: Updated to v0.21.0

#### Key Changes in v0.2.0

- **Fixed ADK schema types**: Fixed removal of null types
- **pipx support**: Enabled running server via pipx

#### Unreleased Breaking Changes

| Change | Impact |
|---|---|
| Renamed package to `analytics-mcp` (#44) | Install command needs updating |

#### Reference Links

- [Google Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp)

---

### MCP (Google Cloud)

**Current version**: Continuous deployment (no version tags)

**Nature**: Official Google repository aggregating MCP server directories, deployment guidance, and starter examples (continuous deployment).

#### 2026-08-17 Updates (demo agent model update)

- **Updated agent model in `launchmybakery` demo to `gemini-3.5-flash`**. No directory layout changes

#### 2026-06-18 Updates (Added Angular CLI MCP)

- **Added Angular CLI MCP** (#38): Included Angular CLI MCP server in directory and examples

#### Recent Changes

- **Fixed bakery `demographics.csv`**: Removed `median_household_income` column from `launchmybakery` demo `demographics.csv` and fixed dataset description (#53)
- **Updated remote MCP server / examples section**: (#44)
- **Automated bakery demo**: Automated enabling `gcloud mcp` with `--quiet` flag
- **Fixed `launchmybakery` cold start**: Set explicit timeout on MCP endpoint (cold start handling)
- **Pinned bakery ADK version**: Pinned ADK tool to v1.28.0; added Ctrl+C stop instructions
- **Enabled `bigquery.googleapis.com` in bakery**: Enabled API in `setup_env.sh`
- **Cloud Data MCP sample**: Added lab for DK and Cloud SQL remote MCP (#22)
- **Demo video / badges**: Added demo video and badges to README
- **Chrome DevTools server**: Added new MCP server

#### Key Changes

- **Gemini 3.1 Pro Preview**: Updated root agent model to `gemini-3.1-pro-preview`
- **Remote server aggregation**: AlloyDB, BigQuery, Bigtable, Cloud Resource Manager, Cloud SQL (MySQL/PostgreSQL/SQL Server), Compute Engine, Firestore, Google Maps, Chronicle, GKE, Spanner, Cloud Run, Cloud Storage
- **Open-source MCP server integration**: Workspace, Firebase, Cloud Run, Google Analytics, MCP Toolbox, GCS, etc.

#### Reference Links

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**Current version**: `secops-v0.7.1` / `gti-v0.1.3` / `scc-v0.1.1` / `secops-soar-v0.1.2` (2026-08-27, per-server tag scheme)

**Checkout state**: `9885ec6` (HEAD 2026-09-07. No new tag issued)

#### 2026-09-01 to 2026-09-15 Updates (ADK v2 runner migration + SOAR case management; tags unchanged)

- **feat(adk)**: Migrated demo SOC agent to **native ADK v2 CLI runner** (#303), FastAPI factory / Typer CLI (`chat`/`serve`/`info`) / multi-transport toolset manager
- **SOAR**: **Case Management tools** (#281), improved `certifi` / `aiohttp.ClientSSLError` error messages (#191 / #308)

#### 2026-08-01 to 2026-08-29 Updates (SCC v2 API migration + SOAR fixes + 4 server tags issued)

- **`scc-mcp`**: **Migrated to SCC v2 API**, new finding tools, organization-level findings support, added mute tool, extracted filter helpers and fixed sorting → **`scc-v0.1.1`**
- **`secops-mcp`**: Fixed `test_rule` buffered hour calculation by truncating `end_time` to the start of the hour → **`secops-v0.7.1`**
- **`gti-mcp`**: Enabled `trust_env` on VirusTotal client (proxy support) → **`gti-v0.1.3`**
- **`secops-soar-mcp`**: Aligned setup entrypoint, declared dotenv dependency, stopped creating SOAR sessions on close and made cleanup idempotent, fixed case details response key, added docs on finding `SOAR_URL` → **`secops-soar-v0.1.2`**

#### Changes after v0.7.0

- **Added `list_parsers` tool**: Added `list_parsers` tool to `secops-mcp`, standardized parser management return types, and added pagination token support (#252)
- **Applied pyink formatting**: Applied pyink formatting to `parser_management.py`
- **SOC persona docs**: Added SOC persona to documentation (#245)
- **Moved `gemini-extension.json`**: Refactored to top level

#### Key Changes in v0.7.0

- **Rule Exclusions management tools**: Added rule exclusion management tools (#242)

#### Key Changes in v0.6.0

- **Investigation management tools**: Added investigation management tools (#220)
- **Watchlist management tools**: Added watchlist management tools (#222)
- **Remote MCP server**: Remote MCP server implementation and docs (#215)

#### Reference Links

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**Current version**: **v1.14.0 (2026-10-08)** (v1.13.1 was 2026-09-25, v1.13.0 was 2026-09-24)

**Checkout state**: `c8922eba2b8` (HEAD = v1.14.0 + 3 commits. Repo URL is `googleapis/mcp-toolbox`)

#### Verified 2026-10-13 (**v1.14.0** 2026-10-08 + HEAD)

[Diff for this update](https://github.com/googleapis/mcp-toolbox/compare/69aa2f25...c8922eba). Below separates [v1.14.0 CHANGELOG](https://github.com/googleapis/mcp-toolbox/blob/v1.14.0/CHANGELOG.md) from subsequent unreleased changes.

- **v1.14.0 (2026-10-08, #4159)**: Formally released prior HEAD items: **Spanner Omni source** (#4198), **`looker-get-explore` tool** (#4173), LookML dashboards in `looker` `get_dashboards` (#4216), **BigQuery authorized views and dataset restriction** (#2561), lexical dataset reference check before BigQuery dry run (#4164), propagated requester header in Firestore `get_schema` (#4131), Bigtable / Firestore reference support in data analytics query (#4136), lowercased resource-template URI schemes (#4023)
- **HEAD (after v1.14.0, unreleased)**: Removed `Authorized()` from the `Tool` interface and centralized `authRequired` checks (#4254). Previously, 25 tools always returned `true`, failing to enforce configured `authRequired`. Expanded cloudgda integration test coverage (#4160); moved CI zig fetch to GCS

##### Breaking Changes and Migration Verified in This Update (Unreleased)

- **Removed `Authorized()` from `Tool` / `BaseTool`**: Downstream callers must be updated. Move authorization checks to server handling using `GetAuthRequired()` from config and centralized `tools.IsAuthorized(...)`. Do not bypass authorization with per-tool always-allow overrides. Because this enforces configured `authRequired`, verify auth settings on affected tools

Source: [Authorization fix commit](https://github.com/googleapis/mcp-toolbox/commit/00ce6356a53).

#### 2026-09-23 to 2026-10-07 Updates (**v1.13.0 / v1.13.1** + HEAD: looker / BigQuery / Spanner Omni)

- **v1.13.1**: Reverted "connect sources on first use" (#4137), `geminidataanalytics` v1.4.0 (deprecated Spanner region #3920)
- **Around v1.13.0**: `conversational-analytics-list-accessible-data-agents` returns all data agents and supports manual paging (#4066), `value_format` / `value_format_name` in looker field metadata (#4094), moved tool annotations to `ConfigBase` (#4064), fixed YAML comment handling in `parseEnv` (#4039)
- **HEAD (after v1.13.1)**: **Spanner Omni source** (#4198), **`looker-get-explore` tool** (#4173), LookML dashboards in `looker` `get_dashboards` (#4216), **BigQuery authorized views and dataset restriction** (#2561), BigQuery checks lexically referenced datasets before dry run (#4164), propagated requester header in Firestore `get_schema` (#4131), `gemini-data-analytics-query` supports Bigtable / Firestore references (#4136), normalized resource-template URI schemes to lowercase (#4023)

#### 2026-09-16 to 2026-09-22 Updates (**v1.12.0**: OpenAI Apps challenge + looker extensions + bigtable prebuilt)

- **feat**: Serve `/.well-known/openai-apps-challenge` (#4038) — OpenAI Apps challenge endpoint
- **looker**: Expose `certification_metadata` in dashboard/look tools (#4041), require embed parameters in `looker-generate-embed-url` (#3913), annotations for OpenAI plugins (#4035)
- **fix**: Release handles on connection failure in cockroachdb/redis sources (#3933), clarify `execute_sql` tool description in `cloud-sql-postgres` (#3884)
- **docs**: Groups schema and specification for `com.google.cloud/toolbox.v1` (#3937)
- **ci**: `cloud-sql-mssql` evals (#3942), parameterized exit gate configuration (#4047)
- **HEAD (after v1.12.0)**: Bigtable prebuilt config (#4068), connect sources on first use (#4076), expanded `cloud-sql-postgres` evals

#### 2026-09-01 to 2026-09-15 Updates (**v1.11.0**: MCP Apps / MCP Resources / groups extension)

- **MCP Apps support** (#4008), **MCP Resources support** (#3968)
- **mcp**: Exposed `groups/list` and `groups/get` as Toolbox extensions (#3914)
- **`source/bigquery`**: Passed SQLCommenter attributes to BigQuery job labels (#3843)
- **sources**: `ConnectOnce` for initial connection (#3905), Toolbox version check at startup (#3837)
- **SECURITY**: **Default SSRF guard in HTTP source blocks IETF protocol assignments range** (#3909), released handles on connection failure (#3921)
- **docs**: `secureParam` schema for `com.google.cloud/toolbox.v1` (#3890), read-only tools security docs (#3978)

#### 2026-08-01 to 2026-08-28 Updates (v1.9.0 / v1.10.0 releases: FalkorDB / Secure Parameters / read-only mode / databaseinsights)

- **v1.9.0 (2026-08-14)**: Alongside prior window's unreleased items (Bigtable admin / `bigtable-list-schemas` / Looker dashboard tools / `/healthz` / BigQuery `apiEndpoint`), added **`cloud-sql-connect-gce` (pg/mysql/mssql)** (#3740), **AlloyDB Advanced Query Insights tools + `databaseinsights` source** (#3722, #3461), **`ttlMs` / `cacheScope` customization for groups** (#3805), **generic client extension registry** (#3723), migrated `toolset` → `group` kind (#3704), **renamed Spanner `execute_sql_dql` → `execute_sql_readonly`** (#3776, breaking rename), `review-prs` skill (#3743)
- **v1.10.0 (2026-08-27)**: **Native read-only mode for sources and dynamic tool annotations** (#3872), **FalkorDB source / tools** (#3692), **supported MCP Secure Parameters as experimental Toolbox extension** (#3394), **supported `com.google.cloud/toolbox.v1` extension at v20260728** (#3801), **`firestore-execute-mql` / `firestore-get-…` tools for `firestore-mongodb`** (#3826), runtime collection specification for mongodb (#3715), `fix-failing-tests` skill (#3821)
- **Fixes / security**: String normalization for postgres UUIDs (#3806), **resolved symlinks at local path boundaries in `cloud-storage` source** (#3810), merged prebuilt tools on custom config reload (#3864), compared env var offsets in config in rune space (#3856), background process filter in `postgres-list-active-queries` (#3885), resource leak fix (`context.WithoutCancel`, #3849)
- **CI**: Isolated eval step failures and sped up change detection (#3904). Only breaking change is Spanner tool rename (#3776)

#### 2026-07-28 to 2026-07-31 Updates (v1.8.0 release + follow-up dev: Bigtable admin / BigQuery `apiEndpoint` / healthz)

- **v1.8.0 release (#3653)**: Officially tagged previously recorded unreleased work (skills generation improvements / groups / Looker tools / SSRF guard #3625, etc.). No breaking changes
- **Bigtable admin tools**: Added admin lifecycle and listing tools (#3596)
- **BigQuery `apiEndpoint`**: Added field on source to override BigQuery API host (#3437)
- **`/healthz` endpoint**: Added container health check endpoint to server (#3060)
- **Added `dataplex-update-data-product-aspects` tool** (#3607); **migrated prebuilt `skills-repo` toolsets to `kind: group` (with descriptions)** (#3595)
- **Updated draft specs to 2026-07-28** (#3699); improved error messaging when env vars are unset (#3718)
- **fix**: Preserved provider error classification in `bigquery-execute-sql` (#3738); re-introduced startup tool validation (#3705); made existing `LIMIT` detection whitespace-independent in cockroachdb (#3554)

#### Updates as of 2026-07-27 (unreleased dev after v1.7.0: skills generation / groups / Looker tools / SSRF guard → included in v1.8.0)

- **Enhanced skills generation**: Generate skill from 1 group with `--group` (#3585), default `--name` to `--group`/`--toolset`/single `--prebuilt` name (#3586), made description optional (#3584)
- **Added groups support** (#3605)
- **Looker tools**: Added `get_field_value_suggestions` (#3696), supported result-makers / merge queries in `run-dashboard` (#3698)
- **SECURITY: Default SSRF guard in `source/http` blocks CGNAT `100.64.0.0/10`** (#3625), validated source instance in `cloud-sql-admin` backup-run restore (#3555), tool name validation (#3654)
- Stabilized alphabetical sorting for default toolset (#3539); added maintainer playbook (#3693)

#### Updates as of 2026-07-18 (v1.6.0 → v1.7.0: ArcadeDB / Dataplex data-product / ClickHouse vector)

- **ArcadeDB support**: Added new arcadedb source and tools (#2961)
- **`quotaProject` support**: Allowed specifying `quotaProject` in BigQuery / Looker conversational analytics (#2610)
- **Dataplex expansion**: Added create/update data product, create/update data asset, and get data asset tools (#3574, #3503, #3504)
- **ClickHouse vectors**: Added native vector embedding support to `clickhouse-sql` tool (#3229)
- **Postgres `connectTimeout`** (#3620); fixed parameters returning an error instead of panicking on non-string types (#3516, #3512)
- Breaking changes: None (no BREAKING CHANGES listed in v1.7.0)

**Notable**: **v1.6.0 release (#3495)**. Main highlight is **MCP 2026 draft spec support** (#3544) — added `vdraft` protocol implementation enabled via `--enable-draft-specs` opt-in flag, with draft spec provisionally scheduled for official release on 2026-07-28 (runs alongside existing v20241105 / v20250326 / v20250618 / v20251125). On the supply-chain front, **integrated Kokoro code signing into the release workflow to digitally sign Toolbox binaries** (#3528, separating unsigned/signed GCS buckets + adding signature verification user guide, addressing long-standing issue #996). On the tool side, expanded **Dataplex data-product tools** (`dataplex-get-data-product` #3499 / `dataplex-list-data-assets` #3500) and **configurable object operation parameters in `cloud-storage`** (#3529). Fixed **mTLS / `GOOGLE_API_USE_MTLS_ENDPOINT` support in GDA (Gemini Data Analytics) client** (#3460, restoring Context Aware Access (CAA) per AIP-4114). This release formally tagged unreleased dev already recorded in 2026-06-26 updates (Dataplex/Looker tools, #3337/#3478/#3494/#3507/#3531/#3515). See [UPGRADING.md](https://github.com/googleapis/genai-toolbox/blob/main/UPGRADING.md).

#### 2026-07-01 to 2026-07-07 Updates (unreleased dev after v1.6.0: continued Dataplex tools + ClickHouse vector)

- **Added native vector embedding support to ClickHouse SQL tool** (#3229)
- **Added `dataplex-create-data-product` tool** (#3504); **added `dataplex-get-data-asset` tool** (#3503)
- **Hardened parameters**: Reported offending value on array/map type errors (#3512); returned error instead of panicking on non-string fields (#3516)
- **docs**: Documented least-privilege permissions for `execute_sql` (#3416); added Announcement Banner config (#3532)
- **CI**: zizmor autofix (#3560)

#### Key Changes in v1.6.0 Release (2026-06-30)

New additions accumulated after the previous record point `b67419d34` (= #3531) up to the v1.6.0 tag.

**[Features]**

- **MCP 2026 draft spec support** (#3544): Added `vdraft` protocol implementation (manifests / method / types), enabled opt-in via `--enable-draft-specs` flag. Official draft spec release provisionally scheduled for 2026-07-28
- **Added `dataplex-get-data-product` tool** (#3499): Tool to fetch a single Dataplex data product
- **Added `dataplex-list-data-assets` tool** (#3500): Tool to list Dataplex data assets
- **Configurable object operation parameters in `cloud-storage` tool** (#3529): Made object operation parameters configurable

**[Security / Supply chain]**

- **Integrated Kokoro code signing into release workflow to digitally sign binaries** (#3528): Uploads unsigned binaries to unsigned GCS bucket and signed binaries to signed bucket + verifies signed binaries when generating release tables; added verification instructions to user guide (issue #996)

**[Fixes]**

- **mTLS / `GOOGLE_API_USE_MTLS_ENDPOINT` support in GDA (Gemini Data Analytics) client** (#3460): Fixed custom REST HTTP client lacking dynamic mTLS endpoint routing (violating AIP-4114 and breaking Context Aware Access (CAA)). Dynamically selects endpoints via `GOOGLE_API_USE_CLIENT_CERTIFICATE` / `GOOGLE_API_USE_MTLS_ENDPOINT`. Switched `bigquery-conversational-analytics` / `conversational-analytics-ask-data-agent` / `conversational-analytics-get-data-agent-info` / `conversational-analytics-list-accessible-data-agents` / `looker-conversational-analytics` to use `NewGDAClient`

**[Docs / deps]**

- **Updated hugo for release** (#3556)

No breaking changes (MCP draft spec is opt-in via `--enable-draft-specs` leaving default behavior unchanged; code signing affects release artifacts only).

#### 2026-06-26 Updates (unreleased dev after v1.5.0: Dataplex / Looker tools)

20 commits on main after v1.5.0 (no new release tag yet). Key items:

**[Features]**

- **Added `dataplex-list-data-products` tool** (#3337): Tool to list Dataplex data products
- **Configurable parameters support in `cloud-storage` tool** (#3478)
- **Looker: `dynamic_fields` parameter support in queries** (#3507); **complex `filter_expression` parameter support** (#3494)

**[Fixes]**

- **Changed Looker `explore_references` from panic to shape validation** (#3531)
- **Fixed Looker API payload structure in `looker-create-view-from-table`** (#3515)

**[Refactor / Internal]**

- **Refactored `NewParameter` to functional-options pattern** (#3314)
- **Grouped config flags into cobra flag group** (#3477); **added deprecation support for primitives** (#3327)

**[Docs / deps]**

- **Redirected SDK pages (Python/JS/Go) to API reference site** (#3505); fixed `sql-commenter` flag description in CLI docs (#3473)
- **Security bump of langchain to v1.3.9** (#3469); Go updates (#3393, #3471); GitHub Actions major (#3434); Hugo (#3317)

#### 2026-06-19 Updates (v1.5.0 release / SSRF guards SECURITY / MCP auth guard / MySQL tools)

**[Security]**

- **Implemented SSRF guard in `source/http`** (#3448)
- **`source/cloudhealthcare`: Prevented SSRF via `pageURL` parameter validation** (#3453)
- **`bigquery-execute-sql`: Blocked dataset restriction bypass** (#3452)
- **Failed startup when both MCP auth and `enable-api` are enabled** (#3435): Rejected unsafe configuration at server startup

**[Features]**

- **Added `show-query-stats` / `list-all-locks` tools for MySQL / Cloud SQL MySQL** (#2954)
- **Added URL parameter binding for HTTP transport** (#3112)
- **Spanner: Used read-only annotation when `readOnly` is set** (#3338)

**[Fixes]**

- **`InitializeConfigs`: Returned error instead of panicking** (#3397)
- **`auth/dataplex`: Fixed source failure with service account credentials** (#3369)
- **npm: Read binary version from `cmd/version.txt`** (#3417)
- **release 1.5.0 (#3379)** / updated hugo for release (#3479) / removed v0.31.0 from docsite version dropdown (#3481)

#### 2026-06-18 Updates (ScyllaDB source / Dataplex enrichment / query-plan injection prevention / toolset filtering)

**[Features]**

- **Added ScyllaDB source / tools** (#3119): Added new source support for ScyllaDB
- **Dataplex metadata enrichment workflow tools** (#3270): Added tools to Dataplex supporting metadata enrichment workflows
- **Toolset filtering support on `prebuilt` CLI flag** (#3245): Enabled toolset filtering via `prebuilt` CLI flag
- **Per-source level flags for SQL commenter** (#3465): Enabled SQL commenter flags at source level
- **Wired BigQuery `maximumBytesBilled` to prebuilt config** (#3385)
- **Added doc / line context to config parse errors** (#2957)

**[Security]**

- **SECURITY: Prevented query execution bypass + statement injection in `mysql-get-query-plan`** (#3235): Prevented query execution bypass and statement injection in `mysql-get-query-plan` tool
- **SECURITY: Restricted bucket / local path access in `cloud-storage` source** (#3454): Restricted access to buckets and local paths
- **SECURITY: Required `audience` or `clientId` in `auth/google` when `mcpEnabled`** (#3450)
- **fix(deps): Patched npm audit vulnerabilities in JS doc samples** (#3442)

**[CI / docs / deps]**

- **Automated publishing via OSS Exit Gate**: Automated npm publishing (#3391) and PyPI publishing (#3430); wrote npm `.npmrc` to `$HOME` and passed `--registry` to npm publish (#3431); ungrouped npm major updates into per-dependency PRs (#3427)
- **docs**: Clarified Cloud Run VPC configuration (#3414); SQL commenter and telemetry attributes (#3458); added mariadb to readme (#3242)
- **Fixed integration test skips and centralized core patterns** (#3401); **added `wontfix` label** (#3470)
- **JS quickstart dependency bumps**: langchain 1.2.12 → 1.3.9 (#3467), `@google/adk` ^1.2.0 (#3428, #3436), `@google/genai` ^2.8.0 (#3438), ws 8.20.1 → 8.21.0 (#3466, #3432), form-data 4.0.5 → 4.0.6 (#3468, #3433)

#### 2026-06-15 Updates (regex method injection / path normalization bypass patches)

- **SECURITY: Bumped `picomatch`**: Bumped `picomatch` to 2.3.2 (#3426) / 4.0.4 (#3429) to fix regex method injection
- **SECURITY: Bumped `fast-uri` to 3.1.2**: Bumped `fast-uri` to 3.1.2 to fix path normalization bypass (#3425)
- **Docs quickstart dependency bumps**: Bumped fast-xml-parser 5.5.x → 5.9.0 (#3424, #3421), hono 4.12.x → 4.12.25 (#3422, #3361), axios 1.15.0 → 1.18.0 (#3420, #3419, #3418), qs / express (#3282, #3309), ip-address / express-rate-limit (#3423), `@grpc/grpc-js` 1.14.3 → 1.14.4 (#3404) across ADK / genkit / langchain quickstarts

#### 2026-06-12 Updates (SQL injection escape / MCP HTTP body size limit)

- **SECURITY: Escaped delimiter characters in `applyEscape`**: Escaped delimiter characters in `applyEscape` to prevent SQL injection (#2811); also updated escaping in `bigquery_integration_test.go` (#3392)
- **SECURITY: Limited MCP HTTP body size**: Set upper limit on MCP HTTP body size (#3216)
- **Decoupled tool initialization from sources**: Separated tool initialization from sources (#3355)
- **Offline skills generation**: Enabled generating skills without live source connections (#3388); allowed unset env vars during offline `skills-generate` (#3399)
- **Specified `cloud-platform` scope on default credentials for dataplex / datalineage** (#3376)
- **Made password env var explicitly required in `alloydb-omni` prebuilt** (#3398)
- **Dependency bumps**: Go update (#3310), `@grpc/grpc-js` 1.14.3 → 1.14.4 (#3402)

#### Key Changes in v1.4.0 (2026-06-04)

- **Data Lineage integration**: Added Data Lineage integration (#3285)
- **`--ignore-unknown-tools`**: Flag to ignore unknown tools at startup (#3353)
- **Cloud SQL PG vector assist tools**: Added remaining vector assist tools (#3203)
- **Spanner `search_catalog`**: Implemented `search_catalog` tool (#3140)
- **Required issuer on opaque tokens**: Enforced issuer presence in generic auth opaque token validation (security) (#3360)
- **Separated Google / Generic MCP OAuth verification**: Separated OAuth verification (security) (#3341)
- **`windows/arm64` binary distribution**: Supported `windows/arm64` in CI (#3231)

#### Changes after v1.3.0 (Included in v1.4.0)

- **ClickHouse / BigQuery identifier injection prevention**: Validated identifier parameters to prevent injection (security) (#3219)
- **apache/thrift CVE-2026-41602 fix**: Replaced `apache/thrift` v0.22.0 → v0.23.0 to resolve CVE (#3312)
- **Looker unquoted parameters filter value escape**: Escaped filter values for unquoted parameters (#3289)
- **GitHub Actions major updates**: Updated GitHub Actions to major versions (#3316)
- **Go runtime update**: Updated Go (#3187)
- **Fixed conformance presubmit go version mismatch**: Fixed Go version mismatch in presubmit (#3315)
- **Dependency bumps**: otel 1.39.0 → 1.41.0 (#3198), fast-xml-builder 1.1.4 → 1.2.0 (#3200), brace-expansion (#3246), ws 8.19.0 → 8.21.0 (#3248) / 8.18.3 → 8.20.1 (#3262)

#### Key Changes in v1.3.0 (2026-05-21)

**[Features]**

- **Added `cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` tools**: Added bulk `execute-sql` / `sql` tools for Cloud SQL admin (#3083)
- **SQLCommenter + client metadata emission**: Added SQLCommenter mechanism attaching client metadata comments to SQL (#3064)
- **MCP auth tool-level scopes validation**: Validated tool-level scopes in MCP auth (#3049)
- **Looker client IP propagation**: Propagated client IP from incoming MCP requests to downstream SDK calls (#3253)

**[Bug Fixes]**

- **Prevented HTTP tool path traversal / base path scope escape**: Prevented path traversal and base path scope escape in HTTP tools (security) (#3218)
- **Enforced toolset/promptset boundary**: Enforced toolset/promptset boundaries on `tools/call` and `prompts/get` (#3036)
- **Fixed generic auth expiration**: Fixed integration of expiration field and `authRequired` in generic auth (#3251)
- **Looker 401 passthrough**: Returned 401 directly to MCP client when Looker returns 401 (#3233)
- **Stripped wrapping quotes on Looker filter values**: Removed wrapping quotes from filter values on unquoted parameters (#3273)
- **Initialized query result slices**: Initialized query result slices as empty arrays (#3250)

#### Key Changes in v1.2.0 (2026-05-07)

**[Features]**

- **HTTPS/TLS listener support**: Added HTTPS/TLS listener support (#3126)
- **BigQuery `maximumBytesBilled` source config**: Added `maximumBytesBilled` cost-limiting config on BigQuery sources (#2724)
- **Cloud Storage source (read operations)**: Added Cloud Storage source providing `list_objects` and `read_object` tools (#3081)
- **Cloud Storage bucket / object management tools**: Added bucket and object management tools to Cloud Storage source (#3129)
- **Cloud Storage write/copy/move/delete object tools**: Added write/copy/move/delete operations to Cloud Storage source (#3139)
- **Knowledge-catalog Data Quality Scans search**: Dataplex DQ Scans search tool with scan ID / table name filters, pagination, and sorting (#2444)

**[Bug Fixes]**

- **Allowed string literal block with list conversion**: Permitted the conversion (#3050, closes #3023)
- **Implemented MCP router-level logger injection**: Router-level logger injection in MCP auth (#3067)
- **Prevented `test.db` creation**: Prevented `test.db` creation during unit tests (#3042)
- **Removed SSE hardcoded `*` allowed origin**: Removed hardcoded allow-origin from SSE (security) (#3054)
- **Fixed Postgres source URL encoding**: Applied URL encoding to query string params (#3020)
- **Looker conversational-analytics OAuth token**: Fixed OAuth token in GDA payload (#3058)
- **BigQuery `execute-sql` error output**: Fixed malformed queries not to surface as MCP 500 (#3056)
- **Looker Conversational Analytics OAuth**: Fixed OAuth for Looker Conversational Analytics (#3044)

#### Key Changes in v1.1.0

- **Cloud SQL Postgres vector assist tools**: Added vector assist tools for Cloud SQL Postgres (#2909)
- **Flattened Looker YAML**: Fixed Looker config YAML to flat format (#3022)
- **Renamed `dataplex` → `knowledge-catalog`**: Renamed `dataplex` to `knowledge-catalog` across docs (#3039)

#### Key Changes in v1.0.0 (**Stable Release**)

- **Elasticsearch vector search**: Added vector search support & removed query passthrough parameter (**breaking change**) (#2891)
- **Looker `git-branch` tool refactor**: Split `looker-git-branch` tool into 5 separate tools (**breaking change**) (#2976)
- **Opaque token validation**: Added opaque token validation support in `generic` authService (#2944)
- **Cloud SQL Postgres connection check**: Executes `SELECT 1` after successful connection (#2997)
- **BigQuery semantic search**: Added semantic search support in BigQuery SQL (#2890)
- **Elasticsearch ES/QL**: Added tool to execute arbitrary ES/QL queries (#3013)
- **MySQL `list-table-stats`**: Added MySQL table statistics listing tool (#2938)

#### Key Changes in v0.32.0

- **Repository name update**: Changed repository name (**breaking change**) (#2968)
- **MCP tool annotations**: Added MCP tool annotations to all remaining tools (#2221)
- **BigQuery conversational analytics tools**: Added conversational analytics tools for Data Agents (#2517)
- **Claude Code / Codex skill support**: Added Claude Code and Codex user agent support to generation scripts (#2966, #2973)
- **Tool execution via npx**: Supported calling tools via npx (#2916)
- **Looker agent management**: Managed Looker agents from MCP (#2830)

#### Key Changes in v0.31.0

- **`enable-api` flag**: Added flag to enable API (**breaking change**)
- **Protected Resource Metadata endpoint**: Added Protected Resource Metadata endpoint
- **Manual PRM override**: Added manual PRM override support
- **Dataplex lookup context tool**: Added Dataplex lookup context tool
- **Removed deprecated items & updated `tools-file` flag**: Removed deprecated items (**breaking change**)

#### Breaking Changes

| Change | Impact |
|---|---|
| Elasticsearch vector search (v1.0.0, #2891) | Removed query passthrough parameter |
| Looker `git-branch` refactor (v1.0.0, #2976) | Split 1 tool → 5 tools |
| Repository name update (v0.32.0, #2968) | Repository URL changed |
| `enable-api` flag (v0.31.0) | Explicit enabling of API endpoints required |
| Removed deprecated items (v0.31.0, #2806) | Changes to `tools-file` flag, etc. |
| Sanitized HTTP non-2xx error output (v0.31.0, #2654) | Error response format changed |
| Reorganized prebuilt toolsets (v0.29.0) | AlloyDB, Spanner, etc. toolset structure changed |
| Config file v2 (v0.27.0, #2369) | Config file format updates required |

#### Reference Links

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

### Knowledge Catalog

**Current version**: Continuous deployment (no version tags; newly tracked)

**Checkout state**: `77a4431` (main HEAD, 2026-10-12)

**Maintainer**: Google Cloud Platform (samples/tools repo, not an official Google product)

#### Verified 2026-10-13 (enhanced mdcode semantic-model loader + samples)

[Diff for this update](https://github.com/GoogleCloudPlatform/knowledge-catalog/compare/cd6fb05c...77a44318). Untagged HEAD changes; deploy preflight commit is dated 2026-10-07.

- **feat (mdcode)**: Binding profile files, overlay merge, and completeness check (#481); KC deploy preflight checks (#484); per-engine expression list (#489); enforced strict entity sources (#490); named deployments support and rejected inline profiles in semantic-model loader (#492); consistently applied profile files in-memory (#493)
- **samples**: Added governance / policy-as-code agents from `knowledge-catalog-labs` (#498)

##### Breaking Changes and Migration Verified in This Update (Untagged HEAD)

- **Google flavor model config**: Migrate `deployment_target` to a named `deployments` list. Inline `profiles` are rejected; split them into `<model>.profile.<name>.yaml` sidecar files (#492)
- **Stricter entity sources**: Normalize to `bigquery:` / `spanner:` / `alloydb:` or full resource names. Legacy bare source resolution applies only when `allowLegacyBareSource: true` is explicitly set (#490)

Sources: [deployment / profile migration](https://github.com/GoogleCloudPlatform/knowledge-catalog/commit/7e63f07), [source strictness](https://github.com/GoogleCloudPlatform/knowledge-catalog/commit/aeb8351).

#### 2026-09-16 to 2026-09-22 Updates (28 commits: mdcode pivoted to Agent Skill generation + multiple BREAKING changes)

- **BREAKING (mdcode)**: Removed kcmd agent-tools and unused TS runtime, centering on `skills-generate` (#459); removed entity lookup tools from agent tool derivation (#458); removed `kcmd action-run` / `action-list` (#457); removed store-reading judge from runtime (#455); trimmed action command lines to curation essentials (#454); projected action parameters from fields (#452); rejected `sql` executor on models with profiles (#449); made `judgment` the sole constraint body (#446); removed generated row keys (#431)
- **feat**: Generate Agent Skills from semantic models — `kcmd skills-generate` outputs `SKILL.md` + `references/<action>.md` folder (#451); validated action DML against store on push (BigQuery dryRun / Spanner PLAN) (#464); added parameter descriptions/defaults/optionality to actions (#442)
- **demo**: Commerce demo installs generated skill rather than agent (#453)
- **docs**: Rewrote `skills.md` user guide and optimized `skills-generate` (#460); reorganized actions guide

#### 2026-09-01 to 2026-09-15 Updates (mdcode: actions / constraints / AlloyDB + deriving agents from semantic models)

- **semantic model**: Version-gated schema, fail-fast validation, leaf-only measures, normative model spec (#392)
- **actions**: Announced write operations as semantic-actions; declared affected targets with `affects` (#407); guarded with constraints via `guards` (#404); executors bound via profiles (#416); `kcmd action` rejects operations that cannot be verified against live stores (#413)
- **constraints**: Model-level constraints with violation actions and severity (#410); rules expressible as natural-language judgments (#414); **judge reads the model's own tables to adjudicate guards** (#422 / #426)
- **Agent derivation**: Derived runnable agents and tools from semantic models (#419 / #420)
- **AlloyDB**: Added as second operational store; runs agent demo across both stores (#424 / #425)

**Notable**: **Knowledge Catalog (formerly Dataplex)** = AI-powered data catalog and metadata management platform. Provides a dynamic knowledge graph over structured and unstructured data to give AI agents semantics and business context. This repository contains demos, tools, and **samples / tools** for building **context management / enrichment / retrieval** solutions using Knowledge Catalog features. Aligns with GenAI Toolbox's **dataplex → knowledge-catalog rename** (#3039) and Cloud SQL / BigQuery DQ Scans search tools (#2444) along the "Dataplex renamed to Knowledge Catalog" theme. **Reorganized repo around Open Knowledge Format (OKF) on 2026-06-20**: removed top-level `agents/` folder and consolidated enrichment agent into `okf/src/reference_agent` (renamed `enrichment_agent` → `reference_agent`). Current layout: `okf/` (OKF reference implementation + `reference_agent`), `samples/` (discovery, enrichment), `toolbox/` (enrichment, mdcode).

#### 2026-08-01 to 2026-08-30 Updates (semantic-model codelab + Spanner Graph push + OWL logical model)

- **mdcode: Added semantic-model codelab** (#349 and others): Split into task-focused pages (#335), marked production-ready (#369), Spanner deploy via binding profiles (#364), paste-safe placeholders (#385), top-down RDF diagrams (#380), reorganized semantic-model deploy guide (govern-first, #386)
- **mdcode: Introduced binding profiles** (#358, design #357) — derives graph backend from profiles with `--no-profile` / `--profile` / `--all-profiles` + `--no-kc` axes (#376)
- **mdcode: Added Spanner Graph as `kcmd push` target** (#361), resolved Spanner graph KEY/REFERENCES to physical columns (#363), logical-only source output for KC entities (#368), and **KC push for logical-only models** (#367)
- **OWL import**: **Generated pure logical models** (#375), opt-in compact flow YAML `--compact` (#377), carried `owl:oneOf` / `propertyChainAxiom` / set-level axioms (AllDisjoint*/AllDifferent), carried non-native OWL constructs as custom extensions (#333), pushed class hierarchies to BigQuery Graph (labels + field flattening, #331)
- **fix / env**: Backticked reserved words in generated graph DDL (#382), allowed re-pushing non-addressable entry-link aspects (#384), env overrides for Dataplex endpoint and KC type project (#347)

#### Updates as of 2026-07-27 (Migrated to Open Knowledge Format v0.2)

- **Migrated format / tooling to OKF v0.2** (#227)
- **Updated SPEC.md**

#### 2026-06-20 Updates (Reorganized around OKF / renamed `reference_agent` / `ConversationLearner` agent)

- **Reorganized repo around OKF**: Focused README title and intro on format (OKF) (#130), renamed `enrichment_agent` package to `reference_agent` (#129), removed top-level `agents/` folder (#128)
- **Added `ConversationLearner` agent** (#105): New agent learning knowledge from conversation logs. Followed by per-conversation parallel analysis + dedup (#114), log fetching with `page_size=1000` (#116), optional stable proposal IDs (#117), local human-in-the-loop proposal review UI (#118), non-interactive CLI entrypoint (#126), and cross-conversation recurrence aggregation (#127)
- **enrichment agent: Confluence / SharePoint sources + OKF output** (#106, #108); **cross-cutting hybrid KB / per-entry table `fact_recall` / public goldens** (#103)

#### Key Structure

- **Open Knowledge Format (OKF)**: Reference implementation for **metadata-as-code** (`okf/`). Includes OKF demo (including GA4 demo #19), linking Documents Layout on Dataplex via `parent` (#24), and file-relative paths for OKF cross-links so bundles render on GitHub (#45). Reference agent lives at `okf/src/reference_agent` (renamed and consolidated from `enrichment_agent` #129)
- **enrichment agent (ADK-based)**: Synced enrichment agent + evaluation harness to old `agents/enrichment` (now `samples/enrichment` + `toolbox/enrichment`) (#42); imported OKF reference enrichment agent (#28); bundled eval corpora for `financial_services` / `phone_services`
- **Onboarding setup**: Added agent `requirements.txt` and improved onboarding docs (#54)

#### Reference Links

- [knowledge-catalog (GitHub)](https://github.com/GoogleCloudPlatform/knowledge-catalog)
- [Knowledge Catalog (Google Cloud)](https://cloud.google.com/products/knowledge-catalog)

---

## Key Highlights

### Breaking Changes Summary

| Target | Change | Action Priority |
|---|---|---|
| **A2UI Python SDK v0.8.0 / core v0.3.0 (public release)** | Core dependency `>=0.3.0,<0.4.0`. Handle parser model return types via conversion helpers; pass catalogs as a list. Old schema modifiers removed. Component tree `type` renamed to `component` | High |
| **A2UI Python SDK (unreleased HEAD)** | Removed stream-parser and `create_stream_parser`; migrate to `create_parser().parse_chunk`. Update `CatalogConfig` import and provider name | Medium |
| **A2UI TS public release (Angular 0.12.0, Lit / React / web_core 0.13.0)** | Legacy v0.8 APIs for Angular / Lit / React moved to `/v0_8`. React v0.9 basic catalog moved to `web_core`. Component trees read `tree.component` | High |
| **AG-UI Mastra 2.0.0 / 2.0.1 (public release)** | Requires AG-UI `>=1.0.0` and optional CopilotKit peer `^1.76.0`. Removed legacy `on_interrupt` / `forwardedProps.command` / `emitInterruptOutcome`; migrate to `RUN_FINISHED` outcome / `RunAgentInput.resume`. Re-verify tool approvals and wire output | High |
| **GenAI Toolbox HEAD after v1.14.0 (unreleased)** | Removed `Tool` / `BaseTool.Authorized()`. Move callers to centralized `GetAuthRequired` / `IsAuthorized` checks and review previously unenforced auth settings (#4254) | High |
| **Knowledge Catalog mdcode (untagged HEAD)** | Migrate Google flavor `deployment_target` to named `deployments`, and inline profiles to sidecar files. Use canonical prefixes / full resource names for entity sources (#490 / #492) | Medium |
| **AG-UI 1.0** (2026-09-17) | Spec freeze + 1.0.0 SDKs (TS/Py/.NET). `THINKING_*` → `REASONING_*`, `InputContent` → `ContentPart` rename, added `RUN_FINISHED.outcome`, subagent events, `ACTIVITY_*`, HTTP+Protobuf binary wire. 0.x agents work with 1.0 clients (compatibility boundary + `DEPRECATIONS.md`) | High |
| **Knowledge Catalog mdcode** (2026-09) | Pivoted to Agent Skill generation. 8 `!` commits including removal of `kcmd` `agent-tools` / `action-run` / `action-list`, removal of store-reading judge from runtime, and removal of generated row keys | Medium |
| **ADK Go (main after v2.4.0, 2026-09)** | Web server binds to loopback by default (#1456); adkrest rejects DNS-rebinding hosts and cross-origin browsers (#1615) | Medium |
| **MCP-Apps v2.0.0** (2026-09-08) | Migrated from single MCP TypeScript SDK 1.x package to 2.x split peers (`client`/`server`/`core`/`node`/`express`), dropped zod 3, changed handler context / `setRequestHandler` args. **Wire (`ui/*`) remains compatible with 1.x** | High |
| **ADK Python v2.9.0** (2026-09-10) | Failed workflow nodes re-execute on resume (no completion replay → make node bodies idempotent); GCS tool local paths restricted under `local_file_root`; `InMemorySessionService` raises `SessionNotFoundError` on append to unowned session | High |
| **A2UI `web_core` / `lit` 0.11.0** (2026-09, v0.9 track) | Invalid numeric literals throw `A2uiExpressionError` instead of `NaN`; basic catalog moved to `web_core`; **Shadow DOM → Light DOM** (#2204, 0.10.4 unpublished). Production spec v0.9.1 version unchanged | Medium |
| **UCP v2026-08-25 protocol release** (2026-08-25) | Structural refactoring for multi-vertical expansion (moved Payment constructs / common types to `common/`, reorganized domain verticals), Location Search + Lookup capabilities, request constraints + PAN/Network Token credential type split, vertical-agnostic token binding, transition & deprecated schema cleanup. **Major breaking release with 7 `!` commits** | High |
| **ADK Python v2.7.0: split `pyarrow` out of `gcp` extra** (2026-08-13) | Moved `pyarrow` to new `bigquery-analytics` extra. `BigQueryAgentAnalyticsPlugin` users must explicitly install `google-adk[bigquery-analytics]` | Medium |
| **AG-UI `aws-strands` TypeScript CORS opt-in** (2026-08, `fix(aws-strands)!`) | TS adapter no longer allows CORS with credentials by default, matching Python auth parity. Affected integrations must review CORS config. No protocol event spec incompatibility | Medium |
| **ADK JS v2.0.0** (2026-08-21) | Major bump. Made situational subsystems optional peers (reducing installed packages 591 → 172). Explicit install required when using those subsystems | Medium |
| **A2UI v1.0 (Candidate) `callableFrom` → `allowedCallers` rename** (#2238, 2026-08) | Incompatible schema rename on v1.0 dev track; production v0.9.1 users unaffected | Medium |
| **GenAI Toolbox Spanner `execute_sql_dql` → `execute_sql_readonly` rename** (#3776, v1.9.0) | Spanner tool rename; callers must migrate to new name | Low |
| **MCP 2026-07-28 spec GA — statelessness finalized** (tagged 2026-07-28) | Removed initialize handshake and moved to per-request meta (SEP-2575), removed `Mcp-Session-Id` (SEP-2567), server-initiated requests → MRTR (SEP-2322), replaced `resources/subscribe` → `subscriptions/listen`, renamed `MetaObject`, removed `ping`/`logging/setLevel`, error code `-32002`→`-32602`, **deprecated HTTP+SSE transport**. Promoted from RC to **official release**, making connection-model migration concrete work | High |
| **ADK Python v2.6.0 artifact namespacing + required LangGraph runtime** (2026-07-30) | Namespaced file artifacts per app (f72f0db) — breaks compatibility with existing artifact paths. Required patched async LangGraph runtime and updated graph field types (551372b). Also excluded LangGraph releases containing unsafe checkpoint loading from dependencies | High |
| **Removed `surfaceProperties` from A2UI v1.0 spec** (#2126/#2129, late 2026-07) | Incompatible field removal from v1.0 (dev track) schema. Also renamed transport format term to `direct_json` (#2130) and restricted default input/output modes to valid MIME types (#2097) | Medium |
| **AG-UI crewai integration dependency boundary change** (`ag-ui-crewai@0.2.1`, 2026-07-28) | Pinned crewai to `>=1.0,<2` and moved `crewai-tools` to optional `[tools]` extra. No protocol event spec incompatibility, but crewai 0.x users cannot update the integration | Medium |
| **ADK Python rejected `base_url`/`extra_body` in `generate_content_config`** (main, unreleased 2026-07) | Passing `base_url`/`extra_body` to `generate_content_config` is rejected to close accidental external exfiltration paths; affected configs must migrate (`http_options.extra_body` remains allowed) | Medium |
| **ADK Python v2.5.0 removed OTel Events API** (2026-07-16) | Removed event logger setup due to OpenTelemetry Events API/SDK deprecation. Telemetry config via Events API is disabled | Medium |
| **UCP promoted `keys[]` to canonical signing key field** (#566, 2026-07-12) | Profile signing key lookup changed; consumers of old field must migrate | Medium |
| **ADK Python telemetry metrics removed/renamed** (main, unreleased 2026-07) | Removed `gen_ai.agent.workflow.steps` / `gen_ai.agent.{request,response}.size` and renamed duration metrics to GenAI semconv names. Review existing OTel dashboards and alerts | Medium |
| **UCP normalized namespace authority binding** (#530, 2026-07-03) | Tightened binding procedure from declared schema URL → reverse-domain authority (requires https, rejects userinfo, requires registered domain). Resolved contradictory normative text; existing implementations must verify compliance | Medium |
| **ADK Go v2.0.0** (2026-06-30) | Changed module path `google.golang.org/adk` → `/v2`, required `context.Context` on `session.NewEvent`, unified ToolContext/CallbackContext into Context, removed `InvocationContext.TriggeredBy()`. Centered on new `workflow` package. 1.x continues maintenance on `v1` branch | High |
| **AG-UI Mastra enabled standard interrupt-outcome by default** (#2059, unreleased main) | `emitInterruptOutcome` now defaults to TRUE (opt-out). **Requires CopilotKit client >= 1.61.2** (older clients leave runs stranded) | Medium |
| **ADK Python Anthropic effort/thinking config** (main, 2026-06-29 onward) | With `AnthropicGenerateContentConfig`, temperature/top_p/top_k/stop_sequences/max_output_tokens—previously ignored on Claude—now propagate to the client, and `max_output_tokens` overrides the default `max_tokens=8192` | Medium |
| **ADK JS v1.3.0** (2026-06-22) | Officially released post-v1.2.0 main work: Skills Registry trilogy, OpenAPI REST tool part 3, integrations package, `--reload_agents`. **Breaking**: dev server default port 8000 → 8080 (#439), Agent Engine deploy target GCR → Artifact Registry (#441) | High |
| **UCP expanded fulfillment methods to catalog** (#507, 2026-06-26) | `feat!` composed fulfillment into catalog surfaces (search/lookup/get_product), opened checkout `type` enum to open vocabulary, unified destinations to a single shape. Migrate to method-first discovery | Medium |
| **Added AG-UI .NET SDK + `langgraph>=0.6.0`** (release/2026-06-24) | Added full C#/.NET SDK (0.1.0-preview) (#1963). LangGraph structured interrupt/resume support requires **`langgraph>=0.6.0`** (opt-in, default off, #1945) | Medium |
| **ADK Python v2.3.0** (2026-06-19) | Merged next 2.x release to main. **SECURITY: Fixed Code Generation Template Injection via Filenames**, preserved JSON-native types in A2A `_serialize_value()`, supported tuple tool parameters, fixed LiteLLM Claude thinking blocks, rolled back instruction util refactor (broke internal customers) | High |
| **GenAI Toolbox v1.5.0** (2026-06-19) | **Security-hardening release**: `source/http` SSRF guard (#3448), cloudhealthcare pageURL SSRF prevention (#3453), bigquery dataset restriction bypass prevention (#3452), fail on simultaneous MCP auth + `enable-api` (#3435). Features: MySQL `show-query-stats` / `list-all-locks` (#2954), HTTP URL parameter binding (#3112) | High |
| **AG-UI package releases** (release/2026-06-19) | `@ag-ui/a2ui-middleware` 0.0.10, `@ag-ui/aws-strands` + `ag_ui_strands` 0.2.1, `@ag-ui/langgraph` + `ag-ui-langgraph` 0.0.42. Ported A2UI sub-agent rendering tool to ADK (OSS-158), set `google-adk` floor to 1.28.1 and allowed `<3.0` (removed `<2.0` cap) | Medium |
| **Removed A2UI v1.0 Text component heading variants** (#1668, 2026-06-17) | `spec(v1.0)!` removed redundant heading variants from Text component (backward-incompatible). Also tightened and consolidated v1.0 catalog JSON Schema restrictions (#1629) | Medium |
| **UCP buyer consent per-segment** (#451, 2026-06-12) | `feat!` made buyer consent extensible per segment, breaking backward compatibility. Bundled delegated identity providers + accelerated IdP flow (#423) | Medium |
| **A2UI v0.10 → v1.0 spec promotion + inline catalog instructions** (#1590, 2026-06-12) | Next spec promoted to `specification/v1_0`. Changed catalog instructions from relative file URIs to inline Markdown (BREAKING) and removed `instructions.md` | Medium |
| **ADK Python telemetry metrics unit change** (main, 2026-06-13) | Changed agent / tool execution duration metrics from milliseconds → seconds. Review existing OTel dashboards and alert thresholds | Medium |
| **ADK Python v2.2.0** (2026-06-04) | Google GenAI SDK v2.0.0 support, AutoTracingPlugin, RubricBasedMultiTurnTrajectoryEvaluator, batch of security fixes (path traversal / Zip Slip / unpickle restriction / CVE-2026-48710) | High |
| **ADK JS v1.2.0** (2026-06-03) | Incorporated post-v1.1.0 security fixes (CORS, OAuth2 SSRF, host restriction). Subsequent main has Skills Registry trilogy + streaming prototype pollution fix | High |
| **GenAI Toolbox v1.4.0** (2026-06-04) | Data Lineage integration, `--ignore-unknown-tools`, identifier injection prevention / mandatory opaque token issuer / separated OAuth verification (security) | Medium |
| **A2UI v0.10 `theme` → `surfaceProperties`** (#1525, 2026-06) | BREAKING rename + removed `primaryColor`. v0.10 also made `surfaceId` globally unique per client session (#1543) | Medium |
| **A2UI v0.10 MIME change** (#1493, 2026-06) | Changed mime type to `application/a2ui+json` per IANA convention (POTENTIALLY BREAKING). Affects content-type checks in existing A2UI-over-HTTP / MCP clients | Medium |
| **MCP-Apps v1.7.4 mandatory PKCE** (#681, 2026-06-04) | Required PKCE and bound `redirect_uri` in `lazy-auth-server` token exchange (security hardening). Legacy non-PKCE flows are rejected. Also supported base-path mounting (#683) | Medium |
| **ADK Go v1.4.0** (2026-05-29) | Context unification (internal merge of tool context into callbackContext), `adka2a` structured error propagation, migrated examples / CLI to `a2a-go/v2` SDK, accepted metadata-only SSE chunks to prevent stream aborts | High |
| **GenAI Toolbox v1.3.0** (2026-05-21) | `cloud-sql-admin-execute-sql-many` / `sql-many` bulk tools, SQLCommenter (client metadata emission), MCP auth tool-level scopes validation, HTTP tool path traversal prevention (security) | Medium |
| **GKE MCP v0.13.0** (2026-05-28) | Expanded k8s resource operation tools (apply / get / describe / patch / delete / logs / rollout / auth / api-resources / cluster-info / events), install checksum verification, CI check preventing insecure `pull_request_target` | Medium |
| **Google Analytics MCP 0.6.0** (2026-05-21) | Officially released subprocess stdio handle inheritance prevention (resolving follow-up deadlock from v0.4.0 #151, #154) | Low |
| **ADK Python v2.0.0 GA** (2026-05-19) | Major promotion v1.x → v2.0. Multi-Agent Workflow Engine / Flexible Execution Graphs / Intelligent Task Delegation / Native Inter-Agent Routing reached production-grade GA. Main branch transitioned to v2.0.0. v1.34.0 continues as LTS. Recent HEAD repointed v2 release workflows to `v1` branch | High |
| **ADK Go v1.3.0** (2026-05-20) | Batch release of Live bidirectional streaming core features (session resumption / streaming tools / audio cache), `a2a-go/v2` compatibility, VertexAI MemoryBank support, `gen_ai.usage` attribute rename (OTel alignment) | High |
| **Agent Starter Pack maintenance mode** (2026-05-21) | **Officially surfaced maintenance mode** in README and pushed migration to successor `agents-cli` (#967). New projects should use `agents-cli` | High |
| **UCP loyalty extension** (#340, post-v2026-04-08) | Added loyalty extension to catalog / cart / checkout capabilities; 2nd official extension after discount | Medium |
| **UTCP v1.0** (newly tracked, latest commit 2026-05-05) | Structural alternative to MCP (agent calls native endpoints directly), completely redesigned to a plugin architecture | Medium |
| **Visa Trusted Agent Protocol** (newly tracked, `payments/`) | Agent identity / authorization standard in agentic commerce; cryptographic signature-based | Medium |
| **Mastercard Verifiable Intent v0.1.0** (newly tracked, open-sourced 2026-03-05, `payments/`) | Verifies user → agent delegation scope via SD-JWT chain; privacy-preserving via Selective Disclosure | Medium |
| **Gemini Cloud Assist MCP v0.8.0** (newly tracked, 2026-04-21) | Overhauled from Local Node.js → Remote MCP Server; v0.2.0 (local) fully deprecated | High |
| **ADK Python v1.34.0** (2026-05-18) | `a2a` persistent task stores, Gemini Live API in ADK evaluate, mTLS Cloud Telemetry exporter, `GCPSkillRegistry` / Skill Registry implementation, `McpToolset` OAuth PKCE | High |
| **ADK Python v1.33.0** (2026-05-08) | `BufferableSessionService`, `LlmResponse` function call/response helpers, `ApigeeLlm` credential injection, `adk web` hot reload | Medium |
| **GenAI Toolbox v1.2.0** (2026-05-07) | Cloud Storage source write/copy/move/delete, HTTPS/TLS listener, BigQuery `maximumBytesBilled`, Knowledge-catalog DQ Scans search | Medium |
| **MCP SEP-2567/SEP-2575** (post-2025-11-25) | Sessionless MCP via Explicit State Handles + Make MCP Stateless — major spec shift toward statelessness | High |
| **ACP post-v2026-04-17 #429 (UCP)** | UCP profile schemas validation fix is breaking; existing implementations must re-validate | Medium |
| **UCP post-v2026-04-08** | Identity Linking OAuth 2.0 foundation, capability-driven scopes (breaking), profile schemas validation fix (#429, breaking) | High |
| **MCP-UI v7.1.1** (2026-05-09) | Cancelled sandbox proxy iframe timeout to stabilize StrictMode; pairs with v7.1.0 `hostInfo`/`hostCapabilities` props | Medium |
| **ADK Python v1.32.0** (2026-04-30) | Security fixes (SSRF / RCE / credential isolation), Anthropic thinking blocks, native OTel agentic metrics | High |
| **GKE MCP v0.12.0** | Anthropic Claude ADK adapter, node pool management tools, new cluster tools | Medium |
| **Google Analytics MCP 0.5.0** | Conversions schema/spec tools; v0.4.0 fixed tool call deadlocks and added `run_funnel_report` tool and ADK Skills | Medium |
| **AP2 v0.2.0** (2026-04-28) | Official V2 spec release; first major update in 7 months since v0.1.0 | High |
| **gcloud-mcp storage-mcp v0.6.0** (2026-05-06) | Removed `download_object_safe` tool (breaking change). Must migrate to destructive `download_object` or `read_object_content` / `read_object_metadata` | Medium |
| **ADK JS v1.0.0 → v1.1.0** | Added `UrlContextTool`/`Vertex AI Search Tool`, fixed MCP prefix stripping, `AgentTool` session reuse | Medium |
| **ADK Go v1.2.0** | Agent Engine integration, Skill Source proxies, `SkillToolset` implementation, `stream_query` simple text support | Medium |
| **UCP v2026-04-08** | 6 breaking changes: variant options rename, webhook separation, error unification, required currency, etc. | High |
| **GenAI Toolbox v1.0.0** | Elasticsearch vector search refactor, Looker tool split | High |
| **GenAI Toolbox v0.32.0** | Repository name update | High |
| **GenAI Toolbox v0.31.0** | `enable-api` flag mandatory, removed deprecated items | High |
| **A2A v1.0.0** | Consolidated Push Notification Config, `blocking`→`return_immediately`, spec refactor | High |
| **MCP-UI v7.0.0** | Complete removal of legacy specification | High |
| **ACP v2026-01-30** | Introduced Payment Handlers Framework | High |
| **MCP-Apps v1.7.0** | WebMCP-style tool registration spec, Zod jitless by default | Medium |
| **x402** | Main repository moved to foundation repo | Medium |
| **ADK Python v1.29.0** | `SecretManagerClient` package move | Medium |
| **Google Analytics MCP** (unreleased) | Package renamed to `analytics-mcp` | Low |

### Major Updates

**Verified 2026-10-13**

- **GenAI Toolbox v1.14.0**: Included Spanner Omni, Looker explore, and BigQuery authorized views in public release. Authorization centralization (#4254) is on subsequent unreleased HEAD
- **A2UI Python SDK v0.8.0 / core v0.3.0**: Changed parser types and catalog API. Blueprint API redesign is on unreleased HEAD, so migrate separately
- **AG-UI adapter / .NET updates**: Mastra 2.0.1, Claude Agent SDK adapter 0.0.6 / 0.2.1, .NET 1.0.1. Mastra removed legacy interrupt APIs; Claude adapter stopped implicitly loading host settings
- **Knowledge Catalog mdcode**: Adopted named deployments, sidecar profiles, and strict entity sources. Config changes on untagged HEAD

**— 2026-09-22 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: AG-UI 1.0** (2026-09-17) - Spec freeze + 1.0.0 SDKs (TS/Py/.NET). `THINKING_*` → `REASONING_*`, `InputContent` → `ContentPart`, `RUN_FINISHED.outcome`, subagent events, `ACTIVITY_*`, HTTP+Protobuf binary wire. 0.x agents work with 1.0 clients (compatibility boundary + `DEPRECATIONS.md`)
0. **NEW: ADK JS v2.1.0** (2026-09-15) - Formally released 90 commits after v2.0.0. Chrome Prompt API BaseLlm, `ContainerCodeExecutor`, `VertexAiRagMemoryService`, PKCE S256, SSRF/DNS-rebinding hardening
0. **NEW: ADK Python v2.9.1 / v2.9.2** (2026-09-15 / 09-18) - v2.9.1 adds Claude adaptive thinking (visible thoughts); v2.9.2 preserves OTel event names. HEAD adds `OpenAILlm` `api_key`/`base_url`, `tool_config` mode, and stronger Chat Completions parsing
0. **NEW: GenAI Toolbox v1.12.0** (2026-09-17) - OpenAI Apps challenge endpoint, looker `certification_metadata` / embed parameters, bigtable prebuilt config, connect sources on first use
0. **NEW: Knowledge Catalog mdcode Agent Skill generation** (2026-09) - Generates Agent Skills (`SKILL.md` + `references/`) from semantic models. 8 BREAKING changes including removal of `kcmd` `agent-tools` / `action-run` / `action-list`
0. **NEW: MCP Skills extension published** (2026-09) - SEP-2640 Final; Skills Over MCP WG maintains official Skills extension (`io.modelcontextprotocol/skills`)
0. **NEW: A2UI `web_core` recursion guard + MCP catalog functions** (2026-09) - Guarded excessive recursion in DynamicValue resolution (prevents CWE-674); MCP result processing functions (`jmespath`/`split`/`regexCapture`/`regexReplace`/`updateDataModel`)
0. **NEW: `webmcp-tools` demo SECURITY hardening + BestPrice.gr** (2026-09) - DOMPurify sanitization across demos, DOM XSS/DoS mitigations, sandboxed iframes. Added BestPrice.gr production site
0. **NEW: ADK Go web server SECURITY hardening** (2026-09) - Bound web server to loopback by default; adkrest rejects DNS-rebinding hosts and cross-origin browsers

**— 2026-09-15 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: MCP-Apps v2.0.0** (2026-09-08) - Migrated to MCP TypeScript SDK 2.x. **Wire compatible with 1.x**; TS API / peers are breaking (zod 4.2+, split peers, handler context changes). Migration guide `docs/migrate-to-2.md`
0. **NEW: ADK Python v2.9.0** (2026-09-10) - **`FallbackModel`** / **LiveKit runner** / YAML graph load / MCP SDK 2.x coexistence. Breaking: failed node re-execution on resume, GCS local paths restricted to `local_file_root`, `SessionNotFoundError` for in-memory sessions
0. **NEW: ADK Go v2.4.0 / v1.7.0** (2026-09-11) - **adkrest authentication & authorization**, full application of OpenAI stream / generation config, `session.ErrNotFound`, `ParallelWorker` fail-fast
0. **NEW: GenAI Toolbox v1.11.0** (2026-09-10) - **MCP Apps** / **MCP Resources** / `groups/list` & `groups/get` extensions; HTTP SSRF guard blocks IETF protocol assignments range
0. **NEW: MCP SEP-2640 Skills Over MCP Finalized** (#2640) - Formalized SEP integrating Agent Skills as an MCP extension. No version bump to 2026-07-28 spec text
0. **NEW: A2UI `web_core` / `lit` 0.11.0** (2026-09) - Light DOM migration + breaking expression parser errors, `SkillGenerator` API, UI resource resolution in MCP catalog
0. **NEW: AG-UI MCP Apps middleware + mastra 1.1.4 / strands 0.4.0 / Java 0.1.1** (release/2026-09-08 to 09-14) - Added `@ag-ui/mcp-apps-middleware@0.1.1`; no breaking changes to core event spec
0. **NEW: 90 commits after ADK JS v2.0.0** (2026-09, no new tag issued) - Chrome Prompt API BaseLlm, `ContainerCodeExecutor`, `VertexAiRagMemoryService`, Origin validation / A2A SSRF / PKCE S256
0. **NEW: Knowledge Catalog mdcode actions / constraints / AlloyDB** (2026-09) - Derives agents / tools from semantic models; judge adjudicates guards by reading model's own tables

**— 2026-08-31 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: UCP v2026-08-25 protocol release** (2026-08-25) - Multi-vertical expansion (Location Search + Lookup, request constraints, 3DS2 security, independent capability versioning, grocery readiness). **Lodging TC formed** (Amadeus / Booking.com / Expedia / Google / Hilton / Marriott / Trip.com) in the same month
0. **NEW: Added AG-UI subagent lifecycle to protocol** (#2350, 2026-08) - Propagated `SUBAGENT_*` events + `subagentRunId` attribution across core/client/Python/protobuf/.NET/langgraph; **metadata on every event/message** (PNI-198). **Java SDK 0.1.0**, TS SDK 0.0.59, Python protocol 0.1.21, 5 new TS integrations (crewai/ag2/agno/llamaindex/pydantic-ai)
0. **NEW: ADK JS v2.0.0** (2026-08-21) - Major release. Optional peers cut install from 591 → 172 packages, typed-errors port, ReflectAndRetry plugins, RoutedAgent/RoutedLlm graduated
0. **NEW: ADK Python v2.7.0 / v2.8.0 + lts v1.39.x** (2026-08-13 / 08-25 / 08-27) - v2.7.0 is a correctness release (model capability declaration / media-returning tools / Jinja2 templates). v2.8.0 adds **Model Armor guardrail plugin** / **`FallbackModel`** / YAML graph workflows
0. **NEW: ADK Go v2.2.0 / v2.3.0 + v1.6.0** (2026-08-10 / 08-31 / 08-11) - **Context compaction suite** (invocation summarization / mid-invocation compaction / durable facts), credentials-service REST client, `gen_ai` content attributes
0. **NEW: Published MCP next spec release roadmap** (#3290) - 5 priority areas (agentic messaging / HTTP-native transport consolidation / agent identity & enterprise security / improved primitives / SDK DX). Enterprise IG charter, Rust SDK promoted to Tier 1
0. **NEW: GenAI Toolbox v1.9.0 / v1.10.0** (2026-08-14 / 08-27) - FalkorDB source, **MCP Secure Parameters experimental extension**, source read-only mode, AlloyDB Advanced Query Insights, `toolbox.v1` extension (v20260728)
0. **NEW: 4 MCP Security releases under per-server tag scheme** (2026-08-27) - **SCC v2 API migration** (`scc-v0.1.1`), `secops-v0.7.1`, `gti-v0.1.3`, `secops-soar-v0.1.2`
0. **NEW: `webmcp-tools` v0.0.4** (2026-08-28) - Renamed evals-cli to `webmcp-evals`, tool abort support, WebMCP Kit / WindTunnel
0. **NEW: Full A2UI Swift SDK implementation** (2026-08) - Basic Catalog schemas / SwiftUI components / conformance harness / core validation & reactivity. `web_core` added node layer + `Catalog.fromJson` ingestion engine

**— 2026-08-01 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: MCP 2026-07-28 spec GA** (2026-07-28) - **Official release of stateless protocol generation**. `server/discover` / `subscriptions/listen` / per-request `_meta`; HTTP+SSE deprecated. Promoted to default docs version; examples updated to SDK v2 (`mcp 2.0.0`)
0. **NEW: ADK Python v2.6.0 / v2.6.1** (2026-07-30 / 07-31) - CLI telemetry infra, **OCI Generative AI provider** (#5069), `ReflectAndRetryModelPlugin`, **supply-chain protection via published constraints files** (75c773e). Breaking: per-app artifact namespacing + required patched async LangGraph runtime
0. **NEW: ADK JS v1.5.0** (2026-07-30) - Formally released security improvements including **mandatory auth when mounting A2A server** (#529) and Python parity tools (`EnterpriseWebSearchTool` / `getUserChoiceTool`, etc.)
0. **NEW: GenAI Toolbox v1.8.0** (2026-07-28) - Formally tagged skills generation improvements / groups / Looker tools / SSRF guard (#3625). Immediately followed on main by Bigtable admin tools (#3596) / `/healthz` (#3060)
0. **NEW: GKE MCP v0.15.0** (2026-07-28) - Formally tagged `query_prometheus` / `query_traces` / evals mock infra; safety checks on `delete_cluster` (#481)
0. **NEW: AG-UI Claude Managed Agents integration** (release/2026-07-31) - New integration across 3 languages: TS / Python / .NET (#2247); full crewai 1.x support (`ag-ui-crewai@0.2.1`)
0. **NEW: Google Analytics MCP 0.7.0** (2026-07-29) - Maintenance release including upper bound on `mcp` dependency (#200)

**— 2026-07-27 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: ADK Go v2.1.0 / v1.5.1** (2026-07-23 / 07-22) - Highlights: **OpenAI support** (#1178) and **BigQuery Agent Analytics Plugin** (#738). Multi-module Go CI support; fixed `parallelagent` waiting for early-stop teardown (#1186)
0. **NEW: ADK JS v1.4.0** (2026-07-20) - **Anchored Iterative Summarization** (context compactor, #470), **`GlobalInstructionPlugin`** (adk-python parity, #507), **ported `LoopAgent` live streaming to TS** (#504), Trie branch matching (#509). Also fixed message-part replacement on Artifact save (#515)
0. **NEW: MCP-Apps v1.7.5** (2026-07-23) - Tagged ext-apps 1.7.5 (#724). Fixed experimental capability setting retention (#721); reduced npm audit findings 15→3 (#725)
0. **NEW: AG-UI release/2026-07-22 + `ag_ui_strands@0.2.3`** - **Added AG-UI Java (`ag-ui-4j`) core client/server** (#2057), strands-py session reconcile (OSS-563), mastra responses msg-id sanitize (OSS-381), raw event opt-out (OSS-607), fixed CORS credentialed wildcard (#2204)
0. **NEW: ADK Python v1.36.2 (stable lts) + 76 commits on main** (2026-07-21) - **SECURITY: Prevented tool confirmation continuation forgery** / rejected `base_url` and `extra_body` in `generate_content_config`. **Eventarc Advanced toolset**, telemetry consent endpoint, audio user simulator + eval samples. v2.x stays at v2.5.0
0. **NEW: UCP `policies[]` + extension-defined Actions + shopping permalink (unreleased)** - Added `policies[]` to cart/checkout/catalog/order (#572), extension-defined Actions primitive (#582), shopping permalink capability (#523). Fixed authority binding exact name-host match (#627)
0. **NEW: GenAI Toolbox post-v1.7.0 (unreleased)** - Enhanced skills generation (`--group`/`--name` default/optional description), groups support (#3605), Looker `get_field_value_suggestions` (#3696), **SECURITY: SSRF guard blocks CGNAT `100.64.0.0/10` (#3625)**
0. **NEW: GKE MCP `query_prometheus` tool (unreleased)** - Added PromQL metric query tool (#471) + expanded evals mock infra (#468/#472/#482)
0. **NEW: A2UI v1.0 RC continued + Swift SDK** - Required `value` / enforced `null` deletion in `updateDataModel` (#2068), Atom Inference Format (#2056), Swift SDK core engine implementation, **SECURITY: `web_core` `DataModel` prototype pollution protection (#2085)**
0. **NEW: Knowledge Catalog migrated to OKF v0.2** (#227) - Updated Open Knowledge Format to v0.2

**— 2026-07-18 Updates (Tracking Submodule Remote HEAD) —**

0. **NEW: MCP 2026-07-28-RC draft moving to statelessness** - At RC/draft stage, major breaking changes landed: removing initialize handshake, removing sessions, `server/discover`, `subscriptions/listen`, MRTR (removing server-initiated requests) (SEP-2575/2567/2322). Pre-finalization, but watch for fundamental connection-model changes
0. **NEW: ADK Python v2.5.0** (2026-07-16) - ManagedAgent (`single_turn`/remote MCP), Skill/Agent Registry (`GCPSkillRegistry`), Workflow resumability/HITL, pervasive mTLS. **Breaking**: removed OTel Events API. Shares Multi-Agent Workflow GA track with `adk-go` v2.0.0
0. **NEW: GenAI Toolbox v1.7.0** (2026-07) - ArcadeDB source/tools, expanded Dataplex data-product tools, ClickHouse native vector embedding, `quotaProject` support. No breaking changes
0. **NEW: A2UI v1.0 RC accelerating** (2026-07, 71 commits) - Synchronous client→server RPC / `callFunction` / bulk `createSurface` generation. **Breaking (v1.0 RC vs v0.9)**: `theme`→`surfaceProperties`, MIME `application/a2ui+json`, catalog `functions` as map. Production remains v0.9.1
0. **NEW: Post-ADK Go v2.0.0 / post-ADK JS v1.3.0 (unreleased)** - Go: `agentregistry` package + provider auth + MCP per-request auth (+24 commits). JS: Gemini Interaction API (#364) + Agent-Controlled Compaction (#477) + Skills Registry + OpenAPI REST tool (+28 commits)
0. **NEW: Cloud Run MCP Docker Compose deploy (unreleased)** - Direct deploy to Cloud Run from compose definitions via `deployCompose` capability, supporting volumes/Secret Manager/AI models and Cloud Build integration (#252, etc.)
0. **NEW: UCP promoted `keys[]` (breaking, #566, 2026-07-12)** - Canonicalized profile signing key field. Also Web Bot Auth interop + per-operation Requirement column
0. **NEW: OpenResponses WebSocket transport + compaction** - WebSocket mode on `/v1/responses` (#71/#72), `POST /v1/responses/compact` (#68), introduced date-based spec versioning (#77)
0. **NEW: `webmcp-tools` v0.0.3** (2026-07-17) - `execute_batch` "Code Mode" for Page Agent (#287), WebMCP Polyfill (#276), Gemini/Ollama in Backend (#294)

**— Records Prior to 2026-07-10 Below —**

0. **NEW: Tagged ADK Python v2.4.0 / v1.36.1** (2026-07-07 / 07-06) - Tagged on release branch (CHANGELOG not yet reflected in mirror main; full breakdown in next window). Main side has +67 commits including Workflow as Tool / ManagedAgent / DaytonaEnvironment / expanded mTLS / cross-user artifact prevention & DNS rebinding protection (security)
0. **NEW: GKE MCP v0.14.0** (2026-07-06) - `verify_unused` cluster safety check skill / TPU dynamic slices monitoring & management skill / `query_logs` View parameter (`BASIC|FULL`). Dependencies updated to `adk` 1.5.0 and `adk-anthropic-go` 1.0.0 (major)
0. **NEW: AG-UI `mastra@1.1.0/1.1.1` release** (2026-07-02 / 07-03) - Officially tagged Mastra interrupt/resume work. Observational Memory as activity events (OSS-92), shared-state remote parity (OSS-414), `tracingOptions` passthrough (#2083). `sdk-dotnet` `AGUI.*` 0.0.3 (NuGet release support) in same window
0. **NEW: UCP Web Bot Auth interop + namespace authority binding** (2026-07-02/03) - Added EdDSA (Ed25519) as optional signing algorithm (MUST when WBA interop selected, #483); normalized schema URL → RDNS authority binding procedure (#530)
0. **NEW: ADK Go v2.0.0** (2026-06-30) - **Major release**. Changed module path `google.golang.org/adk` → `/v2` (breaking). Introduced `workflow` package (scheduler-based goroutine-per-node execution engine, HITL pause/resume & handoff/re-entry modes, JoinNode fan-in; massive 547-file squash, #1109). Simultaneous breaking changes: mandatory context on `session.NewEvent`, unified ToolContext/CallbackContext, removed `InvocationContext.TriggeredBy()`. 1.x continues maintenance on `v1` branch; v1.5.0 also released just prior on the same day
0. **NEW: GenAI Toolbox v1.6.0** (2026-06-30) - **Added MCP 2026 draft spec support** (#3544, `--enable-draft-specs` opt-in, official release provisionally scheduled 2026-07-28). **Integrated Kokoro code signing into release workflow to digitally sign binaries** (#3528, addresses issue #996). Expanded Dataplex data-product tools (#3499, #3500); fixed GDA client mTLS/CAA support (#3460). No breaking changes
0. **NEW: AG-UI Mastra interrupt/resume overhaul** (main, 2026-07-01, unreleased) - Native `useInterrupt` suspend/resume, standard interrupt-outcome enabled by default (**breaking, CopilotKit client >= 1.61.2 required**, #2059), remote agent resume support, background tasks as activity events, progressive streaming of tool-call args. No new release tags issued
0. **NEW: ADK JS v1.3.0** (2026-06-22) - Officially released post-v1.2.0 main work: **Skills Registry trilogy** (Core + GCP remote + dynamic `SearchSkillsTool`, #422-424), **OpenAPI REST API tool (part 3, #386)**, **new `integrations` package (#449)**, **`--reload_agents` hot-reload (#304)**, **Gemini 2.5/3.x Live Models (#409)**. Security: streaming prototype pollution fix (#410). **Breaking**: default dev server port 8000 → 8080 (#439), Agent Engine deploy target GCR → Artifact Registry (#441)
0. **NEW: Added AG-UI .NET SDK + langgraph structured interrupt/resume** (release/2026-06-24) - **Added full C#/.NET SDK (0.1.0-preview)** (#1963): `AGUI.Abstractions` / `.Formatting` / `.Client` / `.Server` / protobuf transport / OTel tracing / cross-language test harness. **Structured interrupt/resume** in langgraph (opt-in, requires `langgraph>=0.6.0`, #1945), DeepSeek `reasoning_content` support (#1256), stable messageId reuse (#1317). `ag_ui_adk` 0.7.0 / `aws-strands` 0.2.3
0. **NEW: ADK Python v2.3.0** (2026-06-19) - Merged next 2.x release to main. Highlight: **SECURITY: Fixed Code Generation Template Injection via Filenames**. Preserved JSON-native types and container recursion in A2A `_serialize_value()`, tuple tool parameters support, Pydantic model handling in `safe_json_serialize`, LiteLLM Claude thinking blocks (`display:"omitted"`) fix, `file_data` URI refs in `GcsArtifactService`, placeholder / nested path matching fixes in `instructions_utils` (rolled back instruction util refactor breaking internal customers)
0. **NEW: GenAI Toolbox v1.5.0** (2026-06-19) - **SSRF guard hardening release** (#3379). `source/http` SSRF guard (#3448), `source/cloudhealthcare` `pageURL` validation (#3453), `bigquery-execute-sql` dataset restriction bypass prevention (#3452), fail on simultaneous MCP auth + `enable-api` (#3435), `InitializeConfigs` panic → error (#3397). Features: MySQL / Cloud SQL MySQL `show-query-stats` / `list-all-locks` (#2954), HTTP transport URL parameter binding (#3112), Spanner `readOnly` annotation (#3338)
0. **NEW: AG-UI package releases** (release/2026-06-19) - `@ag-ui/a2ui-middleware` 0.0.10 / `@ag-ui/aws-strands` + `ag_ui_strands` 0.2.1 / `@ag-ui/langgraph` + `ag-ui-langgraph` 0.0.42. **Ported A2UI sub-agent rendering tool to ADK (OSS-158)**: rendering tool with recovery loop, auto-injected `generate_a2ui` (Strands parity), surface reconstruction on `intent="update"`, `google-adk` floor 1.28.1 / `<3.0` allowed. Progressive A2UI paint in langgraph (inner `render_a2ui` delta stream via native `OnChatModelStream`), A2UI catalog parity + streamed `catalogId` stamp in `aws-strands`, added minimal ADK agent resolver
0. **NEW: Started tracking Knowledge Catalog** (`gcloud/knowledge-catalog`, 2026-06-14) - Added submodule of samples / agents / tools demonstrating **Knowledge Catalog (formerly Dataplex)** AI-powered data catalog capabilities. Centered on **Open Knowledge Format (OKF)** metadata-as-code reference + **ADK-based enrichment agent** (with bundled eval harness, #42 / #28 / #40). Complements GenAI Toolbox's `dataplex` → `knowledge-catalog` rename (#3039) and DQ Scans search tools (#2444) along the "Dataplex renamed to Knowledge Catalog" theme
0. **NEW: ADK Python v2.2.0** (2026-06-04) - Google GenAI SDK v2.0.0 support, AutoTracingPlugin (OTel auto-instrumentation), RubricBasedMultiTurnTrajectoryEvaluator, native `gen_ai.client.*` metrics, enhanced A2A integration (`to_a2a(Workflow)` / metadata retention / `input-required` vs `auth-required`). Security: Agent Builder path traversal / GCS skill Zip Slip / v0 actions unpickle restriction / `delete_session` ownership validation / CVE-2026-48710 (starlette & fastapi bump). LTS side backported Gemini 3.1 Live fixes in v1.35.0 (2026-06-10)
0. **NEW: ADK JS v1.2.0** (2026-06-03) - Officially released post-v1.1.0 security / robustness fixes. Subsequent main has Skills Registry (Core + GCP remote + `SearchSkillsTool`, #422-424), OpenAPI parser/auth handler part 2 (#385), and streaming prototype pollution fix (#410)
0. **NEW: GenAI Toolbox v1.4.0** (2026-06-04) - Data Lineage integration (#3285), `--ignore-unknown-tools` (#3353), Cloud SQL PG vector assist tools (#3203), Spanner `search_catalog` (#3140), `windows/arm64` distribution. Security: identifier injection prevention (#3219), mandatory opaque token issuer (#3360), separated Google/Generic OAuth verification (#3341), Looker filter escape (#3289)
0. **NEW: ADK Go v1.4.0** (2026-05-29) - Centered on Context unification (internal merge of tool context into callbackContext: #871, #868), plus `adka2a` structured error propagation (#874), migration of examples / CLI launcher to `a2a-go/v2` SDK (#780), accepting metadata-only SSE chunks in `StreamingResponseAggregator` (continues stream without aborting: #918), and conformance test recording plugin (#890)
0. **NEW: GenAI Toolbox v1.3.0** (2026-05-21) - Officially released `cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` bulk tools (#3083), client metadata emission via SQLCommenter (#3064), MCP auth tool-level scopes validation (#3049), HTTP tool path traversal / base path scope escape prevention (security: #3218), and toolset/promptset boundary enforcement (#3036). Subsequent identifier injection prevention (#3219) / thrift CVE-2026-41602 fix (#3312) were officially released in v1.4.0 (2026-06-04)
0. **NEW: GKE MCP v0.13.0** (2026-05-28) - Batch expansion of k8s resource operation tools: `list_k8s_api_resources` (#378), `patch_k8s_resource` (#387), `get_k8s_rollout_status` (#386), `check_k8s_auth` (#385), `describe_k8s_resource` (#388), `get_k8s_cluster_info` (#379), `get_k8s_logs` (#370), `delete_k8s_resource` (#368). Set default delete cascade policy to background (#376), install checksum verification (#398), CI check preventing insecure `pull_request_target` (#400)
0. **NEW: Google Analytics MCP 0.6.0** (2026-05-21) - Officially released subprocess stdio handle inheritance prevention (#154). Resolves follow-up deadlock from v0.4.0 #151 (tool call deadlock / stdout corruption) fix
0. **NEW: ADK Python v2.0.0 GA** (2026-05-19) - Reached **Google ADK v2.0 General Availability**. Brought Multi-Agent Workflow Engine (Flexible Execution Graphs + Intelligent Task Delegation: parallel sub-agent workers, nested hierarchical teams, resilient dynamic scheduling) and Dynamic Agent Collaboration (Native Inter-Agent Routing: messaging / control state handoffs / context propagation) to production-grade. Transitioned main branch to v2.0.0. Released via alpha (a1–a3) and beta (b1)
0. **NEW: ADK Go v1.3.0** (2026-05-20) - Batch release of Live bidirectional streaming core features: session resumption (#837), streaming tools (#836), audio cache for save artifact (#838), sequential agent live run (#835), live example (#834), core bidirectional streaming (#833). `a2a-go/v2` support, VertexAI MemoryBank support, user auth propagation fix (`adka2a` compat)
0. **NEW: Agent Starter Pack maintenance mode** (2026-05-21) - **Officially surfaced maintenance mode** and pushed migration to successor **`agents-cli`** (#967). Google's agent dev tooling strategy effectively migrated to `agents-cli`
0. **NEW: UCP loyalty extension** (#340) - Added loyalty extension to catalog / cart / checkout capabilities. 2nd official extension after discount, broadening commerce protocol extension axes
0. **NEW: UTCP v1.0** (latest commit 2026-05-05, newly tracked) - Universal Tool Calling Protocol. While MCP invokes tools via proxies, UTCP has agents call native endpoints (HTTP/gRPC/WebSocket/CLI) directly after discovery, cutting wrapper tax. Redesigned to plugin-based architecture in v1.0, subsuming MCP itself as a plugin. Official Python / TypeScript / Go implementations
0. **NEW: Created `payments/` directory** - Separated 5 existing commerce protocols (ACP / AP2 / UCP / x402 / Visa-TAP) from `protocols/` into `payments/`, plus newly added Mastercard Verifiable Intent for 6 total. Clarified separation between generic protocols and payment protocols
0. **NEW: Visa Trusted Agent Protocol** (newly tracked, `payments/`) - Cryptographic standard for agent identity / authorization in agentic commerce. AI agents prove identity and user-delegated authority to merchants via cryptographic signatures containing timestamp / session id / key id. Identity complement layer for ACP/AP2/UCP/x402
0. **NEW: Mastercard Verifiable Intent v0.1.0** (open-sourced 2026-03-05, newly tracked, `payments/`) - Co-developed by Mastercard + Google. **SD-JWT (Selective Disclosure JWT)**-based tamper-evident proof of user → agent delegation scope. Two execution modes: Immediate / Autonomous. Based on FIDO/EMVCo/IETF/W3C. Designed to interoperate with AP2 / UCP. Endorsed by Adyen / Worldpay / Fiserv / IBM / Checkout.com / Basis Theory / Getnet
0. **NEW: NLIP 1st edition** (Ecma approved 2025-12-10, newly tracked) - Natural-language application-level protocol standardized by Ecma TC56. 6-document suite: ECMA-430 core + 4 bindings (HTTP/WebSocket/AMQP/Security profiles) + TR/113 explanatory guide. Submitted to ISO (2026-01-25); Claude Skills-compatible reference implementation scheduled 2026-02-28
0. **NEW: Gemini Cloud Assist MCP v0.8.0** (2026-04-21, newly tracked) - MCP server to understand / manage / troubleshoot GCP environments in natural language. Overhauled from Local Node.js to Remote MCP Server architecture (**breaking change**); v0.2.0 (local) fully deprecated. Bundles `designing-and-deploying-infrastructure` / `operating-google-cloud` skills. Currently Private Preview (allowlist)
1. **ADK Python v1.33.0 → v1.34.0 → v2.0.0 GA** (2026-05-08 / 05-18 / 05-19) - 3 releases in short succession. v1.33.0 added `BufferableSessionService`, `LlmResponse` function call/response helpers, `ApigeeLlm` credential injection, and `adk web` hot reload. v1.34.0 added `a2a` persistent task stores, Gemini Live API in ADK evaluate, mTLS Cloud Telemetry exporter, `GCPSkillRegistry` / Skill Registry implementation, and `McpToolset` OAuth PKCE. v2.0.0 GA established production-grade multi-agent workflow engine and dynamic agent collaboration
1a. **ADK Python v1.31.x → v1.32.0** (2026-04-30) - **Previous stable release**. Anthropic thinking blocks, native OpenTelemetry agentic metrics, event compaction tracing, `GcpAuthProvider` 2LO/3LO/API Key samples, ~25% faster cold start, and multiple security fixes (SSRF/RCE/credential isolation/PubSub `user_id` sanitization)
2. **GKE MCP v0.11.1 → v0.12.0** - LLM abstract factory + Anthropic Claude ADK adapter, node pool management tools, giq `fetch_model_servers` / `fetch_profiles`, GKE AI TPU troubleshooting skill
3. **Google Analytics MCP v0.4.0 → 0.5.0** - New conversions schema/spec tools, dependency bumps to `google-analytics-data` v0.22.0 / `admin` v0.29.0. v0.4.0 added `run_funnel_report` tool (Data API v1alpha), Skills for ADK, and fixed tool call deadlocks / stdout corruption
4. **MCP-UI v7.1.0 → v7.1.1** (2026-05-09) - Cancelled sandbox proxy iframe timeout to prevent StrictMode unhandled rejections. v7.1.0 added `hostInfo` / `hostCapabilities` props to `AppRenderer` (2026-05-01)
5. **AP2 v0.1.0 → v0.2.0** (2026-04-28) - **Official V2 spec release**. First major release in 7 months, including `PaymentReceipt`, X402 payment integration, Vertex AI auth, Go sample, UCP integration, etc.
6. **ADK JS v1.0.0 → v1.1.0 + follow-up** - `UrlContextTool` (Gemini 2+ URL context), Vertex AI Search Tool, MCP prefix stripping, `AgentTool` session reuse, Google Maps tool, `VertexRagRetrievalTool`, `MCPToolset.getTools` `toolFilter`
7. **ADK Go v1.2.0 → v1.3.0** (2026-05-20) - Live bidirectional streaming core (session resumption / streaming tools / audio cache / sequential agent live run / live example), `a2a-go/v2` support, VertexAI MemoryBank, `stream_query` simple text support, `gen_ai.usage` attribute rename, user auth propagation fix
8. **ADK Python v1.30.0 → v1.31.1** - v1.31.x added Parameter Manager/Secret Manager user-agent, Firestore, Vertex AI Agent Engine Sandbox, `memories.ingest_events`
9. **ACP v2026-01-30 → v2026-04-17 + follow-up** - Cart Capability, Product Feeds API, Marketing Consent, Markdown Content Specification, Payment Intent, Mandatory Idempotency, etc. Post-release updates continue with Order Schema Post-Checkout (#232), `UpsertProductsResponse` JSON Schema (#241), Meta TSC member (#236), etc.
10. **AG-UI release/2026-04-22** - State Snapshot/Delta compaction (#1535), `AgentCapabilities` Python SDK addition, Strands/Mastra adapter fixes, LFS migration
11. **MCP-Apps v1.7.0 → v1.7.1** - PDF Server lazy form extraction (#639), cross-instance cache sharing (#637), `qr-server` FastMCP host/port support (#372)
12. **OpenResponses + Phase Compaction** - Compact response endpoint and `phase` parameter alongside WebSocket mode implementation
13. **GenAI Toolbox v1.1.0 → v1.2.0** (2026-05-07) - **New minor stable release**. Officially included Cloud Storage source (list/read + write/copy/move/delete), HTTPS/TLS listener, BigQuery `maximumBytesBilled`, and Knowledge-catalog Data Quality Scans search tool. Post-v1.2.0 work underway on MCP auth tool-level scopes validation (#3049), HTTP tool path traversal prevention (#3218, security), etc.
14. **Post-MCP 2025-11-25** - Major shift toward statelessness underway via **SEP-2567 (Sessionless MCP via Explicit State Handles) Final/Accepted promotion** and **SEP-2575 (Make MCP Stateless)**. Security bump to `vm2` 3.11.3 for GHSA-vwrp-x96c-mhwq. MRTR (Multi-Round Tool Result) schema cleanup, rename to `InputRequiredResult`, Augmented Tool Call flow, SDK Working Group charter
15. **Agent Starter Pack v0.41.1 → v0.41.3 (+ maintenance mode)** - `langgraph-prebuilt` pin, announced next-generation project `agents-cli` in v0.41.2 (#952), **officially surfaced maintenance mode and pushed migration to `agents-cli` in #967 after v0.41.3**
16. **Post-UCP v2026-04-08** - **Identity Linking OAuth 2.0 foundation (#354, breaking)**, `attribution` field (#391), expanded `core-concepts` (#336), added Twum Djin to Governance Council
17. **gcloud-mcp storage-mcp-v0.5.1** - Moved `delete_object` to destructive tools (security hardening)
18. **ADP dataset expansion** - Added per-step reward field (#183), CoderForge-Preview, Nemotron Terminal Corpus, Toucan, Toucan-1.5M, mini-coder trajectories, Catalog dataset guidelines (#186), etc.
19. **MCP Security post-secops-v0.7.0** - Added `list_parsers` tool, standardized return types, and added pagination token support (#252)
20. **Cloud Run MCP post-v1.10.0** - Docker compose deployments, BUILD_ID-based scheduled cloudbuild, Cloud Run skills

### New Protocol Integrations

0. **AG-UI MCP Apps middleware** (`@ag-ui/mcp-apps-middleware@0.1.1`, 2026-09) - Middleware connecting MCP Apps into AG-UI event streams; also added `@ag-ui/mcp-middleware@0.0.2` in parallel
0. **MCP Skills Over MCP (SEP-2640, Final)** - Formalized SEP integrating Agent Skills as an MCP extension; spec GA tag itself remains 2026-07-28
0. **UTCP (Universal Tool Calling Protocol)** - Structural alternative to MCP where agents call native endpoints directly without a proxy; existing MCP is subsumed as a plugin and can coexist inside UTCP
0. **Visa Trusted Agent Protocol** (`payments/`) - Agentic commerce identity standard driven by a major financial player (Visa); fills the identity complement axis for ACP/AP2/UCP/x402
0. **Mastercard Verifiable Intent** (`payments/`) - Co-developed by Mastercard + Google; tamper-evident verification of user → agent delegation scope via SD-JWT chain with privacy-preserving Selective Disclosure; forms the other pole of identity standards alongside Visa TAP
0. **NLIP (Natural Language Interaction Protocol)** - Standardized by Ecma TC56, structured as ECMA-430 to 434 + TR/113; complements existing lineup (A2A: opaque agent-to-agent / MCP: agent-to-tool) by handling natural-language application-level communication
0. **Gemini Cloud Assist MCP** - MCP server for natural-language operation of GCP environments (Private Preview); complements the "GCP operational" axis alongside `cloud-run-mcp` / `gke-mcp` / `gcloud-mcp`
0. **Knowledge Catalog** (`gcloud/knowledge-catalog`) - Samples + ADK enrichment agent demonstrating Knowledge Catalog (formerly Dataplex) data catalog / metadata management; handles metadata-as-code with OKF (Open Knowledge Format); complements the "GCP data context" axis alongside GenAI Toolbox's `knowledge-catalog` tools
1. **AP2 v0.2.0** - Official V2 spec release: X402 payments, Vertex AI auth, UCP integration, Go sample
2. **ADK JS + `UrlContextTool` / Vertex AI Search Tool** - Gemini 2+ URL context grounding and Vertex AI Search tool
3. **ADK Go + Agent Engine** - Agent Engine integration, updating existing instances, automatic session ID generation
4. **ADK Python + Firestore / Vertex AI Agent Engine Sandbox** - Firestore support and Agent Engine Sandbox integration
5. **ADK JS + Skills system** - Supports Skills interface, toolset, loader, and script execution
6. **ADK JS + `RoutedAgent`/`RoutedLlm`** - New routable Agent and LLM
7. **ADK Go + Skill Source proxy** - Merge/preload skill source proxies
8. **GenAI Toolbox + Cloud Storage bucket/object management** - Bucket/object management tools and HTTPS/TLS listener
9. **ACP + Product Feeds / Cart Capability / Marketing Consent** - Major expansion of Commerce protocol
9a. **UCP + Loyalty Extension** (#340) - Added loyalty extension to catalog / cart / checkout capabilities; 2nd official extension after discount
9b. **GenAI Toolbox + `cloud-sql-admin-execute-sql-many` / `sql-many`** (#3083) - Bulk execute/sql tools for Cloud SQL admin
9c. **GKE MCP + `apply_k8s_manifest` + `adk-anthropic-go`** (#358, #356) - K8s manifest apply tool; integrated Anthropic Claude Go library on ADK
9d. **ADK JS + Agent Engine Sandbox Code Executor** (#317) - Code execution Executor via Agent Engine Sandbox
9e. **ADK Python + `GCPSkillRegistry` / Skill Registry / Gemini Live API in evaluate** (v1.34.0) - Skill Registry implementation and Gemini Live API evaluation support
9f. **ADK Go + Live bidirectional streaming core** (v1.3.0) - Session resumption / streaming tools / audio cache / sequential agent live run / live example
10. **A2UI + Kotlin SDK / C++ port** - Kotlin SDK conformance tests and initial C++ port of Python agent SDK
11. **ADP + per-step reward / new datasets** - Reward field for RL training; datasets including CoderForge-Preview, Nemotron Terminal Corpus, Toucan
12. **MCP-Apps + WebMCP-style tool registration** - WebMCP-style tool registration specification
13. **OpenResponses + WebSocket / Phase Compaction** - WebSocket mode and compact response endpoint
14. **GKE MCP + GIQ tool** - Integrated GIQ tool into manifest agent
15. **`gcloud-mcp` + `backupdr-mcp`** - Added new Backup DR MCP server
16. **AgentSkills + `fast-agent` / Google AI Edge Gallery / `nanobot` / `Workshop.ai`** - Expanded client showcase
17. **A2A + custom protocol bindings** - Added custom protocol bindings documentation

### Security Updates

- **GenAI Toolbox (unreleased HEAD after v1.14.0)**: Fixed `authRequired` not being enforced on 25 tools by centralizing authorization checks (#4254)
- **AG-UI Claude Agent SDK adapter (TS 0.0.6 / Py 0.2.1)**: Stopped implicitly loading host settings; specify `settingSources` / `setting_sources` explicitly only when needed

- **A2UI `web_core` (2026-09)**: Guarded excessive recursion in DynamicValue resolution with `MAX_DYNAMIC_VALUE_DEPTH = 20` (#2432) — prevents CWE-674 where 20,000-deep nested function calls crash the renderer process
- **ADK Go (main after v2.4.0, 2026-09)**: **Bound web server to loopback by default (#1456)**; **adkrest rejects DNS-rebinding hosts and cross-origin browsers (#1615)**
- **`webmcp-tools` (2026-09)**: **Sanitized `innerHTML` with DOMPurify across demos** (page-agent / french-bistro #469, french-bistro modalDetails #471, ticket-booking movieGrid #472); **mitigated DOM XSS and DoS in pizza-maker (#468)**; **nested `webmcp-maze` EvalTool Web Worker in a sandboxed iframe (#470)**
- **A2UI `web_core` 0.11.0 (2026-09)**: Prototype chain traversal fix on v0.8 read path (#2355); hid V8 stack traces from DataContext errors (#2429); capped `MAX_ARRAY_INDEX` / `MAX_DYNAMIC_CHILD_LIST_SIZE` / expression parser template length (#2430 / #2431 / #2433)
- **ADK JS (main after v2.0.0, 2026-09)**: **Origin validation in dev server (DNS rebinding defense, #557)**; **prevented SSRF / silent file reads in A2A agent-card resolution (#832)**; **OAuth2 PKCE S256 (#820)**; rejected unauthenticated requests when OpenAPI HTTP credentials are unusable (#816); removed `httpOptions` with credentials from telemetry (#815)
- **ADK Go v2.4.0 (2026-09-11)**: Removed consent URI from `ConsentRequiredError` messages (#1519); removed caller identifiers from GCP auth service errors (#1520); validated deploy CLI values before Dockerfile interpolation (#1240)
- **GenAI Toolbox v1.11.0 (2026-09-10)**: **Default SSRF guard in HTTP source blocks IETF protocol assignments range (#3909)**; released handles on connection failure (#3921)
- **UCP (2026-09)**: **Updated `js-yaml` to 4.3.2 to resolve CVE-2026-84375 (#814)**; mitigated vulnerability via `fast-uri` override (#803); disallowed private registries in lockfiles (#806)
- **AG-UI `aws-strands` (2026-08)**: **URL fetch scheme restrictions, redirect downgrade rejection, DNS rebinding prevention, zero-net URL target blocking**; closed auth fail-open paths; per-request CORS credentials decision and null origin rejection (breaking CORS opt-in in TS); rejected unsafe native frontend identities
- **ADK JS v2.0.0 (2026-08-21)**: **DNS rebinding guard on dev server (#744)**; **credential scrubbing before forwarding to remote A2A peers (#767)**; closed author-blind confirmation-resolution paths (#755); bound HITL confirmation to approved action (#771); OAuth2 authorization code log redaction (#640)
- **ADK Python v2.7.x/v2.8.0 + main (2026-08)**: **SQL injection guard for BigQuery tools (d6290a0)**; **fenced relayed agent output (prevents instruction spoofing, 9ffe8be)**; **YAML/ruamel deserialization block on agent-config code references (924d802)**; OIDC verification on Pub/Sub and Eventarc triggers (73d9fe05); rejected transfers to forbidden agents (b0503a03)
- **ADK Go v2.2.0/v2.3.0 (2026-08)**: **Fixed unsafe use of A2A peer-supplied `transferToAgent` metadata (#1226)**; restricted agent card sources to http(s)/path (#1328); rejected conflicting tool confirmation requests (#1369) and resume from non-agent-created events (#1357)
- **GenAI Toolbox v1.10.0 (2026-08-27)**: **Resolved symlinks at local path boundaries in `cloud-storage` source to prevent escape (#3810)**
- **MCP (2026-08)**: **Patched 2 high-severity advisories** in dev dependencies (881ee655); raised Node floor from EOL 20 to 24
- **ADK Python v2.6.x + main (2026-07-27 to 07-31)**: **Mitigated transitive dependency supply-chain attacks by publishing `constraints-3.11/3.12.txt` (4-day buffer, 75c773e)**; **excluded LangGraph releases with unsafe checkpoint loading from dependencies (1b12ee39)**; restricted A2A agent card RPC targets (SSRF mitigation, 16cbb7d); ignored A2A peer-supplied event actions metadata (0ba7d3c); stopped mounting cluster credentials into GKE code sandbox (8207880); excluded `config.http_options` credentials from traces (761f1ac); validated skill names (11101ac); killed runaway code on executor timeout (27548e3)
- **ADK JS v1.5.0 (2026-07-30)**: **Required authentication when mounting A2A server (#529)**; **required confirmation before running inline skill scripts (#528)**; **rejected zip-slip in zipped skills (#584)**; PowerShell `-NoProfile` / `cmd.exe /D` in `UnsafeLocalCodeExecutor` (#566); cryptographically secure `randomUUID` (#577)
- **GKE MCP v0.15.0 (2026-07-28)**: **Added safety checks to `delete_cluster` (#481)**; vulnerability bumps: `brace-expansion` 5.0.7 (#483) / `fast-uri` 3.1.4 (#485)
- **A2A (2026-07-28)**: Migrated vulnerability reporting to **GitHub Security Advisories** (#2086, operational change)
- **ADK Python (main, unreleased 2026-07)**: **Prevented continuation forgery on tool confirmations** (blocks spoofing confirmed continuations); **rejected `base_url` / `extra_body` in `generate_content_config`** (closes external exfiltration paths)
- **GenAI Toolbox (main after v1.7.0, 2026-07)**: **Default SSRF guard in `source/http` blocks CGNAT `100.64.0.0/10` (#3625)**; validated source instance in `cloud-sql-admin` backup-run restore (#3555)
- **A2UI (`web_core`, 2026-07)**: **Protected `DataModel` against prototype pollution (#2085)**
- **ADK Python (main, 2026-07-02 to 07-07)**: **Path segment validation in `GcsArtifactService` / `InMemoryArtifactService` prevents cross-user artifact access (8718aeff)**; **scoped artifact references to caller (f8631500)**; **added DNS rebinding protection to `_OriginCheckMiddleware` (9a4f479d)**; enabled Jinja2 autoescape in gepa sample (XSS mitigation, a721c1eb)
- **ADK JS (main, 2026-07-01 to 07-05)**: **Applied SSRF blocklist to OAuth2 token endpoint in `fetchOAuth2Tokens` (#465)**
- **UCP (2026-07-02/03)**: **Added optional EdDSA (Ed25519, RFC 8037) signing for WBA interoperability (#483)**; **normalized namespace authority binding to prevent namespace spoofing (#530)**
- **GenAI Toolbox v1.6.0 (2026-06-30)**: **Integrated Kokoro code signing into release workflow to digitally sign Toolbox binaries (supply-chain hardening, #3528)**; separated unsigned/signed GCS buckets + signature verification when generating release tables (addresses long-standing issue #996)
- **GKE MCP (2026-06-29)**: **Fixed UI dependency vulnerabilities (updated `ui/package-lock.json`, mainly Babel toolchain transitive dependencies, #448)**
- **ADK Python (main, 2026-06-27)**: **Prevented path traversal in `AgentTool` `config_path` resolution (171ae9e)**; **hardened `ContainerCodeExecutor` sandbox by default (0a9ce0f)**; **module blocklist for YAML agent-config code references (6a5be34)** / enforced args denylist under `adk web` (e506fa6)
- **ADK JS v1.3.0 (2026-06-22)**: **Fixed streaming prototype pollution (via model-controlled JSON paths, #410)**
- **MCP (2026-06-25)**: **Added Security best practices tutorial (#1554)**; **added SDK vulnerability disclosure process + stdio trust-boundary guidance to `SECURITY.md` (#2973)**
- **ADK Python v2.3.0 (main, 2026-06-19)**: **Fixed Code Generation Template Injection via Filenames** (blocks template injection through filenames); fixed loss of `display: "omitted"` in LiteLLM Claude thinking blocks
- **GenAI Toolbox v1.5.0 (2026-06-19)**: **Implemented SSRF guard in `source/http` (#3448)**; **prevented SSRF via `pageURL` validation in `source/cloudhealthcare` (#3453)**; **blocked dataset restriction bypass in `bigquery-execute-sql` (#3452)**; **guard failing when both MCP auth and `enable-api` are enabled (#3435)**; returned errors instead of panicking in `InitializeConfigs` (#3397)
- **ADK JS (main, 2026-06-18)**: **Blocked `127.0.0.0/8` and cloud-metadata hostnames in OAuth2 discovery SSRF check (#431)**
- **A2UI (`web_core`, 2026-06-18)**: **Restricted `openUrl` to http/https protocols only (#1707)** (blocks unsafe schemes)
- **GenAI Toolbox (main after v1.4.0, 2026-06-18)**: **Prevented query execution bypass + statement injection in `mysql-get-query-plan` (#3235)**; **restricted bucket / local path access in `cloud-storage` source (#3454)**; **required `audience` or `clientId` in `auth/google` when `mcpEnabled` (#3450)**; patched npm audit vulnerabilities in JS doc samples (#3442)
- **ADK Python (main, 2026-06-18)**: **Prevented ReDoS in code block extraction**; **safely handled missing client-credentials scopes in auth**; improved operator safety for generated `.env` files
- **GenAI Toolbox (main after v1.4.0, 2026-06-15)**: **Bumped `picomatch` to 2.3.2 / 4.0.4 to fix regex method injection (#3426, #3429)**; **bumped `fast-uri` to 3.1.2 to fix path normalization bypass (#3425)**
- **GenAI Toolbox (main after v1.4.0, 2026-06-12)**: **Prevented SQL injection by escaping delimiter characters in `applyEscape` (#2811)**; **set upper limit on MCP HTTP body size (#3216)**; specified `cloud-platform` scope on default credentials for dataplex / datalineage (#3376); made password env explicitly required in `alloydb-omni` prebuilt (#3398)
- **ADK Go (main after v1.4.0, 2026-06-10)**: **Bumped `golang.org/x/net` and OTel OTLP exporters to patched versions for govulncheck advisory (#994)**
- **ADK Python (main HEAD, 2026-06-13)**: CI security hardening — added repository check preventing workflow execution on forks, gated pr-triage secrets to same-repository `pull_request_target`, stopped shell interpolation of release analyzer workflow inputs
- **ADK Python v2.2.0 (2026-06-04)**: **Blocked path traversal in Agent Builder file tools (1fa7cda)**; **fixed Zip Slip in GCS skill extraction (2f15c6c)**; **restricted unpickling of v0 actions blobs (9db48ce)**; **validated session ownership in `delete_session` (b2916c7)**; **CVE-2026-48710 mitigation (starlette / fastapi bump, 81add39)**; shell-escaped `ReadFileTool` (e16629b); omitted scope from OAuth2 token requests (6ce4b87)
- **ADK JS v1.2.0 (2026-06-03) + subsequent main**: Officially released post-v1.1.0 **CORS vulnerability fix (disabled `express.urlencoded` parser, #378)**, **OAuth2 SSRF prevention (blocked IPv4-mapped IPv6, #354)**, `run_sse` hardcoded `*` removal (#360), and `AdkApiServer` host restriction (#383). Main fixed **streaming prototype pollution (via model-controlled JSON paths, #410)**
- **GenAI Toolbox v1.4.0 (2026-06-04)**: Officially released **ClickHouse / BigQuery identifier injection prevention (#3219)**, **mandatory issuer in opaque token validation (#3360)**, **separated Google / Generic MCP OAuth verification (#3341)**, Looker filter value escape (#3289), and `apache/thrift` CVE-2026-41602 fix
- **MCP-Apps v1.7.4 (2026-06-04)**: **Required PKCE + bound `redirect_uri` in `lazy-auth-server` token exchange (#681)** — prevents OAuth authorization code interception attacks; legacy non-PKCE flows are rejected
- **GKE MCP v0.13.0 (2026-05-28)**: Added install checksum verification (#398); added CI check preventing insecure `pull_request_target` usage (#400)
- **ADK Python v1.34.0 / v2.0.0 GA**: Persisted refreshed OAuth2 credentials to store (218ea76, #5329), removed unused OAuth flows (c35a579), prevented double-escaping from dict pre-serialization in Interactions API (85f397d), prevented AnyIO `CancelScope` task boundary violations (4309159), caught `OSError` on `AnthropicLlm` import (91cb5c6), prevented accidental compaction of HITL events (bb2efb6)
- **MCP HEAD (post-2025-11-25)**: **`vm2` 3.11.3 security bump for GHSA-vwrp-x96c-mhwq** (#2711)
- **GenAI Toolbox (post-v1.3.0 → included in v1.4.0)**: **ClickHouse / BigQuery identifier injection prevention (#3219)**, **`apache/thrift` CVE-2026-41602 fix (v0.22.0 → v0.23.0, #3312)**, Looker unquoted parameters filter value escape (#3289)
- **GenAI Toolbox v1.3.0 (released, 2026-05-21)**: **HTTP tool path traversal / base path scope escape prevention (#3218)**, MCP auth tool-level scopes validation (#3049), toolset/promptset boundary enforcement (#3036)
- **GenAI Toolbox v1.2.0 (released, 2026-05-07)**: Removed SSE hardcoded `*` allowed origin (#3054, included security fix), router-level logger injection (#3067)
- **ACP post-v2026-04-17 → UCP post-v2026-04-08**: `urllib3` v2.7.0 security bump (#434)
- **ADK Python HEAD after v1.33.0**: Multiple safety hardenings including `OSError` catch on `AnthropicLlm` import (crash avoidance) and persisting refreshed OAuth2 credentials (auth)
- **ADK Python v1.32.0 (released, 2026-04-30)**: **Fixed `load_web_page` SSRF / local-file access (0447e93)**, **blocked RCE vulnerability via nested YAML configs (74f235b)**, credential isolation in auth context (prevents race conditions / data leaks) (5578772), `user_id` sanitization from PubSub subscriptions / Eventarc sources (#5324, 0c4f157), raised minimum `litellm` to 1.83.7 for CVE patch (6d2ada8), scoped Vertex RAG memory display names (784350d)
- **GenAI Toolbox (unreleased → included in v1.2.0)**: `pgx` v5.9.2 security update (#3133), removed SSE hardcoded `*` allowed origin (#3054), moved macOS SDK to internal GCS bucket (#3025), `pytest` v9.0.3 security update (#3047)
- **`gcloud-mcp` `storage-mcp` v0.6.0 (2026-05-06)**: Removed `download_object_safe` tool (breaking change; its design allowed writing to sensitive destination paths). Must migrate to destructive `download_object` or `read_object_content` / `read_object_metadata` (#420, #422)
- **`gcloud-mcp` `storage-mcp`**: Moved `delete_object` from safe → destructive tools (prevents accidental deletion)
- **A2UI**: Bumped Python `google-adk` to 1.28.1 (security)
- **MCP-Apps v1.7.0**: Patch version bumps for vite / hono / `@hono/node-server` (#616)
- **AG-UI**: CVE-2026-25528 dependency vulnerability fix (#1527), ADK middleware critical/high Dependabot vulnerability fixes (#1517)
- **ADK Python v1.30.0**: Fixed Agent Registry credential leak vulnerability, path traversal validation (#5110)
- **ADK JS**: Fixed `FileArtifactService` path traversal vulnerability (CWE-22), lodash security updates
- **UCP**: lodash security update (Trivy vulnerability fix) (#333), standardized lockfile registries (#368)
- **x402**: `HTTPFacilitatorClient` redirect fix, Facilitator signer random selection fix
- **MCP-Apps v1.4.0**: `path-to-regexp` ReDoS CVE fix
- **GKE MCP v0.10.0**: Fixed Shell Command Injection (`ui/scripts/build.ts`)
- **Google Analytics MCP**: Updated minimum `google-adk` version to 1.28.1 (mitigates GHSA-rg7c-g689-fr3x)
- **MCP**: OIDC / Enterprise Managed Authorization updates, SEP-2207 refresh token guidance
