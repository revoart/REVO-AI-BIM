using System.Text.Json;
using RevoAI.Contracts.Protocol;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class PointCloudContractTests
{
    [Fact]
    public void ImportParametersUseCamelCaseAndDefaults()
    {
        var parameters = new PointCloudImportParams
        {
            Path = @"C:\scans\building.e57",
            OutputDirectory = @"C:\scans\store",
            RemoveOutliers = true,
            VoxelSizeMeters = 0.02,
        };

        using var document = JsonDocument.Parse(RevoAIJson.Serialize(parameters));
        var root = document.RootElement;

        Assert.Equal(@"C:\scans\building.e57", root.GetProperty("path").GetString());
        Assert.Equal(@"C:\scans\store", root.GetProperty("outputDirectory").GetString());
        Assert.Equal("auto", root.GetProperty("unit").GetString());
        Assert.Equal(25.0, root.GetProperty("chunkSizeMeters").GetDouble());
        Assert.Equal(20, root.GetProperty("outlierNeighbors").GetInt32());
        Assert.Equal(2.0, root.GetProperty("outlierStdRatio").GetDouble());
        Assert.True(root.GetProperty("removeOutliers").GetBoolean());
        Assert.Equal(0.02, root.GetProperty("voxelSizeMeters").GetDouble());
    }

    [Fact]
    public void ImportResultDeserializesFromEngineShape()
    {
        const string json = """
            {
              "scanId": "scan-1",
              "storePath": "C:\\scans\\store\\scan-1",
              "sourcePath": "C:\\scans\\scan.e57",
              "format": "e57",
              "unit": "meters",
              "unitSource": "format",
              "pointCount": {
                "original": 100,
                "valid": 100,
                "afterOutlierRemoval": 98,
                "afterDownsampling": 50,
                "stored": 50
              },
              "bounds": { "min": [0, 0, 0], "max": [10, 5, 3] },
              "sourceBounds": { "min": [0, 0, 0], "max": [10, 5, 3] },
              "chunkCount": 4,
              "attributes": ["colors", "intensity"],
              "warnings": ["test warning"],
              "elapsedMs": 123.4,
              "sourceSha256": "abc",
              "engineVersion": "0.3.0"
            }
            """;

        var result = RevoAIJson.Deserialize<PointCloudImportResult>(json);

        Assert.Equal("scan-1", result.ScanId);
        Assert.Equal("format", result.UnitSource);
        Assert.Equal(50, result.PointCount.Stored);
        Assert.Equal(4, result.ChunkCount);
        Assert.Equal(10, result.Bounds.Max[0]);
        Assert.Equal("abc", result.SourceSha256);
        Assert.Equal(["colors", "intensity"], result.Attributes);
    }

    [Fact]
    public void QueryResultDeserializesPositionsAndColours()
    {
        const string json = """
            {
              "positions": [[0, 0, 0], [1, 2, 3]],
              "count": 2,
              "returned": 2,
              "truncated": false,
              "colors": [[255, 0, 0], [0, 255, 0]],
              "intensity": [10.0, 20.0]
            }
            """;

        var result = RevoAIJson.Deserialize<PointCloudQueryResult>(json);

        Assert.Equal(2, result.Positions.Count);
        Assert.Equal([1.0, 2.0, 3.0], result.Positions[1]);
        Assert.NotNull(result.Colors);
        Assert.Equal(255, result.Colors![0][0]);
        Assert.NotNull(result.Intensity);
        Assert.Equal(20.0f, result.Intensity![1]);
    }

    [Fact]
    public void QueryParametersSerializeBoundsOrRadius()
    {
        var bounds = new PointCloudQueryParams
        {
            StorePath = "store",
            Bounds = new Bounds3
            {
                Min = [0, 0, 0],
                Max = [1, 1, 1],
            },
            MaxPoints = 500,
        };

        using var document = JsonDocument.Parse(RevoAIJson.Serialize(bounds));
        var root = document.RootElement;

        Assert.Equal("store", root.GetProperty("storePath").GetString());
        Assert.Equal(0, root.GetProperty("bounds").GetProperty("min")[0].GetDouble());
        Assert.Equal(500, root.GetProperty("maxPoints").GetInt32());
    }
}
