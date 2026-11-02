using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;

namespace RevoAI.Revit.RevitApi;

public static partial class ModelBuilder
{
    public static int CreateLevels(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        using var transaction = new Transaction(document, "Revo AI BIM - Build levels");
        transaction.Start();
        try
        {
            var levels = ResolveLevels(
                document,
                session.Plan.Levels,
                session.CreatedLevels,
                session.Warnings);
            foreach (var pair in levels)
            {
                session.Levels[pair.Key] = pair.Value.Id;
            }

            transaction.Commit();
            return levels.Count;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static int CreateSlabs(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        var floorType = new FilteredElementCollector(document)
            .OfClass(typeof(FloorType))
            .Cast<FloorType>()
            .FirstOrDefault(type => !type.IsFoundationSlab)
            ?? throw new InvalidOperationException("The project has no floor type.");

        var created = 0;
        using var transaction = new Transaction(document, "Revo AI BIM - Build slabs");
        transaction.Start();
        try
        {
            foreach (var floorPlan in session.Plan.Floors)
            {
                if (!TryLevel(document, session, floorPlan.LevelId, out var level))
                {
                    session.Warnings.Add($"Skipped slab {floorPlan.Id}: level was not resolved.");
                    continue;
                }

                var loop = CreateBoundaryLoop(document, floorPlan, level, session.Warnings);
                if (loop is null)
                {
                    continue;
                }

                var floor = Floor.Create(
                    document,
                    new List<CurveLoop> { loop },
                    floorType.Id,
                    level.Id);
                MarkInferred(floor, true, floorPlan, "slab");
                session.Floors.Add(floor.Id);
                created++;
            }

            transaction.Commit();
            return created;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static int CreateWalls(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        var wallType = new FilteredElementCollector(document)
            .OfClass(typeof(WallType))
            .Cast<WallType>()
            .FirstOrDefault(type => type.Kind == WallKind.Basic)
            ?? throw new InvalidOperationException("The project has no basic wall type.");
        var cache = new Dictionary<int, ElementId>();
        var created = 0;

        using var transaction = new Transaction(document, "Revo AI BIM - Build walls");
        transaction.Start();
        try
        {
            foreach (var wallPlan in session.Plan.Walls)
            {
                if (!TryLevel(document, session, wallPlan.LevelId, out var level))
                {
                    session.Warnings.Add($"Skipped wall {wallPlan.Id}: level was not resolved.");
                    continue;
                }

                var start = ToXyz(wallPlan.Start, level.Elevation);
                var end = ToXyz(wallPlan.End, level.Elevation);
                if (start.DistanceTo(end) < 0.01)
                {
                    session.Warnings.Add($"Skipped wall {wallPlan.Id}: zero-length line.");
                    continue;
                }

                var height = UnitUtils.ConvertToInternalUnits(
                    Math.Clamp(wallPlan.HeightMeters, 0.5, 10.0),
                    UnitTypeId.Meters);
                var typeId = ResolveWallType(
                    document,
                    wallType,
                    wallPlan.ThicknessMeters,
                    cache,
                    session.Warnings);
                var wall = Wall.Create(
                    document,
                    Line.CreateBound(start, end),
                    typeId,
                    level.Id,
                    height,
                    0.0,
                    false,
                    false);
                MarkInferred(wall, true, wallPlan, "wall");
                session.CreatedWalls.Add(wall.Id);
                session.Walls[wallPlan.Id] = wall.Id;
                created++;
            }

            transaction.Commit();
            return created;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static int CreateOpenings(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        var door = FirstSymbol(document, BuiltInCategory.OST_Doors);
        var window = FirstSymbol(document, BuiltInCategory.OST_Windows);
        var created = 0;

        using var transaction = new Transaction(document, "Revo AI BIM - Host openings");
        transaction.Start();
        try
        {
            foreach (var opening in session.Plan.Openings)
            {
                if (!session.Walls.TryGetValue(opening.HostWallId, out var hostId) ||
                    document.GetElement(hostId) is not Wall host)
                {
                    session.Warnings.Add($"Skipped opening {opening.Id}: host wall was not created.");
                    continue;
                }

                var symbol = opening.Kind == "door" ? door : window;
                if (symbol is null)
                {
                    session.Warnings.Add($"Skipped {opening.Kind} {opening.Id}: no family symbol.");
                    continue;
                }

                if (document.GetElement(host.LevelId) is not Level level)
                {
                    session.Warnings.Add($"Skipped opening {opening.Id}: host level was not found.");
                    continue;
                }

                var instance = CreateHostedOpening(
                    document,
                    host,
                    level,
                    opening,
                    symbol,
                    session.Warnings);
                if (instance is null)
                {
                    continue;
                }

                MarkInferred(instance, true, opening.Kind, opening.Id, opening.Source);
                session.Openings.Add(instance.Id);
                created++;
            }

            transaction.Commit();
            return created;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static int CreateRoofs(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        var roofType = new FilteredElementCollector(document)
            .OfClass(typeof(RoofType))
            .Cast<RoofType>()
            .FirstOrDefault();
        if (roofType is null)
        {
            session.Warnings.Add("Skipped all roofs: no roof type is loaded.");
            return 0;
        }

        var created = 0;
        using var transaction = new Transaction(document, "Revo AI BIM - Build roofs");
        transaction.Start();
        try
        {
            foreach (var roof in session.Plan.Roofs)
            {
                if (!TryLevel(document, session, roof.LevelId, out var level))
                {
                    session.Warnings.Add($"Skipped roof {roof.Id}: level was not resolved.");
                    continue;
                }

                var element = CreateRoof(document, roof, level, roofType, session.Warnings);
                if (element is null)
                {
                    continue;
                }

                MarkInferred(element, true, "roof", roof.Id, roof.Source);
                session.Roofs.Add(element.Id);
                created++;
            }

            transaction.Commit();
            return created;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static int CreateColumns(UIApplication app, BuildSession session)
    {
        var document = RequireDocument(app);
        var symbol =
            FirstSymbol(document, BuiltInCategory.OST_Columns)
            ?? FirstSymbol(document, BuiltInCategory.OST_StructuralColumns);
        if (symbol is null)
        {
            session.Warnings.Add("Skipped all columns: no column family is loaded.");
            return 0;
        }

        var created = 0;
        using var transaction = new Transaction(document, "Revo AI BIM - Build columns");
        transaction.Start();
        try
        {
            foreach (var column in session.Plan.Columns)
            {
                if (!TryLevel(document, session, column.LevelId, out var level))
                {
                    session.Warnings.Add($"Skipped column {column.Id}: level was not resolved.");
                    continue;
                }

                var point = new XYZ(
                    UnitUtils.ConvertToInternalUnits(column.Center[0], UnitTypeId.Meters),
                    UnitUtils.ConvertToInternalUnits(column.Center[1], UnitTypeId.Meters),
                    level.Elevation);
                var instance = document.Create.NewFamilyInstance(
                    point,
                    symbol,
                    level,
                    Autodesk.Revit.DB.Structure.StructuralType.Column);
                MarkInferred(instance, true, "column", column.Id, column.Source);
                session.Columns.Add(instance.Id);
                created++;
            }

            transaction.Commit();
            return created;
        }
        catch
        {
            if (transaction.GetStatus() == TransactionStatus.Started)
            {
                transaction.RollBack();
            }

            throw;
        }
    }

    public static void ShowBuildProgress(UIApplication app, BuildSession session)
    {
        try
        {
            var uidoc = app.ActiveUIDocument;
            if (uidoc is null)
            {
                return;
            }

            var document = uidoc.Document;
            var view3d = new FilteredElementCollector(document)
                .OfClass(typeof(View3D))
                .Cast<View3D>()
                .FirstOrDefault(view => !view.IsTemplate && view.ViewType == ViewType.ThreeD);
            if (view3d is not null && uidoc.ActiveView.Id != view3d.Id)
            {
                uidoc.ActiveView = view3d;
            }

            var ids = session.AllCreated.Take(5_000).ToList();
            if (ids.Count > 0)
            {
                uidoc.ShowElements(ids);
            }

            uidoc.RefreshActiveView();
        }
        catch (Exception ex)
        {
            RevoLog.Warn("Could not update the build view: " + ex.Message);
        }
    }

    private static Document RequireDocument(UIApplication app)
    {
        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project before generating BIM.");
        if (document.IsReadOnly)
        {
            throw new InvalidOperationException("The active Revit project is read-only.");
        }

        return document;
    }

    private static bool TryLevel(
        Document document,
        BuildSession session,
        string planLevelId,
        out Level level)
    {
        level = null!;
        if (!session.Levels.TryGetValue(planLevelId, out var id) ||
            document.GetElement(id) is not Level resolved)
        {
            return false;
        }

        level = resolved;
        return true;
    }
}
