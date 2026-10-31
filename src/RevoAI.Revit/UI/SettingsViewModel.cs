using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows.Input;
using Microsoft.Win32;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;

namespace RevoAI.Revit.UI;

public sealed class SettingsViewModel : ObservableObject
{
    private string _pythonExecutable = string.Empty;
    private string _engineRoot = string.Empty;
    private string _startupTimeoutText = "60";
    private string _requestTimeoutText = "120";
    private string _statusMessage = "Changes apply the next time the engine starts.";

    public SettingsViewModel()
    {
        try
        {
            Load();
        }
        catch (Exception ex)
        {
            StatusMessage = "Could not read the current configuration: " + ex.Message;
            RevoLog.Error("Could not load configuration into Settings.", ex);
        }

        SaveCommand = new RelayCommand(Save);
        BrowsePythonCommand = new RelayCommand(BrowsePython);
        BrowseEngineRootCommand = new RelayCommand(BrowseEngineRoot);
        OpenLogFolderCommand = new RelayCommand(OpenLogFolder);
    }

    public string PythonExecutable
    {
        get => _pythonExecutable;
        set => SetProperty(ref _pythonExecutable, value);
    }

    public string EngineRoot
    {
        get => _engineRoot;
        set => SetProperty(ref _engineRoot, value);
    }

    public string StartupTimeoutText
    {
        get => _startupTimeoutText;
        set => SetProperty(ref _startupTimeoutText, value);
    }

    public string RequestTimeoutText
    {
        get => _requestTimeoutText;
        set => SetProperty(ref _requestTimeoutText, value);
    }

    public string StatusMessage
    {
        get => _statusMessage;
        private set => SetProperty(ref _statusMessage, value);
    }

    public string ConfigPath => RevoConfig.DefaultConfigPath;

    public string LogDirectory => RevoLog.Directory;

    public ICommand SaveCommand { get; }

    public ICommand BrowsePythonCommand { get; }

    public ICommand BrowseEngineRootCommand { get; }

    public ICommand OpenLogFolderCommand { get; }

    private void Load()
    {
        var config = RevoConfig.Load();
        PythonExecutable = config.PythonExecutable;
        EngineRoot = config.EngineRoot ?? string.Empty;
        StartupTimeoutText = config.StartupTimeoutSeconds.ToString(CultureInfo.CurrentCulture);
        RequestTimeoutText = config.RequestTimeoutSeconds.ToString(CultureInfo.CurrentCulture);
    }

    private void Save()
    {
        if (!int.TryParse(StartupTimeoutText, NumberStyles.Integer, CultureInfo.CurrentCulture, out var startup) ||
            startup is < 1 or > 600)
        {
            StatusMessage = "Startup timeout must be a whole number between 1 and 600 seconds.";
            return;
        }

        if (!int.TryParse(RequestTimeoutText, NumberStyles.Integer, CultureInfo.CurrentCulture, out var request) ||
            request is < 1 or > 3600)
        {
            StatusMessage = "Request timeout must be a whole number between 1 and 3600 seconds.";
            return;
        }

        var python = PythonExecutable.Trim();
        if (python.Length > 0 && Path.IsPathRooted(python) && !File.Exists(python))
        {
            StatusMessage = "The configured Python executable does not exist.";
            return;
        }

        var engineRoot = EngineRoot.Trim();
        if (engineRoot.Length > 0 && !Directory.Exists(engineRoot))
        {
            StatusMessage = "The configured engine root folder does not exist.";
            return;
        }

        try
        {
            var config = new RevoConfig
            {
                PythonExecutable = python,
                EngineRoot = engineRoot.Length == 0 ? null : engineRoot,
                StartupTimeoutSeconds = startup,
                RequestTimeoutSeconds = request,
            };

            RevoConfigWriter.Save(config);
            StatusMessage = "Saved to " + RevoConfig.DefaultConfigPath;
            RevoLog.Info("Configuration saved from Settings window.");
        }
        catch (Exception ex)
        {
            StatusMessage = "Could not save the configuration: " + ex.Message;
            RevoLog.Error("Configuration save failed.", ex);
        }
    }

    private void BrowsePython()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select python.exe",
            Filter = "Python executable (python.exe)|python.exe|All files (*.*)|*.*",
            CheckFileExists = true,
        };

        if (dialog.ShowDialog() == true)
        {
            PythonExecutable = dialog.FileName;
        }
    }

    private void BrowseEngineRoot()
    {
        var dialog = new OpenFolderDialog
        {
            Title = "Select the Revo AI BIM engine root (contains src\\RevoAI.Engine)",
        };

        if (dialog.ShowDialog() == true)
        {
            EngineRoot = dialog.FolderName;
        }
    }

    private void OpenLogFolder()
    {
        try
        {
            Directory.CreateDirectory(RevoLog.Directory);
            Process.Start(new ProcessStartInfo
            {
                FileName = RevoLog.Directory,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            StatusMessage = "Could not open the log folder: " + ex.Message;
        }
    }
}

public sealed class AboutViewModel
{
    public AboutViewModel(string revitVersion)
    {
        RevitVersion = revitVersion;
    }

    public string ProductName => "Revo AI BIM";

    public string Version => BuildInfo.Version;

    public string InformationalVersion => BuildInfo.InformationalVersion;

    public string RevitVersion { get; }

    public string ProtocolVersion => RevoAI.Contracts.Protocol.ProtocolVersion.Current;

    public string LogDirectory => RevoLog.Directory;

    public string ConfigPath => RevoConfig.DefaultConfigPath;

    public string Copyright => "© 2026 RevoStudioz. All rights reserved.";
}
