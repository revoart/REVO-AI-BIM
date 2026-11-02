using System.Reflection;

namespace RevoAI.Revit;

public static class BuildInfo
{
    public static string Version { get; } = ReadVersion();

    public static string InformationalVersion { get; } =
        typeof(BuildInfo).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
        ?? Version;

    private static string ReadVersion() =>
        typeof(BuildInfo).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";
}
