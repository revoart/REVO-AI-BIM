using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// All Revit reads/writes used by the Phase 2 workspace. Every method here must
/// be called on Revit's main thread (through <see cref="RevitTaskRunner"/>).
/// </summary>
public static class DocumentReader
{
    public static DocumentSnapshot Read(UIApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);

        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project before using the workspace.");

        var units = document.GetUnits();
        var lengthUnit = units.GetFormatOptions(SpecTypeId.Length).GetUnitTypeId();
        var unitsPerFoot = UnitUtils.ConvertFromInternalUnits(1.0, lengthUnit);
        if (unitsPerFoot <= 0 || double.IsNaN(unitsPerFoot) || double.IsInfinity(unitsPerFoot))
        {
            unitsPerFoot = 1.0;
        }

        var levels = new FilteredElementCollector(document)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .OrderBy(level => level.Elevation)
            .Select(level => new LevelSnapshot(level.Name, level.Elevation))
            .ToList();

        var projectName = document.ProjectInformation?.Name;
        if (string.IsNullOrWhiteSpace(projectName))
        {
            projectName = document.Title;
        }

        return new DocumentSnapshot
        {
            Title = document.Title,
            Path = string.IsNullOrWhiteSpace(document.PathName) ? "(unsaved project)" : document.PathName,
            ProjectName = projectName,
            RevitVersion = $"{app.Application.VersionNumber} (build {app.Application.VersionBuild})",
            LengthUnitLabel = LabelUtils.GetLabelForUnit(lengthUnit),
            UnitsPerFoot = unitsPerFoot,
            Levels = levels,
        };
    }

    /// <summary>
    /// Creates the requested levels in one transaction. Existing level names are
    /// skipped rather than duplicated.
    /// </summary>
    public static LevelCreationResult CreateLevels(UIApplication app, IReadOnlyList<LevelRequest> requests)
    {
        ArgumentNullException.ThrowIfNull(app);
        ArgumentNullException.ThrowIfNull(requests);

        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project before creating levels.");

        if (document.IsReadOnly)
        {
            throw new InvalidOperationException("The active Revit project is read-only.");
        }

        if (requests.Count == 0)
        {
            return new LevelCreationResult([], []);
        }

        var invalid = requests
            .Where(request =>
                string.IsNullOrWhiteSpace(request.Name) ||
                double.IsNaN(request.ElevationFeet) ||
                double.IsInfinity(request.ElevationFeet))
            .Select(request => request.Name)
            .ToList();

        if (invalid.Count > 0)
        {
            throw new InvalidOperationException(
                "Level names must not be empty and elevations must be finite numbers.");
        }

        var duplicateRequest = requests
            .GroupBy(request => request.Name.Trim(), StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(group => group.Count() > 1);

        if (duplicateRequest is not null)
        {
            throw new InvalidOperationException($"Level name '{duplicateRequest.Key}' is requested more than once.");
        }

        var existingNames = new HashSet<string>(
            new FilteredElementCollector(document)
                .OfClass(typeof(Level))
                .Cast<Level>()
                .Select(level => level.Name),
            StringComparer.OrdinalIgnoreCase);

        var created = new List<string>();
        var skipped = new List<string>();

        using var transaction = new Transaction(document, "Revo AI BIM - Create Levels");
        transaction.Start();

        try
        {
            foreach (var request in requests)
            {
                var name = request.Name.Trim();

                if (existingNames.Contains(name))
                {
                    skipped.Add(name);
                    continue;
                }

                var level = Level.Create(document, request.ElevationFeet);
                level.Name = name;
                existingNames.Add(name);
                created.Add(name);
            }

            if (transaction.Commit() != TransactionStatus.Committed)
            {
                throw new InvalidOperationException("Revit did not commit the level transaction.");
            }
        }
        catch
        {
            if (transaction.HasStarted())
            {
                transaction.RollBack();
            }

            throw;
        }

        RevoLog.Info($"Level creation: {created.Count} created, {skipped.Count} skipped.");
        return new LevelCreationResult(created, skipped);
    }
}
