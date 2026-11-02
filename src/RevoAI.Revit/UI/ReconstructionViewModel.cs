using System.Collections.ObjectModel;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Windows.Input;
using Autodesk.Revit.UI;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;
using RevoAI.Revit.RevitApi;

namespace RevoAI.Revit.UI;

/// <summary>
/// Builds a Revit-ready reconstruction plan and creates native floors and walls
/// in a single Revit transaction. The plan is shown before anything is created.
/// </summary>
public sealed class ReconstructionViewModel : ObservableObject
{
    private readonly RevitTaskRunner? _runner;
    private string _storePath;
    private string _confidenceThresholdText;
    private string _fallbackWallHeightText = "2.7";
    private string _levelToleranceText = "0.25";
    private string _maxElementsText = "200";
    private string _selectedProvider = "Revo AI (DeepSeek Go)";
    private string _externalPlanPath = string.Empty;
    private bool _markInferred;
    private string _statusMessage = "Create a plan to preview native floors and walls before building them.";
    private string _errorMessage = string.Empty;
    private string _warningsText = string.Empty;
    private string _planSummary = string.Empty;
    private string _blockingIssuesText = string.Empty;
    private bool _isBuildable = true;
    private double _buildProgressValue;
    private string _buildProgressText = string.Empty;
    private bool _isBusy;
    private ReconstructionPlanResult? _plan;

    public ReconstructionViewModel(
        RevitTaskRunner? runner,
        string storePath,
        double confidenceThreshold,
        bool markInferred)
    {
        _runner = runner;
        _storePath = storePath ?? string.Empty;
        _confidenceThresholdText = confidenceThreshold.ToString("0.00", CultureInfo.InvariantCulture);
        _markInferred = markInferred;

        ProviderOptions =
        [
            "Revo AI (DeepSeek Go)",
            "External plan JSON",
        ];

        PreviewCommand = new AsyncRelayCommand(PreviewAsync, CanPreview);
        BuildCommand = new RelayCommand(Build, CanBuild);
        OpenStoreFolderCommand = new RelayCommand(OpenStoreFolder, () => Plan is not null);
        BrowseExternalPlanCommand = new RelayCommand(BrowseExternalPlan, () => !IsBusy);
    }

    public event Action<ReconstructionBuildResult>? BuildCompleted;

    public ObservableCollection<PlanFloor> Floors { get; } = [];

    public ObservableCollection<PlanWall> Walls { get; } = [];

    public ICommand PreviewCommand { get; }

    public ICommand BuildCommand { get; }

    public ICommand OpenStoreFolderCommand { get; }

    public IReadOnlyList<string> ProviderOptions { get; }

    public ICommand BrowseExternalPlanCommand { get; }

    public string StorePath
    {
        get => _storePath;
        set
        {
            if (SetProperty(ref _storePath, value))
            {
                (PreviewCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public string ConfidenceThresholdText
    {
        get => _confidenceThresholdText;
        set => SetProperty(ref _confidenceThresholdText, value);
    }

    public string FallbackWallHeightText
    {
        get => _fallbackWallHeightText;
        set => SetProperty(ref _fallbackWallHeightText, value);
    }

    public string LevelToleranceText
    {
        get => _levelToleranceText;
        set => SetProperty(ref _levelToleranceText, value);
    }

    public string MaxElementsText
    {
        get => _maxElementsText;
        set => SetProperty(ref _maxElementsText, value);
    }

    public string SelectedProvider
    {
        get => _selectedProvider;
        set
        {
            if (SetProperty(ref _selectedProvider, value))
            {
                OnPropertyChanged(nameof(IsExternalPlanProvider));
                OnPropertyChanged(nameof(IsAstraSubscriptionProvider));
            }
        }
    }

    public bool IsExternalPlanProvider => SelectedProvider == "External plan JSON";

    public bool IsAstraSubscriptionProvider =>
        SelectedProvider == "Revo AI (DeepSeek Go)";

    public string AiProviderLabel
    {
        get
        {
            var preferred = Environment.GetEnvironmentVariable("REVOAI_AI_PROVIDER");
            if (string.Equals(preferred, "openai", StringComparison.OrdinalIgnoreCase))
            {
                return "OpenAI";
            }
            if (string.Equals(preferred, "claude", StringComparison.OrdinalIgnoreCase))
            {
                return "Claude";
            }
            if (string.Equals(preferred, "deepseek", StringComparison.OrdinalIgnoreCase))
            {
                return "DeepSeek Go";
            }

            var claudeKey =
                Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ??
                Environment.GetEnvironmentVariable("REVOAI_ANTHROPIC_API_KEY");
            if (!string.IsNullOrWhiteSpace(claudeKey))
            {
                return "Claude";
            }

            var openAiKey =
                Environment.GetEnvironmentVariable("OPENAI_API_KEY") ??
                Environment.GetEnvironmentVariable("REVOAI_OPENAI_API_KEY");
            return string.IsNullOrWhiteSpace(openAiKey) ? "DeepSeek Go" : "OpenAI";
        }
    }

    public string ExternalPlanPath
    {
        get => _externalPlanPath;
        set => SetProperty(ref _externalPlanPath, value);
    }

    public bool MarkInferred
    {
        get => _markInferred;
        set => SetProperty(ref _markInferred, value);
    }

    public string StatusMessage
    {
        get => _statusMessage;
        private set => SetProperty(ref _statusMessage, value);
    }

    public string ErrorMessage
    {
        get => _errorMessage;
        private set
        {
            if (SetProperty(ref _errorMessage, value))
            {
                OnPropertyChanged(nameof(HasError));
            }
        }
    }

    public bool HasError => !string.IsNullOrWhiteSpace(ErrorMessage);

    public string WarningsText
    {
        get => _warningsText;
        private set => SetProperty(ref _warningsText, value);
    }

    public string PlanSummary
    {
        get => _planSummary;
        private set => SetProperty(ref _planSummary, value);
    }

    public string BlockingIssuesText
    {
        get => _blockingIssuesText;
        private set => SetProperty(ref _blockingIssuesText, value);
    }

    public bool IsBuildable
    {
        get => _isBuildable;
        private set
        {
            if (SetProperty(ref _isBuildable, value))
            {
                OnPropertyChanged(nameof(HasBlockingIssues));
                OnPropertyChanged(nameof(BuildButtonText));
                (BuildCommand as RelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool HasBlockingIssues => !IsBuildable && !string.IsNullOrWhiteSpace(BlockingIssuesText);

    public double BuildProgressValue
    {
        get => _buildProgressValue;
        private set => SetProperty(ref _buildProgressValue, value);
    }

    public string BuildProgressText
    {
        get => _buildProgressText;
        private set => SetProperty(ref _buildProgressText, value);
    }

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (SetProperty(ref _isBusy, value))
            {
                OnPropertyChanged(nameof(IsNotBusy));
                OnPropertyChanged(nameof(PreviewButtonText));
                OnPropertyChanged(nameof(BuildButtonText));
                (PreviewCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
                (BuildCommand as RelayCommand)?.RaiseCanExecuteChanged();
                (BrowseExternalPlanCommand as RelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool IsNotBusy => !IsBusy;

    public string PreviewButtonText => IsBusy ? "Working…" : "Create preview";

    public string BuildButtonText =>
        IsBusy ? "Building…" : Plan is null ? "Build with AI" : IsBuildable ? "Build in Revit" : "Measurements incomplete";

    public ReconstructionPlanResult? Plan
    {
        get => _plan;
        private set
        {
            if (SetProperty(ref _plan, value))
            {
                OnPropertyChanged(nameof(HasPlan));
                OnPropertyChanged(nameof(BuildButtonText));
                (BuildCommand as RelayCommand)?.RaiseCanExecuteChanged();
                (OpenStoreFolderCommand as RelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool HasPlan => Plan is not null;

    private bool CanPreview() =>
        !IsBusy && !string.IsNullOrWhiteSpace(StorePath) && Directory.Exists(StorePath);

    private bool CanBuild() =>
        !IsBusy && _runner is not null && !string.IsNullOrWhiteSpace(StorePath) &&
        Directory.Exists(StorePath);

    private async Task PreviewAsync()
    {
        if (IsBusy)
        {
            return;
        }

        if (!CanPreview())
        {
            ErrorMessage = "Choose an existing scan store.";
            return;
        }

        if (IsExternalPlanProvider && !File.Exists(ExternalPlanPath))
        {
            ErrorMessage = "Choose an existing external BIM plan JSON file.";
            return;
        }

        if (!TryParseDouble(ConfidenceThresholdText, out var confidence) ||
            !double.IsFinite(confidence) || confidence is < 0 or > 1)
        {
            ErrorMessage = "Confidence threshold must be between 0 and 1.";
            return;
        }

        if (!TryParseDouble(FallbackWallHeightText, out var wallHeight) ||
            !double.IsFinite(wallHeight) || wallHeight is < 0.5 or > 10)
        {
            ErrorMessage = "Fallback wall height must be between 0.5 and 10 metres.";
            return;
        }

        if (!TryParseDouble(LevelToleranceText, out var tolerance) ||
            !double.IsFinite(tolerance) || tolerance is < 0.01 or > 2)
        {
            ErrorMessage = "Level tolerance must be between 0.01 and 2 metres.";
            return;
        }

        if (!TryParseInt(MaxElementsText, out var maxElements) || maxElements is < 1 or > 1000)
        {
            ErrorMessage = "Max elements must be between 1 and 1000.";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;
        WarningsText = string.Empty;
        PlanSummary = string.Empty;
        Plan = null;
        Floors.Clear();
        Walls.Clear();
        IsBuildable = true;
        BlockingIssuesText = string.Empty;
        StatusMessage = "Starting the Python engine…";

        try
        {
            var config = RevoConfig.Load();
            await using var client = await PythonEngineClient.StartAsync(config);

            StatusMessage = "Reading segmentation and building the floor/wall plan…";
            var plan = await client.CreateReconstructionPlanAsync(new ReconstructionPlanParams
            {
                StorePath = StorePath,
                Provider = MapProvider(SelectedProvider),
                ExternalPlanPath = IsExternalPlanProvider ? ExternalPlanPath : null,
                ConfidenceThreshold = confidence,
                FallbackWallHeightMeters = wallHeight,
                LevelToleranceMeters = tolerance,
                MaxElements = maxElements,
            });

            Plan = plan;
            ApplyPlanQuality(plan);
            foreach (var floor in plan.Floors)
            {
                Floors.Add(floor);
            }

            foreach (var wall in plan.Walls)
            {
                Walls.Add(wall);
            }

            PlanSummary = BuildSummary(plan);
            WarningsText = plan.Warnings.Count == 0
                ? "No plan warnings."
                : string.Join(Environment.NewLine, plan.Warnings.Select(warning => "• " + warning));
            StatusMessage =
                IsBuildable
                    ? $"Preview ready: {plan.Levels.Count} level(s), {plan.Floors.Count} floor(s) " +
                      $"and {plan.Walls.Count} wall(s). Nothing has been created in Revit yet."
                    : $"Preview ready but blocked: {BlockingIssuesText.Replace(Environment.NewLine, " ")}";
            RevoLog.Info(
                $"Reconstruction plan {plan.ScanId}: {plan.Levels.Count} levels, " +
                $"{plan.Floors.Count} floors, {plan.Walls.Count} walls, buildable={IsBuildable}.");
        }
        catch (RevoAIEngineException ex)
        {
            ErrorMessage = string.IsNullOrWhiteSpace(ex.Error.Remedy)
                ? ex.Error.Message
                : $"{ex.Error.Message} {ex.Error.Remedy}";
            StatusMessage = "Plan creation failed. No model was changed.";
            RevoLog.Error("Reconstruction plan failed.", ex);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage = "Plan creation failed. No model was changed.";
            RevoLog.Error("Reconstruction plan failed.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void Build()
    {
        if (IsBusy)
        {
            return;
        }

        if (_runner is null)
        {
            ErrorMessage = "The Revit task runner is not available.";
            return;
        }

        _ = BuildWithAiAsync();
    }

    private async Task BuildWithAiAsync()
    {
        if (Plan is null)
        {
            await PreviewAsync();
            if (Plan is null || !IsBuildable)
            {
                return;
            }
        }

        if (!IsBuildable)
        {
            ErrorMessage =
                "Resolve the blocking measurement issues before creating geometry. " +
                "Nothing has been created in Revit.";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;
        BuildProgressValue = 0;
        BuildProgressText = "Preparing build";
        StatusMessage = "Building in Revit. The model will appear stage by stage.";

        var plan = Plan!;
        var session = new BuildSession(plan);

        try
        {
            await RunBuildStep("Creating levels", 5, app => ModelBuilder.CreateLevels(app, session), session);
            await RunBuildStep("Creating slabs", 20, app => ModelBuilder.CreateSlabs(app, session), session);
            await RunBuildStep("Creating walls", 40, app => ModelBuilder.CreateWalls(app, session), session);
            await RunBuildStep("Hosting doors and windows", 65, app => ModelBuilder.CreateOpenings(app, session), session);
            await RunBuildStep("Creating roofs", 80, app => ModelBuilder.CreateRoofs(app, session), session);
            await RunBuildStep("Creating columns", 90, app => ModelBuilder.CreateColumns(app, session), session);

            BuildProgressValue = 100;
            BuildProgressText = "Build complete";
            var result = new ReconstructionBuildResult(
                session.Floors,
                session.CreatedWalls,
                session.CreatedLevels,
                session.Warnings,
                $"Created {session.Floors.Count} slab(s), {session.CreatedWalls.Count} wall(s), " +
                $"{session.Openings.Count} opening(s), {session.Roofs.Count} roof(s), " +
                $"{session.Columns.Count} column(s) and {session.CreatedLevels.Count} level(s).",
                session.Openings,
                session.Roofs,
                session.Columns);
            WarningsText = result.Warnings.Count == 0
                ? "No build warnings."
                : string.Join(Environment.NewLine, result.Warnings.Select(warning => "• " + warning));
            StatusMessage = result.Message;
            RevoLog.Info(result.Message);

            try
            {
                BuildCompleted?.Invoke(result);
            }
            catch (Exception ex)
            {
                RevoLog.Warn($"The workspace could not apply the build result: {ex.Message}");
            }
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage =
                "Build stopped. Geometry created before the failure remains in the model; " +
                "review the error and use Undo if needed.";
            RevoLog.Error("Incremental BIM generation failed.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task RunBuildStep(
        string label,
        double progress,
        Func<UIApplication, int> step,
        BuildSession session)
    {
        BuildProgressText = label;
        BuildProgressValue = progress;
        StatusMessage = label + "…";
        var count = await _runner!.InvokeAsync(step);
        BuildProgressText = $"{label}: {count}";
        await _runner.InvokeAsync(app => ModelBuilder.ShowBuildProgress(app, session));
        await Task.Delay(150);
    }

    private void BrowseExternalPlan()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = "Choose an external BIM plan",
            Filter = "BIM plan JSON (*.json)|*.json|All files (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false,
        };

        if (dialog.ShowDialog() == true)
        {
            ExternalPlanPath = dialog.FileName;
            SelectedProvider = "External plan JSON";
            StatusMessage = "External plan selected. Create a preview to validate it.";
            ErrorMessage = string.Empty;
        }
    }

    private void OpenStoreFolder()
    {
        if (Plan is null)
        {
            return;
        }

        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = Plan.StorePath,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            ErrorMessage = "Could not open the scan store folder: " + ex.Message;
        }
    }

    private void ApplyPlanQuality(ReconstructionPlanResult plan)
    {
        var buildable = true;
        var reasons = new List<string>();

        if (plan.Report is JsonElement report && report.ValueKind == JsonValueKind.Object)
        {
            if (report.TryGetProperty("buildable", out var flag) &&
                flag.ValueKind == JsonValueKind.False)
            {
                buildable = false;
            }

            if (report.TryGetProperty("blockingIssues", out var issues) &&
                issues.ValueKind == JsonValueKind.Array)
            {
                foreach (var issue in issues.EnumerateArray())
                {
                    if (issue.ValueKind == JsonValueKind.String)
                    {
                        var text = issue.GetString();
                        if (!string.IsNullOrWhiteSpace(text))
                        {
                            reasons.Add(text);
                        }
                    }
                }
            }
        }

        if (reasons.Count > 0)
        {
            buildable = false;
        }

        IsBuildable = buildable;
        BlockingIssuesText = string.Join(
            Environment.NewLine,
            reasons.Select(reason => "• " + reason));
    }

    private static string BuildSummary(ReconstructionPlanResult plan)
    {
        var levels = string.Join(
            Environment.NewLine,
            plan.Levels.Select(level => $"  {level.Name}: {level.ElevationMeters:0.###} m"));
        var fallback = plan.Walls.Count(wall => wall.HeightSource == "fallback");
        return
            $"Scan: {plan.ScanId}{Environment.NewLine}" +
            $"Method: {plan.Method}{Environment.NewLine}" +
            $"Levels: {plan.Levels.Count}{Environment.NewLine}{levels}{Environment.NewLine}" +
            $"Floors: {plan.Floors.Count:N0} · Walls: {plan.Walls.Count:N0}" +
            (fallback == 0 ? string.Empty : $" · fallback wall heights: {fallback}") +
            Environment.NewLine +
            BuildReportSummary(plan) +
            $"Plan file: {plan.ResultPath}";
    }

    private static string BuildReportSummary(ReconstructionPlanResult plan)
    {
        if (plan.Report is not JsonElement report ||
            report.ValueKind != JsonValueKind.Object)
        {
            return string.Empty;
        }

        static string Text(JsonElement element, string name) =>
            element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                ? value.GetString() ?? string.Empty
                : string.Empty;

        static int Count(JsonElement element, string name) =>
            element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array
                ? value.GetArrayLength()
                : 0;

        return
            $"Units: {Text(report, "units")} · Datum: {Text(report, "datum")} · Axes: {Text(report, "axes")}" +
            Environment.NewLine +
            $"Measured: {Count(report, "measured")} · Assumed: {Count(report, "assumed")} · " +
            $"Verify: {Count(report, "verify")}{Environment.NewLine}";
    }

    private static string MapProvider(string label) => label switch
    {
        "External plan JSON" => "external",
        "Revo AI (DeepSeek Go)" => "ai",
        _ => "geometric",
    };

    private static bool TryParseDouble(string text, out double value) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value) ||
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value);

    private static bool TryParseInt(string text, out int value) =>
        int.TryParse(text, NumberStyles.Integer, CultureInfo.CurrentCulture, out value) ||
        int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out value);
}
