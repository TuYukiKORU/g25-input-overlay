# Validation policy

The user prefers fewer test runs at the end of each chat. Apply the testing
guidance in [CONTRIBUTING.md](CONTRIBUTING.md#testing) to changes made for the
current request, accounting for relevant dependencies.

- Default to the smallest meaningful set of existing tests for the changed
  behavior. Include affected callers and failure/lifecycle paths when relevant.
- Do not run the full suite merely because a chat is ending, or because the
  working tree contains unrelated changes from earlier work.
- Reuse passing results while the relevant code is unchanged. After a fix,
  rerun failed and affected checks; expand coverage only for an identified risk.
- Documentation and copy-only edits need review and `git diff --check`, not
  application tests. Frontend-only changes do not normally need Python tests.
- For visible UI behavior, verify one affected browser workflow. Repeat it only
  after a relevant fix or when something remains unresolved. Avoid unrelated
  screenshots, app restarts, desktop launches, or package builds.
- Run performance measurements for performance changes or investigations.
  Once a representative check answers the question, do not repeat benchmarks
  just for final confirmation.
- Reserve a full-suite run for changes spanning multiple subsystems, shared
  data/API contracts, dependencies, desktop lifecycle/security, or a release.
  Run it once on the final relevant code; do not also rerun overlapping targeted
  tests afterward without a reason.
- Keep existing regression tests. Add tests for meaningful new behavior or bugs,
  not trivial reversible edits or tests that only mirror implementation details.
- Report checks actually run and any material verification gap concisely.
