using System.Windows;

namespace RevoAI.Revit.UI;

public partial class ScanAnalysisWindow : Window
{
    public ScanAnalysisWindow(string storePath, double confidenceThreshold)
    {
        ViewModel = new ScanAnalysisViewModel(storePath, confidenceThreshold);
        InitializeComponent();
        DataContext = ViewModel;
    }

    public ScanAnalysisViewModel ViewModel { get; }
}
