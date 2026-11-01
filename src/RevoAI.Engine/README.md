# RevoAI.Engine

Local Python processing engine for Revo AI BIM.

Phases 3-4 implement the point cloud engine and Scan Analysis baseline:

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
- structured stderr/file logging

The Phase 4 method is a deterministic geometric baseline, not a trained neural
network. BIM geometry reconstruction is added in Phase 5. No capability is
reported unless it is implemented.
