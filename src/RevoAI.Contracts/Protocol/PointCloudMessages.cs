namespace RevoAI.Contracts.Protocol;

/// <summary>
/// Axis-aligned bounds. Import/query <c>bounds</c> are metres; <c>sourceBounds</c>
/// is in the file's source unit.
/// </summary>
public sealed class Bounds3
{
    public required double[] Min { get; init; }

    public required double[] Max { get; init; }
}

/// <summary>Point counts at each stage of import and preprocessing.</summary>
public sealed class PointCounts
{
    public required int Original { get; init; }

    public required int Valid { get; init; }

    public required int AfterOutlierRemoval { get; init; }

    public required int AfterDownsampling { get; init; }

    public required int Stored { get; init; }
}

/// <summary>Parameters for <c>pointcloud.import</c>.</summary>
public sealed class PointCloudImportParams
{
    public required string Path { get; init; }

    /// <summary>Optional explicit format: e57, las, laz, ply or xyz.</summary>
    public string? Format { get; init; }

    /// <summary>
    /// Source unit: auto, millimeters, centimeters, meters, inches, feet or
    /// usSurveyFeet. <c>auto</c> uses reliable file metadata and otherwise
    /// assumes metres.
    /// </summary>
    public string Unit { get; init; } = "auto";

    public required string OutputDirectory { get; init; }

    public string? ScanId { get; init; }

    public double ChunkSizeMeters { get; init; } = 25.0;

    public double? VoxelSizeMeters { get; init; }

    public bool RemoveOutliers { get; init; }

    public int OutlierNeighbors { get; init; } = 20;

    public double OutlierStdRatio { get; init; } = 2.0;

    public bool Overwrite { get; init; }
}

/// <summary>Result of a successful point cloud import.</summary>
public sealed class PointCloudImportResult
{
    public required string ScanId { get; init; }

    public required string StorePath { get; init; }

    public required string SourcePath { get; init; }

    public required string Format { get; init; }

    public required string Unit { get; init; }

    /// <summary>format, header, user or assumed.</summary>
    public required string UnitSource { get; init; }

    public required PointCounts PointCount { get; init; }

    public required Bounds3 Bounds { get; init; }

    public required Bounds3 SourceBounds { get; init; }

    public required int ChunkCount { get; init; }

    public required IReadOnlyList<string> Attributes { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required double ElapsedMs { get; init; }

    public required string SourceSha256 { get; init; }

    public required string EngineVersion { get; init; }
}

/// <summary>Parameters for <c>pointcloud.info</c>.</summary>
public sealed class PointCloudInfoParams
{
    public required string StorePath { get; init; }
}

/// <summary>Metadata for an existing point cloud store.</summary>
public sealed class PointCloudInfoResult
{
    public required string ScanId { get; init; }

    public required string StorePath { get; init; }

    public required string SourcePath { get; init; }

    public required string Format { get; init; }

    public required string Unit { get; init; }

    public required string UnitSource { get; init; }

    public required PointCounts PointCount { get; init; }

    public required Bounds3 Bounds { get; init; }

    public required Bounds3 SourceBounds { get; init; }

    public required int ChunkCount { get; init; }

    public required IReadOnlyList<string> Attributes { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required DateTimeOffset CreatedAt { get; init; }

    public required string EngineVersion { get; init; }
}

/// <summary>Parameters for <c>pointcloud.query</c>.</summary>
public sealed class PointCloudQueryParams
{
    public required string StorePath { get; init; }

    /// <summary>Bounds query in metres. Mutually exclusive with centre/radius.</summary>
    public Bounds3? Bounds { get; init; }

    /// <summary>Radius query centre in metres.</summary>
    public double[]? Center { get; init; }

    public double? Radius { get; init; }

    public int MaxPoints { get; init; } = 10_000;

    public bool IncludeColors { get; init; }

    public bool IncludeIntensity { get; init; }
}

/// <summary>Points returned by a query, in metres.</summary>
public sealed class PointCloudQueryResult
{
    public required IReadOnlyList<double[]> Positions { get; init; }

    /// <summary>Total points matching before the maxPoints limit.</summary>
    public required int Count { get; init; }

    public required int Returned { get; init; }

    public required bool Truncated { get; init; }

    public IReadOnlyList<int[]>? Colors { get; init; }

    public IReadOnlyList<float>? Intensity { get; init; }
}
