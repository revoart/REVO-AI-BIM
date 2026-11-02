using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Creates a sampled, model-wide point-cloud reference. Revit's native
/// PointCloudInstance requires RCP/RCS, so this uses either a triangle mesh or
/// short model lines from the local scan store. It is a visual aid, not native
/// scan data.
/// </summary>
public static class PointCloudReferenceBuilder
{
    public const string ElementName = "Revo Point Cloud Reference";
    private const string Comment =
        "Revo AI BIM sampled point-cloud reference. Not reconstruction geometry.";
    private const int MaxMarkers = 4_000;

    public static bool Exists(UIApplication app)
    {
        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project first.");
        return FindExisting(document) is not null;
    }

    public static bool Hide(UIApplication app)
    {
        var document = RequireDocument(app);
        using var transaction = new Transaction(document, "Revo AI BIM - Hide point cloud");
        transaction.Start();

        try
        {
            var existing = FindExisting(document);
            if (existing is null)
            {
                transaction.RollBack();
                return false;
            }

            foreach (var id in AllReferenceIds(document))
            {
                document.Delete(id);
            }

            transaction.Commit();
            return false;
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

    public static bool Show(UIApplication app, IReadOnlyList<double[]> positions)
    {
        var document = RequireDocument(app);
        using var transaction = new Transaction(document, "Revo AI BIM - Show point cloud");
        transaction.Start();

        try
        {
            foreach (var id in AllReferenceIds(document))
            {
                document.Delete(id);
            }

            CreateShape(document, positions);
            transaction.Commit();
            return true;
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

    private static Document RequireDocument(UIApplication app)
    {
        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project first.");
        if (document.IsReadOnly)
        {
            throw new InvalidOperationException("The active Revit project is read-only.");
        }

        return document;
    }

    private static DirectShape? FindExisting(Document document) =>
        new FilteredElementCollector(document)
            .OfClass(typeof(DirectShape))
            .Cast<DirectShape>()
            .FirstOrDefault(element =>
                string.Equals(element.Name, ElementName, StringComparison.Ordinal));

    private static IEnumerable<ElementId> AllReferenceIds(Document document) =>
        new FilteredElementCollector(document)
            .OfClass(typeof(DirectShape))
            .Cast<DirectShape>()
            .Where(element =>
                string.Equals(element.Name, ElementName, StringComparison.Ordinal))
            .Select(element => element.Id)
            .ToList();

    private static void CreateShape(Document document, IReadOnlyList<double[]> positions)
    {
        if (positions.Count == 0)
        {
            throw new InvalidOperationException("The scan sample contains no points.");
        }

        var min = new XYZ(double.MaxValue, double.MaxValue, double.MaxValue);
        var max = new XYZ(double.MinValue, double.MinValue, double.MinValue);
        var converted = new List<XYZ>(Math.Min(positions.Count, MaxMarkers));
        foreach (var point in positions)
        {
            if (converted.Count >= MaxMarkers)
            {
                break;
            }

            if (point.Length < 3 ||
                !double.IsFinite(point[0]) ||
                !double.IsFinite(point[1]) ||
                !double.IsFinite(point[2]))
            {
                continue;
            }

            var xyz = new XYZ(
                UnitUtils.ConvertToInternalUnits(point[0], UnitTypeId.Meters),
                UnitUtils.ConvertToInternalUnits(point[1], UnitTypeId.Meters),
                UnitUtils.ConvertToInternalUnits(point[2], UnitTypeId.Meters));
            converted.Add(xyz);
            min = new XYZ(Math.Min(min.X, xyz.X), Math.Min(min.Y, xyz.Y), Math.Min(min.Z, xyz.Z));
            max = new XYZ(Math.Max(max.X, xyz.X), Math.Max(max.Y, xyz.Y), Math.Max(max.Z, xyz.Z));
        }

        if (converted.Count == 0)
        {
            throw new InvalidOperationException("The scan sample contains no valid points.");
        }

        var extent = new XYZ(max.X - min.X, max.Y - min.Y, max.Z - min.Z);
        var largest = Math.Max(extent.X, Math.Max(extent.Y, extent.Z));
        var markerMeters = Math.Clamp(largest / 600.0, 0.02, 0.12);
        var marker = UnitUtils.ConvertToInternalUnits(markerMeters, UnitTypeId.Meters);

        try
        {
            var geometry = BuildMesh(converted, marker);
            CreateDirectShape(document, geometry, marker, useLines: false);
            RevoLog.Info(
                $"Point-cloud reference created from {converted.Count:N0} sampled points (mesh).");
        }
        catch (Exception ex) when (IsGeometryFailure(ex))
        {
            RevoLog.Warn(
                "Mesh point-cloud reference failed; falling back to model lines. " +
                ex.GetType().Name + ": " + ex.Message);
            var geometry = BuildLines(converted, marker);
            CreateDirectShape(document, geometry, marker, useLines: true);
            RevoLog.Info(
                $"Point-cloud reference created from {converted.Count:N0} sampled points (lines).");
        }
    }

    private static IList<GeometryObject> BuildMesh(IReadOnlyList<XYZ> points, double marker)
    {
        using var builder = new TessellatedShapeBuilder
        {
            Target = TessellatedShapeBuilderTarget.Mesh,
            Fallback = TessellatedShapeBuilderFallback.Mesh,
        };
        builder.OpenConnectedFaceSet(false);

        foreach (var center in points)
        {
            var a = center + new XYZ(marker, 0, 0);
            var b = center + new XYZ(-marker, 0, 0);
            var c = center + new XYZ(0, marker, 0);
            var d = center + new XYZ(0, 0, marker);

            AddTriangle(builder, a, b, c);
            AddTriangle(builder, a, c, d);
            AddTriangle(builder, a, d, b);
            AddTriangle(builder, b, d, c);
        }

        builder.CloseConnectedFaceSet();
        builder.Build();

        using var result = builder.GetBuildResult();
        if (!result.AreObjectsAvailable ||
            result.Outcome == TessellatedShapeBuilderOutcome.Nothing)
        {
            throw new InvalidOperationException(
                "Revit could not build the sampled point-cloud mesh.");
        }

        return result.GetGeometricalObjects();
    }

    private static IList<GeometryObject> BuildLines(IReadOnlyList<XYZ> points, double marker)
    {
        var lines = new List<GeometryObject>(points.Count * 2);
        var vertical = new XYZ(0, 0, marker * 1.5);
        var horizontal = new XYZ(marker * 1.5, 0, 0);

        foreach (var point in points)
        {
            lines.Add(Line.CreateBound(point, point + vertical));
            lines.Add(Line.CreateBound(point, point + horizontal));
        }

        return lines;
    }

    private static void CreateDirectShape(
        Document document,
        IList<GeometryObject> geometry,
        double marker,
        bool useLines)
    {
        var shape = DirectShape.CreateElement(
            document,
            new ElementId(BuiltInCategory.OST_GenericModel));
        shape.SetName(ElementName);
        shape.SetShape(geometry);
        shape.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)?.Set(Comment);
        shape.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set("REVO-REFERENCE");

        if (useLines)
        {
            ApplyReferenceOverrides(document, shape.Id, marker);
        }
    }

    private static void ApplyReferenceOverrides(
        Document document,
        ElementId shapeId,
        double marker)
    {
        try
        {
            var overrideSettings = new OverrideGraphicSettings();
            overrideSettings.SetProjectionLineColor(new Color(0, 120, 215));
            overrideSettings.SetProjectionLineWeight(2);
            overrideSettings.SetSurfaceForegroundPatternColor(new Color(0, 120, 215));

            foreach (var view in new FilteredElementCollector(document)
                         .OfClass(typeof(View3D))
                         .Cast<View3D>()
                         .Where(view => !view.IsTemplate))
            {
                view.SetElementOverrides(shapeId, overrideSettings);
            }
        }
        catch (Exception ex)
        {
            RevoLog.Warn("Could not apply point-cloud view overrides: " + ex.Message);
        }
    }

    private static bool IsGeometryFailure(Exception ex) =>
        ex is Autodesk.Revit.Exceptions.InternalException
            or Autodesk.Revit.Exceptions.ApplicationException
            or InvalidOperationException;

    private static void AddTriangle(
        TessellatedShapeBuilder builder,
        XYZ first,
        XYZ second,
        XYZ third)
    {
        using var face = new TessellatedFace(
            new List<XYZ> { first, second, third },
            ElementId.InvalidElementId);
        builder.AddFace(face);
    }
}
