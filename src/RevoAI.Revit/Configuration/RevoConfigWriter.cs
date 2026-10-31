using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RevoAI.Revit.Configuration;

/// <summary>
/// Writes the machine-level configuration file. Kept separate from
/// <see cref="RevoConfig"/> so the read path stays side-effect free and testable.
/// </summary>
public static class RevoConfigWriter
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static void Save(RevoConfig config, string? path = null)
    {
        ArgumentNullException.ThrowIfNull(config);
        path ??= RevoConfig.DefaultConfigPath;

        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var payload = new
        {
            pythonExecutable = string.IsNullOrWhiteSpace(config.PythonExecutable) ? null : config.PythonExecutable,
            pythonArguments = config.PythonArguments is { Length: > 0 } ? config.PythonArguments : null,
            engineRoot = config.EngineRoot,
            logDirectory = config.LogDirectory,
            startupTimeoutSeconds = config.StartupTimeoutSeconds,
            requestTimeoutSeconds = config.RequestTimeoutSeconds,
        };

        File.WriteAllText(path, JsonSerializer.Serialize(payload, Options));
    }
}
