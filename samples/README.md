# Samples

Local scan fixtures used for development and acceptance testing.

- Customer scans must never be committed.
- Scan binaries are git-ignored.
- Keep a small, legally redistributable fixture for automated tests from
  Phase 3, plus a written description of its source and licence.

Suggested layout:

```
samples/
├─ README.md
├─ synthetic/          generated geometry with known ground truth
├─ public/             openly licensed scans (record licence)
└─ private/            local-only customer data (git-ignored)
```
