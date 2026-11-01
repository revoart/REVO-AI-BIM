using System.Windows;
using RevoAI.Revit.RevitApi;

namespace RevoAI.Revit.UI;

public partial class ReconstructionWindow : Window
{
    public ReconstructionWindow(
        RevitTaskRunner runner,
        string storePath,
        double confidenceThreshold,
        bool markInferred)
        : this(new ReconstructionViewModel(runner, storePath, confidenceThreshold, markInferred))
    {
    }

    /// <summary>Design/probe constructor; does not touch Revit or the engine.</summary>
    public ReconstructionWindow()
    {
        ViewModel = null!;
        InitializeComponent();
    }

    private ReconstructionWindow(ReconstructionViewModel viewModel)
    {
        ViewModel = viewModel;
        InitializeComponent();
        DataContext = ViewModel;
    }

    public ReconstructionViewModel ViewModel { get; }
}
