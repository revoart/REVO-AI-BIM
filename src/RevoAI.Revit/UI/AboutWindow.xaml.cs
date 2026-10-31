using System.Windows;

namespace RevoAI.Revit.UI;

public partial class AboutWindow : Window
{
    public AboutWindow(string revitVersion)
    {
        InitializeComponent();
        DataContext = new AboutViewModel(revitVersion);
    }
}
