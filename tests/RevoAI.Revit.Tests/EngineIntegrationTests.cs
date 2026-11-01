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
    public async Task PointCloudImportInfoAndQueryWorkEndToEnd()
    {
        var repoRoot = TestPaths.FindRepositoryRoot();
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");

        if (!File.Exists(venvPython))
        {
            _output.WriteLine($"SKIPPED: Python environment not found at {venvPython}.");
            return;
        }

        RevoLog.Initialize(Path.Combine(Path.GetTempPath(), "revoai-tests", "logs"));

        var work = Path.Combine(Path.GetTempPath(), "revoai-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        var source = Path.Combine(work, "scan.xyz");
        await File.WriteAllLinesAsync(
            source,
            ["0 0 0 255 0 0", "1 2 3 0 255 0", "2 4 6 0 0 255"]);

        var config = new RevoConfig
        {
            EngineRoot = repoRoot,
            StartupTimeoutSeconds = 60,
            RequestTimeoutSeconds = 60,
        };

        try
        {
            await using var client = await PythonEngineClient.StartAsync(config);
            Assert.Contains(EngineMethods.PointCloudImport, client.Handshake!.Capabilities);
            Assert.Contains(EngineMethods.PointCloudInfo, client.Handshake.Capabilities);
            Assert.Contains(EngineMethods.PointCloudQuery, client.Handshake.Capabilities);

            var imported = await client.ImportPointCloudAsync(new PointCloudImportParams
            {
                Path = source,
                Unit = "meters",
                OutputDirectory = Path.Combine(work, "store"),
                ScanId = "csharp-scan",
                ChunkSizeMeters = 2.0,
            });

            Assert.Equal("csharp-scan", imported.ScanId);
            Assert.Equal("meters", imported.Unit);
            Assert.Equal("user", imported.UnitSource);
            Assert.Equal(3, imported.PointCount.Stored);
            Assert.True(Directory.Exists(imported.StorePath));
            Assert.True(File.Exists(Path.Combine(imported.StorePath, "metadata.json")));
            Assert.Equal(0.0, imported.Bounds.Min[0]);

            var info = await client.GetPointCloudInfoAsync(imported.StorePath);
            Assert.Equal(imported.ScanId, info.ScanId);
            Assert.Equal(imported.ChunkCount, info.ChunkCount);
            Assert.Equal(imported.PointCount.Stored, info.PointCount.Stored);

            var queried = await client.QueryPointCloudAsync(new PointCloudQueryParams
            {
                StorePath = imported.StorePath,
                Bounds = new Bounds3
                {
                    Min = [-1, -1, -1],
                    Max = [1.5, 3.5, 5.0],
                },
                MaxPoints = 10,
                IncludeColors = true,
            });

            Assert.Equal(2, queried.Count);
            Assert.Equal(2, queried.Returned);
            Assert.Equal(0.0, queried.Positions[0][0]);
            Assert.NotNull(queried.Colors);
            Assert.Equal(255, queried.Colors![0][0]);

            var sampled = await client.QueryPointCloudAsync(new PointCloudQueryParams
            {
                StorePath = imported.StorePath,
                MaxPoints = 1,
                IncludeColors = true,
            });
            Assert.Equal(3, sampled.Count);
            Assert.Equal(1, sampled.Returned);
            Assert.False(sampled.Truncated);
            Assert.NotNull(sampled.Colors);

            var missing = await Assert.ThrowsAsync<RevoAIEngineException>(async () =>
            {
                await client.ImportPointCloudAsync(new PointCloudImportParams
                {
                    Path = Path.Combine(work, "missing.xyz"),
                    OutputDirectory = Path.Combine(work, "store-missing"),
                });
            });
            Assert.Equal(EngineErrorCodes.FileNotFound, missing.Code);
        }
        finally
        {
            try
            {
                Directory.Delete(work, recursive: true);
            }
            catch (IOException)
            {
                // A failed test should not be masked by temp cleanup.
            }
        }
    }

    [Fact]
    public async Task SegmentationRunAndInfoWorkEndToEnd()
    {
        var repoRoot = TestPaths.FindRepositoryRoot();
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");

        if (!File.Exists(venvPython))
        {
            _output.WriteLine($"SKIPPED: Python environment not found at {venvPython}.");
            return;
        }

        RevoLog.Initialize(Path.Combine(Path.GetTempPath(), "revoai-tests", "logs"));

        var work = Path.Combine(Path.GetTempPath(), "revoai-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(work);
        var source = Path.Combine(work, "room.xyz");
        await File.WriteAllLinesAsync(source, SyntheticRoomLines());

        var config = new RevoConfig
        {
            EngineRoot = repoRoot,
            StartupTimeoutSeconds = 60,
            RequestTimeoutSeconds = 60,
        };

        try
        {
            await using var client = await PythonEngineClient.StartAsync(config);
            Assert.Contains(EngineMethods.SegmentationRun, client.Handshake!.Capabilities);
            Assert.Contains(EngineMethods.SegmentationInfo, client.Handshake.Capabilities);
            Assert.Contains(EngineMethods.ReconstructionPlan, client.Handshake.Capabilities);

            var imported = await client.ImportPointCloudAsync(new PointCloudImportParams
            {
                Path = source,
                Unit = "meters",
                OutputDirectory = Path.Combine(work, "store"),
                ScanId = "csharp-room",
                ChunkSizeMeters = 5.0,
            });

            var missingAnalysis = await Assert.ThrowsAsync<RevoAIEngineException>(async () =>
                await client.GetSegmentationInfoAsync(imported.StorePath));
            Assert.Equal(EngineErrorCodes.AnalysisNotFound, missingAnalysis.Code);

            var analysis = await client.RunSegmentationAsync(new SegmentationRunParams
            {
                StorePath = imported.StorePath,
                VoxelSizeMeters = 0,
                MaxPoints = 10_000,
                PlaneDistanceMeters = 0.01,
                MinPlanePoints = 100,
                MaxPlanes = 20,
            });

            Assert.Equal("csharp-room", analysis.ScanId);
            Assert.Equal("geometric-plane-baseline/1", analysis.Method);
            Assert.True(analysis.Summary.Segments >= 6);
            Assert.True(analysis.Summary.ByKind["floor"] >= 1);
            Assert.True(analysis.Summary.ByKind["ceiling"] >= 1);
            Assert.True(analysis.Summary.ByKind["wall"] >= 4);
            Assert.True(analysis.Summary.MeanConfidence > 0.8);
            Assert.True(File.Exists(analysis.ResultPath));

            var info = await client.GetSegmentationInfoAsync(imported.StorePath);
            Assert.Equal(analysis.Summary.Segments, info.Summary.Segments);
            Assert.Equal(analysis.ResultPath, info.ResultPath);

            var plan = await client.CreateReconstructionPlanAsync(new ReconstructionPlanParams
            {
                StorePath = imported.StorePath,
                ConfidenceThreshold = 0.5,
                MaxElements = 20,
            });
            Assert.Single(plan.Levels);
            Assert.Single(plan.Floors);
            Assert.Equal(4, plan.Walls.Count);
            Assert.True(File.Exists(plan.ResultPath));
        }
        finally
        {
            try
            {
                Directory.Delete(work, recursive: true);
            }
            catch (IOException)
            {
                // A failed test should not be masked by temp cleanup.
            }
        }
    }

    private static IEnumerable<string> SyntheticRoomLines()
    {
        const int xCount = 20;
        const int yCount = 15;
        const int zCount = 15;

        for (var ix = 0; ix < xCount; ix++)
        {
            var x = 0.1 + 3.8 * ix / (xCount - 1);
            for (var iy = 0; iy < yCount; iy++)
            {
                var y = 0.1 + 2.8 * iy / (yCount - 1);
                yield return FormattableString.Invariant($"{x:0.######} {y:0.######} 0");
                yield return FormattableString.Invariant($"{x:0.######} {y:0.######} 2.7");
            }
        }

        for (var iy = 0; iy < yCount; iy++)
        {
            var y = 0.1 + 2.8 * iy / (yCount - 1);
            for (var iz = 0; iz < zCount; iz++)
            {
                var z = 0.05 + 2.6 * iz / (zCount - 1);
                yield return FormattableString.Invariant($"0 {y:0.######} {z:0.######}");
                yield return FormattableString.Invariant($"4 {y:0.######} {z:0.######}");
            }
        }

        for (var ix = 0; ix < xCount; ix++)
        {
            var x = 0.1 + 3.8 * ix / (xCount - 1);
            for (var iz = 0; iz < zCount; iz++)
            {
                var z = 0.05 + 2.6 * iz / (zCount - 1);
                yield return FormattableString.Invariant($"{x:0.######} 0 {z:0.######}");
                yield return FormattableString.Invariant($"{x:0.######} 3 {z:0.######}");
            }
        }
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
