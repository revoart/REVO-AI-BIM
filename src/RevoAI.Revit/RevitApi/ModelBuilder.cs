using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Creates native Revit floors and walls from a reconstruction plan. Every call
/// must run on Revit's main thread. The caller owns the transaction.
/// </summary>
public static class ModelBuilder
{
    public static ReconstructionBuildResult Create(
        UIApplication app,
        ReconstructionPlanResult plan,
        bool markInferred)
    {
        ArgumentNullException.ThrowIfNull(app);
        ArgumentNullException.ThrowIfNull(plan);

        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project before generating BIM.");
        if (document.IsReadOnly)
        {
            throw new InvalidOperationException("The active Revit project is read-only.");
        }

        var warnings = new List<string>(plan.Warnings);
        var createdFloors = new List<ElementId>();
        var createdWalls = new List<ElementId>();
        var createdLevels = new List<ElementId>();

        var floorType = new FilteredElementCollector(document)
            .OfClass(typeof(FloorType))
            .Cast<FloorType>()
            .FirstOrDefault(type => !type.IsFoundationSlab)
            ?? new FilteredElementCollector(document)
                .OfClass(typeof(FloorType))
                .Cast<FloorType>()
                .FirstOrDefault()
            ?? throw new InvalidOperationException("The project has no floor type.");

        var wallType = new FilteredElementCollector(document)
            .OfClass(typeof(WallType))
            .Cast<WallType>()
            .FirstOrDefault(type => type.Kind == WallKind.Basic)
            ?? throw new InvalidOperationException("The project has no basic wall type.");

        using var transaction = new Transaction(document, "Revo AI BIM - Generate walls and floors");
        transaction.Start();

        try
        {
            var levelMap = ResolveLevels(
                document,
                plan.Levels,
                createdLevels,
                warnings);

            foreach (var floorPlan in plan.Floors)
            {
                if (!levelMap.TryGetValue(floorPlan.LevelId, out var level))
                {
                    warnings.Add($"Skipped floor {floorPlan.Id}: level {floorPlan.LevelId} was not resolved.");
                    continue;
                }

                var loop = CreateBoundaryLoop(document, floorPlan, level, warnings);
                if (loop is null)
                {
                    warnings.Add($"Skipped floor {floorPlan.Id}: boundary is not a valid closed loop.");
                    continue;
                }

                var floor = Floor.Create(
                    document,
                    new List<CurveLoop> { loop },
                    floorType.Id,
                    level.Id);
                MarkInferred(floor, markInferred, floorPlan, "floor");
                createdFloors.Add(floor.Id);
            }

            foreach (var wallPlan in plan.Walls)
            {
                if (!levelMap.TryGetValue(wallPlan.LevelId, out var level))
                {
                    warnings.Add($"Skipped wall {wallPlan.Id}: level {wallPlan.LevelId} was not resolved.");
                    continue;
                }

                var start = ToXyz(wallPlan.Start, level.Elevation);
                var end = ToXyz(wallPlan.End, level.Elevation);
                if (start.DistanceTo(end) < 0.01)
                {
                    warnings.Add($"Skipped wall {wallPlan.Id}: zero-length line.");
                    continue;
                }

                var height = UnitUtils.ConvertToInternalUnits(
                    Math.Clamp(wallPlan.HeightMeters, 0.5, 10.0),
                    UnitTypeId.Meters);
                var wall = Wall.Create(
                    document,
                    Line.CreateBound(start, end),
                    wallType.Id,
                    level.Id,
                    height,
                    0.0,
                    false,
                    false);
                MarkInferred(wall, markInferred, wallPlan, "wall");
                createdWalls.Add(wall.Id);
            }

            if (createdFloors.Count == 0 && createdWalls.Count == 0)
            {
                transaction.RollBack();
                return new ReconstructionBuildResult(
                    createdFloors,
                    createdWalls,
                    createdLevels,
                    warnings,
                    "No valid floors or walls were created.");
            }

            transaction.Commit();
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }

        return new ReconstructionBuildResult(
            createdFloors,
            createdWalls,
            createdLevels,
            warnings,
            $"Created {createdFloors.Count} floor(s), {createdWalls.Count} wall(s) and " +
            $"{createdLevels.Count} level(s) from the scan.");
    }

    private static Dictionary<string, Level> ResolveLevels(
        Document document,
        IReadOnlyList<PlanLevel> planLevels,
        List<ElementId> createdLevels,
        List<string> warnings)
    {
        var existing = new FilteredElementCollector(document)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .OrderBy(level => level.Elevation)
            .ToList();
        var usedNames = new HashSet<string>(
            existing.Select(level => level.Name),
            StringComparer.OrdinalIgnoreCase);
        var result = new Dictionary<string, Level>(StringComparer.Ordinal);

        foreach (var planLevel in planLevels)
        {
            var elevation = UnitUtils.ConvertToInternalUnits(
                planLevel.ElevationMeters,
                UnitTypeId.Meters);
            var level = existing.FirstOrDefault(
                candidate => Math.Abs(candidate.Elevation - elevation) <= 0.01);
            if (level is null)
            {
                level = Level.Create(document, elevation);
                var name = planLevel.Name;
                var suffix = 2;
                while (!usedNames.Add(name))
                {
                    name = $"{planLevel.Name} ({suffix++})";
                }

                level.Name = name;
                existing.Add(level);
                createdLevels.Add(level.Id);
                warnings.Add($"Created level '{name}' at {planLevel.ElevationMeters:0.###} m.");
            }

            result[planLevel.Id] = level;
        }

        return result;
    }

    private static CurveLoop? CreateBoundaryLoop(
        Document document,
        PlanFloor floorPlan,
        Level level,
        List<string> warnings)
    {
        var points = new List<XYZ>();
        foreach (var point in floorPlan.Boundary)
        {
            if (point.Length < 3)
            {
                continue;
            }

            var xyz = ToXyz(point, level.Elevation);
            if (points.Count == 0 || points[^1].DistanceTo(xyz) > 1e-5)
            {
                points.Add(xyz);
            }
        }

        if (points.Count > 1 && points[0].DistanceTo(points[^1]) <= 1e-5)
        {
            points.RemoveAt(points.Count - 1);
        }

        if (points.Count < 3)
        {
            return null;
        }

        var loop = new CurveLoop();
        try
        {
            for (var index = 0; index < points.Count; index++)
            {
                var next = points[(index + 1) % points.Count];
                loop.Append(Line.CreateBound(points[index], next));
            }

            return loop;
        }
        catch (Exception exception)
        {
            warnings.Add($"Floor {floorPlan.Id} boundary failed: {exception.Message}");
            return null;
        }
    }

    private static void MarkInferred(
        Element element,
        bool markInferred,
        PlanFloor plan,
        string kind)
    {
        if (!markInferred)
        {
            return;
        }

        element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)?.Set(
            $"Revo AI BIM inferred {kind} from scan segment {plan.SourceSegmentId} " +
            $"(confidence {plan.Confidence:0.000}).");
        element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set("REVO-INFERRED");
    }

    private static void MarkInferred(
        Element element,
        bool markInferred,
        PlanWall plan,
        string kind)
    {
        if (!markInferred)
        {
            return;
        }

        element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)?.Set(
            $"Revo AI BIM inferred {kind} from scan segment {plan.SourceSegmentId} " +
            $"(confidence {plan.Confidence:0.000}, height source {plan.HeightSource}).");
        element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set("REVO-INFERRED");
    }

    private static XYZ ToXyz(IReadOnlyList<double> metres, double zFeet)
    {
        return new XYZ(
            UnitUtils.ConvertToInternalUnits(metres[0], UnitTypeId.Meters),
            UnitUtils.ConvertToInternalUnits(metres[1], UnitTypeId.Meters),
            zFeet);
    }
}

public sealed record ReconstructionBuildResult(
    IReadOnlyList<ElementId> CreatedFloors,
    IReadOnlyList<ElementId> CreatedWalls,
    IReadOnlyList<ElementId> CreatedLevels,
    IReadOnlyList<string> Warnings,
    string Message);
