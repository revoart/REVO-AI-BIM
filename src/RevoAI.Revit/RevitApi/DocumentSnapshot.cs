namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Revit-independent snapshot of the active document. Created on Revit's main
/// thread and safe to consume from the WPF window.
/// </summary>
public sealed class DocumentSnapshot
{
    public required string Title { get; init; }

    public required string Path { get; init; }

    public required string ProjectName { get; init; }

    public required string RevitVersion { get; init; }

    public required string LengthUnitLabel { get; init; }

    /// <summary>How many display units equal one foot (Revit's internal unit).</summary>
    public required double UnitsPerFoot { get; init; }

    public required IReadOnlyList<LevelSnapshot> Levels { get; init; }
}

public sealed record LevelSnapshot(string Name, double ElevationFeet);

public sealed record LevelRequest(string Name, double ElevationFeet);

public sealed record LevelCreationResult(
    IReadOnlyList<string> Created,
    IReadOnlyList<string> Skipped);
