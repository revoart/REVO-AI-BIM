using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Input;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;
using RevoAI.Revit.RevitApi;

namespace RevoAI.Revit.UI;

public enum WorkspaceStage
{
    Project,
    Import,
    Analyze,
    Generate,
    Knowledge,
    Subscription,
}

public sealed class WorkspaceViewModel : ObservableObject
{
    private readonly RevitTaskRunner _runner;
    private readonly IntPtr _revitWindowHandle;

    private string _projectName = "No project";
    private string _documentTitle = "Open a Revit project";
    private string _documentPath = string.Empty;
    private string _revitVersion = "—";
    private string _lengthUnitLabel = "m";
    private double _unitsPerFoot = 0.3048;

    private string _scanFileName = "No scan loaded";
    private string _scanStatus = "Import an E57, LAS/LAZ, PLY or XYZ scan to begin.";
    private string _pointCount = "—";
    private string _scanFormat = "—";
    private string _scanUnit = "—";
    private string _scanBounds = "—";
    private string _scanChunks = "—";
    private string _scanStorePath = "—";
    private string _scanWarnings = string.Empty;

    private string _selectedBuildingType = "Single-family house";
    private string _wallHeightText = "2.70";
    private string _floorThicknessText = "0.20";
    private double _confidenceThreshold = 0.75;
    private bool _markInferredGeometry = true;

    private LevelRowViewModel? _selectedLevel;
    private string _newLevelName = string.Empty;
    private string _newLevelElevationText = string.Empty;

    private string _statusMessage = "Workspace ready. No scan loaded.";
    private bool _isBusy;
    private WorkspaceStage _stage = WorkspaceStage.Project;
    private bool _referenceCloudVisible;
    private string _referenceCloudStatus = "No point-cloud reference in the model.";
    private double _progressValue;
    private int _detectedElements;
    private string _confidenceText = "—";

    private string _engineStatus = "Not connected";
    private string _engineDetails = "Run a connection test to verify the Python engine.";
    private string _engineProtocol = ProtocolVersion.Current;

    public WorkspaceViewModel(RevitTaskRunner runner, IntPtr revitWindowHandle)
    {
        _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        _revitWindowHandle = revitWindowHandle;

        BuildingTypes =
        [
            "Single-family house",
            "Semi-detached house",
            "Townhouse",
            "Low-rise residential",
            "Commercial",
            "Other",
        ];

        Import = new ImportScanViewModel();
        Subscription = new SubscriptionViewModel();
        Analysis = new ScanAnalysisViewModel(string.Empty, _confidenceThreshold);
        Generate = new ReconstructionViewModel(
            _runner,
            string.Empty,
            _confidenceThreshold,
            _markInferredGeometry);
        Knowledge = new KnowledgeViewModel(_runner, revitWindowHandle);
        Import.ImportCompleted += ApplyImportResult;
        Analysis.AnalysisCompleted += ApplyAnalysisResult;
        Generate.BuildCompleted += ApplyBuildResult;

        RefreshCommand = new AsyncRelayCommand(RefreshAsync);
        ImportScanCommand = new RelayCommand(ShowImportStage);
        ShowProjectStageCommand = new RelayCommand(ShowProjectStage);
        ShowImportStageCommand = new RelayCommand(ShowImportStage);
        ShowAnalysisStageCommand = new RelayCommand(ShowAnalysisStage);
        ShowGenerateStageCommand = new RelayCommand(ShowGenerateStage);
        ShowKnowledgeStageCommand = new RelayCommand(ShowKnowledgeStage);
        ShowSubscriptionStageCommand = new RelayCommand(ShowSubscriptionStage);
        TestEngineCommand = new AsyncRelayCommand(TestEngineAsync);
        ToggleReferenceCloudCommand = new AsyncRelayCommand(
            ToggleReferenceCloudAsync,
            () => HasScanStore() && !IsBusy);
        AddLevelCommand = new RelayCommand(AddLevel);
        RemoveLevelCommand = new RelayCommand(RemoveLevel, () => SelectedLevel is { IsExisting: false });
        CreateLevelsCommand = new AsyncRelayCommand(CreateLevelsAsync, () => !IsBusy && Levels.Any(level => !level.IsExisting));
        OpenLogFolderCommand = new RelayCommand(OpenLogFolder);
        OpenSettingsCommand = new RelayCommand(OpenSettings);

        Levels.CollectionChanged += (_, _) => RaiseLevelCommandStates();
    }

    public ObservableCollection<LevelRowViewModel> Levels { get; } = [];

    public ObservableCollection<string> Errors { get; } = [];

    public IReadOnlyList<string> BuildingTypes { get; }

    public ImportScanViewModel Import { get; }

    public ScanAnalysisViewModel Analysis { get; }

    public ReconstructionViewModel Generate { get; }

    public KnowledgeViewModel Knowledge { get; }

    public SubscriptionViewModel Subscription { get; }

    public ICommand RefreshCommand { get; }

    public ICommand ImportScanCommand { get; }

    public ICommand ShowProjectStageCommand { get; }

    public ICommand ShowImportStageCommand { get; }

    public ICommand ShowAnalysisStageCommand { get; }

    public ICommand ShowGenerateStageCommand { get; }

    public ICommand ShowKnowledgeStageCommand { get; }

    public ICommand ShowSubscriptionStageCommand { get; }

    public bool IsProjectStage => _stage == WorkspaceStage.Project;

    public bool IsImportStage => _stage == WorkspaceStage.Import;

    public bool IsAnalyzeStage => _stage == WorkspaceStage.Analyze;

    public bool IsGenerateStage => _stage == WorkspaceStage.Generate;

    public bool IsKnowledgeStage => _stage == WorkspaceStage.Knowledge;

    public bool IsSubscriptionStage => _stage == WorkspaceStage.Subscription;

    public string StageTitle => _stage switch
    {
        WorkspaceStage.Import => "Import scan",
        WorkspaceStage.Analyze => "Analyze scan",
        WorkspaceStage.Generate => "Generate BIM",
        WorkspaceStage.Knowledge => "Knowledge library",
        WorkspaceStage.Subscription => "Subscription",
        _ => "Project setup",
    };

    public string StageSubtitle => _stage switch
    {
        WorkspaceStage.Import => "Bring a supported scan into a local chunked store.",
        WorkspaceStage.Analyze => "Detect planar floors, ceilings and walls with confidence.",
        WorkspaceStage.Generate => "Preview the plan, then create native Revit floors and walls.",
        WorkspaceStage.Knowledge => "Search, review and extract local BIM knowledge with full provenance.",
        WorkspaceStage.Subscription => "Choose the Revo AI BIM plan that fits your work.",
        _ => "Inspect the project, levels, engine and workspace settings.",
    };

    public ICommand TestEngineCommand { get; }

    public ICommand ToggleReferenceCloudCommand { get; }

    public ICommand AddLevelCommand { get; }

    public ICommand RemoveLevelCommand { get; }

    public ICommand CreateLevelsCommand { get; }

    public ICommand OpenLogFolderCommand { get; }

    public ICommand OpenSettingsCommand { get; }

    public string ProductVersion => BuildInfo.Version;

    public string ProjectName
    {
        get => _projectName;
        private set => SetProperty(ref _projectName, value);
    }

    public string DocumentTitle
    {
        get => _documentTitle;
        private set => SetProperty(ref _documentTitle, value);
    }

    public string DocumentPath
    {
        get => _documentPath;
        private set => SetProperty(ref _documentPath, value);
    }

    public string RevitVersion
    {
        get => _revitVersion;
        private set => SetProperty(ref _revitVersion, value);
    }

    public string LengthUnitLabel
    {
        get => _lengthUnitLabel;
        private set
        {
            if (SetProperty(ref _lengthUnitLabel, value))
            {
                OnPropertyChanged(nameof(ElevationUnitLabel));
            }
        }
    }

    public string ElevationUnitLabel => LengthUnitLabel;

    public double UnitsPerFoot
    {
        get => _unitsPerFoot;
        private set => SetProperty(ref _unitsPerFoot, value);
    }

    public string ScanFileName
    {
        get => _scanFileName;
        private set => SetProperty(ref _scanFileName, value);
    }

    public string ScanStatus
    {
        get => _scanStatus;
        private set => SetProperty(ref _scanStatus, value);
    }

    public string PointCount
    {
        get => _pointCount;
        private set => SetProperty(ref _pointCount, value);
    }

    public string ScanFormat
    {
        get => _scanFormat;
        private set => SetProperty(ref _scanFormat, value);
    }

    public string ScanUnit
    {
        get => _scanUnit;
        private set => SetProperty(ref _scanUnit, value);
    }

    public string ScanBounds
    {
        get => _scanBounds;
        private set => SetProperty(ref _scanBounds, value);
    }

    public string ScanChunks
    {
        get => _scanChunks;
        private set => SetProperty(ref _scanChunks, value);
    }

    public string ScanStorePath
    {
        get => _scanStorePath;
        private set
        {
            if (SetProperty(ref _scanStorePath, value))
            {
                OnPropertyChanged(nameof(HasScan));
                (ToggleReferenceCloudCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool HasScan => HasScanStore();

    public bool ReferenceCloudVisible
    {
        get => _referenceCloudVisible;
        private set
        {
            if (SetProperty(ref _referenceCloudVisible, value))
            {
                OnPropertyChanged(nameof(ReferenceCloudButtonText));
            }
        }
    }

    public string ReferenceCloudButtonText =>
        ReferenceCloudVisible ? "Hide point cloud reference" : "Show point cloud reference";

    public string ReferenceCloudStatus
    {
        get => _referenceCloudStatus;
        private set => SetProperty(ref _referenceCloudStatus, value);
    }

    public string ScanWarnings
    {
        get => _scanWarnings;
        private set => SetProperty(ref _scanWarnings, value);
    }

    public string SelectedBuildingType
    {
        get => _selectedBuildingType;
        set => SetProperty(ref _selectedBuildingType, value);
    }

    public string WallHeightText
    {
        get => _wallHeightText;
        set
        {
            if (SetProperty(ref _wallHeightText, value))
            {
                Generate.FallbackWallHeightText = value;
            }
        }
    }

    public string FloorThicknessText
    {
        get => _floorThicknessText;
        set => SetProperty(ref _floorThicknessText, value);
    }

    public double ConfidenceThreshold
    {
        get => _confidenceThreshold;
        set
        {
            if (SetProperty(ref _confidenceThreshold, value))
            {
                Analysis.ConfidenceThresholdText = value.ToString("0.00", CultureInfo.InvariantCulture);
                Generate.ConfidenceThresholdText = value.ToString("0.00", CultureInfo.InvariantCulture);
            }
        }
    }

    public bool MarkInferredGeometry
    {
        get => _markInferredGeometry;
        set
        {
            if (SetProperty(ref _markInferredGeometry, value))
            {
                Generate.MarkInferred = value;
            }
        }
    }

    public LevelRowViewModel? SelectedLevel
    {
        get => _selectedLevel;
        set
        {
            if (SetProperty(ref _selectedLevel, value))
            {
                (RemoveLevelCommand as RelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public string NewLevelName
    {
        get => _newLevelName;
        set => SetProperty(ref _newLevelName, value);
    }

    public string NewLevelElevationText
    {
        get => _newLevelElevationText;
        set => SetProperty(ref _newLevelElevationText, value);
    }

    public string StatusMessage
    {
        get => _statusMessage;
        private set => SetProperty(ref _statusMessage, value);
    }

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (SetProperty(ref _isBusy, value))
            {
                RaiseLevelCommandStates();
                (ToggleReferenceCloudCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public double ProgressValue
    {
        get => _progressValue;
        private set => SetProperty(ref _progressValue, value);
    }

    public int DetectedElements
    {
        get => _detectedElements;
        private set => SetProperty(ref _detectedElements, value);
    }

    public string ConfidenceText
    {
        get => _confidenceText;
        private set => SetProperty(ref _confidenceText, value);
    }

    public string EngineStatus
    {
        get => _engineStatus;
        private set => SetProperty(ref _engineStatus, value);
    }

    public string EngineDetails
    {
        get => _engineDetails;
        private set => SetProperty(ref _engineDetails, value);
    }

    public string EngineProtocol
    {
        get => _engineProtocol;
        private set => SetProperty(ref _engineProtocol, value);
    }

    public string LogDirectory => RevoLog.Directory;

    public Task InitializeAsync() => RefreshAsync();

    /// <summary>Initializes from the Idling callback, already on Revit's main thread.</summary>
    public void InitializeFrom(UIApplication application)
    {
        try
        {
            var snapshot = DocumentReader.Read(application);
            ApplySnapshot(snapshot);
            StatusMessage = $"Loaded '{snapshot.Title}'.";
        }
        catch (Exception ex)
        {
            AddError("Could not read the active Revit document.", ex);
        }
    }

    public void ShowProjectStage() => SetStage(WorkspaceStage.Project);

    public void ShowImportStage() => SetStage(WorkspaceStage.Import);

    public void ShowAnalysisStage()
    {
        PrepareScanStages();
        SetStage(WorkspaceStage.Analyze);
        if (!HasScanStore())
        {
            StatusMessage = "Import a scan first; Scan Analysis becomes available after an import.";
        }
    }

    public void ShowGenerateBim() => ShowGenerateStage();

    public void ShowGenerateStage()
    {
        PrepareScanStages();
        SetStage(WorkspaceStage.Generate);
        if (!HasScanStore())
        {
            StatusMessage = "Import a scan and run Scan Analysis before generating BIM.";
        }
    }

    public void ShowKnowledgeStage()
    {
        SetStage(WorkspaceStage.Knowledge);
        _ = Knowledge.LoadAsync();
    }

    public void ShowSubscriptionStage() => SetStage(WorkspaceStage.Subscription);

    private void SetStage(WorkspaceStage stage)
    {
        if (_stage == stage)
        {
            return;
        }

        _stage = stage;
        OnPropertyChanged(nameof(IsProjectStage));
        OnPropertyChanged(nameof(IsImportStage));
        OnPropertyChanged(nameof(IsAnalyzeStage));
        OnPropertyChanged(nameof(IsGenerateStage));
        OnPropertyChanged(nameof(IsKnowledgeStage));
        OnPropertyChanged(nameof(IsSubscriptionStage));
        OnPropertyChanged(nameof(StageTitle));
        OnPropertyChanged(nameof(StageSubtitle));
    }

    private bool HasScanStore() =>
        !string.IsNullOrWhiteSpace(ScanStorePath) &&
        ScanStorePath != "—" &&
        Directory.Exists(ScanStorePath);

    private void PrepareScanStages()
    {
        if (!HasScanStore())
        {
            return;
        }

        Analysis.StorePath = ScanStorePath;
        Generate.StorePath = ScanStorePath;
    }

    private async Task RefreshAsync()
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;

        try
        {
            var snapshot = await _runner.InvokeAsync(DocumentReader.Read);
            ApplySnapshot(snapshot);
            ReferenceCloudVisible = await _runner.InvokeAsync(PointCloudReferenceBuilder.Exists);
            ReferenceCloudStatus = ReferenceCloudVisible
                ? "Point-cloud reference is present in the model."
                : "No point-cloud reference in the model.";
            StatusMessage = $"Loaded '{snapshot.Title}'.";
        }
        catch (Exception ex)
        {
            AddError("Could not read the active Revit document.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void ApplySnapshot(DocumentSnapshot snapshot)
    {
        ProjectName = snapshot.ProjectName;
        DocumentTitle = snapshot.Title;
        DocumentPath = snapshot.Path;
        RevitVersion = snapshot.RevitVersion;
        LengthUnitLabel = snapshot.LengthUnitLabel;
        UnitsPerFoot = snapshot.UnitsPerFoot;

        Levels.Clear();
        foreach (var level in snapshot.Levels)
        {
            Levels.Add(new LevelRowViewModel(
                level.Name,
                level.ElevationFeet * snapshot.UnitsPerFoot,
                isExisting: true));
        }

        SelectedLevel = null;
        RaiseLevelCommandStates();
    }

    private void AddLevel()
    {
        var name = NewLevelName.Trim();
        if (string.IsNullOrWhiteSpace(name))
        {
            StatusMessage = "Enter a level name before adding it.";
            return;
        }

        if (Levels.Any(level => string.Equals(level.Name, name, StringComparison.OrdinalIgnoreCase)))
        {
            StatusMessage = $"A level named '{name}' is already in the list.";
            return;
        }

        if (!TryParseElevation(NewLevelElevationText, out var elevation))
        {
            StatusMessage = "Enter a valid elevation in " + ElevationUnitLabel + ".";
            return;
        }

        Levels.Add(new LevelRowViewModel(name, elevation, isExisting: false));
        NewLevelName = string.Empty;
        NewLevelElevationText = string.Empty;
        StatusMessage = $"Added '{name}' to the list. It is not in Revit yet.";
        RaiseLevelCommandStates();
    }

    private void RemoveLevel()
    {
        if (SelectedLevel is not { IsExisting: false })
        {
            return;
        }

        var name = SelectedLevel.Name;
        Levels.Remove(SelectedLevel);
        SelectedLevel = null;
        StatusMessage = $"Removed '{name}' from the list.";
        RaiseLevelCommandStates();
    }

    private async Task CreateLevelsAsync()
    {
        var newLevels = Levels.Where(level => !level.IsExisting).ToList();
        if (newLevels.Count == 0)
        {
            StatusMessage = "There are no new levels to create.";
            return;
        }

        if (UnitsPerFoot <= 0)
        {
            StatusMessage = "The project unit conversion is invalid; refresh the workspace.";
            return;
        }

        var requests = newLevels
            .Select(level => new LevelRequest(level.Name.Trim(), level.ElevationDisplay / UnitsPerFoot))
            .ToList();

        IsBusy = true;
        string? successMessage = null;

        try
        {
            var result = await _runner.InvokeAsync(app => DocumentReader.CreateLevels(app, requests));

            successMessage = result.Created.Count == 0
                ? $"No levels created. {result.Skipped.Count} already existed."
                : $"Created {result.Created.Count} level(s) in Revit. Skipped {result.Skipped.Count} existing.";

            RevoLog.Info(successMessage);
        }
        catch (Exception ex)
        {
            AddError("Level creation failed. No changes were committed.", ex);
        }
        finally
        {
            IsBusy = false;
        }

        await RefreshAsync();

        if (successMessage is not null)
        {
            StatusMessage = successMessage;
        }
    }

    private async Task ToggleReferenceCloudAsync()
    {
        if (!HasScanStore())
        {
            StatusMessage = "Import a scan before showing its reference cloud.";
            return;
        }

        await SetReferenceCloudVisibleAsync(!ReferenceCloudVisible);
    }

    private async Task ShowReferenceCloudAsync(bool force = false)
    {
        if (!HasScanStore() || IsBusy || (ReferenceCloudVisible && !force))
        {
            return;
        }

        await SetReferenceCloudVisibleAsync(show: true);
    }

    private async Task SetReferenceCloudVisibleAsync(bool show)
    {
        IsBusy = true;
        try
        {
            if (!show)
            {
                await _runner.InvokeAsync(PointCloudReferenceBuilder.Hide);
                ReferenceCloudVisible = false;
                ReferenceCloudStatus = "Hidden: the model reference was removed.";
                StatusMessage = "Point-cloud reference hidden.";
                RevoLog.Info(ReferenceCloudStatus);
                return;
            }

            var config = RevoConfig.Load();
            await using var client = await PythonEngineClient.StartAsync(config);
            var sample = await client.QueryPointCloudAsync(new PointCloudQueryParams
            {
                StorePath = ScanStorePath,
                MaxPoints = 4_000,
            });

            if (sample.Positions.Count == 0)
            {
                throw new InvalidOperationException("The scan sample contains no points.");
            }

            var positions = sample.Positions;
            var visible = await _runner.InvokeAsync(
                app => PointCloudReferenceBuilder.Show(app, positions));

            ReferenceCloudVisible = visible;
            ReferenceCloudStatus =
                $"Shown: {sample.Returned:N0} sampled marker(s) in the model.";
            StatusMessage =
                "Point-cloud reference shown. This is sampled reference geometry, not native point-cloud data.";
            RevoLog.Info(ReferenceCloudStatus);
        }
        catch (Exception ex)
        {
            AddError("Could not update the point-cloud reference.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task TestEngineAsync()
    {
        IsBusy = true;
        EngineStatus = "Connecting…";
        EngineDetails = "Starting the Python engine process.";

        try
        {
            var config = RevoConfig.Load();

            await using var client = await PythonEngineClient.StartAsync(config);
            var handshake = client.Handshake
                ?? throw new InvalidOperationException("The engine did not return a handshake.");
            var pong = await client.PingAsync("workspace");

            EngineStatus = "Connected";
            EngineProtocol = handshake.ProtocolVersion;
            EngineDetails =
                $"Engine {handshake.ServerVersion} · Python {handshake.PythonVersion} · " +
                $"ping {pong.ServerTimeUtc:HH:mm:ss}Z · {string.Join(", ", handshake.Capabilities)}";

            StatusMessage = "Python engine connection verified.";
            RevoLog.Info("Workspace engine test succeeded: " + EngineDetails);
        }
        catch (Exception ex)
        {
            EngineStatus = "Unavailable";
            EngineDetails = ex.Message;
            AddError(
                "Could not start the Python engine. Set the engine root in Settings, then retry.",
                ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void ApplyBuildResult(ReconstructionBuildResult result)
    {
        ProgressValue = 100;
        DetectedElements = result.CreatedFloors.Count + result.CreatedWalls.Count;
        StatusMessage = result.Message;
        RevoLog.Info(result.Message);
        foreach (var warning in result.Warnings)
        {
            RevoLog.Warn(warning);
        }
    }

    private void ApplyAnalysisResult(SegmentationResult result)
    {
        DetectedElements = result.Summary.Segments;
        ConfidenceText = result.Summary.MeanConfidence.ToString("P1", CultureInfo.CurrentCulture);
        ProgressValue = 100;
        ScanStatus = $"Analyzed · {result.Summary.Segments:N0} planar instance(s)";
        StatusMessage =
            $"Scan analysis found {result.Summary.Segments:N0} planar instance(s) at " +
            $"{result.Summary.MeanConfidence:P1} mean plane-fit confidence. " +
            "No Revit geometry was created.";
        RevoLog.Info(
            $"Workspace applied analysis {result.ScanId}: {result.Summary.Segments} segments, " +
            $"{result.Summary.MeanConfidence:0.000} mean confidence.");
    }

    private void ApplyImportResult(PointCloudImportResult result)
    {
        ScanFileName = Path.GetFileName(result.SourcePath);
        ScanStatus = "Imported and chunked locally";
        PointCount = $"{result.PointCount.Stored:N0} stored / {result.PointCount.Original:N0} source";
        ScanFormat = result.Format.ToUpperInvariant();
        ScanUnit = $"{result.Unit} ({result.UnitSource})";
        ScanBounds =
            $"[{result.Bounds.Min[0]:0.###}, {result.Bounds.Min[1]:0.###}, {result.Bounds.Min[2]:0.###}] → " +
            $"[{result.Bounds.Max[0]:0.###}, {result.Bounds.Max[1]:0.###}, {result.Bounds.Max[2]:0.###}] m";
        ScanChunks = result.ChunkCount.ToString("N0", CultureInfo.CurrentCulture);
        ScanStorePath = result.StorePath;
        Analysis.StorePath = result.StorePath;
        Generate.StorePath = result.StorePath;
        _ = ShowReferenceCloudAsync(force: true);
        ScanWarnings = result.Warnings.Count == 0
            ? "No import warnings."
            : string.Join(Environment.NewLine, result.Warnings.Select(warning => "• " + warning));

        StatusMessage =
            $"Scan '{result.ScanId}' imported: {result.PointCount.Stored:N0} stored point(s) in " +
            $"{result.ChunkCount:N0} chunk(s).";
        RevoLog.Info(
            $"Workspace loaded scan {result.ScanId} from {result.StorePath} " +
            $"({result.PointCount.Stored} points, {result.ChunkCount} chunks).");
    }

    private void OpenSettings()
    {
        var window = new SettingsWindow();

        if (_revitWindowHandle != IntPtr.Zero)
        {
            new System.Windows.Interop.WindowInteropHelper(window) { Owner = _revitWindowHandle };
        }

        window.ShowDialog();
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
            AddError("Could not open the log folder.", ex);
        }
    }

    private void AddError(string message, Exception exception)
    {
        var text = $"{message} {exception.Message}";
        Errors.Add(text);
        StatusMessage = text;
        RevoLog.Error(message, exception);
    }

    private bool TryParseElevation(string text, out double elevation)
    {
        if (double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out elevation) ||
            double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out elevation))
        {
            return !double.IsNaN(elevation) && !double.IsInfinity(elevation);
        }

        elevation = 0;
        return false;
    }

    private void RaiseLevelCommandStates()
    {
        (RemoveLevelCommand as RelayCommand)?.RaiseCanExecuteChanged();
        (CreateLevelsCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
    }
}

public sealed class LevelRowViewModel : ObservableObject
{
    public LevelRowViewModel(string name, double elevationDisplay, bool isExisting)
    {
        Name = name;
        ElevationDisplay = elevationDisplay;
        IsExisting = isExisting;
    }

    public string Name { get; }

    public double ElevationDisplay { get; }

    public bool IsExisting { get; }

    public string Source => IsExisting ? "Revit" : "New";

    public string ElevationText =>
        ElevationDisplay.ToString("0.###", CultureInfo.CurrentCulture);
}
