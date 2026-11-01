using System.Windows;

namespace RevoAI.Revit.UI;

public partial class ImportScanWindow : Window
{
    public ImportScanWindow()
    {
        ViewModel = new ImportScanViewModel();
        InitializeComponent();
        DataContext = ViewModel;
    }

    public ImportScanViewModel ViewModel { get; }
}
