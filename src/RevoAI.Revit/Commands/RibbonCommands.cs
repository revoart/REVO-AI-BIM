using System.Windows;
using System.Windows.Interop;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using RevoAI.Revit.UI;

namespace RevoAI.Revit.Commands;

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class WorkspaceCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.ShowAfterCommand(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class ImportScanCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.ImportScan(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class ScanAnalysisCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.AnalyzeScan(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class GenerateBimCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.GenerateBim(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class KnowledgeCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.ShowKnowledge(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class ExtractKnowledgeCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        WorkspaceController.ExtractProjectKnowledge(commandData.Application);
        return Result.Succeeded;
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class ModelReviewCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData) =>
        PhaseMessages.Show(
            "Model Review",
            "Detected-element review, acceptance and type assignment arrive with the " +
            "reconstruction pipeline in Phase 5.\n\nThere is nothing to review yet.");
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class QualityCheckCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData) =>
        PhaseMessages.Show(
            "Quality Check",
            "Scan-to-model deviation analysis and confidence reporting are implemented in Phase 8.\n\n" +
            "No accuracy figure is reported until it has been measured against a defined method.");
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class SettingsCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        var window = new SettingsWindow();
        AttachOwner(window, commandData.Application);
        window.ShowDialog();
        return Result.Succeeded;
    }

    internal static void AttachOwner(Window window, UIApplication application)
    {
        if (application.MainWindowHandle != IntPtr.Zero)
        {
            new WindowInteropHelper(window) { Owner = application.MainWindowHandle };
        }
    }
}

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public sealed class AboutCommand : RevoCommandBase
{
    protected override Result ExecuteCore(ExternalCommandData commandData)
    {
        var revitVersion =
            $"{commandData.Application.Application.VersionNumber} " +
            $"(build {commandData.Application.Application.VersionBuild})";

        var window = new AboutWindow(revitVersion);
        SettingsCommand.AttachOwner(window, commandData.Application);
        window.ShowDialog();
        return Result.Succeeded;
    }
}
