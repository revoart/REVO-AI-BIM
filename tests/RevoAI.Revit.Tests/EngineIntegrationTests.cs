using RevoAI.Contracts.Protocol;
using RevoAI.Revit;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;
using Xunit;
using Xunit.Abstractions;

namespace RevoAI.Revit.Tests;

/// <summary>
/// Exercises the real C# client against the real Python engine process.
/// The test soft-skips (with a message) when the repository virtual
/// environment is not present, for example on a build agent that only runs the
/// pure unit tests.
/// </summary>
public sealed class EngineIntegrationTests
{
    private readonly ITestOutputHelper _output;

    public EngineIntegrationTests(ITestOutputHelper output)
    {
        _output = output;
    }

    [Fact]
    public async Task HandshakePingAndShutdownWorkEndToEnd()
    {
        var repoRoot = TestPaths.FindRepositoryRoot();
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");

        if (!File.Exists(venvPython))
        {
            _output.WriteLine($"SKIPPED: Python environment not found at {venvPython}.");
            return;
        }

        RevoLog.Initialize(Path.Combine(Path.GetTempPath(), "revoai-tests", "logs"));

        var config = new RevoConfig
        {
            EngineRoot = repoRoot,
            StartupTimeoutSeconds = 60,
            RequestTimeoutSeconds = 60,
        };

        await using var client = await PythonEngineClient.StartAsync(config);

        Assert.True(client.IsRunning);
        Assert.NotNull(client.Handshake);
        Assert.Equal(ProtocolVersion.Current, client.Handshake!.ProtocolVersion);
        Assert.Contains(EngineMethods.Initialize, client.Handshake.Capabilities);
        Assert.Contains(EngineMethods.Ping, client.Handshake.Capabilities);
        Assert.False(string.IsNullOrWhiteSpace(client.Handshake.PythonVersion));

        _output.WriteLine(
            $"Engine {client.Handshake.ServerVersion}, Python {client.Handshake.PythonVersion}, " +
            $"capabilities: {string.Join(", ", client.Handshake.Capabilities)}");

        var pong = await client.PingAsync("hello from xunit");

        Assert.Equal("hello from xunit", pong.Message);
        Assert.Equal(client.Handshake.ServerVersion, pong.EngineVersion);
        Assert.True(pong.ServerTimeUtc > DateTimeOffset.UtcNow.AddMinutes(-5));

        await client.ShutdownAsync();
    }

    [Fact]
    public async Task UnknownMethodReturnsTypedProtocolError()
    {
        var repoRoot = TestPaths.FindRepositoryRoot();
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");

        if (!File.Exists(venvPython))
        {
            _output.WriteLine("SKIPPED: Python environment not available.");
            return;
        }

        RevoLog.Initialize(Path.Combine(Path.GetTempPath(), "revoai-tests", "logs"));

        await using var client = await PythonEngineClient.StartAsync(
            new RevoConfig { EngineRoot = repoRoot, StartupTimeoutSeconds = 60 });

        var exception = await Assert.ThrowsAsync<RevoAIEngineException>(async () =>
        {
            // Drive an unsupported method through the public client surface.
            await client.CallAsync("reconstruct.everything");
        });

        Assert.Equal(EngineErrorCodes.MethodNotFound, exception.Code);
    }
}
