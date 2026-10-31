namespace RevoAI.Revit.Tests;

internal static class TestPaths
{
    /// <summary>
    /// Walks up from the test binaries until the repository marker is found.
    /// </summary>
    public static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            var marker = Path.Combine(
                current.FullName,
                "src",
                "RevoAI.Engine",
                "revoai_engine",
                "__init__.py");

            if (File.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException(
            "Could not locate the Revo AI BIM repository root from " + AppContext.BaseDirectory);
    }
}
