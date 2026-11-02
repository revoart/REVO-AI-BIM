using Autodesk.Revit.DB;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Temporary diagnostic used to identify a stable Revit tessellation strategy
/// for point-cloud reference markers. It only builds in-memory geometry and
/// never touches the document.
/// </summary>
public static class PointCloudReferenceProbe
{
    public static void Run()
    {
        var points = new List<XYZ>();
        for (var i = 0; i < 4_000; i++)
        {
            points.Add(new XYZ(
                (i % 50) * 0.1,
                ((i / 50) % 50) * 0.1,
                (i / 2_500) * 0.1));
        }

        foreach (var count in new[] { 1, 100, 1_000, 4_000 })
        {
            var slice = points.Take(count).ToList();
            Try($"tetra-mesh-one-{count}", () => Build(slice, 0.02, tetra: true, oneSet: true, solid: false, target: TessellatedShapeBuilderTarget.Mesh));
            Try($"tetra-solid-one-{count}", () => Build(slice, 0.02, tetra: true, oneSet: true, solid: true, target: TessellatedShapeBuilderTarget.Solid));
            Try($"tetra-mesh-sets-{count}", () => Build(slice, 0.02, tetra: true, oneSet: false, solid: false, target: TessellatedShapeBuilderTarget.Mesh));
            Try($"tetra-solid-sets-{count}", () => Build(slice, 0.02, tetra: true, oneSet: false, solid: true, target: TessellatedShapeBuilderTarget.Solid));
            Try($"triangle-mesh-one-{count}", () => Build(slice, 0.02, tetra: false, oneSet: true, solid: false, target: TessellatedShapeBuilderTarget.Mesh));
        }
    }

    private static void Try(string name, Action action)
    {
        try
        {
            action();
            RevoLog.Info($"REFERENCE PROBE {name}: OK");
        }
        catch (Exception ex)
        {
            RevoLog.Error($"REFERENCE PROBE {name}: FAIL {ex.GetType().Name}: {ex.Message}");
        }
    }

    private static void Build(
        IReadOnlyList<XYZ> points,
        double radius,
        bool tetra,
        bool oneSet,
        bool solid,
        TessellatedShapeBuilderTarget target)
    {
        using var builder = new TessellatedShapeBuilder
        {
            Target = target,
            Fallback = solid ? TessellatedShapeBuilderFallback.Mesh : TessellatedShapeBuilderFallback.Mesh,
        };

        if (oneSet)
        {
            builder.OpenConnectedFaceSet(solid);
        }

        foreach (var center in points)
        {
            if (!oneSet)
            {
                builder.OpenConnectedFaceSet(solid);
            }

            if (tetra)
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
            else
            {
                AddFace(builder, center, center + new XYZ(radius, 0, 0), center + new XYZ(0, radius, 0));
            }

            if (!oneSet)
            {
                builder.CloseConnectedFaceSet();
            }
        }

        if (oneSet)
        {
            builder.CloseConnectedFaceSet();
        }

        builder.Build();
        using var result = builder.GetBuildResult();
        if (!result.AreObjectsAvailable || result.Outcome == TessellatedShapeBuilderOutcome.Nothing)
        {
            throw new InvalidOperationException($"No geometry. Outcome={result.Outcome}.");
        }
    }

    private static void AddFace(TessellatedShapeBuilder builder, XYZ a, XYZ b, XYZ c)
    {
        using var face = new TessellatedFace(
            new List<XYZ> { a, b, c },
            ElementId.InvalidElementId);
        builder.AddFace(face);
    }
}
