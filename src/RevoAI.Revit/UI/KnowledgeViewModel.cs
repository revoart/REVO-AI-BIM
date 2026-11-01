using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using Microsoft.Win32;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;
using RevoAI.Revit.RevitApi;

namespace RevoAI.Revit.UI;

/// <summary>
/// Local knowledge library: search, import sources, review statuses and extract
/// verified Revit projects. Every operation is local; nothing is uploaded.
/// </summary>
public sealed class KnowledgeViewModel : ObservableObject
{
    private readonly RevitTaskRunner? _runner;
    private readonly IntPtr _revitWindowHandle;

    private string _searchText = string.Empty;
    private string _selectedStatus = "All statuses";
    private string _documentKind = "local_file";
    private KnowledgeListItemViewModel? _selectedItem;
    private string _detailsText = "Search or select a record to inspect its procedure and provenance.";
    private string _provenanceText = string.Empty;
    private string _statsText = "Local knowledge library not loaded yet.";
    private string _statusMessage = "Knowledge is stored locally and never uploaded by this workflow.";
    private string _errorMessage = string.Empty;
    private bool _isBusy;
    private bool _canReview;

    public KnowledgeViewModel(RevitTaskRunner? runner = null, IntPtr revitWindowHandle = default)
    {
        _runner = runner;
        _revitWindowHandle = revitWindowHandle;

        StatusOptions =
        [
            "All statuses",
            "approved",
            "pending_review",
            "extracted",
            "needs_correction",
            "rejected",
        ];

        DocumentKindOptions =
        [
            "local_file",
            "autodesk_docs",
            "youtube_transcript",
            "other",
        ];

        SearchCommand = new AsyncRelayCommand(SearchAsync, () => !IsBusy);
        RefreshCommand = new AsyncRelayCommand(LoadAsync, () => !IsBusy);
        ApproveCommand = new AsyncRelayCommand(() => ReviewAsync("approve"), () => CanReview);
        RejectCommand = new AsyncRelayCommand(() => ReviewAsync("reject"), () => CanReview);
        NeedsCorrectionCommand = new AsyncRelayCommand(
            () => ReviewAsync("needs_correction"),
            () => CanReview);
        DeleteCommand = new AsyncRelayCommand(DeleteAsync, () => CanReview);
        ImportDocumentCommand = new AsyncRelayCommand(ImportDocumentAsync, () => !IsBusy);
        ImportTranscriptCommand = new AsyncRelayCommand(ImportTranscriptAsync, () => !IsBusy);
        ExtractProjectCommand = new AsyncRelayCommand(
            ExtractProjectAsync,
            () => _runner is not null && !IsBusy);
        BackupCommand = new AsyncRelayCommand(BackupAsync, () => !IsBusy);
        ExportCommand = new AsyncRelayCommand(ExportAsync, () => !IsBusy);
        OpenRootCommand = new RelayCommand(OpenRoot);
    }

    public ObservableCollection<KnowledgeListItemViewModel> Results { get; } = [];

    public IReadOnlyList<string> StatusOptions { get; }

    public IReadOnlyList<string> DocumentKindOptions { get; }

    public ICommand SearchCommand { get; }

    public ICommand RefreshCommand { get; }

    public ICommand ApproveCommand { get; }

    public ICommand RejectCommand { get; }

    public ICommand NeedsCorrectionCommand { get; }

    public ICommand DeleteCommand { get; }

    public ICommand ImportDocumentCommand { get; }

    public ICommand ImportTranscriptCommand { get; }

    public ICommand ExtractProjectCommand { get; }

    public ICommand BackupCommand { get; }

    public ICommand ExportCommand { get; }

    public ICommand OpenRootCommand { get; }

    public string SearchText
    {
        get => _searchText;
        set => SetProperty(ref _searchText, value);
    }

    public string SelectedStatus
    {
        get => _selectedStatus;
        set => SetProperty(ref _selectedStatus, value);
    }

    public string DocumentKind
    {
        get => _documentKind;
        set => SetProperty(ref _documentKind, value);
    }

    public KnowledgeListItemViewModel? SelectedItem
    {
        get => _selectedItem;
        set
        {
            if (SetProperty(ref _selectedItem, value))
            {
                CanReview = value is { IsRecord: true, RecordId: not null } && !IsBusy;
                _ = ShowSelectionAsync(value);
            }
        }
    }

    public string DetailsText
    {
        get => _detailsText;
        private set => SetProperty(ref _detailsText, value);
    }

    public string ProvenanceText
    {
        get => _provenanceText;
        private set => SetProperty(ref _provenanceText, value);
    }

    public string StatsText
    {
        get => _statsText;
        private set => SetProperty(ref _statsText, value);
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

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (SetProperty(ref _isBusy, value))
            {
                OnPropertyChanged(nameof(IsNotBusy));
                RaiseCommandStates();
            }
        }
    }

    public bool IsNotBusy => !IsBusy;

    public bool CanReview
    {
        get => _canReview;
        private set
        {
            if (SetProperty(ref _canReview, value))
            {
                RaiseCommandStates();
            }
        }
    }

    public async Task LoadAsync()
    {
        await RunAsync(async client =>
        {
            await RefreshStatsAsync(client);
            var result = await client.SearchKnowledgeAsync(new KnowledgeSearchParams
            {
                Query = string.Empty,
                Statuses = ParseStatuses(),
                Limit = 50,
            });
            ApplySearch(result);
            StatusMessage = result.Total == 0
                ? "The local library is empty. Import a transcript or document, or extract the active Revit project."
                : $"Loaded {result.Total:N0} record(s) from the local knowledge library.";
        });
    }

    private async Task SearchAsync()
    {
        await RunAsync(async client =>
        {
            var result = await client.SearchKnowledgeAsync(new KnowledgeSearchParams
            {
                Query = SearchText,
                Statuses = ParseStatuses(),
                Limit = 50,
            });
            ApplySearch(result);
            await RefreshStatsAsync(client);
            StatusMessage =
                $"{result.Records.Count:N0} record(s) and {result.Snippets.Count:N0} source snippet(s) shown.";
        });
    }

    private async Task ShowSelectionAsync(KnowledgeListItemViewModel? item)
    {
        if (item is null)
        {
            DetailsText = "Search or select a record to inspect its procedure and provenance.";
            ProvenanceText = string.Empty;
            return;
        }

        if (!item.IsRecord || string.IsNullOrWhiteSpace(item.RecordId))
        {
            DetailsText = item.SnippetText;
            ProvenanceText = item.SourceLabel;
            return;
        }

        try
        {
            await using var client = await PythonEngineClient.StartAsync(RevoConfig.Load());
            var result = await client.GetKnowledgeRecordAsync(item.RecordId);
            ApplyRecord(result.Record);
        }
        catch (Exception ex)
        {
            DetailsText = "Could not load the selected knowledge record.";
            ErrorMessage = ex.Message;
            RevoLog.Error("Could not load a knowledge record.", ex);
        }
    }

    private void ApplyRecord(KnowledgeRecordDetail record)
    {
        var builder = new StringBuilder();
        builder.AppendLine(record.Subject);
        builder.AppendLine(
            $"Status: {record.Status}   Version: {record.Version}   Confidence: {record.Confidence:P0}");
        builder.AppendLine($"Category: {record.Category}   Source: {record.SourceType}");
        if (!string.IsNullOrWhiteSpace(record.RevitVersion))
        {
            builder.AppendLine($"Revit version: {record.RevitVersion}");
        }

        builder.AppendLine();
        builder.AppendLine(record.Description);
        if (!string.IsNullOrWhiteSpace(record.Body))
        {
            builder.AppendLine();
            builder.AppendLine(record.Body);
        }

        AppendList(builder, "Procedure", record.Procedure, numbered: true);
        AppendList(builder, "API operations", record.ApiOperations);
        AppendList(builder, "Conditions", record.Conditions);
        AppendList(builder, "Constraints", record.Constraints);
        AppendList(builder, "Limitations", record.Limitations);
        if (record.Verification.Count > 0)
        {
            AppendList(builder, "Verification", record.Verification);
        }

        DetailsText = builder.ToString().TrimEnd();

        var provenance = new StringBuilder();
        if (record.Provenance.Count == 0)
        {
            provenance.AppendLine("No source attached. This record is manual knowledge.");
        }
        else
        {
            foreach (var source in record.Provenance)
            {
                provenance.AppendLine($"{source.Title} ({source.Kind})");
                if (!string.IsNullOrWhiteSpace(source.Url))
                {
                    provenance.AppendLine(source.Url);
                }

                if (!string.IsNullOrWhiteSpace(source.Creator))
                {
                    provenance.AppendLine("Creator: " + source.Creator);
                }

                if (!string.IsNullOrWhiteSpace(source.License))
                {
                    provenance.AppendLine("Licence: " + source.License);
                }
            }
        }

        if (record.Reviews.Count > 0)
        {
            provenance.AppendLine();
            provenance.AppendLine("Review history");
            foreach (var review in record.Reviews)
            {
                provenance.AppendLine(
                    $"{review.CreatedAt:u}  {review.Action}  {review.StatusFrom} → {review.StatusTo}" +
                    (string.IsNullOrWhiteSpace(review.Note) ? string.Empty : "  " + review.Note));
            }
        }

        ProvenanceText = provenance.ToString().TrimEnd();
        CanReview = !IsBusy;
    }

    private static void AppendList(
        StringBuilder builder,
        string title,
        IReadOnlyList<string> values,
        bool numbered = false)
    {
        if (values.Count == 0)
        {
            return;
        }

        builder.AppendLine();
        builder.AppendLine(title + ":");
        for (var index = 0; index < values.Count; index++)
        {
            builder.AppendLine(numbered ? $"{index + 1}. {values[index]}" : "• " + values[index]);
        }
    }

    private void ApplySearch(KnowledgeSearchResult result)
    {
        Results.Clear();
        foreach (var record in result.Records)
        {
            Results.Add(KnowledgeListItemViewModel.FromRecord(record));
        }

        foreach (var snippet in result.Snippets)
        {
            Results.Add(KnowledgeListItemViewModel.FromSnippet(snippet));
        }

        if (Results.Count > 0)
        {
            SelectedItem = Results[0];
        }
    }

    private async Task RefreshStatsAsync(PythonEngineClient client)
    {
        var stats = await client.GetKnowledgeStatsAsync();
        StatsText =
            $"{stats.Records:N0} record(s) · {stats.RecordsByStatus.GetValueOrDefault("approved"):N0} approved · " +
            $"{stats.Sources:N0} source(s) · {stats.Documents:N0} document(s) · " +
            $"{stats.Projects:N0} project extraction(s) · {stats.DatabaseBytes / 1024.0:0.0} KB";
    }

    private async Task ReviewAsync(string action)
    {
        if (SelectedItem?.RecordId is not { } recordId)
        {
            return;
        }

        await RunAsync(async client =>
        {
            var result = await client.ReviewKnowledgeAsync(new KnowledgeReviewParams
            {
                RecordId = recordId,
                Action = action,
                Reviewer = Environment.UserName,
            });
            ApplyRecord(result.Record);
            StatusMessage = $"Record {result.Record.Subject} is now {result.Record.Status}.";
            var search = await client.SearchKnowledgeAsync(new KnowledgeSearchParams
            {
                Query = SearchText,
                Statuses = ParseStatuses(),
                Limit = 50,
            });
            ApplySearch(search);
            await RefreshStatsAsync(client);
        });
    }

    private async Task DeleteAsync()
    {
        if (SelectedItem?.RecordId is not { } recordId)
        {
            return;
        }

        var confirmation = MessageBox.Show(
            "Delete this knowledge record? The review history is retained and the record " +
            "stops appearing in search and retrieval.",
            "Delete knowledge record",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);

        if (confirmation != MessageBoxResult.Yes)
        {
            return;
        }

        await RunAsync(async client =>
        {
            await client.DeleteKnowledgeRecordAsync(new KnowledgeDeleteParams
            {
                RecordId = recordId,
                Reviewer = Environment.UserName,
            });
            StatusMessage = "Knowledge record deleted. The audit entry is retained.";
            await RefreshStatsAsync(client);
            await SearchAsyncCore(client);
        });
    }

    private async Task ImportDocumentAsync()    {
        var dialog = new OpenFileDialog
        {
            Title = "Import a knowledge document",
            Filter =
                "Knowledge documents (*.md;*.txt;*.html;*.htm;*.json;*.csv;*.xml;*.log)|" +
                "*.md;*.txt;*.html;*.htm;*.json;*.csv;*.xml;*.log|All files (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false,
        };

        if (dialog.ShowDialog() != true)
        {
            return;
        }

        await RunAsync(async client =>
        {
            var result = await client.ImportKnowledgeDocumentAsync(new KnowledgeDocumentImportParams
            {
                Path = dialog.FileName,
                Title = Path.GetFileNameWithoutExtension(dialog.FileName),
                Kind = DocumentKind,
            });
            StatusMessage = result.Message;
            await RefreshStatsAsync(client);
            await SearchAsyncCore(client);
        });
    }

    private async Task ImportTranscriptAsync()
    {
        var window = new KnowledgeTranscriptWindow();
        if (_revitWindowHandle != IntPtr.Zero)
        {
            new WindowInteropHelper(window) { Owner = _revitWindowHandle };
        }

        if (window.ShowDialog() != true || window.Request is null)
        {
            return;
        }

        await RunAsync(async client =>
        {
            var request = window.Request;
            var result = await client.ImportKnowledgeTranscriptAsync(new KnowledgeTranscriptImportParams
            {
                Title = request.Title,
                Transcript = request.Transcript,
                Url = request.Url,
                Creator = request.Creator,
                License = request.License,
            });
            StatusMessage = result.Message;
            await RefreshStatsAsync(client);
            await SearchAsyncCore(client);
        });
    }

    private async Task ExtractProjectAsync()
    {
        if (_runner is null)
        {
            StatusMessage = "Project extraction needs an open Revit project.";
            return;
        }

        await RunAsync(async client =>
        {
            var extraction = await _runner.InvokeAsync(app => ProjectKnowledgeExtractor.Extract(app));
            var path = ProjectKnowledgeExtractor.SaveToInbox(extraction);
            var result = await client.ImportKnowledgeProjectAsync(
                new KnowledgeProjectImportParams { Path = path });
            StatusMessage =
                $"{result.Message} Categories: " +
                string.Join(", ", extraction.Counts.Select(pair => $"{pair.Key} {pair.Value:N0}"));
            await RefreshStatsAsync(client);
            await SearchAsyncCore(client);
        });
    }

    private async Task BackupAsync()
    {
        await RunAsync(async client =>
        {
            var result = await client.BackupKnowledgeAsync(new KnowledgeBackupParams());
            StatusMessage = $"Backup created: {result.Path}";
        });
    }

    private async Task ExportAsync()
    {
        await RunAsync(async client =>
        {
            var result = await client.ExportKnowledgeAsync(new KnowledgeExportParams());
            StatusMessage = $"Knowledge exported: {result.Path}";
        });
    }

    private async Task SearchAsyncCore(PythonEngineClient client)
    {
        var result = await client.SearchKnowledgeAsync(new KnowledgeSearchParams
        {
            Query = SearchText,
            Statuses = ParseStatuses(),
            Limit = 50,
        });
        ApplySearch(result);
    }

    private async Task RunAsync(Func<PythonEngineClient, Task> action)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        ErrorMessage = string.Empty;
        try
        {
            await using var client = await PythonEngineClient.StartAsync(RevoConfig.Load());
            await action(client);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage = "The knowledge operation failed. No data was fabricated or silently changed.";
            RevoLog.Error("Knowledge operation failed.", ex);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private IReadOnlyList<string>? ParseStatuses()
    {
        if (string.Equals(SelectedStatus, "All statuses", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        return [SelectedStatus];
    }

    private void OpenRoot()
    {
        try
        {
            var root = ProjectKnowledgeExtractor.ResolveRoot();
            Directory.CreateDirectory(root);
            Process.Start(new ProcessStartInfo
            {
                FileName = root,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            ErrorMessage = "Could not open the local knowledge folder: " + ex.Message;
        }
    }

    private void RaiseCommandStates()
    {
        (SearchCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (RefreshCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (ApproveCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (RejectCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (NeedsCorrectionCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (DeleteCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (ImportDocumentCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (ImportTranscriptCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (ExtractProjectCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (BackupCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
        (ExportCommand as AsyncRelayCommand)?.RaiseCanExecuteChanged();
    }
}

public sealed class KnowledgeListItemViewModel
{
    private KnowledgeListItemViewModel(
        string title,
        string subtitle,
        string status,
        string sourceLabel,
        bool isRecord,
        string? recordId,
        string snippetText)
    {
        Title = title;
        Subtitle = subtitle;
        Status = status;
        SourceLabel = sourceLabel;
        IsRecord = isRecord;
        RecordId = recordId;
        SnippetText = snippetText;
    }

    public string Title { get; }

    public string Subtitle { get; }

    public string Status { get; }

    public string SourceLabel { get; }

    public bool IsRecord { get; }

    public string? RecordId { get; }

    public string SnippetText { get; }

    public string KindLabel => IsRecord ? "RECORD" : "SOURCE";

    public static KnowledgeListItemViewModel FromRecord(KnowledgeRecordSummary record) =>
        new(
            record.Subject,
            $"{record.Category} · v{record.Version} · {record.Confidence.ToString("P0", CultureInfo.CurrentCulture)}",
            record.Status,
            record.Provenance.Count == 0
                ? "No source"
                : string.Join(", ", record.Provenance.Select(source => source.Title)),
            isRecord: true,
            recordId: record.Id,
            snippetText: record.Description);

    public static KnowledgeListItemViewModel FromSnippet(KnowledgeSnippet snippet) =>
        new(
            snippet.Title,
            snippet.Kind,
            "source",
            snippet.Url ?? snippet.Kind,
            isRecord: false,
            recordId: null,
            snippetText: snippet.Snippet);
}
