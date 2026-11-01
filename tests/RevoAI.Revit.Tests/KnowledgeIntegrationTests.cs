using RevoAI.Contracts.Protocol;
using RevoAI.Revit;
using RevoAI.Revit.Configuration;
using RevoAI.Revit.Engine;
using Xunit;
using Xunit.Abstractions;

namespace RevoAI.Revit.Tests;

/// <summary>
/// Exercises the real C# knowledge client against the real Python engine and
/// confirms that records persist across engine processes.
/// </summary>
public sealed class KnowledgeIntegrationTests
{
    private readonly ITestOutputHelper _output;

    public KnowledgeIntegrationTests(ITestOutputHelper output)
    {
        _output = output;
    }

    [Fact]
    public async Task KnowledgeImportReviewSearchAndPersistenceWorkEndToEnd()
    {
        var repoRoot = TestPaths.FindRepositoryRoot();
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");

        if (!File.Exists(venvPython))
        {
            _output.WriteLine($"SKIPPED: Python environment not found at {venvPython}.");
            return;
        }

        RevoLog.Initialize(Path.Combine(Path.GetTempPath(), "revoai-tests", "logs"));
        var root = Path.Combine(
            Path.GetTempPath(),
            "revoai-tests",
            "knowledge-" + Guid.NewGuid().ToString("N"));
        var config = new RevoConfig
        {
            EngineRoot = repoRoot,
            KnowledgeRoot = root,
            StartupTimeoutSeconds = 60,
            RequestTimeoutSeconds = 60,
        };

        string recordId;

        await using (var client = await PythonEngineClient.StartAsync(config))
        {
            Assert.Contains(EngineMethods.KnowledgeSearch, client.Handshake!.Capabilities);

            var source = await client.ImportKnowledgeTranscriptAsync(
                new KnowledgeTranscriptImportParams
                {
                    Title = "Residential scan to BIM",
                    Transcript =
                        "Set levels first. Create wall centrelines from detected wall planes, " +
                        "then check joins before creating floors.",
                    Url = "https://example.test/residential",
                    Creator = "Test creator",
                    License = "Test licence",
                });

            Assert.True(source.Created);
            Assert.True(source.ChunkCount > 0);

            var record = await client.AddKnowledgeTechniqueAsync(
                new KnowledgeTechniqueAddParams
                {
                    Subject = "Wall centrelines from planes",
                    Category = "walls",
                    Description = "Place native wall centrelines on detected wall planes.",
                    SourceType = "youtube",
                    SourceIds = [source.SourceId],
                    Procedure = ["Identify wall planes", "Create centreline", "Check joins"],
                    ApiOperations = ["Wall.Create"],
                    Confidence = 0.8,
                    Tags = ["wall", "scan-to-bim"],
                });

            recordId = record.Record.Id;
            Assert.Equal("pending_review", record.Record.Status);
            Assert.Single(record.Record.Provenance);

            var pending = await client.GetKnowledgeContextAsync(
                new KnowledgeContextParams { ElementKinds = ["wall"] });
            Assert.Empty(pending.Records);

            var approved = await client.ReviewKnowledgeAsync(
                new KnowledgeReviewParams
                {
                    RecordId = recordId,
                    Action = "approve",
                    Reviewer = "xunit",
                });
            Assert.Equal("approved", approved.Record.Status);

            var context = await client.GetKnowledgeContextAsync(
                new KnowledgeContextParams { ElementKinds = ["wall"] });
            Assert.Single(context.Records);
            Assert.Contains(recordId, context.Text);
            Assert.Equal(recordId, context.Citations[0].RecordId);

            var search = await client.SearchKnowledgeAsync(
                new KnowledgeSearchParams { Query = "wall centreline", Limit = 20 });
            Assert.Contains(search.Records, item => item.Id == recordId);
            Assert.True(search.Snippets.Count > 0);

            var stats = await client.GetKnowledgeStatsAsync();
            Assert.Equal(1, stats.Sources);
            Assert.True(stats.Records >= 1);
            Assert.Equal(1, stats.RecordsByStatus["approved"]);

            var backup = await client.BackupKnowledgeAsync(new KnowledgeBackupParams());
            Assert.True(File.Exists(backup.Path));
        }

        await using (var reopened = await PythonEngineClient.StartAsync(config))
        {
            var record = await reopened.GetKnowledgeRecordAsync(recordId);
            Assert.Equal("approved", record.Record.Status);

            var stats = await reopened.GetKnowledgeStatsAsync();
            Assert.True(stats.Records >= 1);
            Assert.Equal(1, stats.Sources);
        }
    }
}
