# External BIM Plan Contract

Revo AI BIM can consume a floor/wall plan produced by an external AI tool
(Claude, Astra 6, or a custom model) instead of the built-in geometric baseline.

This is a **file contract**, not a live API connection. The external tool writes
one JSON file; Revo validates it, writes a normalized copy beside the scan, shows
it in the Generate BIM stage, and only then can the user create Revit geometry.

## Workflow

1. Import the scan in Revo AI BIM.
2. Let the external tool read the scan or the Revo metadata/summary.
3. The tool writes `bim-plan.json` in **metres**, using the scan's coordinate
   system.
4. In **Generate BIM**, enable **Use an external AI BIM plan (JSON)** and choose
   the file.
5. Click **Create preview**. Revo validates and normalizes the plan.
6. Review levels, floors and walls, then click **Create in Revit**.

The normalized plan is written to:

```
<scan store>/analysis/reconstruction-plan.json
```

## JSON schema

```json
{
  "method": "claude-or-astra-model-name/version",
  "levels": [
    {
      "id": "L1",
      "name": "Level 1",
      "elevationMeters": 0.0
    }
  ],
  "floors": [
    {
      "id": "F1",
      "sourceSegmentId": "optional-source-id",
      "levelId": "L1",
      "boundary": [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [4.0, 3.0, 0.0],
        [0.0, 3.0, 0.0]
      ],
      "areaM2": 12.0,
      "confidence": 0.91
    }
  ],
  "walls": [
    {
      "id": "W1",
      "sourceSegmentId": "optional-source-id",
      "levelId": "L1",
      "start": [0.0, 0.0, 0.0],
      "end": [4.0, 0.0, 0.0],
      "heightMeters": 2.7,
      "heightSource": "external",
      "confidence": 0.88
    }
  ]
}
```

### Required

- `levels` must be a non-empty array.
- Each level needs a unique `id` and a finite `elevationMeters`.
- Each floor needs a known `levelId` and at least three finite XYZ boundary
  points.
- Each wall needs a known `levelId`, finite XYZ `start`/`end`, and a height
  between 0.5 and 10 m.
- All coordinates are metres and must lie inside or near the scan bounds.

### Optional

- `name`, `sourceSegmentId`, `areaM2`, `confidence`, `heightSource`, `method`.
- Missing confidence is recorded as `0` with a warning.
- Missing wall height uses the fallback from the Generate BIM stage.
- `rooms`, `openings` and `ceilings` are currently ignored with a warning.

## Validation

The engine rejects a plan with `PLAN_INVALID` (`-32027`) when:

- JSON is malformed or not an object.
- `levels` is empty or a level id is duplicated.
- A floor/wall references an unknown level.
- A coordinate is non-finite or far outside the scan bounds.
- A floor boundary has fewer than three points.
- A wall is shorter than 0.3 m or has an invalid height.
- Confidence is outside 0–1.

## What the external model should be given

Recommended context for Claude or Astra 6:

- Scan ID, bounds, units and format.
- Point count and chunk summary.
- Optional `segmentation.json` segments with confidence.
- This schema, including the metre coordinate system.
- An instruction to return only valid JSON and to mark inferred elements with
  confidence.

Do not provide customer scans to an external service without written permission.

## Current limitations

- The external AI is not called directly by Revo yet; the JSON file is the
  integration boundary.
- Only levels, floors and walls are created. Rooms, doors, windows, ceilings,
  stairs and curved surfaces are not yet mapped to Revit.
- External output is not dimensional-accuracy proof. The user must review it.
- The external model's confidence is recorded verbatim; it is not a measured
  accuracy guarantee.
