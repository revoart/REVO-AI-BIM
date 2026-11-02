using System.Reflection;

namespace RevoAI.Revit;

public static class BuildInfo
{
    public static string Version { get; } = ReadVersion();

    public static string InformationalVersion { get; } =
        typeof(BuildInfo).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
        ?? Version;

    /// <summary>
    /// Internal Revo tooling (knowledge review, project extraction) is hidden
    /// from customers. Revo staff enable it with REVOAI_INTERNAL_TOOLS=1.
    /// </summary>
    public static bool InternalToolsEnabled { get; } =
        string.Equals(
            Environment.GetEnvironmentVariable("REVOAI_INTERNAL_TOOLS"),
            "1",
            StringComparison.OrdinalIgnoreCase);

    private static string ReadVersion() =>
        typeof(BuildInfo).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";
}
