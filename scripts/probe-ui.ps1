# Builds and runs a throwaway WPF probe that constructs the add-in windows and
# loads every ribbon icon. This catches XAML/resource errors without Revit.
#
# It does not exercise Revit API behaviour; that still requires launching Revit.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$probe = Join-Path $env:TEMP 'revoai-ui-probe'

Remove-Item $probe -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $probe | Out-Null

$project = @"
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <EnableDefaultApplicationDefinition>false</EnableDefaultApplicationDefinition>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="$root\src\RevoAI.Revit\RevoAI.Revit.csproj" />
  </ItemGroup>
</Project>
"@
Set-Content "$probe\probe.csproj" $project -Encoding UTF8

$program = @'
using System;
using System.Windows.Media.Imaging;
using RevoAI.Revit.UI;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        var workspace = new WorkspaceWindow();
        var import = new ImportScanWindow();
        var settings = new SettingsWindow();
        var about = new AboutWindow("2026 (probe)");

        foreach (var name in new[] { "workspace", "import", "analysis", "generate", "review", "quality", "settings", "about" })
        {
            var uri = new Uri($"pack://application:,,,/RevoAI.Revit;component/Resources/Icons/{name}-32.png", UriKind.Absolute);
            var image = new BitmapImage(uri);
            if (image.PixelWidth != 32 || image.PixelHeight != 32)
            {
                throw new InvalidOperationException($"Icon {name} has unexpected size.");
            }
        }

        Console.WriteLine("XAML and icon resources OK.");
        Console.WriteLine("Workspace: " + workspace.Title);
        Console.WriteLine("Import:    " + import.Title);
        Console.WriteLine("Settings:  " + settings.Title);
        Console.WriteLine("About:     " + about.Title);
    }
}
'@
Set-Content "$probe\Program.cs" $program -Encoding UTF8

Push-Location $probe
try {
    dotnet run -c Debug
    if ($LASTEXITCODE -ne 0) { throw 'UI probe failed.' }
}
finally {
    Pop-Location
}
