# RevoAI.Engine

Local Python processing engine for Revo AI BIM.

Phases 3-5 implement the point cloud engine, Scan Analysis and reconstruction
planning:

- `revoai_engine.service` - newline-delimited JSON-RPC 2.0 over stdin/stdout
- `initialize`, `ping`, `shutdown`
- `pointcloud.import`, `pointcloud.info`, `pointcloud.query`
- E57, LAS, LAZ, PLY and XYZ/TXT readers
- unit detection and explicit override, with source bounds preserved
- optional statistical outlier removal and voxel downsampling
- chunked NPZ stores with a 3D grid index
- bounds, radius, nearest and sample queries
- `segmentation.run`, `segmentation.info`
- geometric floor/ceiling/wall plane segmentation with plane-fit confidence
- `reconstruction.plan` with levels, floor polygons and wall lines
- structured stderr/file logging

The analysis method is a deterministic geometric baseline, not a trained neural
network. The reconstruction plan is Revit-ready data; the C# add-in owns the
Revit transaction. No capability is reported unless it is implemented.
