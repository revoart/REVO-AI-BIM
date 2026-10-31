using Autodesk.Revit.UI;
using RevoAI.Revit.Ribbon;
using RevoAI.Revit.UI;

namespace RevoAI.Revit;

/// <summary>
/// Add-in entry point: initialises logging, builds the REVO AI BIM ribbon and
/// shuts the workspace down cleanly. All Revit work triggered by the modeless
/// window is marshalled through <c>RevitTaskRunner</c>.
/// </summary>
public sealed class App : IExternalApplication
{
    public Result OnStartup(UIControlledApplication application)
    {
        try
        {
            RevoLog.Initialize();
            RevoRibbon.Create(application);
            RevoLog.Info(
                $"Revo AI BIM {BuildInfo.Version} loaded. Revit {application.ControlledApplication.VersionNumber} " +
                $"build {application.ControlledApplication.VersionBuild}.");
            return Result.Succeeded;
        }
        catch (Exception ex)
        {
            RevoLog.Error("Revo AI BIM failed to start.", ex);
            return Result.Failed;
        }
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        try
        {
            WorkspaceController.Close();
            RevoLog.Info("Revo AI BIM shutting down.");
            RevoLog.Shutdown();
            return Result.Succeeded;
        }
        catch
        {
            // Never let logging failures block Revit shutdown.
            return Result.Succeeded;
        }
    }
}
