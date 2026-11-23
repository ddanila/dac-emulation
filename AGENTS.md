# Instructions for this repository

These add to `../AGENTS.md`.

## Tests

Tests must stay lean and must survive correct changes to the thing they test.

- **Test behaviour, not bytes.** A test checks a tool's logic, or a value
  against a limit or a documented target. It does not require a fresh result
  to equal a saved report file, and it does not compare stored input hashes
  with current files.
- **Do not chain reports by hash.** A report or tool must not refuse to run
  because an upstream report or schematic changed since it was saved. Record a
  hash for provenance if useful; do not gate on it.
- **A stale test is deleted or rewritten, never "refreshed".** If a test fails
  only because an input was corrected, keep its value checks and drop the pin.
  If nothing is left, delete the test. Do not regenerate a saved report just to
  make a test pass.
- **Exact pinning is for frozen deliverables only**, such as a published frame
  and its report, or retained evidence that a plan names as final.
- **No test for work that is closed.** A screen, audit or comparison that a
  plan no longer continues does not get new tests.
- **Keep CI cheap.** Do not add a workflow, a job or a wider trigger without a
  stated reason that covers its run minutes. The monitor study
  (`verification/robotron-monitor`) has no CI job; run `make test-monitor`
  locally.

## Documents

Plans and other `.md` files show the current state, not the path to it. No
work logs, dated narratives or run results: results go in report files,
history goes in commit messages. Edit a changed line in place.
