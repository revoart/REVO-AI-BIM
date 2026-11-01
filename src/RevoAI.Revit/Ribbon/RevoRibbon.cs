using System.Reflection;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.Ribbon;

/// <summary>
/// Builds the REVO AI BIM ribbon tab. Phase 2 exposes the full command surface;
/// commands for later phases report honestly that their capability is not
/// implemented yet.
/// </summary>
public static class RevoRibbon
{
    private const string TabName = "REVO AI BIM";

    public static void Create(UIControlledApplication application)
    {
        ArgumentNullException.ThrowIfNull(application);

        try
        {
            application.CreateRibbonTab(TabName);
        }
        catch (ArgumentException)
        {
            // Tab already exists (for example after a manual reload).
        }

        var assemblyPath = Assembly.GetExecutingAssembly().Location;

        var workspacePanel = application.CreateRibbonPanel(TabName, "Revo AI BIM");
        workspacePanel.AddItem(CreateButton<Commands.WorkspaceCommand>(
            "RevoAIWorkspace", "Workspace", assemblyPath, "workspace",
            "Open the Revo AI BIM workspace",
            "Project information, scan status, reconstruction settings, levels and engine diagnostics."));

        var scanPanel = application.CreateRibbonPanel(TabName, "Scan");
        scanPanel.AddItem(CreateButton<Commands.ImportScanCommand>(
            "RevoAIImportScan", "Import Scan", assemblyPath, "import",
            "Import a laser scan",
            "Point cloud import (E57, LAS/LAZ, PLY, XYZ) is implemented in Phase 3."));
        scanPanel.AddItem(CreateButton<Commands.ScanAnalysisCommand>(
            "RevoAIScanAnalysis", "Scan Analysis", assemblyPath, "analysis",
            "Analyse the imported scan",
            "Noise removal, segmentation and AI classification are implemented in Phases 3-4."));

        var bimPanel = application.CreateRibbonPanel(TabName, "BIM");
        bimPanel.AddItem(CreateButton<Commands.GenerateBimCommand>(
            "RevoAIGenerateBim", "Generate BIM", assemblyPath, "generate",
            "Generate native Revit elements",
            "Native wall and floor generation is implemented in Phase 5."));
        bimPanel.AddItem(CreateButton<Commands.ModelReviewCommand>(
            "RevoAIModelReview", "Model Review", assemblyPath, "review",
            "Review detected geometry",
            "Element review and acceptance is implemented with the reconstruction pipeline in Phase 5."));
        bimPanel.AddItem(CreateButton<Commands.QualityCheckCommand>(
            "RevoAIQualityCheck", "Quality Check", assemblyPath, "quality",
            "Compare the model with the scan",
            "Scan-to-model deviation analysis is implemented in Phase 8."));

        var projectPanel = application.CreateRibbonPanel(TabName, "Project");
        projectPanel.AddItem(CreateButton<Commands.SettingsCommand>(
            "RevoAISettings", "Settings", assemblyPath, "settings",
            "Configure Revo AI BIM",
            "Python engine location, timeouts, configuration file and log folder."));
        projectPanel.AddItem(CreateButton<Commands.AboutCommand>(
            "RevoAIAbout", "About", assemblyPath, "about",
            "About Revo AI BIM",
            "Version, Revit compatibility, engine protocol and log location."));

        var knowledgePanel = application.CreateRibbonPanel(TabName, "Knowledge");
        knowledgePanel.AddItem(CreateButton<Commands.KnowledgeCommand>(
            "RevoAIKnowledge", "Knowledge Library", assemblyPath, "review",
            "Open the local BIM knowledge library",
            "Search, review and inspect locally stored BIM techniques, API notes and verified projects."));
        knowledgePanel.AddItem(CreateButton<Commands.ExtractKnowledgeCommand>(
            "RevoAIExtractKnowledge", "Extract Project", assemblyPath, "analysis",
            "Extract the active project into the local knowledge library",
            "Read-only extraction of levels, walls, floors, doors, windows and parameters. The project is not modified."));
    }

    private static PushButtonData CreateButton<TCommand>(
        string id,
        string text,
        string assemblyPath,
        string iconName,
        string toolTip,
        string longDescription)
        where TCommand : Autodesk.Revit.UI.IExternalCommand
    {
        return new PushButtonData(id, text, assemblyPath, typeof(TCommand).FullName!)
        {
            ToolTip = toolTip,
            LongDescription = longDescription,
            Image = LoadIcon($"{iconName}-16.png"),
            LargeImage = LoadIcon($"{iconName}-32.png"),
        };
    }

    private static BitmapImage LoadIcon(string fileName)
    {
        var image = new BitmapImage();
        image.BeginInit();
        image.UriSource = new Uri(
            $"pack://application:,,,/RevoAI.Revit;component/Resources/Icons/{fileName}",
            UriKind.Absolute);
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.EndInit();
        image.Freeze();
        return image;
    }
}
