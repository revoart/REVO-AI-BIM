using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows.Input;
using Microsoft.Win32;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;

namespace RevoAI.Revit.UI;

/// <summary>
/// Drives the real point cloud import: the file is sent to the Python engine,
/// which writes a chunked store and returns metadata. No point data is faked in
/// the UI.
/// </summary>
public sealed class ImportScanViewModel : ObservableObject
{
    private string _outputDirectory;
    private string _filePath = string.Empty;
    private string _selectedUnit = "Auto (read from file)";
    private string _chunkSizeText = "25";
    private bool _removeOutliers;
    private string _outlierNeighborsText = "20";
    private string _outlierStdRatioText = "2.0";
    private bool _voxelDownsample;
    private string _voxelSizeText = "0.05";
    private bool _overwrite;
    private string _statusMessage = "Choose a scan to import. Units are read from the file when reliable metadata exists.";
    private string _errorMessage = string.Empty;
    private string _warningsText = string.Empty;
    private string _resultSummary = string.Empty;
    private bool _isBusy;
    private PointCloudImportResult? _result;

    public ImportScanViewModel()
    {
        _outputDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "RevoAI",
            "scans");

        UnitOptions =
        [
            "Auto (read from file)",
            "Meters",
            "Millimeters",
            "Centimeters",
            "Feet",
            "US survey feet",
            "Inches",
        ];

        BrowseCommand = new RelayCommand(Browse);
        ImportCommand = new AsyncRelayCommand(ImportAsync, CanImport);
        OpenStoreFolderCommand = new RelayCommand(OpenStoreFolder, () => Result is not null);
    }

    /// <summary>Raised after a successful import, even if the dialog is closing.</summary>
    public event Action<PointCloudImportResult>? ImportCompleted;

    public IReadOnlyList<string> UnitOptions { get; }

    public ICommand BrowseCommand { get; }

    public ICommand ImportCommand { get; }

    public ICommand OpenStoreFolderCommand { get; }

    public string FilePath
    {
        get => _filePath;
        set
        {
            if (SetProperty(ref _filePath, value))
            {
                OnPropertyChanged(nameof(FormatLabel));
                (ImportCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public string FormatLabel
    {
        get
        {
            if (string.IsNullOrWhiteSpace(FilePath))
            {
                return "Format detected from the file extension.";
            }

            var extension = Path.GetExtension(FilePath).TrimStart('.').ToLowerInvariant();
            return extension switch
            {
                "e57" => "E57 · coordinates are metres by specification.",
                "las" => "LAS · unit is read from a WKT CRS when present, otherwise assumed metres.",
                "laz" => "LAZ · unit is read from a WKT CRS when present, otherwise assumed metres.",
                "ply" => "PLY · no unit metadata; choose the source unit if it is not metres.",
                "xyz" or "txt" or "asc" or "pts" => "XYZ · no unit metadata; choose the source unit if it is not metres.",
                _ => "Unsupported extension. Use E57, LAS, LAZ, PLY, XYZ or TXT.",
            };
        }
    }

    public string SelectedUnit
    {
        get => _selectedUnit;
        set => SetProperty(ref _selectedUnit, value);
    }

    public string OutputDirectory
    {
        get => _outputDirectory;
        set => SetProperty(ref _outputDirectory, value);
    }

    public string ChunkSizeText
    {
        get => _chunkSizeText;
        set => SetProperty(ref _chunkSizeText, value);
    }

    public bool RemoveOutliers
    {
        get => _removeOutliers;
        set => SetProperty(ref _removeOutliers, value);
    }

    public string OutlierNeighborsText
    {
        get => _outlierNeighborsText;
        set => SetProperty(ref _outlierNeighborsText, value);
    }

    public string OutlierStdRatioText
    {
        get => _outlierStdRatioText;
        set => SetProperty(ref _outlierStdRatioText, value);
    }

    public bool VoxelDownsample
    {
        get => _voxelDownsample;
        set => SetProperty(ref _voxelDownsample, value);
    }

    public string VoxelSizeText
    {
        get => _voxelSizeText;
        set => SetProperty(ref _voxelSizeText, value);
    }

    public bool Overwrite
    {
        get => _overwrite;
        set => SetProperty(ref _overwrite, value);
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
                OnPropertyChanged(nameof(ImportButtonText));
                (ImportCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
            }
        }
    }

    public bool IsNotBusy => !IsBusy;

    public string ImportButtonText => IsBusy ? "Importing…" : "Import scan";

    public PointCloudImportResult? Result
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

    private bool CanImport() =>
        !IsBusy && !string.IsNullOrWhiteSpace(FilePath) && File.Exists(FilePath);

    private void Browse()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose a point cloud",
            Filter =
                "Point clouds (*.e57;*.las;*.laz;*.ply;*.xyz;*.txt;*.asc;*.pts)|" +
                "*.e57;*.las;*.laz;*.ply;*.xyz;*.txt;*.asc;*.pts|" +
                "E57 (*.e57)|*.e57|LAS/LAZ (*.las;*.laz)|*.las;*.laz|PLY (*.ply)|*.ply|" +
                "XYZ (*.xyz;*.txt;*.asc;*.pts)|*.xyz;*.txt;*.asc;*.pts|All files (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false,
        };

        if (dialog.ShowDialog() == true)
        {
            FilePath = dialog.FileName;
            StatusMessage = "Ready to import. Review the unit and preprocessing options.";
            ErrorMessage = string.Empty;
        }
    }

    private async Task ImportAsync()
    {
        if (IsBusy)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(OutputDirectory))
        {
            ErrorMessage = "Choose an output folder for the local scan store.";
            return;
        }

        string sourcePath;
        string outputDirectory;
        try
        {
            sourcePath = Path.GetFullPath(FilePath);
            outputDirectory = Path.GetFullPath(OutputDirectory);
        }
        catch (Exception ex)
        {
            ErrorMessage = "The scan or output path is not valid: " + ex.Message;
            return;
        }

        if (!File.Exists(sourcePath))
        {
            ErrorMessage = "Choose an existing point cloud file.";
            return;
        }

        if (!TryParsePositive(ChunkSizeText, out var chunkSize) || chunkSize is < 0.1 or > 1000)
        {
            ErrorMessage = "Chunk size must be between 0.1 and 1000 metres.";
            return;
        }

        double? voxelSize = null;
        if (VoxelDownsample)
        {
            if (!TryParsePositive(VoxelSizeText, out var parsedVoxel) ||
                parsedVoxel is < 0.0001 or > 1000)
            {
                ErrorMessage = "Voxel size must be between 0.0001 and 1000 metres.";
                return;
            }

            voxelSize = parsedVoxel;
        }

        var neighbors = 20;
        if (RemoveOutliers &&
            (!TryParseInt(OutlierNeighborsText, out neighbors) || neighbors is < 3 or > 200))
        {
            ErrorMessage = "Outlier neighbours must be a whole number between 3 and 200.";
            return;
        }

        var stdRatio = 2.0;
        if (RemoveOutliers &&
            (!TryParseDouble(OutlierStdRatioText, out stdRatio) || stdRatio is < 0.1 or > 10))
        {
            ErrorMessage = "Outlier standard-deviation ratio must be between 0.1 and 10.";
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;
        WarningsText = string.Empty;
        ResultSummary = string.Empty;
        Result = null;
        StatusMessage = "Starting the Python engine…";

        try
        {
            var config = RevoConfig.Load();
            await using var client = await PythonEngineClient.StartAsync(config);

            StatusMessage = "Importing, converting units and writing chunks…";
            var result = await client.ImportPointCloudAsync(new PointCloudImportParams
            {
                Path = sourcePath,
                Unit = MapUnit(SelectedUnit),
                OutputDirectory = outputDirectory,
                ChunkSizeMeters = chunkSize,
                VoxelSizeMeters = voxelSize,
                RemoveOutliers = RemoveOutliers,
                OutlierNeighbors = neighbors,
                OutlierStdRatio = stdRatio,
                Overwrite = Overwrite,
            });

            Result = result;
            ResultSummary = BuildSummary(result);
            WarningsText = result.Warnings.Count == 0
                ? "No warnings."
                : string.Join(Environment.NewLine, result.Warnings.Select(warning => "• " + warning));
            StatusMessage =
                $"Imported {result.PointCount.Stored:N0} stored point(s) in " +
                $"{result.ElapsedMs / 1000.0:0.0} s. The scan is ready for Phase 4 analysis.";
            RevoLog.Info(
                $"Point cloud imported: {result.ScanId} · {result.PointCount.Stored} stored points · " +
                $"{result.ChunkCount} chunks · {result.StorePath}");

            // Notify last so the workspace never sees a half-populated view model.
            try
            {
                ImportCompleted?.Invoke(result);
            }
            catch (Exception ex)
            {
                RevoLog.Warn($"The workspace could not apply the imported scan summary: {ex.Message}");
            }
        }
        catch (RevoAIEngineException ex)
        {
            ErrorMessage = string.IsNullOrWhiteSpace(ex.Error.Remedy)
                ? ex.Error.Message
                : $"{ex.Error.Message} {ex.Error.Remedy}";
            StatusMessage = "Import failed. The source file was not modified.";
            RevoLog.Error("Point cloud import failed.", ex);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage = "Import failed. The source file was not modified.";
            RevoLog.Error("Point cloud import failed.", ex);
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

    private static string BuildSummary(PointCloudImportResult result)
    {
        var bounds = result.Bounds;
        var sourceBounds = result.SourceBounds;
        return
            $"Scan id: {result.ScanId}{Environment.NewLine}" +
            $"Source: {result.SourcePath}{Environment.NewLine}" +
            $"Format: {result.Format.ToUpperInvariant()}{Environment.NewLine}" +
            $"Unit: {result.Unit} ({result.UnitSource}){Environment.NewLine}" +
            $"Points: {result.PointCount.Original:N0} source · {result.PointCount.Stored:N0} stored{Environment.NewLine}" +
            $"Chunks: {result.ChunkCount:N0}{Environment.NewLine}" +
            $"Bounds (m): [{bounds.Min[0]:0.###}, {bounds.Min[1]:0.###}, {bounds.Min[2]:0.###}] → " +
            $"[{bounds.Max[0]:0.###}, {bounds.Max[1]:0.###}, {bounds.Max[2]:0.###}]{Environment.NewLine}" +
            $"Source bounds: [{sourceBounds.Min[0]:0.###}, {sourceBounds.Min[1]:0.###}, {sourceBounds.Min[2]:0.###}] → " +
            $"[{sourceBounds.Max[0]:0.###}, {sourceBounds.Max[1]:0.###}, {sourceBounds.Max[2]:0.###}]" +
            Environment.NewLine +
            $"Store: {result.StorePath}";
    }

    private static string MapUnit(string label) => label switch
    {
        "Meters" => "meters",
        "Millimeters" => "millimeters",
        "Centimeters" => "centimeters",
        "Feet" => "feet",
        "US survey feet" => "usSurveyFeet",
        "Inches" => "inches",
        _ => "auto",
    };

    private static bool TryParsePositive(string text, out double value) =>
        TryParseDouble(text, out value) &&
        !double.IsNaN(value) &&
        !double.IsInfinity(value) &&
        value > 0;

    private static bool TryParseDouble(string text, out double value) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value) ||
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value);

    private static bool TryParseInt(string text, out int value) =>
        int.TryParse(text, NumberStyles.Integer, CultureInfo.CurrentCulture, out value) ||
        int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out value);
}
