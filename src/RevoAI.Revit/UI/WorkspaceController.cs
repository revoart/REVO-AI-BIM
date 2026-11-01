using System.Windows;
using System.Windows.Interop;
using Autodesk.Revit.UI;
using Autodesk.Revit.UI.Events;

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

    /// <summary>
    /// Must be called during Revit's standard API execution (OnStartup), because
    /// ExternalEvent.Create is not allowed from an Idling callback.
    /// </summary>
    public static void Initialize()
    {
        _runner ??= new RevitApi.RevitTaskRunner();
    }

    internal static Window? CurrentWindow => _window;

    public static void Show(UIApplication application, bool initialize = true)
    {
        ArgumentNullException.ThrowIfNull(application);

        if (_window is { IsLoaded: true })
        {
            _window.Activate();
            return;
        }

        if (_runner is null)
        {
            throw new InvalidOperationException(
                "The Revo AI BIM Revit task runner was not initialized during add-in startup.");
        }

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

        if (initialize)
        {
            RunWhenIdle(application, () => _ = _viewModel?.InitializeAsync());
        }
    }

    /// <summary>Shows the workspace after the current Revit command has returned.</summary>
    public static void ShowAfterCommand(UIApplication application) =>
        RunWhenIdle(application, () => Show(application));

    /// <summary>Shows the workspace and opens the real point cloud import dialog.</summary>
    public static void ImportScan(UIApplication application) =>
        RunWhenIdle(application, () =>
        {
            Show(application, initialize: false);
            _viewModel?.BeginImport();
        });

    /// <summary>Shows the workspace and runs Scan Analysis for the loaded scan.</summary>
    public static void AnalyzeScan(UIApplication application) =>
        RunWhenIdle(application, () =>
        {
            Show(application);
            _viewModel?.BeginAnalysis();
        });

    /// <summary>
    /// Runs work on Revit's main thread after the current external command has
    /// returned. A nested WPF modal loop or ExternalEvent raised from inside a
    /// ribbon command can terminate Revit, so every window-opening action goes
    /// through the Idling event instead.
    /// </summary>
    private static void RunWhenIdle(UIApplication application, Action action)
    {
        ArgumentNullException.ThrowIfNull(application);
        ArgumentNullException.ThrowIfNull(action);

        EventHandler<IdlingEventArgs>? handler = null;
        handler = (_, _) =>
        {
            application.Idling -= handler;
            try
            {
                action();
            }
            catch (Exception ex)
            {
                RevoLog.Error("Deferred Revo AI BIM UI action failed.", ex);
            }
        };
        application.Idling += handler;
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
