using System.IO;
using System.Text.Json;

namespace RevoAI.Revit.Configuration;

/// <summary>
/// Machine-level configuration for the add-in. Stored as JSON at
/// <c>%APPDATA%\RevoAI\config.json</c>; environment variables override the file
/// so developers and CI can point at a different engine without editing it.
/// </summary>
public sealed class RevoConfig
{
    public const string PythonEnvironmentVariable = "REVOAI_PYTHON";
    public const string EngineRootEnvironmentVariable = "REVOAI_ENGINE_ROOT";
    public const string LogDirectoryEnvironmentVariable = "REVOAI_LOG_DIR";
    public const string KnowledgeRootEnvironmentVariable = "REVOAI_KNOWLEDGE_ROOT";

    /// <summary>
    /// Python executable. Empty means "auto": use the repository virtual
    /// environment when present, otherwise the <c>py</c> launcher.
    /// </summary>
    public string PythonExecutable { get; init; } = string.Empty;

    /// <summary>Explicit interpreter arguments. Null means "auto".</summary>
    public string[]? PythonArguments { get; init; }

    /// <summary>Root of the repository/installation containing the Python packages.</summary>
    public string? EngineRoot { get; init; }

    public string? LogDirectory { get; init; }

    /// <summary>
    /// Local knowledge database root. Null uses the engine default
    /// (<c>%LOCALAPPDATA%\RevoAI\knowledge</c>).
    /// </summary>
    public string? KnowledgeRoot { get; init; }

    public int StartupTimeoutSeconds { get; init; } = 60;

    public int RequestTimeoutSeconds { get; init; } = 120;

    public static string DefaultConfigPath =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "RevoAI",
            "config.json");

    public static RevoConfig Load(string? path = null, IReadOnlyDictionary<string, string?>? environment = null)
    {
        path ??= DefaultConfigPath;
        environment ??= ReadEnvironment();

        var file = File.Exists(path) ? ReadFile(path) : new ConfigFile();

        return new RevoConfig
        {
            PythonExecutable = FirstNonEmpty(
                environment.GetValueOrDefault(PythonEnvironmentVariable),
                file.PythonExecutable) ?? string.Empty,
            PythonArguments = file.PythonArguments,
            EngineRoot = FirstNonEmpty(
                environment.GetValueOrDefault(EngineRootEnvironmentVariable),
                file.EngineRoot),
            LogDirectory = FirstNonEmpty(
                environment.GetValueOrDefault(LogDirectoryEnvironmentVariable),
                file.LogDirectory),
            KnowledgeRoot = FirstNonEmpty(
                environment.GetValueOrDefault(KnowledgeRootEnvironmentVariable),
                file.KnowledgeRoot),
            StartupTimeoutSeconds = file.StartupTimeoutSeconds is > 0 and <= 600
                ? file.StartupTimeoutSeconds.Value
                : 60,
            RequestTimeoutSeconds = file.RequestTimeoutSeconds is > 0 and <= 3600
                ? file.RequestTimeoutSeconds.Value
                : 120,
        };
    }

    /// <summary>
    /// Finds the engine root. When not configured, walks up from the supplied
    /// directory (normally the add-in location) looking for the Python package.
    /// </summary>
    public string ResolveEngineRoot(string? startDirectory = null)
    {
        if (!string.IsNullOrWhiteSpace(EngineRoot))
        {
            var configured = Environment.ExpandEnvironmentVariables(EngineRoot);
            if (!Directory.Exists(configured))
            {
                throw new DirectoryNotFoundException(
                    $"Configured engine root does not exist: '{configured}'. " +
                    $"Set {EngineRootEnvironmentVariable} or update {DefaultConfigPath}.");
            }

            return Path.GetFullPath(configured);
        }

        var current = new DirectoryInfo(startDirectory ?? AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "src", "RevoAI.Engine", "revoai_engine", "__init__.py")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException(
            "Revo AI BIM engine root could not be located. Install the engine or set " +
            $"{EngineRootEnvironmentVariable} to the folder containing 'src\\RevoAI.Engine'.");
    }

    public EngineLaunchPlan CreateLaunchPlan(string? startDirectory = null)
    {
        var engineRoot = ResolveEngineRoot(startDirectory);
        var executable = ResolvePythonExecutable(engineRoot);
        var arguments = ResolvePythonArguments(executable);

        return new EngineLaunchPlan
        {
            EngineRoot = engineRoot,
            Executable = executable,
            Arguments = arguments,
            WorkingDirectory = engineRoot,
        };
    }

    public string ResolvePythonExecutable(string engineRoot)
    {
        if (!string.IsNullOrWhiteSpace(PythonExecutable))
        {
            var expanded = Environment.ExpandEnvironmentVariables(PythonExecutable.Trim());
            if (Path.IsPathRooted(expanded) && !File.Exists(expanded))
            {
                throw new FileNotFoundException(
                    $"Configured Python executable does not exist: '{expanded}'.");
            }

            return expanded;
        }

        var venvPython = Path.Combine(engineRoot, ".venv", "Scripts", "python.exe");
        if (File.Exists(venvPython))
        {
            return venvPython;
        }

        return OperatingSystem.IsWindows() ? "py" : "python3";
    }

    public string[] ResolvePythonArguments(string executable)
    {
        if (PythonArguments is { Length: > 0 })
        {
            return PythonArguments;
        }

        var name = Path.GetFileNameWithoutExtension(executable);
        if (string.Equals(name, "py", StringComparison.OrdinalIgnoreCase))
        {
            // The Windows launcher needs an explicit interpreter selection.
            return ["-3.14"];
        }

        return [];
    }

    private static ConfigFile ReadFile(string path)
    {
        try
        {
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<ConfigFile>(
                json,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)) ?? new ConfigFile();
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException(
                $"Revo AI BIM configuration file is invalid: '{path}'. {ex.Message}", ex);
        }
    }

    private static IReadOnlyDictionary<string, string?> ReadEnvironment() =>
        new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase)
        {
            [PythonEnvironmentVariable] = Environment.GetEnvironmentVariable(PythonEnvironmentVariable),
            [EngineRootEnvironmentVariable] = Environment.GetEnvironmentVariable(EngineRootEnvironmentVariable),
            [LogDirectoryEnvironmentVariable] = Environment.GetEnvironmentVariable(LogDirectoryEnvironmentVariable),
            [KnowledgeRootEnvironmentVariable] = Environment.GetEnvironmentVariable(KnowledgeRootEnvironmentVariable),
        };

    private static string? FirstNonEmpty(params string?[] values) =>
        values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value));

    private sealed class ConfigFile
    {
        public string? PythonExecutable { get; init; }

        public string[]? PythonArguments { get; init; }

        public string? EngineRoot { get; init; }

        public string? LogDirectory { get; init; }

        public string? KnowledgeRoot { get; init; }

        public int? StartupTimeoutSeconds { get; init; }

        public int? RequestTimeoutSeconds { get; init; }
    }
}

public sealed class EngineLaunchPlan
{
    public required string EngineRoot { get; init; }

    public required string Executable { get; init; }

    public required string[] Arguments { get; init; }

    public required string WorkingDirectory { get; init; }
}
