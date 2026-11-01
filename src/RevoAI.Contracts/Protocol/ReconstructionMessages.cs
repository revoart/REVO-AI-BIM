using System.Text.Json;

namespace RevoAI.Contracts.Protocol;

/// <summary>Parameters for <c>reconstruction.plan</c>.</summary>
public sealed class ReconstructionPlanParams
{
    public required string StorePath { get; init; }

    /// <summary>Optional JSON plan produced by an external AI tool.</summary>
    public string? ExternalPlanPath { get; init; }

    public double ConfidenceThreshold { get; init; } = 0.75;

    public double FallbackWallHeightMeters { get; init; } = 2.7;

    public double LevelToleranceMeters { get; init; } = 0.25;

    public int MaxElements { get; init; } = 200;
}

public sealed class PlanLevel
{
    public required string Id { get; init; }

    public required string Name { get; init; }

    public required double ElevationMeters { get; init; }
}

public sealed class PlanFloor
{
    public required string Id { get; init; }

    public required string SourceSegmentId { get; init; }

    public required string LevelId { get; init; }

    public required IReadOnlyList<double[]> Boundary { get; init; }

    public required double AreaM2 { get; init; }

    public required double Confidence { get; init; }
}

public sealed class PlanWall
{
    public required string Id { get; init; }

    public required string SourceSegmentId { get; init; }

    public required string LevelId { get; init; }

    public required double[] Start { get; init; }

    public required double[] End { get; init; }

    public required double HeightMeters { get; init; }

    /// <summary>ceiling or fallback.</summary>
    public required string HeightSource { get; init; }

    public required double Confidence { get; init; }
}

/// <summary>Revit-ready floor and wall descriptors. No Revit objects have been created.</summary>
public sealed class ReconstructionPlanResult
{
    public required string ScanId { get; init; }

    public required string StorePath { get; init; }

    public required string Method { get; init; }

    public required JsonElement Parameters { get; init; }

    public required IReadOnlyList<PlanLevel> Levels { get; init; }

    public required IReadOnlyList<PlanFloor> Floors { get; init; }

    public required IReadOnlyList<PlanWall> Walls { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required string ResultPath { get; init; }

    public required DateTimeOffset CreatedAt { get; init; }

    public required string EngineVersion { get; init; }

    public required double ElapsedMs { get; init; }
}
