# Phase 5 Completion Report — Native Walls and Floors

**Version:** 0.8.3  
**Date:** 2026-11-01  
**Status:** Implemented and automatically verified. Import, analysis and
generation now share one staged Workspace window. Native geometry creation in
Revit is **not yet manually verified**.

## 1. Scope delivered

| Capability | State |
| --- | --- |
| Ordered boundaries on segmentation instances | Working, tested |
| Confidence-filtered reconstruction plan | Working, tested |
| Floor level clustering | Working, tested |
| Closed floor polygons | Working, tested |
| Wall lines with base level and height | Working, tested |
| `reconstruction.plan` JSON-RPC method | Working, tested |
| External AI plan JSON validation (`PLAN_INVALID`) | Working, tested |
| GPT-6 Astra BYO provider (`gpt-6-astra`, `OPENAI_API_KEY`) | Implemented; mocked tests pass, live API not exercised |
| GPT-6 Astra subscription gateway client | Implemented; mocked tests pass, backend not yet built |
| Generate BIM preview stage in the Workspace window | Implemented, XAML probe passed |
| Native Revit `Floor.Create` / `Wall.Create` | Implemented, build-tested; manual check pending |
| Existing level reuse / missing level creation | Implemented; manual check pending |
| `REVO-INFERRED` marking | Implemented; manual check pending |
| Transaction rollback | Implemented; manual check pending |
| Doors, windows, ceilings, stairs, curves | **Not implemented** |
| Dimensional accuracy | **Not measured** |

## 2. Pipeline

```
segmentation.json
  → confidence filter
  → level clustering from floor elevations
  → closed floor boundary polygons
  → wall lines, base levels and ceiling/fallback heights
  → reconstruction-plan.json
  → Generate BIM preview
  → one Revit transaction: levels, floors, walls
```

- The plan is written to `<scan store>/analysis/reconstruction-plan.json`.
- Existing Revit levels within 0.01 m are reused; otherwise levels are created.
- Floors use default non-foundation floor types.
- Walls use the first basic wall type.
- Created elements receive `Comments` and `Mark = REVO-INFERRED`.
- A failed transaction rolls back; no placeholder geometry is created.

## 3. Automated evidence

| Check | Result |
| --- | --- |
| Python tests | **65 passed** |
| .NET tests | **32 passed** |
| Revit 2026 Release build | **0 warnings, 0 errors** |
| Revit 2027 Release build | **0 warnings, 0 errors** |
| WPF probe (single workspace with all stages, settings, about) | **Passed** |
| Synthetic room plan | **1 level, 1 floor, 4 walls** |
| Real C# → Python `reconstruction.plan` | **Passed** |
| Real 27.8M-point E57 plan | **2 levels, 3 floors, 0 walls** |
| External AI plan validation and normalization | **Passed** |
| Invalid external plan rejected with `PLAN_INVALID` | **Passed** |
| Astra provider request/response path (mocked) | **Passed** |
| Missing `OPENAI_API_KEY` rejected with `AI_PROVIDER_FAILED` | **Passed** |
| Subscription gateway path with mocked response | **Passed** |
| Missing subscription token rejected with `SUBSCRIPTION_REQUIRED` | **Passed** |

The real scan did not produce a wall instance above the 0.75 confidence
threshold; the plan therefore contains floors only. That is an honest result,
not a wall-creation test.

## 4. What is deliberately not claimed

- **Native floor/wall creation is not yet verified in Revit.** The C# compiles
  and the plan is tested, but `Floor.Create`/`Wall.Create` have not been observed
  on a real project.
- Floor boundaries are convex hulls; concave or L-shaped rooms are simplified.
- Wall planes are reduced to one line and are not merged.
- Default types are used; wall thickness is not applied.
- No ceilings, doors, windows, furniture, stairs or curved elements.
- No dimensional accuracy claim.
- No cancellation or progress percentage.

## 5. Manual verification required

1. Install 0.8.3 for Revit 2026 and 2027.
2. On the unsigned-add-in security prompt choose **Always Load**; choosing
   "Do Not Load" hides the Revo tab.
3. Import a scan and confirm the **Revo Point Cloud Reference** appears in a 3D
   view as sampled markers in scan coordinates.
4. Use the sidebar **Show/Hide point cloud reference** button and confirm the
   element is removed and rebuilt without errors. Save and reopen the project to
   confirm the reference persists and the button state is detected.
5. Use the sidebar **2 Analyze scan** stage, then select **3 Generate BIM**.
6. Click **Create preview** and confirm levels/floors/walls without any model
   change. Optionally repeat with **PLAN SOURCE → External plan JSON** and a
   validated plan file, or **Revo AI (subscription)** when signed in.
7. Click **Create in Revit**.
8. Confirm native floors/walls, `REVO-INFERRED`, correct levels and no crash.
9. Repeat for the other Revit version.

Manual Scan Analysis verification is also still pending.
