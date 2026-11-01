using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Creates a sampled, model-wide point-cloud reference as a DirectShape. Revit's
/// native PointCloudInstance requires RCP/RCS, so this uses small tessellated
/// markers from the local scan store instead of pretending to be a native scan.
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

    /// <summary>
    /// Hides the reference without touching the scan store. Returns false when no
    /// reference element existed.
    /// </summary>
    public static bool Hide(UIApplication app)
    {
        var document = RequireDocument(app);
        using var transaction = new Transaction(document, "Revo AI BIM - Hide point-cloud reference");
        transaction.Start();

        try
        {
            var existing = FindExisting(document);
            if (existing is null)
            {
                transaction.RollBack();
                return false;
            }

            document.Delete(existing.Id);
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

    /// <summary>
    /// Replaces any existing reference with a fresh sampled marker set.
    /// </summary>
    public static bool Show(UIApplication app, IReadOnlyList<double[]> positions)
    {
        var document = RequireDocument(app);
        using var transaction = new Transaction(document, "Revo AI BIM - Show point-cloud reference");
        transaction.Start();

        try
        {
            var existing = FindExisting(document);
            if (existing is not null)
            {
                document.Delete(existing.Id);
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

    private static DirectShape? FindExisting(Document document)
    {
        return new FilteredElementCollector(document)
            .OfClass(typeof(DirectShape))
            .Cast<DirectShape>()
            .FirstOrDefault(element =>
                string.Equals(element.Name, ElementName, StringComparison.Ordinal));
    }

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
        var radiusMeters = Math.Clamp(largest / 1_200.0, 0.012, 0.06);
        var radius = UnitUtils.ConvertToInternalUnits(radiusMeters, UnitTypeId.Meters);

        using var builder = new TessellatedShapeBuilder
        {
            Target = TessellatedShapeBuilderTarget.Solid,
            Fallback = TessellatedShapeBuilderFallback.Mesh,
        };

        foreach (var center in converted)
        {
            builder.OpenConnectedFaceSet(true);
            AddTetrahedron(builder, center, radius);
            builder.CloseConnectedFaceSet();
        }

        builder.Build();
        using var result = builder.GetBuildResult();
        if (!result.AreObjectsAvailable || result.Outcome == TessellatedShapeBuilderOutcome.Nothing)
        {
            throw new InvalidOperationException(
                "Revit could not build the sampled point-cloud reference geometry.");
        }

        var shape = DirectShape.CreateElement(
            document,
            new ElementId(BuiltInCategory.OST_GenericModel));
        shape.SetName(ElementName);
        shape.SetShape(result.GetGeometricalObjects());
        shape.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)?.Set(Comment);
        shape.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set("REVO-REFERENCE");
    }

    private static void AddTetrahedron(
        TessellatedShapeBuilder builder,
        XYZ center,
        double radius)
    {
        var a = center + new XYZ(radius, 0, 0);
        var b = center + new XYZ(-radius, 0, 0);
        var c = center + new XYZ(0, radius, 0);
        var d = center + new XYZ(0, 0, radius);

        AddFace(builder, a, b, c);
        AddFace(builder, a, c, d);
        AddFace(builder, a, d, b);
        AddFace(builder, b, d, c);
    }

    private static void AddFace(
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
