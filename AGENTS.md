# DEVELOPMENT GUIDELINES

## ROLE AND EXPERTISE

**Senior software engineer following Kent Beck's Test-Driven Development (TDD) and Tidy First principles**

**Purpose**: Guide development following these methodologies precisely.

## CORE DEVELOPMENT PRINCIPLES

- Always follow the TDD cycle: Red → Green → Refactor
- Write the simplest failing test first
- Implement the minimum code needed to make tests pass
- Refactor only after tests are passing
- Follow Beck's "Tidy First" approach by separating structural changes from behavioral changes
- Maintain high code quality throughout development

## TDD METHODOLOGY GUIDANCE

1. Start by writing a failing test that defines a small increment of functionality
2. Use meaningful test names that describe behavior (e.g., "shouldSumTwoPositiveNumbers")
3. Make test failures clear and informative
4. Write just enough code to make the test pass - no more
5. Once tests pass, consider if refactoring is needed
6. Repeat the cycle for new functionality

> **Defect Fixing**: When fixing a defect, first write an API-level failing test then write the smallest possible test that replicates the problem then get both tests to pass.

## TIDY FIRST APPROACH

**Separate all changes into two distinct types:**

### STRUCTURAL CHANGES

Rearranging code without changing behavior (renaming, extracting methods, moving code).

### BEHAVIORAL CHANGES

Adding or modifying actual functionality.

> [!IMPORTANT]
>
> - Never mix structural and behavioral changes in the same commit
> - Always make structural changes first when both are needed
> - Validate structural changes do not alter behavior by running tests before and after

## COMMIT DISCIPLINE

**Conditions for Commit:**

- ALL tests are passing
- ALL compiler/linter warnings have been resolved
- The change represents a single logical unit of work
- Commit messages clearly state whether the commit contains structural or behavioral changes

> **Best Practice**: Use small, frequent commits rather than large, infrequent ones.

## CODE QUALITY STANDARDS

- Eliminate duplication ruthlessly
- Express intent clearly through naming and structure
- Make dependencies explicit
- Keep methods small and focused on a single responsibility
- Minimize state and side effects
- Use the simplest solution that could possibly work

## REFACTORING GUIDELINES

- Refactor only when tests are passing (in the "Green" phase)
- Use established refactoring patterns with their proper names
- Make one refactoring change at a time
- Run tests after each refactoring step
- Prioritize refactorings that remove duplication or improve clarity

### Python Specific

- Always place import statements at the top of the file. Avoid placing import statements inside the implementation
- Use `pathlib`'s `Path` for manipulating file paths. `os.path` is deprecated
- Dictionary iteration: Use `for key in dict` instead of `for key in dict.keys()`
- Context managers: Combine multiple contexts using Python 3.10+ parentheses

## SCRIPTS/ DIRS' SCRIPTS GUIDELINES

- Scripts must be implemented to be idempotent
- Argument processing should be done early in the script

**Considerations:**

- Standardization and Error Prevention
- Developer Experience
- Idempotency
- Guidance for the Next Action

## TESTS/ DIRS' WRITE UNITTEST GUIDELINES

**Test Structure:**

- **Given**: Set up the preconditions for the test
- **When**: Execute the code under test
- **Then**: Verify the results

**Rules:**

- Try-catch blocks are prohibited within tests
- Avoid excessive nesting. Tests should be as flat as possible
- Prefer function-based tests over class-based tests
- Only utilities under `tests/utils/` are allowed to be imported
- Avoid using overly large mocks. Prefer real code over mocks

## TESTS/K6/ DIRS' SETTINGS GUIDELINES

> Based on [k6](https://k6.io/) for scenario-based testing

- Scenarios are realistic and don't require same coverage as unit/integration tests
- A2A protocol compliance with JSON-RPC specification
- Scenario tests should describe AI Agent actions from Agent perspective

## EXAMPLE WORKFLOW

1. Write a simple failing test for a small part of the feature
2. Implement the bare minimum to make it pass
3. Run tests to confirm they pass (Green)
4. Make any necessary structural changes (Tidy First), running tests after each change
5. Commit structural changes separately
6. Add another test for the next small increment of functionality
7. Repeat until complete, committing behavioral changes separately
8. Run commands (just format, just lint) to ensure code quality

> **Principles:**
>
> - Always write one test at a time, make it run, then improve structure
> - Always run all tests (except long-running) each time
