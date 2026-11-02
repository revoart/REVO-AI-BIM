using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Creates native Revit floors and walls from a reconstruction plan. Every call
/// must run on Revit's main thread. The caller owns the transaction.
/// </summary>
public static partial class ModelBuilder
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
        var createdOpenings = new List<ElementId>();
        var createdRoofs = new List<ElementId>();
        var createdColumns = new List<ElementId>();
        var wallsById = new Dictionary<string, Wall>(StringComparer.Ordinal);
        var wallLevelsById = new Dictionary<string, Level>(StringComparer.Ordinal);
        var wallTypeCache = new Dictionary<int, ElementId>();

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

        var doorSymbol = FirstSymbol(document, BuiltInCategory.OST_Doors);
        var windowSymbol = FirstSymbol(document, BuiltInCategory.OST_Windows);
        var columnSymbol =
            FirstSymbol(document, BuiltInCategory.OST_Columns)
            ?? FirstSymbol(document, BuiltInCategory.OST_StructuralColumns);
        var roofType = new FilteredElementCollector(document)
            .OfClass(typeof(RoofType))
            .Cast<RoofType>()
            .FirstOrDefault();

        if (plan.Openings.Count > 0)
        {
            if (doorSymbol is null && plan.Openings.Any(item => item.Kind == "door"))
            {
                warnings.Add("No door family symbol is loaded; door openings were skipped.");
            }
            if (windowSymbol is null && plan.Openings.Any(item => item.Kind == "window"))
            {
                warnings.Add("No window family symbol is loaded; window openings were skipped.");
            }
        }
        if (plan.Roofs.Count > 0 && roofType is null)
        {
            warnings.Add("No roof type is loaded; roofs were skipped.");
        }
        if (plan.Columns.Count > 0 && columnSymbol is null)
        {
            warnings.Add("No column family symbol is loaded; columns were skipped.");
        }
        if (plan.Walls.Any(item => item.ThicknessMeters > 0))
        {
            warnings.Add("Wall thicknesses were applied by duplicating the base wall type.");
        }

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
                var wallTypeId = ResolveWallType(
                    document,
                    wallType,
                    wallPlan.ThicknessMeters,
                    wallTypeCache,
                    warnings);
                var wall = Wall.Create(
                    document,
                    Line.CreateBound(start, end),
                    wallTypeId,
                    level.Id,
                    height,
                    0.0,
                    false,
                    false);
                MarkInferred(wall, markInferred, wallPlan, "wall");
                createdWalls.Add(wall.Id);
                wallsById[wallPlan.Id] = wall;
                wallLevelsById[wallPlan.Id] = level;
            }

            foreach (var opening in plan.Openings)
            {
                if (!wallsById.TryGetValue(opening.HostWallId, out var host))
                {
                    warnings.Add($"Skipped opening {opening.Id}: host wall {opening.HostWallId} was not created.");
                    continue;
                }

                var symbol = opening.Kind == "door" ? doorSymbol : windowSymbol;
                if (symbol is null)
                {
                    warnings.Add($"Skipped {opening.Kind} {opening.Id}: no family symbol is loaded.");
                    continue;
                }

                try
                {
                    var created = CreateHostedOpening(
                        document,
                        host,
                        wallLevelsById[opening.HostWallId],
                        opening,
                        symbol,
                        warnings);
                    if (created is not null)
                    {
                        MarkInferred(
                            created,
                            markInferred,
                            opening.Kind,
                            opening.Id,
                            opening.Source);
                        createdOpenings.Add(created.Id);
                    }
                }
                catch (Exception ex)
                {
                    warnings.Add($"Opening {opening.Id} failed: {ex.Message}");
                }
            }

            foreach (var roof in plan.Roofs)
            {
                if (roofType is null)
                {
                    warnings.Add($"Skipped roof {roof.Id}: no roof type is loaded.");
                    continue;
                }
                if (!levelMap.TryGetValue(roof.LevelId, out var level))
                {
                    warnings.Add($"Skipped roof {roof.Id}: level {roof.LevelId} was not resolved.");
                    continue;
                }

                try
                {
                    var created = CreateRoof(document, roof, level, roofType, warnings);
                    if (created is not null)
                    {
                        MarkInferred(created, markInferred, "roof", roof.Id, roof.Source);
                        createdRoofs.Add(created.Id);
                    }
                }
                catch (Exception ex)
                {
                    warnings.Add($"Roof {roof.Id} failed: {ex.Message}");
                }
            }

            foreach (var column in plan.Columns)
            {
                if (columnSymbol is null)
                {
                    warnings.Add($"Skipped column {column.Id}: no column symbol is loaded.");
                    continue;
                }
                if (!levelMap.TryGetValue(column.LevelId, out var level))
                {
                    warnings.Add($"Skipped column {column.Id}: level {column.LevelId} was not resolved.");
                    continue;
                }

                try
                {
                    var point = new XYZ(
                        UnitUtils.ConvertToInternalUnits(column.Center[0], UnitTypeId.Meters),
                        UnitUtils.ConvertToInternalUnits(column.Center[1], UnitTypeId.Meters),
                        level.Elevation);
                    var created = document.Create.NewFamilyInstance(
                        point,
                        columnSymbol,
                        level,
                        Autodesk.Revit.DB.Structure.StructuralType.Column);
                    MarkInferred(created, markInferred, "column", column.Id, column.Source);
                    createdColumns.Add(created.Id);
                }
                catch (Exception ex)
                {
                    warnings.Add($"Column {column.Id} failed: {ex.Message}");
                }
            }

            if (createdFloors.Count == 0 && createdWalls.Count == 0 &&
                createdOpenings.Count == 0 && createdRoofs.Count == 0 &&
                createdColumns.Count == 0)
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
            $"Created {createdFloors.Count} slab(s), {createdWalls.Count} wall(s), " +
            $"{createdOpenings.Count} opening(s), {createdRoofs.Count} roof(s), " +
            $"{createdColumns.Count} column(s) and {createdLevels.Count} level(s) from the scan.",
            createdOpenings,
            createdRoofs,
            createdColumns);
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

    private static FamilySymbol? FirstSymbol(Document document, BuiltInCategory category)
    {
        var symbol = new FilteredElementCollector(document)
            .OfCategory(category)
            .OfClass(typeof(FamilySymbol))
            .Cast<FamilySymbol>()
            .FirstOrDefault();
        if (symbol is { IsActive: false })
        {
            symbol.Activate();
            document.Regenerate();
        }

        return symbol;
    }

    private static ElementId ResolveWallType(
        Document document,
        WallType baseType,
        double thicknessMeters,
        Dictionary<int, ElementId> cache,
        List<string> warnings)
    {
        var thicknessFeet = UnitUtils.ConvertToInternalUnits(
            Math.Clamp(thicknessMeters, 0.05, 1.0),
            UnitTypeId.Meters);
        var key = (int)Math.Round(thicknessFeet * 1000.0);
        if (cache.TryGetValue(key, out var cached))
        {
            return cached;
        }

        try
        {
            var duplicate = (WallType)baseType.Duplicate(
                $"Revo Wall {thicknessMeters * 1000:0} mm");
            var structure = duplicate.GetCompoundStructure();
            if (structure is { LayerCount: > 0 })
            {
                structure.SetLayerWidth(0, thicknessFeet);
                duplicate.SetCompoundStructure(structure);
            }

            cache[key] = duplicate.Id;
            return duplicate.Id;
        }
        catch (Exception ex)
        {
            warnings.Add(
                $"Could not create a {thicknessMeters * 1000:0} mm wall type ({ex.Message}); " +
                "the base wall type was used.");
            cache[key] = baseType.Id;
            return baseType.Id;
        }
    }

    private static FamilyInstance? CreateHostedOpening(
        Document document,
        Wall host,
        Level level,
        PlanOpening opening,
        FamilySymbol symbol,
        List<string> warnings)
    {
        if (host.Location is not LocationCurve location ||
            location.Curve is not Line line)
        {
            warnings.Add($"Opening {opening.Id}: host wall has no straight location line.");
            return null;
        }

        var start = line.GetEndPoint(0);
        var end = line.GetEndPoint(1);
        var direction = (end - start).Normalize();
        var center = start + direction * UnitUtils.ConvertToInternalUnits(
            opening.CenterMeters,
            UnitTypeId.Meters);
        var sill = UnitUtils.ConvertToInternalUnits(opening.SillMeters, UnitTypeId.Meters);
        var head = UnitUtils.ConvertToInternalUnits(opening.HeadMeters, UnitTypeId.Meters);
        var insertion = new XYZ(center.X, center.Y, level.Elevation + sill);

        var instance = document.Create.NewFamilyInstance(
            insertion,
            symbol,
            host,
            level,
            Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
        instance.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)?.Set(sill);
        instance.get_Parameter(BuiltInParameter.INSTANCE_HEAD_HEIGHT_PARAM)?.Set(head);
        return instance;
    }

    private static FootPrintRoof? CreateRoof(
        Document document,
        PlanRoof roof,
        Level level,
        RoofType roofType,
        List<string> warnings)
    {
        var points = new List<XYZ>();
        foreach (var point in roof.Boundary)
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
            warnings.Add($"Roof {roof.Id}: boundary is not a valid closed loop.");
            return null;
        }

        var curves = new CurveArray();
        for (var index = 0; index < points.Count; index++)
        {
            curves.Append(Line.CreateBound(points[index], points[(index + 1) % points.Count]));
        }

        var modelCurves = new ModelCurveArray();
        var created = document.Create.NewFootPrintRoof(
            curves,
            level,
            roofType,
            out modelCurves);
        if (created is null)
        {
            warnings.Add($"Roof {roof.Id}: Revit returned no roof element.");
            return null;
        }
        if (roof.PitchDegrees > 1.0)
        {
            warnings.Add(
                $"Roof {roof.Id}: measured pitch {roof.PitchDegrees:0.#}° was not applied; " +
                "a flat roof was created.");
        }

        return created;
    }

    private static void MarkInferred(
        Element element,
        bool markInferred,
        string kind,
        string sourceId,
        string source)
    {
        if (!markInferred)
        {
            return;
        }

        element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)?.Set(
            $"Revo AI BIM {kind} from schedule item {sourceId} ({source}).");
        element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set(
            source == "MEASURED" ? "REVO-MEASURED" : "REVO-INFERRED");
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
    string Message,
    IReadOnlyList<ElementId>? CreatedOpenings = null,
    IReadOnlyList<ElementId>? CreatedRoofs = null,
    IReadOnlyList<ElementId>? CreatedColumns = null);
