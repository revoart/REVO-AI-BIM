# Scan-to-BIM agent contract

This document is the governing behaviour for the Revo scan-to-BIM agent. The
agent is a surveyor first and a modeller second.

## Core principle

```
MEASURE -> WRITE A SCHEDULE -> BUILD FROM THE SCHEDULE -> VERIFY AGAINST THE SCAN
```

Every element must trace to a measurement or be explicitly labelled `ASSUMED`.
Anything weak is tagged `VERIFY` and listed in the delivery report.

## Hard rules

1. Do not invent features. Model the most likely element where evidence is weak,
   but tag it `VERIFY`.
2. Openings are real voids cut through hosts. Doors and windows are hosted in
   those openings, never surface decals.
3. Separate `MEASURED` from `ASSUMED` (wall thickness, floor build-up, roof
   thickness, footings, interior layout). Label every assumption.
4. Never silently change units, axes or datum. State them once, then keep them.
5. One coordinate system for scan, schedule, model and drawings.
6. Exterior-only or partial scans must not be used to fabricate interiors.

## Pipeline

### Step 0 — Ingest and sanity check

- Read the header: point count, attributes, bounds.
- Detect units and state confidence; ask if uncertain.
- Work on a voxel-downsampled copy; keep the full cloud for verification.

### Step 1 — Orient and level

- Fit the ground/floor plane and correct tilt.
- Find dominant yaw and axis-align the main walls.
- Re-check ground flatness and wall verticality.

### Step 2 — Find the structure

- Floor levels and storeys from Z histograms.
- Wall planes from horizontal slices, cleaned and clustered.
- Footprint polygon, recesses, bays and wings.
- Roof pitch/ridge/eaves where visible; mark assumed where not scanned.
- Steps, plinths, ramps, retaining walls and thresholds.

### Step 3 — Orthographic projections for openings

- Depth-buffered orthographic images from each side, plan and sections.
- Verify the axis direction before measuring. The right-hand direction changes
  with the viewing side.
- Measure opening left/right, sill and head, host wall and position.
- Classify windows, doors, garage doors, panels, vents, louvres and storefronts.
- Use colour/intensity as evidence, confirm with geometry.

### Step 4 — Write the schedule

The schedule is the only input to the build step. Every item carries:

- `id`
- `host`
- position along host
- sill/head or base/top
- `source`: `MEASURED` or `ASSUMED`
- `confidence`: `high`, `medium` or `low`
- `VERIFY` when evidence is weak

### Step 5 — Build from the schedule

Order: levels and grids, walls, openings, windows/doors, roof, floors, stairs,
columns, small items. Use native elements. If a native type is unavailable, say
so; do not silently skip.

### Step 6 — Verify against the scan

- Overlay elevations on the scan projections.
- Report any edge more than 0.15 ft / 5 cm from the scan.
- Compute cloud-to-model distance (mean, median, 95th percentile).
- Re-render the model with the point cloud in the same coordinates.
- Fix the schedule first, then rebuild.

### Step 7 — Deliver

- Native model + IFC.
- Plan, four elevations and a section.
- Scan-vs-model overlay sheet.
- Schedule JSON.
- Report: units/datum, tilt/yaw corrections, accuracy statistics, assumptions,
  VERIFY items and what the scan could not capture.

## Current implementation status

| Capability | Status |
| --- | --- |
| Point-cloud import, units, bounds, chunked store | Implemented |
| Voxel downsample and outlier removal | Implemented |
| Ground/level fitting and yaw correction | Not implemented; plan records `not applied` |
| Floor plane detection | Implemented (RANSAC baseline) |
| Floor deduplication and minimum level separation | Implemented (1.2 m minimum; largest slab per level) |
| Wall plane detection and centrelines | Implemented (RANSAC baseline) |
| Levels, floors, walls in Revit | Implemented with a safety gate |
| Unit confirmation for PLY/XYZ | Implemented; Auto is blocked |
| Wall thickness measurement | Not implemented; assumed default type |
| Openings, doors, windows | Not implemented; listed as unavailable |
| Ceilings, roofs, columns, stairs | Not implemented; listed as unavailable |
| Measurement report with units/datum/axes/assumptions/VERIFY | Implemented in the plan JSON |
| Build blocking for assumed units/incoherent floors | Implemented |
| Cloud-to-model distance verification | Not implemented; no accuracy claim |
| Orthographic projection measurement | Not implemented |
| Point-cloud overlay | Known issue: tessellation build fails in Revit 2027; line fallback unverified |

The agent must not claim the unimplemented capabilities. It can still produce a
traceable floor/wall schedule and report every assumption.
