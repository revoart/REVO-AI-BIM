using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows.Input;

namespace RevoAI.Revit.UI;

/// <summary>
/// Pricing and plan-selection surface. The billing backend is not connected yet;
/// selecting a plan never charges the customer.
/// </summary>
public sealed class SubscriptionViewModel : ObservableObject
{
    private bool _isYearly;
    private string _selectedPlan = "No plan selected";
    private string _statusMessage =
        "Billing is not connected yet. Pricing is shown for the upcoming Revo AI BIM subscription.";

    public SubscriptionViewModel()
    {
        Plans =
        [
            new SubscriptionPlanViewModel(
                this,
                "Personal",
                35m,
                378m,
                "1 seat",
                "Individual use",
                isRecommended: false),
            new SubscriptionPlanViewModel(
                this,
                "Commercial",
                80m,
                864m,
                "Up to 3 seats",
                "Small teams",
                isRecommended: true),
            new SubscriptionPlanViewModel(
                this,
                "Enterprise",
                250m,
                2700m,
                "Organization-wide",
                "Company deployment",
                isRecommended: false),
        ];

        ShowMonthlyCommand = new RelayCommand(() => IsYearly = false);
        ShowYearlyCommand = new RelayCommand(() => IsYearly = true);
        ApplyBillingPeriod();
    }

    public ObservableCollection<SubscriptionPlanViewModel> Plans { get; }

    public ICommand ShowMonthlyCommand { get; }

    public ICommand ShowYearlyCommand { get; }

    public bool IsMonthly => !_isYearly;

    public bool IsYearly
    {
        get => _isYearly;
        set
        {
            if (SetProperty(ref _isYearly, value))
            {
                OnPropertyChanged(nameof(IsMonthly));
                ApplyBillingPeriod();
            }
        }
    }

    public string SelectedPlan
    {
        get => _selectedPlan;
        private set => SetProperty(ref _selectedPlan, value);
    }

    public string StatusMessage
    {
        get => _statusMessage;
        private set => SetProperty(ref _statusMessage, value);
    }

    public string BillingNote =>
        "Yearly billing saves 10%. Prices are in USD. Taxes may apply.";

    internal void SelectPlan(SubscriptionPlanViewModel plan)
    {
        SelectedPlan = plan.Name;
        StatusMessage =
            $"{plan.Name} selected. Checkout becomes available when the Revo billing backend is connected.";
    }

    private void ApplyBillingPeriod()
    {
        foreach (var plan in Plans)
        {
            plan.SetBillingPeriod(IsYearly);
        }
    }
}

public sealed class SubscriptionPlanViewModel : ObservableObject
{
    private readonly SubscriptionViewModel _owner;

    public SubscriptionPlanViewModel(
        SubscriptionViewModel owner,
        string name,
        decimal monthlyPrice,
        decimal yearlyPrice,
        string seats,
        string audience,
        bool isRecommended)
    {
        _owner = owner;
        Name = name;
        MonthlyPrice = monthlyPrice;
        YearlyPrice = yearlyPrice;
        Seats = seats;
        Audience = audience;
        IsRecommended = isRecommended;
        SelectCommand = new RelayCommand(() => _owner.SelectPlan(this));
        SetBillingPeriod(false);
    }

    public string Name { get; }

    public decimal MonthlyPrice { get; }

    public decimal YearlyPrice { get; }

    public string Seats { get; }

    public string Audience { get; }

    public bool IsRecommended { get; }

    public ICommand SelectCommand { get; }

    public string DisplayPrice { get; private set; } = string.Empty;

    public string BillingSuffix { get; private set; } = string.Empty;

    public string YearlyEquivalent { get; private set; } = string.Empty;

    public string FeatureText =>
        "Full Scan-to-BIM workflow\nRevo-managed Astra analysis\nImport, analysis and generation";

    internal void SetBillingPeriod(bool yearly)
    {
        if (yearly)
        {
            DisplayPrice = FormatPrice(YearlyPrice);
            BillingSuffix = "/year";
            YearlyEquivalent =
                $"≈ {FormatPrice(decimal.Round(YearlyPrice / 12m, 2))}/month billed yearly";
        }
        else
        {
            DisplayPrice = FormatPrice(MonthlyPrice);
            BillingSuffix = "/month";
            YearlyEquivalent = "Switch to yearly and save 10%";
        }

        OnPropertyChanged(nameof(DisplayPrice));
        OnPropertyChanged(nameof(BillingSuffix));
        OnPropertyChanged(nameof(YearlyEquivalent));
    }

    private static string FormatPrice(decimal value) =>
        "$" + value.ToString("0.##", CultureInfo.InvariantCulture);
}
