using System.IO;
using System.Windows;
using Microsoft.Win32;

namespace RevoAI.Revit.UI;

public sealed class KnowledgeTranscriptRequest
{
    public required string Title { get; init; }

    public required string Transcript { get; init; }

    public string? Url { get; init; }

    public string? Creator { get; init; }

    public string? License { get; init; }
}

public partial class KnowledgeTranscriptWindow : Window
{
    public KnowledgeTranscriptWindow()
    {
        InitializeComponent();
    }

    public KnowledgeTranscriptRequest? Request { get; private set; }

    private void BrowseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose a transcript file",
            Filter =
                "Transcript files (*.txt;*.md;*.vtt;*.srt)|*.txt;*.md;*.vtt;*.srt|All files (*.*)|*.*",
            CheckFileExists = true,
        };

        if (dialog.ShowDialog() != true)
        {
            return;
        }

        try
        {
            TranscriptBox.Text = File.ReadAllText(dialog.FileName);
            if (string.IsNullOrWhiteSpace(TitleBox.Text))
            {
                TitleBox.Text = Path.GetFileNameWithoutExtension(dialog.FileName);
            }
        }
        catch (Exception ex)
        {
            ErrorText.Text = "Could not read the transcript file: " + ex.Message;
        }
    }

    private void ImportButton_Click(object sender, RoutedEventArgs e)
    {
        var title = TitleBox.Text.Trim();
        var transcript = TranscriptBox.Text.Trim();

        if (string.IsNullOrWhiteSpace(title))
        {
            ErrorText.Text = "Enter a title for the transcript.";
            return;
        }

        if (string.IsNullOrWhiteSpace(transcript))
        {
            ErrorText.Text = "Paste or load the transcript text.";
            return;
        }

        Request = new KnowledgeTranscriptRequest
        {
            Title = title,
            Transcript = transcript,
            Url = NullIfWhiteSpace(UrlBox.Text),
            Creator = NullIfWhiteSpace(CreatorBox.Text),
            License = NullIfWhiteSpace(LicenseBox.Text),
        };

        DialogResult = true;
    }

    private void CancelButton_Click(object sender, RoutedEventArgs e) => DialogResult = false;

    private static string? NullIfWhiteSpace(string value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
