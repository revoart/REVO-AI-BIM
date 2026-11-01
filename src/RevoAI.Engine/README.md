# RevoAI.Engine

Local Python processing engine for Revo AI BIM.

Phase 3 implements the point cloud engine:

- `revoai_engine.service` - newline-delimited JSON-RPC 2.0 over stdin/stdout
- `initialize`, `ping`, `shutdown`
- `pointcloud.import`, `pointcloud.info`, `pointcloud.query`
- E57, LAS, LAZ, PLY and XYZ/TXT readers
- unit detection and explicit override, with source bounds preserved
- optional statistical outlier removal and voxel downsampling
- chunked NPZ stores with a 3D grid index
- bounds, radius, nearest and sample queries
- structured stderr/file logging

AI segmentation and geometry reconstruction are added in Phases 4-5. No
capability is reported unless it is implemented.
