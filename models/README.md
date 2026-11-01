# Models

Trained model artefacts belong here from a future ML phase onward. The Phase 4
Scan Analysis baseline is deterministic geometry and uses no model weights.

Rules:

- Never commit weights (`*.pt`, `*.pth`, `*.onnx`) to Git; they are ignored.
- Each artefact needs a manifest: version, training commit, dataset version and
  hash, metrics, licence of training data.
- No model is used unless its manifest and evaluation report exist.

This folder is intentionally empty in Phase 1.
