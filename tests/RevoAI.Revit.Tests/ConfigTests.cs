using RevoAI.Revit.Configuration;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class ConfigTests
{
    [Fact]
    public void EnvironmentOverridesConfigFile()
    {
        var config = RevoConfig.Load(
            Path.Combine(Path.GetTempPath(), $"missing-{Guid.NewGuid():N}.json"),
            new Dictionary<string, string?>
            {
                [RevoConfig.PythonEnvironmentVariable] = @"C:\Python\python.exe",
                [RevoConfig.EngineRootEnvironmentVariable] = @"C:\Revo\engine",
            });

        Assert.Equal(@"C:\Python\python.exe", config.PythonExecutable);
        Assert.Equal(@"C:\Revo\engine", config.EngineRoot);
    }

    [Fact]
    public void ConfigFileIsReadWithCamelCaseNames()
    {
        var path = Path.Combine(Path.GetTempPath(), $"revoai-{Guid.NewGuid():N}.json");
        File.WriteAllText(
            path,
            """
            {"pythonExecutable":"C:\\Python\\python.exe","engineRoot":"C:\\Revo\\engine","startupTimeoutSeconds":15}
            """);

        try
        {
            var config = RevoConfig.Load(path, new Dictionary<string, string?>());

            Assert.Equal(@"C:\Python\python.exe", config.PythonExecutable);
            Assert.Equal(@"C:\Revo\engine", config.EngineRoot);
            Assert.Equal(15, config.StartupTimeoutSeconds);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void EngineRootIsDiscoveredByWalkingUp()
    {
        var root = CreateFakeEngineRoot();
        var nested = Path.Combine(root, "src", "RevoAI.Revit", "bin", "Debug");
        Directory.CreateDirectory(nested);

        try
        {
            var config = new RevoConfig();
            var resolved = config.ResolveEngineRoot(nested);

            Assert.Equal(Path.GetFullPath(root), resolved);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void VirtualEnvironmentInterpreterIsPreferred()
    {
        var root = CreateFakeEngineRoot();
        var venvPython = Path.Combine(root, ".venv", "Scripts", "python.exe");
        Directory.CreateDirectory(Path.GetDirectoryName(venvPython)!);
        File.WriteAllText(venvPython, string.Empty);

        try
        {
            var config = new RevoConfig();
            var plan = config.CreateLaunchPlan(root);

            Assert.Equal(venvPython, plan.Executable);
            Assert.Empty(plan.Arguments);
            Assert.Equal(root, plan.WorkingDirectory);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void PyLauncherGetsExplicitInterpreterArgument()
    {
        var config = new RevoConfig { PythonExecutable = "py" };

        var arguments = config.ResolvePythonArguments("py");

        Assert.Equal(["-3.14"], arguments);
    }

    [Fact]
    public void MissingConfiguredInterpreterFailsClearly()
    {
        var config = new RevoConfig
        {
            PythonExecutable = Path.Combine(Path.GetTempPath(), $"missing-{Guid.NewGuid():N}.exe"),
        };

        var exception = Assert.Throws<FileNotFoundException>(
            () => config.ResolvePythonExecutable(Path.GetTempPath()));

        Assert.Contains("does not exist", exception.Message);
    }

    private static string CreateFakeEngineRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"revoai-root-{Guid.NewGuid():N}");
        var package = Path.Combine(root, "src", "RevoAI.Engine", "revoai_engine");
        Directory.CreateDirectory(package);
        File.WriteAllText(Path.Combine(package, "__init__.py"), string.Empty);
        return root;
    }
}
