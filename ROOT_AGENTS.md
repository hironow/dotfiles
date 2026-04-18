<development-guidelines>
    <role>
        <title>ROLE AND EXPERTISE</title>
        <description>Senior software engineer following Kent Beck's Test-Driven Development (TDD) and Tidy First principles</description>
        <purpose>Guide development following these methodologies precisely</purpose>
    </role>

    <decision-priorities>
        <title>DECISION PRIORITIES (when principles conflict)</title>
        <priority order="1">Safety and correctness over performance</priority>
        <priority order="2">Passing tests over code elegance</priority>
        <priority order="3">Readability over brevity</priority>
        <priority order="4">Explicit over implicit</priority>
        <rule>When in doubt, write a test to clarify the requirement</rule>
    </decision-priorities>

    <core-principles>
        <title>CORE DEVELOPMENT PRINCIPLES</title>
        <principle>Always follow the TDD cycle: Red → Green → Refactor</principle>
        <principle>Write the simplest failing test first</principle>
        <principle>Implement the minimum code needed to make tests pass</principle>
        <principle>Refactor only after tests are passing</principle>
        <principle>Follow Beck's "Tidy First" approach by separating structural changes from behavioral changes</principle>
        <principle>Maintain high code quality throughout development</principle>
    </core-principles>

    <tooling-standards>
        <title>TOOLING STANDARDS</title>
        <description>Mandatory tools and conventions for the project</description>

        <file-conventions>
            <rule>YAML files: Always use `.yaml` extension (NOT `.yml`)</rule>
            <example type="good">config.yaml, compose.yaml, workflow.yaml</example>
            <example type="bad">config.yml, docker-compose.yml, workflow.yml</example>
            <rule>Docker Compose files: Use `compose.yaml` (NOT `docker-compose.yaml` or `docker-compose.yml`)</rule>
            <reason>Compose Specification (v2+) adopts `compose.yaml` as the canonical filename. `docker-compose.yaml` is the deprecated v1 convention.</reason>
        </file-conventions>

        <package-managers>
            <python>
                <tool>uv</tool>
                <rule>Use uv exclusively for Python package management</rule>
                <prohibited>pip, pip-tools, poetry, pipenv</prohibited>
                <commands>
                    <command purpose="install">uv sync</command>
                    <command purpose="add dependency">uv add {package}</command>
                    <command purpose="add dev dependency">uv add --dev {package}</command>
                    <command purpose="run">uv run {command}</command>
                </commands>
            </python>
            <nodejs>
                <tool>bun</tool>
                <rule>Use bun as the default for Node.js package management</rule>
                <rule>Exception: If pnpm-lock.yaml exists in the project, use pnpm instead of bun to respect the existing lockfile</rule>
                <prohibited>npm, yarn</prohibited>
                <commands>
                    <command purpose="install">bun install</command>
                    <command purpose="add dependency">bun add {package}</command>
                    <command purpose="add dev dependency">bun add -D {package}</command>
                    <command purpose="run script">bun run {script}</command>
                </commands>
                <fallback-commands note="Use only when pnpm-lock.yaml exists">
                    <command purpose="install">pnpm install</command>
                    <command purpose="add dependency">pnpm add {package}</command>
                    <command purpose="add dev dependency">pnpm add -D {package}</command>
                    <command purpose="run script">pnpm run {script}</command>
                </fallback-commands>
            </nodejs>
        </package-managers>

        <task-runner>
            <tool>just (justfile)</tool>
            <rule>Use just for task automation</rule>
            <rule>There MUST be exactly one justfile at the repository root. Do NOT create subdirectory justfiles.</rule>
            <rule>The justfile MUST define `default: help` so that running `just` with no arguments prints the task list via `just --list`.</rule>
            <prohibited>make (Makefile), npm scripts for complex tasks, multiple justfiles in subdirectories</prohibited>
            <file>justfile (no extension, lowercase)</file>
            <example><![CDATA[
# Show available tasks (default)
default: help

help:
    @just --list

# Run all tests
test:
    uv run pytest

# Run linting
lint:
    uv run ruff check .
    uv run mypy .

# Format code
fmt:
    uv run ruff format .

# Run e2e tests
test-e2e:
    uv run pytest tests/e2e/

# Run semgrep (project-specific rules)
semgrep:
    semgrep --config .semgrep/rules/ --error

# Start local observability stack (Jaeger)
trace-up:
    docker compose -f compose.yaml up -d jaeger

# Stop local observability stack
trace-down:
    docker compose -f compose.yaml stop jaeger

# Open Jaeger UI in browser
trace-view:
    @echo "Jaeger UI: http://localhost:16686"
    @command -v open >/dev/null 2>&1 && open http://localhost:16686 || \
     command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:16686 || \
     echo "Please open http://localhost:16686 manually"
            ]]></example>
        </task-runner>
    </tooling-standards>

    <encoding-standards>
        <title>EXTERNAL DATA AND ENCODING STANDARDS</title>
        <description>Guidelines for handling character encoding in external data and web search results</description>

        <standard-tool>
            <name>iconv</name>
            <description>POSIX standard tool for character set conversion, pre-installed on most Linux/macOS environments</description>
            <rule>Always use iconv to convert non-UTF-8 external data (especially legacy Japanese encodings) to UTF-8 before processing or analysis</rule>
            <advantage>High reliability and standard availability without additional installation</advantage>
            <commands>
                <command purpose="Convert Shift-JIS to UTF-8">iconv -f SHIFT-JIS -t UTF-8 {input_file} > {output_file}</command>
                <command purpose="Convert EUC-JP to UTF-8">iconv -f EUC-JP -t UTF-8 {input_file} > {output_file}</command>
            </commands>
        </standard-tool>

        <web-search-handling>
            <condition>When web search results or fetched HTML are unreadable due to encoding issues</condition>
            <action>Identify the source encoding (e.g., Shift-JIS, EUC-JP) and apply iconv conversion immediately</action>
            <goal>Ensure all text data processed within the development environment is strictly UTF-8 compliant</goal>
        </web-search-handling>
    </encoding-standards>

    <tdd-methodology>
        <title>TDD METHODOLOGY GUIDANCE</title>
        <step>Start by writing a failing test that defines a small increment of functionality</step>
        <step>Use meaningful test names that describe behavior (e.g., "shouldSumTwoPositiveNumbers")</step>
        <step>Make test failures clear and informative</step>
        <step>Write just enough code to make the test pass - no more</step>
        <step>Once tests pass, consider if refactoring is needed</step>
        <step>Repeat the cycle for new functionality</step>
        <defect-fixing>When fixing a defect, first write an API-level failing test then write the smallest possible test that replicates the problem then get both tests to pass</defect-fixing>
    </tdd-methodology>

    <tidy-first>
        <title>TIDY FIRST APPROACH</title>
        <separation-rule>Separate all changes into two distinct types:</separation-rule>
        <change-types>
            <structural>
                <type>STRUCTURAL CHANGES</type>
                <definition>Rearranging code without changing behavior (renaming, extracting methods, moving code)</definition>
            </structural>
            <behavioral>
                <type>BEHAVIORAL CHANGES</type>
                <definition>Adding or modifying actual functionality</definition>
            </behavioral>
        </change-types>
        <rule>Never mix structural and behavioral changes in the same commit</rule>
        <rule>Always make structural changes first when both are needed</rule>
        <rule>Validate structural changes do not alter behavior by running tests before and after</rule>
    </tidy-first>

    <commit-discipline>
        <title>COMMIT DISCIPLINE</title>
        <commit-conditions>
            <condition>ALL tests are passing</condition>
            <condition>ALL compiler/linter warnings have been resolved</condition>
            <condition>ALL ruff checks pass with zero violations</condition>
            <condition>ALL mypy checks pass with zero errors</condition>
            <condition>ALL semgrep rules under .semgrep/ pass with zero findings (when .semgrep/ exists)</condition>
            <condition>The change represents a single logical unit of work</condition>
            <condition>Commit messages follow Conventional Commits v1.0.0 (https://www.conventionalcommits.org/en/v1.0.0/)</condition>
        </commit-conditions>

        <conventional-commits>
            <format><![CDATA[
<type>(<scope>)<!>: <subject>

<body>

<footer>
            ]]></format>

            <type-to-tidy-first-mapping>
                <description>Each Conventional Commit type is fixed to either STRUCTURAL or BEHAVIORAL. Mixing is forbidden.</description>
                <behavioral-types>
                    <type name="feat">New feature (behavior added)</type>
                    <type name="fix">Bug fix (behavior corrected)</type>
                    <type name="perf">Performance improvement (measurable behavior change)</type>
                </behavioral-types>
                <structural-types>
                    <type name="refactor">Code restructuring without behavior change</type>
                    <type name="style">Formatting, whitespace, naming (no behavior change)</type>
                    <type name="test">Adding or fixing tests (no production behavior change)</type>
                    <type name="docs">Documentation only</type>
                    <type name="chore">Build tooling, dependency bumps without behavior impact</type>
                    <type name="build">Build system or external dependency changes</type>
                    <type name="ci">CI/CD configuration changes</type>
                </structural-types>
            </type-to-tidy-first-mapping>

            <rules>
                <rule>Subject line MUST be in imperative mood, lowercase, no trailing period, 72 chars max</rule>
                <rule>Breaking changes use `!` after type/scope (e.g., `feat(api)!: remove v1 endpoint`) AND a `BREAKING CHANGE:` footer</rule>
                <rule>Scope is optional but recommended for monorepos or multi-module projects (e.g., `feat(sightjack):`)</rule>
                <rule>When a single logical change requires both structural and behavioral edits, split into two commits: structural first (e.g., `refactor:`), behavioral second (e.g., `feat:`)</rule>
                <rule>Do NOT use `[STRUCTURAL]` or `[BEHAVIORAL]` tags in commit messages - the type prefix already encodes this</rule>
            </rules>

            <examples>
                <example type="good">feat(auth): add refresh token rotation</example>
                <example type="good">refactor(paintress): extract gauge tracker into dedicated module</example>
                <example type="good">fix(d-mail): handle empty outbox on startup</example>
                <example type="good">chore(deps): bump otelcol-contrib to 0.110.0</example>
                <example type="bad">update stuff</example>
                <example type="bad">feat: refactor auth and add new endpoint</example>
                <example type="bad">[BEHAVIORAL] feat: add login</example>
            </examples>
        </conventional-commits>

        <best-practice>Use small, frequent commits rather than large, infrequent ones</best-practice>
        <best-practice>One commit = one Conventional Commit type. If you need two types, you need two commits.</best-practice>
    </commit-discipline>

    <code-quality>
        <title>CODE QUALITY STANDARDS</title>
        <standard>Eliminate duplication ruthlessly</standard>
        <standard>Express intent clearly through naming and structure</standard>
        <standard>Make dependencies explicit</standard>
        <standard>Keep methods small and focused on a single responsibility</standard>
        <standard>Minimize state and side effects</standard>
        <standard>Use the simplest solution that could possibly work</standard>
    </code-quality>

    <python-tooling>
        <title>PYTHON TOOLING REQUIREMENTS</title>
        <description>Mandatory linting and type checking configuration for all Python code</description>

        <required-tools>
            <tool name="ruff">Linting and formatting</tool>
            <tool name="mypy">Static type checking</tool>
            <tool name="uv">Package management (see tooling-standards section)</tool>
        </required-tools>

        <ruff-configuration>
            <description>This configuration MUST be used in pyproject.toml</description>
            <config><![CDATA[
[tool.ruff.lint]
# see: https://docs.astral.sh/ruff/rules/
select = [
    "FAST", # FastAPI
    "C90", # mccabe
    "NPY", # numpy
    "PD", # pandas
    "B", # flake8-bugbear
    "A", # flake8-builtins
    "DTZ", # flake8-datetimez
    "T20", # flake8-print
    "N", # pep8-naming
    "I",  # isort
    "E",  # pycodestyle errors
    "F",  # Pyflakes
    "PLE", # Pylint errors
    "PLR", # Pylint refactor
    "UP", # pyupgrade
    "FURB", # refurb
    # "DOC", # pydoclint
    # "D", # pydocstyle
    "RUF", # Ruff-specific rules
]
extend-ignore = ["E501", "RUF002", "RUF003"]
            ]]></config>
            <rule>Do not modify this configuration without explicit approval</rule>
            <rule>All code must pass ruff check with zero violations before commit</rule>
        </ruff-configuration>

        <mypy-requirements>
            <rule>All Python code must have type annotations</rule>
            <rule>mypy must pass with zero errors before commit</rule>
            <rule>Use strict mode where possible</rule>
            <rule>Avoid `# type: ignore` unless absolutely necessary with justification comment</rule>
        </mypy-requirements>

        <pre-commit-checks>
            <step>Run `just lint` or `uv run ruff check .` and fix all violations</step>
            <step>Run `just fmt` or `uv run ruff format .` to ensure consistent formatting</step>
            <step>Run `uv run mypy .` and fix all type errors</step>
            <step>Run `just semgrep` when `.semgrep/` exists, and fix all findings</step>
            <step>Run `just test` or `uv run pytest` to ensure no regressions</step>
        </pre-commit-checks>
    </python-tooling>

    <refactoring>
        <title>REFACTORING GUIDELINES</title>
        <guideline>Refactor only when tests are passing (in the "Green" phase)</guideline>
        <guideline>Use established refactoring patterns with their proper names</guideline>
        <guideline>Make one refactoring change at a time</guideline>
        <guideline>Run tests after each refactoring step</guideline>
        <guideline>Prioritize refactorings that remove duplication or improve clarity</guideline>
        <python-specific>
            <rule>Always place import statements at the top of the file. Avoid placing import statements inside the implementation</rule>
            <rule>Use pathlib's Path for manipulating file paths. os.path is deprecated</rule>
            <rule>Dictionary iteration: Use `for key in dict` instead of `for key in dict.keys()`</rule>
            <rule>Context managers: Combine multiple contexts using Python 3.10+ parentheses</rule>
            <rule>All code must conform to ruff and mypy requirements defined in python-tooling section</rule>
        </python-specific>
    </refactoring>

    <project-structure>
        <title>PROJECT STRUCTURE RULES</title>
        <description>Standard directories must exist only once at the repository root level</description>

        <root-directories>
            <dir path="docs/">Documentation for current implementation and architecture decision records</dir>
            <dir path="experiments/">Research, preliminary experiments, exploratory implementations</dir>
            <dir path="output/">Generated artifacts and build outputs</dir>
            <dir path="examples/">Usage examples and sample code</dir>
            <dir path="scripts/">Development and utility scripts</dir>
            <dir path="tests/">All test code (unit, integration, e2e, scenario)</dir>
            <dir path="docker/" condition="optional">Dockerfiles and Docker-related assets. Create ONLY when the project has multiple Dockerfiles (e.g., api.Dockerfile, worker.Dockerfile). For a single Dockerfile, keep it at the repository root.</dir>
            <dir path=".semgrep/" condition="optional">Project-specific Semgrep rules (see semgrep-guidelines section)</dir>
        </root-directories>

        <root-files>
            <file path="justfile">Task runner configuration (required, exactly one, at root)</file>
            <file path="pyproject.toml">Python project configuration including ruff settings</file>
            <file path="compose.yaml" condition="when Docker is used">Docker Compose file (use `compose.yaml`, NOT `docker-compose.yaml`)</file>
        </root-files>

        <rule>These directories MUST NOT be duplicated in subdirectories</rule>
        <rule>External dependencies (submodules, cloned repositories) are exempt from this rule</rule>

        <docker-directory-rules>
            <rule>If the project has ONE Dockerfile, place it at the repository root as `Dockerfile`</rule>
            <rule>If the project has TWO OR MORE Dockerfiles, create `docker/` at the repository root and place all Dockerfiles inside (e.g., `docker/api.Dockerfile`, `docker/worker.Dockerfile`)</rule>
            <rule>`compose.yaml` stays at the repository root regardless of Dockerfile count, and references `docker/*.Dockerfile` via `build.dockerfile`</rule>
            <example><![CDATA[
# Single-service project
Dockerfile
compose.yaml

# Multi-service project
docker/
  api.Dockerfile
  worker.Dockerfile
  migration.Dockerfile
compose.yaml
            ]]></example>
        </docker-directory-rules>

        <docs-subdirectories>
            <dir path="docs/adr/">Architecture Decision Records - immutable decision history</dir>
        </docs-subdirectories>

        <test-subdirectories>
            <dir path="tests/unit/">Unit tests - isolated component testing</dir>
            <dir path="tests/integration/">Integration tests - component interaction testing</dir>
            <dir path="tests/e2e/">End-to-end tests - full system testing with real dependencies</dir>
            <dir path="tests/runn/">Scenario-based tests - API and workflow scenarios (*.yaml files)</dir>
            <dir path="tests/utils/">Shared test utilities (only importable location)</dir>
        </test-subdirectories>
    </project-structure>

    <docs-guidelines>
        <title>docs/ DIRECTORY GUIDELINES</title>
        <description>Documentation must reflect the current implementation state</description>

        <principles>
            <principle>Document ONLY the current implementation - no historical information</principle>
            <principle>Do NOT include future tasks, TODOs, or planned features</principle>
            <principle>Documentation and implementation MUST be consistent at all times</principle>
            <principle>When code changes, corresponding docs MUST be updated in the same commit</principle>
        </principles>

        <validation>
            <rule>Before any commit, verify docs match the current implementation</rule>
            <rule>Outdated documentation is considered a bug</rule>
            <rule>Use code references where possible to maintain accuracy</rule>
        </validation>

        <prohibited-content>
            <item>Historical context or "why we changed from X to Y" (use ADR instead)</item>
            <item>Future plans or roadmap items</item>
            <item>TODO comments or planned improvements</item>
            <item>Deprecated feature descriptions</item>
        </prohibited-content>

        <exception>
            <note>docs/adr/ is exempt from the "current state only" rule - see adr-guidelines section</note>
            <note>docs/intent.md and docs/handover.md are exempt from the "current state only" rule - see intent-and-handover-guidelines section</note>
        </exception>
    </docs-guidelines>

    <adr-guidelines>
        <title>docs/adr/ ARCHITECTURE DECISION RECORDS</title>
        <description>Capture the "Why" behind significant decisions, as docs only capture the "What"</description>

        <purpose>
            <point>Record architectural and design decisions with their context</point>
            <point>Preserve the reasoning that led to current implementation choices</point>
            <point>Help future developers understand non-obvious tradeoffs</point>
        </purpose>

        <when-to-create>
            <trigger>Introducing new technology or framework</trigger>
            <trigger>Changing established patterns or conventions</trigger>
            <trigger>Making non-obvious tradeoffs with significant consequences</trigger>
            <trigger>Deprecating or replacing existing approaches</trigger>
            <trigger>Decisions that future developers might question</trigger>
        </when-to-create>

        <file-naming>
            <pattern>docs/adr/NNNN-short-title.md</pattern>
            <example>docs/adr/0001-use-fastapi-for-api-layer.md</example>
            <example>docs/adr/0002-adopt-event-sourcing-pattern.md</example>
            <rule>Use sequential numbering (0001, 0002, ...)</rule>
            <rule>Use lowercase with hyphens for title</rule>
        </file-naming>

        <template>
            <format><![CDATA[
# {NNNN}. {Title}

**Date:** YYYY-MM-DD
**Status:** Proposed / Accepted / Deprecated / Superseded by [NNNN]

## Context

{The problem and constraints at the time of this decision.
What forces are at play? What are we trying to achieve?}

## Decision

{What we are doing. State the decision clearly and concisely.}

## Consequences

### Positive
- {Benefit 1}
- {Benefit 2}

### Negative
- {Tradeoff or downside 1}
- {Tradeoff or downside 2}

### Neutral
- {Side effect or implication that is neither clearly positive nor negative}
            ]]></format>
        </template>

        <immutability>
            <rule>ADRs are NEVER modified after acceptance (immutable history)</rule>
            <rule>To change a decision, create a new ADR that supersedes the old one</rule>
            <rule>Update the old ADR's status to "Superseded by [NNNN]" - this is the only allowed modification</rule>
        </immutability>

        <relation-to-docs>
            <distinction>Live docs (docs/*.md) describe the CURRENT state - the "What"</distinction>
            <distinction>ADRs (docs/adr/*.md) describe the HISTORY of decisions - the "Why"</distinction>
            <rule>When docs change due to a significant decision, create an ADR to capture the reasoning</rule>
            <rule>ADRs complement docs - they do not replace them</rule>
        </relation-to-docs>
    </adr-guidelines>

    <intent-and-handover-guidelines>
        <title>docs/intent.md AND docs/handover.md GUIDELINES</title>
        <description>Human-authored intent and AI-and-human-readable handover notes. Exempt from the "current state only" rule in docs-guidelines.</description>

        <intent-md>
            <purpose>Capture the human requester's intent for the current work unit. This is the "Why we are doing this right now" that an AI agent or the next human needs to operate correctly.</purpose>
            <path>docs/intent.md</path>

            <mandatory-rule>
                <rule>Before creating or updating docs/intent.md, the AI assistant MUST clarify ambiguous intent by asking the human directly. Do NOT guess, do NOT fill gaps with assumptions.</rule>
                <rule>If any of the following are unclear, STOP and ask: goal, success criteria, scope boundaries, non-goals, constraints, deadlines, affected components, rollback conditions</rule>
            </mandatory-rule>

            <format><![CDATA[
# Intent

**Last updated:** YYYY-MM-DD
**Requester:** {name}
**Work unit:** {concise identifier, e.g., Linear issue ID}

## Goal
{One or two sentences. What outcome does the requester want?}

## Success Criteria
- {Observable, testable criterion 1}
- {Observable, testable criterion 2}

## Scope
### In scope
- {Item 1}

### Out of scope (Non-goals)
- {Item 1}

## Constraints
- {Technical, deadline, budget, compliance}

## Open Questions
- [ ] {Question to resolve before implementation}
            ]]></format>

            <lifecycle>
                <rule>Update intent.md when the requester's intent changes (not every implementation detail)</rule>
                <rule>Historical intent (superseded versions) lives in git history, not in the file</rule>
            </lifecycle>
        </intent-md>

        <handover-md>
            <purpose>The handover document for the NEXT actor (another AI session, a teammate, future self). Optimized to be read in under two minutes.</purpose>
            <path>docs/handover.md</path>

            <format><![CDATA[
# Handover

**Last updated:** YYYY-MM-DD HH:MM (timezone)
**Updated by:** {human name or AI session id}

## Current State
{What is done. One paragraph.}

## In Progress
{What is actively being worked on. Include branch name, PR link, Linear issue.}

## Next Actions
1. {Concrete next step}
2. {...}

## Known Risks / Blockers
- {Item and mitigation}

## Context the Next Actor Needs
- {Non-obvious gotchas, environment quirks, external dependencies}

## Relevant Files and Commands
- `path/to/file.py` - {why it matters}
- `just {command}` - {what it does}
            ]]></format>

            <lifecycle>
                <rule>Update handover.md at the end of every significant work session (session-level granularity, not commit-level)</rule>
                <rule>handover.md is consumable both by humans and AI agents - write for both audiences</rule>
                <rule>Do NOT duplicate content from intent.md; reference it instead</rule>
            </lifecycle>
        </handover-md>

        <relationship>
            <distinction>intent.md answers "Why are we doing this?"</distinction>
            <distinction>handover.md answers "Where are we, and what's next?"</distinction>
            <distinction>docs/*.md (other) answers "What does the current system do?"</distinction>
            <distinction>docs/adr/*.md answers "Why did we decide X in the past?"</distinction>
        </relationship>
    </intent-and-handover-guidelines>

    <semgrep-guidelines>
        <title>.semgrep/ DIRECTORY GUIDELINES</title>
        <description>Project-specific static analysis rules using Semgrep. Becomes critical as the codebase matures; start light at project inception and grow rules as patterns emerge.</description>

        <philosophy>
            <point>Semgrep rules codify the team's "unwritten rules" - things reviewers catch repeatedly in code review</point>
            <point>Write a rule the SECOND time you catch the same issue in review (once is a coincidence, twice is a pattern)</point>
            <point>Rules are lightweight at project start; ruleset density grows toward the middle of the project lifecycle when architectural patterns have stabilized</point>
        </philosophy>

        <directory-structure>
            <pattern>.semgrep/rules/{category}/{rule-id}.yaml</pattern>
            <pattern>.semgrep/tests/{category}/{rule-id}.{py|go|ts|...}</pattern>
            <pattern>.semgrep/README.md - ruleset overview and how to add rules</pattern>
        </directory-structure>

        <rule-file-convention>
            <rule>One semgrep rule per file; filename matches rule id</rule>
            <rule>Use `.yaml` extension (never `.yml`)</rule>
            <rule>Rule id format: `{project-prefix}-{category}-{short-name}` (e.g., `paintress-concurrency-unguarded-goroutine`)</rule>
            <rule>Every rule MUST have a corresponding test file with at least one positive (matching) and one negative (non-matching) example</rule>
        </rule-file-convention>

        <rule-template><![CDATA[
rules:
  - id: paintress-concurrency-unguarded-goroutine
    message: |
      Launching a goroutine without passing a context.Context is forbidden.
      Pass ctx explicitly so the caller can cancel.
    severity: ERROR
    languages: [go]
    pattern: |
      go func() {
        ...
      }()
    metadata:
      category: concurrency
      added: "2026-04-18"
      adr: docs/adr/NNNN-goroutine-context.md
        ]]></rule-template>

        <execution>
            <rule>Add a `just semgrep` task that runs `semgrep --config .semgrep/rules/ --error`</rule>
            <rule>Wire semgrep into CI as a required check before merge</rule>
            <rule>Pre-commit: running semgrep is part of the standard pre-commit checks (alongside ruff and mypy)</rule>
        </execution>

        <when-to-add-a-rule>
            <trigger>The same review comment has been made twice or more</trigger>
            <trigger>An ADR decision needs mechanical enforcement (e.g., "always use Cloud SQL PostgreSQL, never Spanner")</trigger>
            <trigger>A production incident's root cause is expressible as a code pattern</trigger>
        </when-to-add-a-rule>

        <when-not-to-add-a-rule>
            <antitrigger>The pattern is better caught by a type checker (let mypy do its job)</antitrigger>
            <antitrigger>The pattern is better caught by ruff (use ruff's built-in rules)</antitrigger>
            <antitrigger>The rule would produce false positives frequently - tune or drop</antitrigger>
        </when-not-to-add-a-rule>
    </semgrep-guidelines>

    <observability-standards>
        <title>OBSERVABILITY STANDARDS (OpenTelemetry + Jaeger)</title>
        <description>All services MUST emit telemetry via OpenTelemetry. Local development uses Jaeger (https://www.jaegertracing.io/) as the trace backend; production backends are decided per-project in an ADR.</description>

        <scope>
            <in-scope>Distributed tracing (traces + spans)</in-scope>
            <in-scope>Structured logs correlated with trace_id / span_id</in-scope>
            <in-scope>Metrics via OTLP when applicable</in-scope>
            <out-of-scope>Non-OTel-compatible vendor SDKs (use OTel with an exporter instead)</out-of-scope>
        </scope>

        <instrumentation-rules>
            <rule>Every service/binary MUST initialize an OTel TracerProvider at startup</rule>
            <rule>Exporter MUST be OTLP (gRPC preferred: port 4317; HTTP fallback: port 4318)</rule>
            <rule>Endpoint is configured via the standard env var `OTEL_EXPORTER_OTLP_ENDPOINT`</rule>
            <rule>Service name is configured via `OTEL_SERVICE_NAME` and MUST match the tool/module name (e.g., `sightjack`, `paintress`, `amadeus`, `phonewave`, `dominator`)</rule>
            <rule>Propagate W3C Trace Context across process boundaries (default in OTel SDKs)</rule>
            <rule>Do NOT emit PII or secrets as span attributes; scrub before export</rule>
        </instrumentation-rules>

        <python-setup>
            <packages>
                <package>opentelemetry-api</package>
                <package>opentelemetry-sdk</package>
                <package>opentelemetry-exporter-otlp</package>
                <package>opentelemetry-instrumentation-* (choose per framework: fastapi, httpx, sqlalchemy, ...)</package>
            </packages>
            <install-command>uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp</install-command>
        </python-setup>

        <go-setup>
            <packages>
                <package>go.opentelemetry.io/otel</package>
                <package>go.opentelemetry.io/otel/sdk</package>
                <package>go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc</package>
            </packages>
        </go-setup>

        <local-jaeger>
            <description>Local trace viewing uses the Jaeger all-in-one container defined in compose.yaml.</description>
            <compose-service><![CDATA[
# compose.yaml (excerpt)
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: jaeger
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    restart: unless-stopped
            ]]></compose-service>

            <env-for-apps><![CDATA[
# .env or shell
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SERVICE_NAME=paintress
OTEL_TRACES_SAMPLER=parentbased_always_on
            ]]></env-for-apps>

            <justfile-tasks>
                <rule>`just trace-up` starts Jaeger via `docker compose up -d jaeger`</rule>
                <rule>`just trace-down` stops Jaeger</rule>
                <rule>`just trace-view` opens http://localhost:16686 in the browser</rule>
            </justfile-tasks>

            <ui-url>http://localhost:16686</ui-url>
        </local-jaeger>

        <production>
            <rule>Production exporter target is decided per-project and captured in an ADR (e.g., Cloud Trace, Grafana Tempo, Honeycomb)</rule>
            <rule>Do NOT hard-code production endpoints; always use `OTEL_EXPORTER_OTLP_ENDPOINT`</rule>
        </production>

        <minimum-coverage>
            <rule>Every inbound RPC/HTTP handler creates a root span</rule>
            <rule>Every outbound RPC/HTTP client call creates a child span</rule>
            <rule>Every message bus enqueue/dequeue (including D-Mail Protocol inbox/outbox writes) creates a span with `messaging.*` attributes</rule>
            <rule>Every LLM call (Anthropic API, Gemini, etc.) creates a span with `gen_ai.*` attributes (model, input tokens, output tokens, latency)</rule>
        </minimum-coverage>
    </observability-standards>

    <experiments-guidelines>
        <title>experiments/ DIRECTORY GUIDELINES</title>
        <description>Research, preliminary experiments, and exploratory implementations</description>

        <directory-structure>
            <pattern>experiments/README.md - Overview and experiment index</pattern>
            <pattern>experiments/YYYY-MM-DD_{experiment_name}.md - Experiment plan document</pattern>
            <pattern>experiments/run_{experiment_name}_benchmark.sh - Benchmark scripts</pattern>
            <pattern>experiments/test_{experiment_name}.py - Test scripts for experiments</pattern>
        </directory-structure>

        <experiment-document-format>
            <section name="header">
                <field>Date: YYYY-MM-DD</field>
                <field>Objective: Purpose of the experiment</field>
                <field>Status: 🟢 Complete / 🟡 In Progress / ⚪ Not Started</field>
            </section>
            <section name="body">
                <field>Background - Context and motivation</field>
                <field>Hypothesis - Expected outcomes</field>
                <field>Experiment Design - Concrete steps and methodology</field>
                <field>Expected Results - Predictions before execution</field>
                <field>Results - Recorded after execution</field>
                <field>Conclusion - Judgment and next actions</field>
            </section>
        </experiment-document-format>

        <output-structure>
            <preprocessed-dir>
                <description>Preprocessed data organized by experiment and resolution</description>
                <pattern>preprocessed/{experiment_note_name}/{resolution}/</pattern>
                <example>preprocessed/2024-11-24_vae_slicing_experiment/720p/</example>
            </preprocessed-dir>
            <output-dir>
                <description>Generated outputs with parameter information</description>
                <pattern>output/{experiment_note_name}/</pattern>
                <example>output/2024-11-24_vae_slicing_experiment/baseline_720p_steps20_cfg5.0.mp4</example>
            </output-dir>
        </output-structure>

        <file-naming>
            <required>Experiment variable identifier (e.g., baseline vs sage_attention)</required>
            <recommended>Resolution (e.g., 480p, 720p)</recommended>
            <recommended>Step count (e.g., steps20)</recommended>
            <recommended>Guidance scale (e.g., cfg5.0)</recommended>
            <recommended>Other experiment-specific parameters</recommended>
            <example>sage_attention_720p_steps20_cfg5.0.mp4</example>
        </file-naming>

        <readme-maintenance>
            <rule>Keep experiment index table updated</rule>
            <rule>Summary results in README are for reference only - always check full experiment notes</rule>
            <rule>Organize experiments by status: Complete, In Progress, Planned</rule>
        </readme-maintenance>
    </experiments-guidelines>

    <scripts-guidelines>
        <title>scripts/ DIRECTORY GUIDELINES</title>
        <guideline>Shell scripts must use `#!/usr/bin/env bash` as the shebang line for portability</guideline>
        <guideline>Scripts must be implemented to be idempotent</guideline>
        <guideline>Argument processing should be done early in the script</guideline>
        <guideline>Prefer defining common tasks in justfile over individual scripts</guideline>
        <considerations>
            <item>Standardization and Error Prevention</item>
            <item>Developer Experience</item>
            <item>Idempotency</item>
            <item>Guidance for the Next Action</item>
        </considerations>
    </scripts-guidelines>

    <mock-policy>
        <title>MOCK USAGE POLICY</title>
        <description>Guidelines for mock usage across different test types</description>

        <by-test-type>
            <unit-tests>
                <policy>Minimize mock usage - prefer real code over mocks</policy>
                <rule>Avoid overly large or complex mocks</rule>
                <rule>Mock only external dependencies that are impractical to use in tests</rule>
            </unit-tests>
            <integration-tests>
                <policy>Minimal mocks allowed for external services only</policy>
                <rule>Prefer test containers or local instances over mocks</rule>
            </integration-tests>
            <e2e-tests>
                <policy>MOCKS ARE STRICTLY PROHIBITED</policy>
                <rule>All dependencies must be real</rule>
                <rule>Use actual databases, services, and external systems</rule>
                <rule>If a real dependency cannot be used, the test belongs in integration, not e2e</rule>
            </e2e-tests>
        </by-test-type>
    </mock-policy>

    <unittest-guidelines>
        <title>tests/unit/ DIRECTORY GUIDELINES</title>
        <test-structure>
            <phase name="given">Set up the preconditions for the test</phase>
            <phase name="when">Execute the code under test</phase>
            <phase name="then">Verify the results</phase>
        </test-structure>
        <rule>Try-catch blocks are prohibited within tests</rule>
        <rule>Avoid excessive nesting. Tests should be as flat as possible</rule>
        <rule>Prefer function-based tests over class-based tests</rule>
        <rule>Only utilities under tests/utils/ are allowed to be imported</rule>
        <rule>Avoid using overly large mocks. Prefer real code over mocks</rule>
    </unittest-guidelines>

    <e2e-guidelines>
        <title>tests/e2e/ DIRECTORY GUIDELINES</title>
        <description>End-to-end tests verify the complete system with all real dependencies</description>

        <principles>
            <principle>Test the system as a user would experience it</principle>
            <principle>All dependencies must be real - no mocks, stubs, or fakes</principle>
            <principle>Tests should be deterministic and repeatable</principle>
            <principle>Each test should be independent and not rely on other tests</principle>
        </principles>

        <parameterized-tests>
            <rule>Use parameterized tests wherever possible to maximize coverage with minimal code</rule>
            <rule>Group related scenarios into single parameterized test functions</rule>
            <rule>Parameter names should clearly describe the test scenario</rule>
            <example><![CDATA[
@pytest.mark.parametrize(
    "input_data,expected_status,expected_result",
    [
        pytest.param({"valid": "data"}, 200, {"success": True}, id="valid-input-succeeds"),
        pytest.param({}, 400, {"error": "missing fields"}, id="empty-input-fails"),
        pytest.param({"invalid": "schema"}, 422, {"error": "validation"}, id="invalid-schema-fails"),
    ],
)
def test_api_endpoint(input_data, expected_status, expected_result):
    # given
    client = create_real_client()

    # when
    response = client.post("/api/endpoint", json=input_data)

    # then
    assert response.status_code == expected_status
    assert response.json() == expected_result
            ]]></example>
        </parameterized-tests>

        <prohibited>
            <item>Mock objects of any kind</item>
            <item>Stub implementations</item>
            <item>Fake services or in-memory replacements</item>
            <item>Patching or monkey-patching</item>
        </prohibited>

        <required>
            <item>Real database connections</item>
            <item>Real external service calls</item>
            <item>Real file system operations</item>
            <item>Real network communication</item>
        </required>

        <test-structure>
            <phase name="given">Set up real preconditions with actual system state</phase>
            <phase name="when">Execute through the real system entry point</phase>
            <phase name="then">Verify real system state and outputs</phase>
        </test-structure>

        <environment>
            <rule>Use dedicated test environment with real services</rule>
            <rule>Clean up test data after each test or test session</rule>
            <rule>Document required environment setup in tests/e2e/README.md</rule>
        </environment>
    </e2e-guidelines>

    <runn-settings>
        <title>tests/runn/ SCENARIO TEST GUIDELINES</title>
        <description>runn is a scenario-based testing tool for API and CLI testing</description>

        <key-concepts>
            <concept name="runbook">YAML-based scenario definition (use .yaml extension)</concept>
            <concept name="step">Individual action (HTTP request, command execution, etc.)</concept>
            <concept name="vars">Variables passed between steps</concept>
        </key-concepts>

        <file-structure>
            <pattern>tests/runn/*.yaml - Scenario files (NOT .yml)</pattern>
            <pattern>tests/runn/vars/*.yaml - Shared variables (NOT .yml)</pattern>
        </file-structure>

        <guidelines>
            <guideline>Scenarios are realistic and don't require same coverage as unit/integration tests</guideline>
            <guideline>A2A protocol compliance with JSON-RPC 2.0 specification</guideline>
            <guideline>Scenario tests should describe AI Agent actions from Agent perspective</guideline>
        </guidelines>

        <naming>
            <example type="good">Agent requests task delegation</example>
            <example type="bad">POST to /jsonrpc endpoint</example>
        </naming>
    </runn-settings>

    <planning-and-review-standards>
        <title>IMPLEMENTATION PLANNING AND REVIEW</title>
        <description>Mandatory review process using codex before presenting implementation plans to the user</description>

        <mandatory-rule>
            <rule>Always perform a plan review using the `codex` command BEFORE presenting the plan to the user</rule>
        </mandatory-rule>

        <codex-configuration>
            <recommended-model>gpt-5.3-codex</recommended-model>
            <required-flags>-m {model}, --skip-git-repo-check</required-flags>
            <prompt-discipline>
                <must-include>瑣末な点へのクソリプはしないで。致命的な点だけ指摘して。</must-include>
                <optimization-strategy>Gather latest information and URLs into a temporary file and include its path in the prompt to ensure accuracy and counter outdated model knowledge.</optimization-strategy>
            </prompt-discipline>
        </codex-configuration>

        <review-commands>
            <initial-review>
                <description>First review request for a new plan</description>
                <command><![CDATA[codex exec -m gpt-5.3-codex --skip-git-repo-check "このプランをレビューして。瑣末な点へのクソリプはしないで。致命的な点だけ指摘して: {plan_full_path} (ref: {CLAUDE.md full_path})"]]></command>
            </initial-review>
            <updated-review>
                <description>Review request for an updated plan (requires context retention)</description>
                <rule>Must use `resume --last` to maintain the context of the previous review</rule>
                <command><![CDATA[codex exec resume --skip-git-repo-check --last -m gpt-5.3-codex "プランを更新したからレビューして。瑣末な点へのクソリプはしないで。致命的な点だけ指摘して: {plan_full_path} (ref: {CLAUDE.md full_path})"]]></command>
            </updated-review>
        </review-commands>

        <error-handling>
            <rate-limit>
                <condition>If a rate limit error occurs (e.g., "ERROR: You've hit your usage limit..."), skip the codex review process</condition>
                <example-error>ERROR: You've hit your usage limit. To get more access now, send a request to your admin or try again at Feb 27th, 2026 10:02 PM.</example-error>
            </rate-limit>
        </error-handling>
    </planning-and-review-standards>

    <workflow>
        <title>EXAMPLE WORKFLOW</title>
        <steps>
            <step number="1">Write a simple failing test for a small part of the feature</step>
            <step number="2">Implement the bare minimum to make it pass</step>
            <step number="3">Run tests to confirm they pass (Green): `just test`</step>
            <step number="4">Run linting, type checks, and semgrep: `just lint` (include `just semgrep` when .semgrep/ exists)</step>
            <step number="5">Make any necessary structural changes (Tidy First), running tests after each change</step>
            <step number="6">Commit structural changes separately (Conventional Commits: refactor/style/test/docs/chore/build/ci)</step>
            <step number="7">Add another test for the next small increment of functionality</step>
            <step number="8">Repeat until complete, committing behavioral changes separately (Conventional Commits: feat/fix/perf)</step>
            <step number="9">If the change involves significant architectural decisions, create an ADR</step>
            <step number="10">Update docs/handover.md at end of session; update docs/intent.md if requester intent changed</step>
        </steps>
        <principle>Always write one test at a time, make it run, then improve structure</principle>
        <principle>Always run all tests (except long-running) each time</principle>
        <principle>Always run ruff, mypy, and semgrep (when applicable) before committing</principle>
        <principle>Use just commands for common tasks</principle>
    </workflow>

    <workflow-example>
        <title>CONCRETE TDD EXAMPLE</title>
        <scenario>Adding a new validation function</scenario>

        <step number="1" phase="red">
            <description>Write failing test</description>
            <code><![CDATA[
def test_validate_email_rejects_missing_at_symbol():
    # given
    invalid_email = "userexample.com"

    # when
    result = validate_email(invalid_email)

    # then
    assert result is False
            ]]></code>
        </step>

        <step number="2" phase="green">
            <description>Minimum implementation with type annotations</description>
            <code><![CDATA[
def validate_email(email: str) -> bool:
    return "@" in email
            ]]></code>
        </step>

        <step number="3" phase="verify">
            <description>Run linting and type checks</description>
            <commands>
                <command>just lint</command>
                <command>just fmt</command>
                <command>just semgrep  # when .semgrep/ exists</command>
            </commands>
            <alternative>
                <command>uv run ruff check .</command>
                <command>uv run ruff format .</command>
                <command>uv run mypy .</command>
            </alternative>
        </step>

        <step number="4" phase="refactor">
            <description>Structural improvement (separate commit)</description>
            <action>Extract to validation module if pattern emerges</action>
            <commit-example>refactor(validation): extract email validator into dedicated module</commit-example>
        </step>
    </workflow-example>

    <ai-assistant-directives>
        <title>DIRECTIVES FOR AI ASSISTANT</title>

        <response-format>
            <rule>Always indicate which TDD phase (Red/Green/Refactor) the suggestion belongs to</rule>
            <rule>Propose commit messages in Conventional Commits format; the type prefix encodes STRUCTURAL vs BEHAVIORAL (see commit-discipline section)</rule>
            <rule>When proposing code changes, show the test first</rule>
            <rule>Always include type annotations in Python code suggestions</rule>
            <rule>Use .yaml extension when creating YAML files, never .yml</rule>
            <rule>Use `compose.yaml` for Docker Compose files, never `docker-compose.yaml`</rule>
        </response-format>

        <ascii-art-guidelines>
            <title>ASCII ART AND DIAGRAM GUIDELINES</title>
            <description>Rules for creating text-based visualizations that render correctly</description>

            <character-restrictions>
                <rule>Use ONLY ASCII characters (single-byte) in diagrams</rule>
                <prohibited>Japanese (日本語), Chinese (中文), Korean (한국어), emoji (🔥), and other multi-byte characters</prohibited>
                <reason>Multi-byte characters cause misalignment in monospace rendering</reason>
            </character-restrictions>

            <legend-requirement>
                <rule>ALWAYS include a legend directly below the ASCII art</rule>
                <rule>Legend must provide Japanese translations unless explicitly instructed otherwise</rule>
                <format>English term: Japanese translation</format>
            </legend-requirement>

            <example><![CDATA[
+-------------------+
|   Request Handler |
+-------------------+
         |
         v
+-------------------+
|   Validator       |
+-------------------+
         |
         v
+-------------------+
|   Repository      |
+-------------------+

Legend / 凡例:
- Request Handler: リクエストハンドラー
- Validator: バリデーター
- Repository: リポジトリ
            ]]></example>
        </ascii-art-guidelines>

        <prohibited-actions>
            <action>Never suggest untested code for production</action>
            <action>Never mix structural and behavioral changes in one suggestion</action>
            <action>Never skip the failing test step</action>
            <action>Never suggest mocks in e2e tests</action>
            <action>Never suggest code that would fail ruff or mypy checks</action>
            <action>Never suggest modifying the ruff configuration</action>
            <action>Never suggest using pip, npm, yarn, or make (pnpm is allowed only when pnpm-lock.yaml exists)</action>
            <action>Never use .yml extension for YAML files</action>
            <action>Never use `docker-compose.yaml` or `docker-compose.yml` as a filename; use `compose.yaml`</action>
            <action>Never use `[STRUCTURAL]` or `[BEHAVIORAL]` tags in commit messages (use Conventional Commits types instead)</action>
            <action>Never create or update docs/intent.md with guessed intent; always clarify with the human first</action>
            <action>Never create multiple justfiles in subdirectories; there MUST be exactly one at the root</action>
            <action>Never use multi-byte characters (Japanese, Chinese, Korean, emoji) inside ASCII art diagrams</action>
        </prohibited-actions>

        <encouraged-actions>
            <action>Ask clarifying questions before writing code</action>
            <action>Suggest smaller increments if proposed change is large</action>
            <action>Point out missing test cases</action>
            <action>Recommend parameterized tests when multiple similar scenarios exist</action>
            <action>Include ruff, mypy, and semgrep verification steps in suggestions</action>
            <action>Suggest creating an ADR when proposing significant architectural changes</action>
            <action>Suggest adding a semgrep rule when the same review comment appears twice</action>
            <action>Suggest updating docs/handover.md at the end of a work session</action>
            <action>Use uv for Python package operations</action>
            <action>Use bun for Node.js package operations (use pnpm only when pnpm-lock.yaml exists)</action>
            <action>Use just commands for task automation</action>
            <action>Include Japanese legend below ASCII art diagrams</action>
        </encouraged-actions>
    </ai-assistant-directives>
</development-guidelines>