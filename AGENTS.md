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

## Repository size

Git holds sources, inputs and conclusions, not bulk output.

- **Not committed:** raw solver traces and logs, waveform dumps, archives
  (`.xz`, `.gz`, `.tar.*`, split parts), compiled simulator or build output
  (`.vvp`, `.vpi`, objects, binaries), and anything that a script in the
  repository can regenerate.
- **Committed:** the summary report (JSON), the deck or other input that
  reproduces it, and the hashes of the raw files it was made from.
- A single file over 1 MB needs a reason stated in the commit message.
- CI does not re-verify raw output. It runs logic tests and checks that read
  summaries.

## Documents

Plans and other `.md` files show the current state, not the path to it. No
work logs, dated narratives or run results: results go in report files,
history goes in commit messages. Edit a changed line in place.
