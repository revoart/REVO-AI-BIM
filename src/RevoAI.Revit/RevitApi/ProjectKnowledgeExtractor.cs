using System.IO;
using System.Security.Cryptography;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Read-only extraction of a Revit project into a structured JSON record for the
/// local knowledge library. It never edits, saves or closes the document.
/// </summary>
public static class ProjectKnowledgeExtractor
{
    public const string SchemaVersion = "1.0";

    private static readonly HashSet<int> AllowedCategories =
    [
        (int)BuiltInCategory.OST_Walls,
        (int)BuiltInCategory.OST_Floors,
        (int)BuiltInCategory.OST_Ceilings,
        (int)BuiltInCategory.OST_Roofs,
        (int)BuiltInCategory.OST_Doors,
        (int)BuiltInCategory.OST_Windows,
        (int)BuiltInCategory.OST_Stairs,
        (int)BuiltInCategory.OST_Railings,
        (int)BuiltInCategory.OST_Columns,
        (int)BuiltInCategory.OST_Rooms,
        (int)BuiltInCategory.OST_Levels,
        (int)BuiltInCategory.OST_Grids,
    ];

    public static ProjectKnowledgeExtraction Extract(UIApplication app, int maxElements = 20_000)
    {
        ArgumentNullException.ThrowIfNull(app);

        var document = app.ActiveUIDocument?.Document
            ?? throw new InvalidOperationException("Open a Revit project before extracting knowledge.");

        var warnings = new List<string>();
        var levels = new FilteredElementCollector(document)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .OrderBy(level => level.Elevation)
            .Select(level => level.Name)
            .ToList();

        var units = document.GetUnits();
        var lengthUnit = units.GetFormatOptions(SpecTypeId.Length).GetUnitTypeId();
        var unitInfo = new Dictionary<string, string>
        {
            ["length"] = LabelUtils.GetLabelForUnit(lengthUnit),
            ["lengthTypeId"] = lengthUnit.TypeId,
        };

        var elements = new List<ProjectKnowledgeElement>();
        var counts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var skipped = 0;

        var candidates = new FilteredElementCollector(document)
            .WhereElementIsNotElementType()
            .Where(element =>
            {
                var category = element.Category;
                return category is not null && AllowedCategories.Contains((int)category.Id.Value);
            })
            .ToList();

        foreach (var element in candidates)
        {
            if (elements.Count >= maxElements)
            {
                skipped = candidates.Count - elements.Count;
                break;
            }

            try
            {
                var record = ExtractElement(document, element);
                elements.Add(record);
                counts[record.Category] = counts.GetValueOrDefault(record.Category) + 1;
            }
            catch (Exception ex)
            {
                warnings.Add(
                    $"Element {element.Id.Value} ({element.Category?.Name ?? "Unknown"}) was skipped: {ex.Message}");
            }
        }

        if (skipped > 0)
        {
            warnings.Add($"Extraction stopped at {maxElements:N0} elements; {skipped:N0} were omitted.");
        }

        foreach (var warning in SafeWarnings(document))
        {
            warnings.Add(warning);
        }

        var projectName = document.ProjectInformation?.Name;
        if (string.IsNullOrWhiteSpace(projectName))
        {
            projectName = document.Title;
        }

        return new ProjectKnowledgeExtraction
        {
            SchemaVersion = SchemaVersion,
            Project = new ProjectKnowledgeProject
            {
                Title = projectName,
                Path = string.IsNullOrWhiteSpace(document.PathName) ? null : document.PathName,
                RevitVersion = app.Application.VersionNumber,
                RevitBuild = app.Application.VersionBuild,
                Units = unitInfo,
                FileSha256 = TryHashDocument(document.PathName),
                ExtractedAt = DateTimeOffset.UtcNow,
                Warnings = warnings,
                Levels = levels,
            },
            Elements = elements,
            Counts = counts,
        };
    }

    public static string SaveToInbox(ProjectKnowledgeExtraction extraction)
    {
        ArgumentNullException.ThrowIfNull(extraction);

        var root = ResolveRoot();
        var inbox = Path.Combine(root, "inbox");
        Directory.CreateDirectory(inbox);

        var name = SanitizeFileName(extraction.Project.Title);
        var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss");
        var path = Path.Combine(inbox, $"project-{name}-{stamp}.json");
        File.WriteAllText(path, RevoAIJson.Serialize(extraction));
        return path;
    }

    public static string ResolveRoot()
    {
        try
        {
            var configured = RevoConfig.Load().KnowledgeRoot;
            if (!string.IsNullOrWhiteSpace(configured))
            {
                return Environment.ExpandEnvironmentVariables(configured);
            }
        }
        catch (Exception ex)
        {
            RevoLog.Warn("Could not read the configured knowledge root: " + ex.Message);
        }

        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "RevoAI",
            "knowledge");
    }

    private static ProjectKnowledgeElement ExtractElement(Document document, Element element)
    {
        var category = element.Category?.Name ?? "Unknown";
        var type = document.GetElement(element.GetTypeId()) as ElementType;
        var level = element.LevelId != ElementId.InvalidElementId
            ? document.GetElement(element.LevelId)?.Name
            : null;

        string? hostId = null;
        string? roomId = null;
        if (element is FamilyInstance instance)
        {
            hostId = instance.Host?.Id.Value.ToString();
            roomId = instance.Room?.Id.Value.ToString();
        }

        var parameters = new List<ProjectKnowledgeParameter>();
        try
        {
            foreach (var parameter in element.GetOrderedParameters().Take(40))
            {
                var name = parameter.Definition?.Name;
                if (string.IsNullOrWhiteSpace(name))
                {
                    continue;
                }

                parameters.Add(new ProjectKnowledgeParameter
                {
                    Name = name,
                    StorageType = parameter.StorageType.ToString(),
                    Value = SafeParameterValue(parameter),
                });
            }
        }
        catch (Exception)
        {
            // Some parameters are not readable in every context; the rest of the
            // element record is still useful.
        }

        return new ProjectKnowledgeElement
        {
            ElementId = element.Id.Value.ToString(),
            UniqueId = element.UniqueId,
            Category = category,
            Family = type?.FamilyName,
            TypeName = type?.Name,
            LevelId = level,
            HostId = hostId,
            RoomId = roomId,
            BoundingBox = SafeBounds(element),
            Parameters = parameters,
            Geometry = SafeGeometry(element),
        };
    }

    private static ProjectKnowledgeBounds? SafeBounds(Element element)
    {
        try
        {
            var box = element.get_BoundingBox(null);
            if (box is null)
            {
                return null;
            }

            var corners = new List<XYZ>();
            foreach (var x in new[] { box.Min.X, box.Max.X })
            {
                foreach (var y in new[] { box.Min.Y, box.Max.Y })
                {
                    foreach (var z in new[] { box.Min.Z, box.Max.Z })
                    {
                        var point = new XYZ(x, y, z);
                        corners.Add(box.Transform is null ? point : box.Transform.OfPoint(point));
                    }
                }
            }

            return new ProjectKnowledgeBounds
            {
                Min =
                [
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Min(point => point.X), UnitTypeId.Meters), 4),
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Min(point => point.Y), UnitTypeId.Meters), 4),
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Min(point => point.Z), UnitTypeId.Meters), 4),
                ],
                Max =
                [
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Max(point => point.X), UnitTypeId.Meters), 4),
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Max(point => point.Y), UnitTypeId.Meters), 4),
                    Math.Round(UnitUtils.ConvertFromInternalUnits(corners.Max(point => point.Z), UnitTypeId.Meters), 4),
                ],
            };
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static ProjectKnowledgeGeometry SafeGeometry(Element element)
    {
        try
        {
            var geometry = element.get_Geometry(new Options
            {
                ComputeReferences = false,
                DetailLevel = ViewDetailLevel.Fine,
            });

            var solidCount = 0;
            if (geometry is not null)
            {
                foreach (var item in geometry)
                {
                    if (item is Solid)
                    {
                        solidCount++;
                    }
                }
            }

            return new ProjectKnowledgeGeometry { SolidCount = solidCount };
        }
        catch (Exception)
        {
            return new ProjectKnowledgeGeometry();
        }
    }

    private static string? SafeParameterValue(Parameter parameter)
    {
        try
        {
            var value = parameter.StorageType switch
            {
                StorageType.String => parameter.AsString(),
                StorageType.Integer => parameter.AsInteger().ToString(),
                StorageType.Double => parameter.AsValueString() ?? parameter.AsDouble().ToString("0.####"),
                StorageType.ElementId => parameter.AsValueString() ?? parameter.AsElementId().Value.ToString(),
                _ => null,
            };

            if (value is null)
            {
                return null;
            }

            return value.Length > 500 ? value[..500] : value;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static IEnumerable<string> SafeWarnings(Document document)
    {
        try
        {
            return document.GetWarnings()
                .Select(warning => warning.GetDescriptionText())
                .Where(description => !string.IsNullOrWhiteSpace(description))
                .Take(200)
                .ToList();
        }
        catch (Exception)
        {
            return [];
        }
    }

    private static string? TryHashDocument(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return null;
        }

        try
        {
            using var stream = File.OpenRead(path);
            return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        }
        catch (Exception ex)
        {
            RevoLog.Warn("Could not hash the Revit project file: " + ex.Message);
            return null;
        }
    }

    private static string SanitizeFileName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string(name.Select(character => invalid.Contains(character) ? '-' : character).ToArray());
        cleaned = cleaned.Trim();
        return cleaned.Length == 0 ? "project" : cleaned[..Math.Min(cleaned.Length, 80)];
    }
}

public sealed class ProjectKnowledgeExtraction
{
    public string SchemaVersion { get; init; } = ProjectKnowledgeExtractor.SchemaVersion;

    public required ProjectKnowledgeProject Project { get; init; }

    public required IReadOnlyList<ProjectKnowledgeElement> Elements { get; init; }

    public required IReadOnlyDictionary<string, int> Counts { get; init; }
}

public sealed class ProjectKnowledgeProject
{
    public required string Title { get; init; }

    public string? Path { get; init; }

    public string? RevitVersion { get; init; }

    public string? RevitBuild { get; init; }

    public required IReadOnlyDictionary<string, string> Units { get; init; }

    public string? FileSha256 { get; init; }

    public required DateTimeOffset ExtractedAt { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required IReadOnlyList<string> Levels { get; init; }
}

public sealed class ProjectKnowledgeElement
{
    public required string ElementId { get; init; }

    public required string UniqueId { get; init; }

    public required string Category { get; init; }

    public string? Family { get; init; }

    public string? TypeName { get; init; }

    public string? LevelId { get; init; }

    public string? HostId { get; init; }

    public string? RoomId { get; init; }

    public ProjectKnowledgeBounds? BoundingBox { get; init; }

    public required IReadOnlyList<ProjectKnowledgeParameter> Parameters { get; init; }

    public required ProjectKnowledgeGeometry Geometry { get; init; }
}

public sealed class ProjectKnowledgeBounds
{
    public required IReadOnlyList<double> Min { get; init; }

    public required IReadOnlyList<double> Max { get; init; }
}

public sealed class ProjectKnowledgeParameter
{
    public required string Name { get; init; }

    public required string StorageType { get; init; }

    public string? Value { get; init; }
}

public sealed class ProjectKnowledgeGeometry
{
    public int SolidCount { get; init; }
}
