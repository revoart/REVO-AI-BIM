using System.Text.Json;
using RevoAI.Revit.Configuration;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class ConfigWriterTests
{
    [Fact]
    public void SavedConfigurationRoundTrips()
    {
        var path = Path.Combine(Path.GetTempPath(), $"revoai-config-{Guid.NewGuid():N}.json");

        try
        {
            RevoConfigWriter.Save(
                new RevoConfig
                {
                    PythonExecutable = @"C:\Python\python.exe",
                    EngineRoot = @"C:\Revo\engine",
                    StartupTimeoutSeconds = 30,
                    RequestTimeoutSeconds = 45,
                },
                path);

            var loaded = RevoConfig.Load(path, new Dictionary<string, string?>());

            Assert.Equal(@"C:\Python\python.exe", loaded.PythonExecutable);
            Assert.Equal(@"C:\Revo\engine", loaded.EngineRoot);
            Assert.Equal(30, loaded.StartupTimeoutSeconds);
            Assert.Equal(45, loaded.RequestTimeoutSeconds);
        }
        finally
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
    }

    [Fact]
    public void SavedFileUsesCamelCaseKeys()
    {
        var path = Path.Combine(Path.GetTempPath(), $"revoai-config-{Guid.NewGuid():N}.json");

        try
        {
            RevoConfigWriter.Save(new RevoConfig { EngineRoot = @"C:\Revo\engine" }, path);

            using var document = JsonDocument.Parse(File.ReadAllText(path));
            Assert.True(document.RootElement.TryGetProperty("engineRoot", out _));
            Assert.True(document.RootElement.TryGetProperty("startupTimeoutSeconds", out _));
        }
        finally
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
    }
}
