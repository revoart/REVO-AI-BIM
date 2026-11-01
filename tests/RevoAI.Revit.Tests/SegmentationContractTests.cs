using System.Text.Json;
using RevoAI.Contracts.Protocol;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class SegmentationContractTests
{
    [Fact]
    public void RunParametersUseCamelCaseAndDefaults()
    {
        var parameters = new SegmentationRunParams
        {
            StorePath = @"C:\scans\store\scan-1",
            VoxelSizeMeters = 0,
            PlaneDistanceMeters = 0.02,
        };

        using var document = JsonDocument.Parse(RevoAIJson.Serialize(parameters));
        var root = document.RootElement;

        Assert.Equal(@"C:\scans\store\scan-1", root.GetProperty("storePath").GetString());
        Assert.Equal(0.0, root.GetProperty("voxelSizeMeters").GetDouble());
        Assert.Equal(200_000, root.GetProperty("maxPoints").GetInt32());
        Assert.Equal(0.02, root.GetProperty("planeDistanceMeters").GetDouble());
        Assert.Equal(300, root.GetProperty("minPlanePoints").GetInt32());
        Assert.Equal(40, root.GetProperty("maxPlanes").GetInt32());
        Assert.Equal(0.75, root.GetProperty("confidenceThreshold").GetDouble());
    }

    [Fact]
    public void ResultDeserializesFromEngineShape()
    {
        const string json = """
            {
              "scanId": "room",
              "storePath": "C:\\scans\\room",
              "method": "geometric-plane-baseline/1",
              "methodNote": "not dimensional accuracy",
              "parameters": { "voxelSizeMeters": 0.05 },
              "summary": {
                "sourcePoints": 1000,
                "analyzedPoints": 800,
                "segments": 2,
                "byKind": { "floor": 1, "wall": 1 },
                "meanConfidence": 0.91,
                "highConfidenceSegments": 2,
                "assignedPoints": 700,
                "coverage": 0.875
              },
              "elements": [
                {
                  "id": "floor-1",
                  "kind": "floor",
                  "pointCount": 500,
                  "confidence": 0.93,
                  "areaM2": 12.5,
                  "centroid": [2.0, 1.5, 0.0],
                  "bounds": { "min": [0, 0, 0], "max": [4, 3, 0] },
                  "plane": { "normal": [0, 0, 1], "offset": 0.0 },
                  "signals": {
                    "planarity": 0.99,
                    "densityPerSquareMeter": 40.0,
                    "coverage": 1.0,
                    "size": 1.0,
                    "fitErrorMeters": 0.001,
                    "inlierRatio": 0.625
                  }
                }
              ],
              "warnings": [],
              "resultPath": "C:\\scans\\room\\analysis\\segmentation.json",
              "createdAt": "2026-11-01T12:00:00Z",
              "engineVersion": "0.4.0",
              "elapsedMs": 42.5
            }
            """;

        var result = RevoAIJson.Deserialize<SegmentationResult>(json);

        Assert.Equal("room", result.ScanId);
        Assert.Equal("geometric-plane-baseline/1", result.Method);
        Assert.Equal(2, result.Summary.Segments);
        Assert.Equal(1, result.Summary.ByKind["floor"]);
        Assert.Single(result.Elements);
        Assert.Equal("floor-1", result.Elements[0].Id);
        Assert.Equal(0.93, result.Elements[0].Confidence);
        Assert.Equal(12.5, result.Elements[0].AreaM2);
        Assert.Equal(0.99, result.Elements[0].Signals.Planarity);
        Assert.Equal(42.5, result.ElapsedMs);
    }
}
