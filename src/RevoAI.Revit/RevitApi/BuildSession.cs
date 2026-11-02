using Autodesk.Revit.DB;
using RevoAI.Contracts.Protocol;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Holds only plan ids and Revit element ids between build steps. Revit objects
/// are never stored on the WPF side; every step resolves elements on Revit's
/// main thread.
/// </summary>
public sealed class BuildSession
{
    public BuildSession(ReconstructionPlanResult plan)
    {
        Plan = plan;
        Warnings.AddRange(plan.Warnings);
    }

    public ReconstructionPlanResult Plan { get; }

    public Dictionary<string, ElementId> Levels { get; } = new(StringComparer.Ordinal);

    public Dictionary<string, ElementId> Walls { get; } = new(StringComparer.Ordinal);

    public List<ElementId> CreatedLevels { get; } = [];

    public List<ElementId> Floors { get; } = [];

    public List<ElementId> CreatedWalls { get; } = [];

    public List<ElementId> Openings { get; } = [];

    public List<ElementId> Roofs { get; } = [];

    public List<ElementId> Columns { get; } = [];

    public List<string> Warnings { get; } = [];

    public IEnumerable<ElementId> AllCreated =>
        CreatedLevels.Concat(Floors).Concat(CreatedWalls)
            .Concat(Openings).Concat(Roofs).Concat(Columns);
}
