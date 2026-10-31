# AI Model Documentation

## Current status

**No AI model exists in this repository.** Phase 1 contains no training code,
no weights, no datasets and no inference path. The `models/` folder is empty by
design.

Any claim of AI capability before Phase 4 would be false.

## Planned scope (Phase 4)

- Semantic segmentation of architectural point clouds into: exterior wall,
  interior wall, floor, ceiling, column, beam, door, window, stair, roof,
  railing, other, unclassified.
- Instance separation for repeated elements (doors, windows, columns).
- Per-instance confidence, bounding box, point references and detection method.

## Architecture evaluation (planned)

- Point Transformer v3 and at least one lighter baseline (e.g. RandLA-Net or a
  KPConv variant) on identical splits.
- Evaluate accuracy, memory, GPU/CPU latency and robustness to scan noise.
- Choose based on measured results, not popularity.

## Data and licensing rules

- Do not train on fabricated labels.
- Every dataset must have a recorded licence that permits commercial training.
- Customer scans require explicit written permission and must be de-identified.
- Synthetic data may be used for augmentation only if its generation method is
  documented and its domain gap is measured.
- Class definitions and annotation guidelines live in `docs/` when Phase 4
  starts.

## Reproducibility requirements (Phase 4)

- Pin dataset version, split hash, code commit, hyperparameters and hardware.
- Report precision, recall, F1 and IoU per class, not only a global score.
- Publish confusion matrices and failure examples.
- Keep model artefacts versioned and checksummed; never commit weights to Git.

## Phase 1 boundary

The only Python "intelligence" present is deterministic unit conversion. That is
intentional: the pipeline must be trustworthy before intelligence is added.
