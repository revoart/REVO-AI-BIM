using System.Windows;
using System.Windows.Interop;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.UI;

/// <summary>
/// Owns the single modeless workspace window. The window is created on Revit's
/// main thread from a ribbon command; all Revit API work it triggers is routed
/// back through <see cref="RevitApi.RevitTaskRunner"/>.
/// </summary>
public static class WorkspaceController
{
    private static WorkspaceWindow? _window;
    private static WorkspaceViewModel? _viewModel;
    private static RevitApi.RevitTaskRunner? _runner;

    public static void Show(UIApplication application)
    {
        ArgumentNullException.ThrowIfNull(application);

        if (_window is { IsLoaded: true })
        {
            _window.Activate();
            return;
        }

        _runner ??= new RevitApi.RevitTaskRunner();
        _viewModel = new WorkspaceViewModel(_runner, application.MainWindowHandle);

        _window = new WorkspaceWindow
        {
            DataContext = _viewModel,
        };

        if (application.MainWindowHandle != IntPtr.Zero)
        {
            new WindowInteropHelper(_window) { Owner = application.MainWindowHandle };
        }

        _window.Closed += (_, _) =>
        {
            _window = null;
            _viewModel = null;
        };

        _window.Show();
        _ = _viewModel.InitializeAsync();
    }

    /// <summary>Shows the workspace and opens the real point cloud import dialog.</summary>
    public static void ImportScan(UIApplication application)
    {
        Show(application);
        _viewModel?.BeginImport();
    }

    public static void Close()
    {
        try
        {
            _window?.Close();
        }
        catch (Exception ex)
        {
            RevoLog.Warn("Could not close the workspace window: " + ex.Message);
        }
        finally
        {
            _window = null;
            _viewModel = null;
        }
    }
}
