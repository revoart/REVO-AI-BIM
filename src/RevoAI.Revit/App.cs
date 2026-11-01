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
            InstallCrashLogging();
            WorkspaceController.Initialize();
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

    private static void InstallCrashLogging()
    {
        // These handlers do not swallow failures; they make sure the add-in log
        // contains the managed exception behind a Revit crash.
        System.Windows.Threading.Dispatcher.CurrentDispatcher.UnhandledException += (_, args) =>
            RevoLog.Error("Unhandled WPF dispatcher exception.", args.Exception);

        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
        {
            if (args.ExceptionObject is Exception exception)
            {
                RevoLog.Error("Unhandled AppDomain exception.", exception);
            }
        };

        TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            RevoLog.Error("Unobserved task exception.", args.Exception);
            args.SetObserved();
        };
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
