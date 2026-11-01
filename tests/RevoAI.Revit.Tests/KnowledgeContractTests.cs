using System.Text.Json;
using RevoAI.Contracts.Protocol;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class KnowledgeContractTests
{
    [Fact]
    public void SearchParametersUseCamelCaseWireNames()
    {
        var parameters = new KnowledgeSearchParams
        {
            Query = "wall centreline",
            Statuses = ["approved"],
            SourceTypes = ["youtube"],
            RevitVersion = "2027",
            Limit = 12,
            Offset = 3,
        };

        var json = RevoAIJson.Serialize(parameters);

        Assert.Contains("\"query\":\"wall centreline\"", json);
        Assert.Contains("\"statuses\":[\"approved\"]", json);
        Assert.Contains("\"sourceTypes\":[\"youtube\"]", json);
        Assert.Contains("\"revitVersion\":\"2027\"", json);
        Assert.Contains("\"limit\":12", json);
        Assert.Contains("\"offset\":3", json);
    }

    [Fact]
    public void SearchResultDeserializesProvenanceAndSnippets()
    {
        const string json = """
        {
          "query": "walls",
          "records": [
            {
              "id": "rec-1",
              "subject": "Wall centrelines",
              "category": "walls",
              "description": "Use wall planes.",
              "status": "approved",
              "sourceType": "youtube",
              "revitVersion": "2027",
              "confidence": 0.8,
              "verification": ["verified_revit"],
              "tags": ["wall"],
              "version": 1,
              "updatedAt": "2026-11-01T00:00:00.000Z",
              "provenance": [
                {
                  "sourceId": "src-1",
                  "kind": "youtube",
                  "title": "Scan to BIM",
                  "url": "https://example.test/v",
                  "creator": "Tester",
                  "license": "Test",
                  "publishedAt": null,
                  "locator": "00:12:30"
                }
              ]
            }
          ],
          "snippets": [
            {
              "chunkId": "chunk-1",
              "documentId": "doc-1",
              "title": "Scan to BIM",
              "kind": "youtube",
              "url": "https://example.test/v",
              "sourceId": "src-1",
              "snippet": "Create [walls] from the scan."
            }
          ],
          "total": 1
        }
        """;

        var result = RevoAIJson.Deserialize<KnowledgeSearchResult>(json);

        Assert.Single(result.Records);
        Assert.Equal("rec-1", result.Records[0].Id);
        Assert.Equal("approved", result.Records[0].Status);
        Assert.Equal("src-1", result.Records[0].Provenance[0].SourceId);
        Assert.Equal("00:12:30", result.Records[0].Provenance[0].Locator);
        Assert.Single(result.Snippets);
        Assert.Equal("chunk-1", result.Snippets[0].ChunkId);
    }

    [Fact]
    public void ProjectImportAcceptsPathOrExtraction()
    {
        var fromPath = new KnowledgeProjectImportParams { Path = @"C:\extract.json" };
        Assert.Equal(@"C:\extract.json", fromPath.Path);

        using var document = JsonDocument.Parse("""{"project":{"title":"House"},"elements":[]}""");
        var fromObject = new KnowledgeProjectImportParams
        {
            Extraction = document.RootElement.Clone(),
        };

        Assert.NotNull(fromObject.Extraction);
        Assert.Equal(JsonValueKind.Object, fromObject.Extraction!.Value.ValueKind);
    }

    [Fact]
    public void StatsDeserializeStatusCounts()
    {
        const string json = """
        {
          "root": "C:/knowledge",
          "databasePath": "C:/knowledge/knowledge.db",
          "databaseBytes": 4096,
          "sources": 2,
          "documents": 3,
          "chunks": 12,
          "records": 4,
          "recordsByStatus": { "approved": 1, "pending_review": 3 },
          "projects": 1,
          "projectElements": 250,
          "decisions": 0,
          "benchmarks": 0,
          "schemaVersion": 1
        }
        """;

        var stats = RevoAIJson.Deserialize<KnowledgeStatsResult>(json);

        Assert.Equal(4, stats.Records);
        Assert.Equal(1, stats.RecordsByStatus["approved"]);
        Assert.Equal(250, stats.ProjectElements);
    }
}
