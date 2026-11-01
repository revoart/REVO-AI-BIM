using System.Text.Json;

namespace RevoAI.Contracts.Protocol;

/// <summary>Parameters for <c>segmentation.run</c>.</summary>
public sealed class SegmentationRunParams
{
    public required string StorePath { get; init; }

    /// <summary>Voxel size for analysis; 0 disables downsampling.</summary>
    public double VoxelSizeMeters { get; init; } = 0.05;

    public int MaxPoints { get; init; } = 200_000;

    public double PlaneDistanceMeters { get; init; } = 0.03;

    public int MinPlanePoints { get; init; } = 300;

    public int MaxPlanes { get; init; } = 40;

    public double ConfidenceThreshold { get; init; } = 0.75;
}

/// <summary>Parameters for <c>segmentation.info</c>.</summary>
public sealed class SegmentationInfoParams
{
    public required string StorePath { get; init; }
}

public sealed class PlaneModel
{
    public required double[] Normal { get; init; }

    public required double Offset { get; init; }
}

public sealed class SegmentationSignals
{
    public required double Planarity { get; init; }

    public required double DensityPerSquareMeter { get; init; }

    public required double Coverage { get; init; }

    public required double Size { get; init; }

    public required double FitErrorMeters { get; init; }

    public required double InlierRatio { get; init; }
}

/// <summary>One detected planar instance. This is not Revit geometry.</summary>
public sealed class SegmentationElement
{
    public required string Id { get; init; }

    /// <summary>floor, ceiling, wall, horizontal or sloped.</summary>
    public required string Kind { get; init; }

    public required int PointCount { get; init; }

    public required double Confidence { get; init; }

    public required double AreaM2 { get; init; }

    public required double[] Centroid { get; init; }

    public required Bounds3 Bounds { get; init; }

    public required PlaneModel Plane { get; init; }

    public required SegmentationSignals Signals { get; init; }
}

public sealed class SegmentationSummary
{
    public required int SourcePoints { get; init; }

    public required int AnalyzedPoints { get; init; }

    public required int Segments { get; init; }

    public required Dictionary<string, int> ByKind { get; init; }

    public required double MeanConfidence { get; init; }

    public required int HighConfidenceSegments { get; init; }

    public required int AssignedPoints { get; init; }

    public required double Coverage { get; init; }
}

/// <summary>Result of a segmentation run and of <c>segmentation.info</c>.</summary>
public sealed class SegmentationResult
{
    public required string ScanId { get; init; }

    public required string StorePath { get; init; }

    public required string Method { get; init; }

    public required string MethodNote { get; init; }

    public required JsonElement Parameters { get; init; }

    public required SegmentationSummary Summary { get; init; }

    public required IReadOnlyList<SegmentationElement> Elements { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required string ResultPath { get; init; }

    public required DateTimeOffset CreatedAt { get; init; }

    public required string EngineVersion { get; init; }

    public required double ElapsedMs { get; init; }
}
