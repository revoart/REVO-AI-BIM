using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows.Input;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;

namespace RevoAI.Revit.UI;

/// <summary>
/// Runs the real Phase 4 geometric segmentation baseline and displays its
/// classes, instances and plane-fit confidence. It creates no Revit geometry.
/// </summary>
public sealed class ScanAnalysisViewModel : ObservableObject
{
    private string _storePath;
    private string _voxelSizeText = "0.05";
    private string _maxPointsText = "200000";
    private string _planeDistanceText = "0.03";
    private string _minPlanePointsText = "300";
    private string _maxPlanesText = "40";
    private string _confidenceThresholdText;
    private string _statusMessage = "Run analysis to detect planar floors, ceilings and walls.";
    private string _errorMessage = string.Empty;
    private string _warningsText = string.Empty;
    private string _resultSummary = string.Empty;
    private bool _isBusy;
    private SegmentationResult? _result;

    public ScanAnalysisViewModel(string storePath, double confidenceThreshold)
    {
        _storePath = storePath ?? string.Empty;
        _confidenceThresholdText = confidenceThreshold.ToString("0.00", CultureInfo.InvariantCulture);

        RunCommand = new AsyncRelayCommand(RunAsync, CanRun);
        OpenStoreFolderCommand = new RelayCommand(OpenStoreFolder, () => Result is not null);
    }

    /// <summary>Raised after a successful analysis, even if the dialog is closing.</summary>
    public event Action<SegmentationResult>? AnalysisCompleted;

    public ObservableCollection<SegmentationElement> Elements { get; } = [];

    public ICommand RunCommand { get; }

    public ICommand OpenStoreFolderCommand { get; }

    public string StorePath
    {
        get => _storePath;
        set
        {
            if (SetProperty(ref _storePath, value))
            {
                (RunCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public string VoxelSizeText
    {
        get => _voxelSizeText;
        set => SetProperty(ref _voxelSizeText, value);
    }

    public string MaxPointsText
    {
        get => _maxPointsText;
        set => SetProperty(ref _maxPointsText, value);
    }

    public string PlaneDistanceText
    {
        get => _planeDistanceText;
        set => SetProperty(ref _planeDistanceText, value);
    }

    public string MinPlanePointsText
    {
        get => _minPlanePointsText;
        set => SetProperty(ref _minPlanePointsText, value);
    }

    public string MaxPlanesText
    {
        get => _maxPlanesText;
        set => SetProperty(ref _maxPlanesText, value);
    }

    public string ConfidenceThresholdText
    {
        get => _confidenceThresholdText;
        set => SetProperty(ref _confidenceThresholdText, value);
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

    public string ResultSummary
    {
        get => _resultSummary;
        private set => SetProperty(ref _resultSummary, value);
    }

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (SetProperty(ref _isBusy, value))
            {
                OnPropertyChanged(nameof(IsNotBusy));
                OnPropertyChanged(nameof(RunButtonText));
                (RunCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool IsNotBusy => !IsBusy;

    public string RunButtonText => IsBusy ? "Analyzing…" : "Run analysis";

    public SegmentationResult? Result
    {
        get => _result;
        private set
        {
            if (SetProperty(ref _result, value))
            {
                OnPropertyChanged(nameof(HasResult));
                (OpenStoreFolderCommand as RelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool HasResult => Result is not null;

    private bool CanRun() =>
        !IsBusy && !string.IsNullOrWhiteSpace(StorePath) && Directory.Exists(StorePath);

    private async Task RunAsync()
    {
        if (IsBusy)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(StorePath) || !Directory.Exists(StorePath))
        {
            ErrorMessage = "Choose an existing point cloud store.";
            return;
        }

        if (!TryParseDouble(VoxelSizeText, out var voxelSize) ||
            !double.IsFinite(voxelSize) ||
            voxelSize is < 0 or > 1)
        {
            ErrorMessage = "Voxel size must be between 0 and 1 metre. Use 0 to disable downsampling.";
            return;
        }

        if (!TryParseInt(MaxPointsText, out var maxPoints) || maxPoints is < 1_000 or > 1_000_000)
        {
            ErrorMessage = "Maximum analysis points must be between 1,000 and 1,000,000.";
            return;
        }

        if (!TryParseDouble(PlaneDistanceText, out var planeDistance) ||
            !double.IsFinite(planeDistance) ||
            planeDistance is < 0.001 or > 0.5)
        {
            ErrorMessage = "Plane distance must be between 0.001 and 0.5 metres.";
            return;
        }

        if (!TryParseInt(MinPlanePointsText, out var minPlanePoints) ||
            minPlanePoints is < 10 or > 100_000)
        {
            ErrorMessage = "Minimum plane points must be between 10 and 100,000.";
            return;
        }

        if (!TryParseInt(MaxPlanesText, out var maxPlanes) || maxPlanes is < 1 or > 200)
        {
            ErrorMessage = "Maximum planes must be between 1 and 200.";
            return;
        }

        if (!TryParseDouble(ConfidenceThresholdText, out var confidence) ||
            !double.IsFinite(confidence) ||
            confidence is < 0 or > 1)
        {
            ErrorMessage = "Confidence threshold must be between 0 and 1.";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;
        WarningsText = string.Empty;
        ResultSummary = string.Empty;
        Result = null;
        Elements.Clear();
        StatusMessage = "Starting the Python engine…";

        try
        {
            var config = RevoConfig.Load();
            await using var client = await PythonEngineClient.StartAsync(config);

            StatusMessage = "Sampling, extracting planes and scoring confidence…";
            var result = await client.RunSegmentationAsync(new SegmentationRunParams
            {
                StorePath = StorePath,
                VoxelSizeMeters = voxelSize,
                MaxPoints = maxPoints,
                PlaneDistanceMeters = planeDistance,
                MinPlanePoints = minPlanePoints,
                MaxPlanes = maxPlanes,
                ConfidenceThreshold = confidence,
            });

            Result = result;
            foreach (var element in result.Elements)
            {
                Elements.Add(element);
            }

            ResultSummary = BuildSummary(result);
            WarningsText = result.Warnings.Count == 0
                ? "No analysis warnings."
                : string.Join(Environment.NewLine, result.Warnings.Select(warning => "• " + warning));
            StatusMessage =
                $"Detected {result.Summary.Segments:N0} plane(s) at " +
                $"{result.Summary.MeanConfidence:P1} mean plane-fit confidence. " +
                "No Revit geometry was created.";
            RevoLog.Info(
                $"Scan analysis {result.ScanId}: {result.Summary.Segments} segments, " +
                $"{result.Summary.MeanConfidence:0.000} mean confidence, {result.ResultPath}");

            try
            {
                AnalysisCompleted?.Invoke(result);
            }
            catch (Exception ex)
            {
                RevoLog.Warn($"The workspace could not apply the analysis summary: {ex.Message}");
            }
        }
        catch (RevoAIEngineException ex)
        {
            ErrorMessage = string.IsNullOrWhiteSpace(ex.Error.Remedy)
                ? ex.Error.Message
                : $"{ex.Error.Message} {ex.Error.Remedy}";
            StatusMessage = "Scan analysis failed. No model was changed.";
            RevoLog.Error("Scan analysis failed.", ex);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage = "Scan analysis failed. No model was changed.";
            RevoLog.Error("Scan analysis failed.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void OpenStoreFolder()
    {
        if (Result is null)
        {
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = Result.StorePath,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            ErrorMessage = "Could not open the scan store folder: " + ex.Message;
        }
    }

    private static string BuildSummary(SegmentationResult result)
    {
        var summary = result.Summary;
        var kinds = string.Join(
            ", ",
            summary.ByKind.OrderBy(pair => pair.Key).Select(pair => $"{pair.Key}: {pair.Value}"));
        return
            $"Scan: {result.ScanId}{Environment.NewLine}" +
            $"Method: {result.Method}{Environment.NewLine}" +
            $"{result.MethodNote}{Environment.NewLine}" +
            $"Segments: {summary.Segments:N0} ({kinds}){Environment.NewLine}" +
            $"Analyzed points: {summary.AnalyzedPoints:N0} of {summary.SourcePoints:N0}{Environment.NewLine}" +
            $"Assigned to planes: {summary.AssignedPoints:N0} ({summary.Coverage:P1}){Environment.NewLine}" +
            $"Mean confidence: {summary.MeanConfidence:P1} · " +
            $"{summary.HighConfidenceSegments:N0} at or above threshold{Environment.NewLine}" +
            $"Result: {result.ResultPath}";
    }

    private static bool TryParseDouble(string text, out double value) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value) ||
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value);

    private static bool TryParseInt(string text, out int value) =>
        int.TryParse(text, NumberStyles.Integer, CultureInfo.CurrentCulture, out value) ||
        int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out value);
}
