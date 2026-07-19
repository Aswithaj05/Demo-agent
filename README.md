# Test-Agents

Agents for QA/test-engineering workflows.

## Regression Test Suite Optimiser

A Claude Code subagent that analyses a code-change diff and recommends the
minimal regression suite that covers the impacted paths — targeting a >=30%
cut in regression run time with no coverage loss. Runs entirely inside
Claude Code: **no API key, no installs**.

Definition: `.claude/agents/regression-suite-optimiser.md`

### How to use

1. Copy the `.claude` folder into your project:

   ```powershell
   Copy-Item -Recurse .claude C:\path\to\your\project\
   ```

2. Open Claude Code in that project and ask:

   > which tests should I run for my current changes?

   or explicitly:

   > use the regression-suite-optimiser on my branch vs origin/main

### What the report contains

1. **Verdict** — "Run N of M tests (~X% of suite, est. Y% time saved)" or
   "Run the full suite because ...", with a confidence level and the
   evidence tier (coverage data > import tracing > naming conventions).
2. **Run commands** — copy-pasteable, using the project's actual runner and
   runner-native selection flags.
3. **Selected tests** — each with the changed symbol that reaches it.
4. **Excluded tests** — with justifications (the coverage-loss proof).
5. **Risk flags** — dynamic-dispatch hazards, stale coverage artifacts,
   pre-existing coverage gaps.
6. **Runtime estimate** — from real timing data when available.

### Safety rails

- Read-only: never modifies the repo, never executes the test suite.
- Runtime-dependency, migration, CI-config, or DI-wiring changes force a
  full-suite recommendation — static tracing is unreliable there.
- Tests covering security/auth, payments, migrations, and serialization are
  never trimmed when the change touches those areas.
- Every exclusion needs a stated justification; every changed hunk must map
  to at least one selected test or be reported as a pre-existing gap.
- Low confidence always widens the suite.

## Sample project

`sample_project/` is a small Python app with a pytest suite, used to
demonstrate and test the optimiser against a real diff.
