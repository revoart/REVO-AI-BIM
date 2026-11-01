using System.Text.Json;
using RevoAI.Contracts.Protocol;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class ReconstructionContractTests
{
    [Fact]
    public void PlanParametersUseCamelCaseAndDefaults()
    {
        var parameters = new ReconstructionPlanParams
        {
            StorePath = @"C:\scans\store",
            ExternalPlanPath = @"C:\scans\external-plan.json",
            MaxElements = 25,
        };

        using var document = JsonDocument.Parse(RevoAIJson.Serialize(parameters));
        var root = document.RootElement;

        Assert.Equal(@"C:\scans\store", root.GetProperty("storePath").GetString());
        Assert.Equal(@"C:\scans\external-plan.json", root.GetProperty("externalPlanPath").GetString());
        Assert.Equal(0.75, root.GetProperty("confidenceThreshold").GetDouble());
        Assert.Equal(2.7, root.GetProperty("fallbackWallHeightMeters").GetDouble());
        Assert.Equal(0.25, root.GetProperty("levelToleranceMeters").GetDouble());
        Assert.Equal(25, root.GetProperty("maxElements").GetInt32());
    }

    [Fact]
    public void PlanResultDeserializesFloorsAndWalls()
    {
        const string json = """
            {
              "scanId": "room",
              "storePath": "C:\\scans\\room",
              "method": "geometric-floor-wall-plan/1",
              "parameters": { "confidenceThreshold": 0.5 },
              "levels": [
                { "id": "level-1", "name": "Revo Level 1", "elevationMeters": 0.0 }
              ],
              "floors": [
                {
                  "id": "floor-plan-1",
                  "sourceSegmentId": "floor-1",
                  "levelId": "level-1",
                  "boundary": [[0,0,0],[4,0,0],[4,3,0],[0,3,0]],
                  "areaM2": 12.0,
                  "confidence": 0.9
                }
              ],
              "walls": [
                {
                  "id": "wall-plan-1",
                  "sourceSegmentId": "wall-1",
                  "levelId": "level-1",
                  "start": [0,0,0],
                  "end": [4,0,0],
                  "heightMeters": 2.7,
                  "heightSource": "ceiling",
                  "confidence": 0.88
                }
              ],
              "warnings": [],
              "resultPath": "C:\\scans\\room\\analysis\\reconstruction-plan.json",
              "createdAt": "2026-11-01T12:00:00Z",
              "engineVersion": "0.5.0",
              "elapsedMs": 12.0
            }
            """;

        var plan = RevoAIJson.Deserialize<ReconstructionPlanResult>(json);

        Assert.Equal("room", plan.ScanId);
        Assert.Single(plan.Levels);
        Assert.Single(plan.Floors);
        Assert.Single(plan.Walls);
        Assert.Equal(4, plan.Floors[0].Boundary.Count);
        Assert.Equal(2.7, plan.Walls[0].HeightMeters);
        Assert.Equal("ceiling", plan.Walls[0].HeightSource);
    }
}
