using System.Text.Json;

namespace RevoAI.Contracts.Protocol;

public sealed class KnowledgeSourceListParams
{
    public string? Kind { get; init; }

    public int Limit { get; init; } = 100;
}

public sealed class KnowledgeSourceInfo
{
    public required string Id { get; init; }

    public required string Kind { get; init; }

    public required string Title { get; init; }

    public string? Url { get; init; }

    public string? Creator { get; init; }

    public string? License { get; init; }

    public string? RetrievedAt { get; init; }
}

public sealed class KnowledgeSourceListResult
{
    public required IReadOnlyList<KnowledgeSourceInfo> Sources { get; init; }
}

public sealed class KnowledgeTranscriptImportParams
{
    public required string Title { get; init; }

    public required string Transcript { get; init; }

    public string? Url { get; init; }

    public string? Creator { get; init; }

    public string? License { get; init; }

    public string? PublishedAt { get; init; }

    public string? ExternalId { get; init; }

    public IReadOnlyList<string> Screenshots { get; init; } = [];
}

public sealed class KnowledgeDocumentImportParams
{
    public required string Path { get; init; }

    public string? Title { get; init; }

    public string Kind { get; init; } = "local_file";

    public string? Url { get; init; }

    public string? Creator { get; init; }

    public string? License { get; init; }

    public string? RevitVersion { get; init; }

    public string? ExternalId { get; init; }
}

public sealed class KnowledgeImportResult
{
    public required string SourceId { get; init; }

    public required string DocumentId { get; init; }

    public string RecordId { get; init; } = string.Empty;

    public required string Title { get; init; }

    public required string Kind { get; init; }

    public required bool Created { get; init; }

    public required int ChunkCount { get; init; }

    public required string Message { get; init; }
}

public sealed class KnowledgeTechniqueAddParams
{
    public required string Subject { get; init; }

    public required string Category { get; init; }

    public required string Description { get; init; }

    public string Body { get; init; } = string.Empty;

    public string SourceType { get; init; } = "manual";

    public string? RevitVersion { get; init; }

    public IReadOnlyList<string> Conditions { get; init; } = [];

    public IReadOnlyList<string> Procedure { get; init; } = [];

    public IReadOnlyList<string> ApiOperations { get; init; } = [];

    public IReadOnlyList<string> Constraints { get; init; } = [];

    public IReadOnlyList<string> Limitations { get; init; } = [];

    public double Confidence { get; init; }

    public IReadOnlyList<string> Tags { get; init; } = [];

    public IReadOnlyList<string> SourceIds { get; init; } = [];

    public string Status { get; init; } = "pending_review";
}

public sealed class KnowledgeTechniqueAddResult
{
    public required KnowledgeRecordDetail Record { get; init; }
}

public sealed class KnowledgeProvenance
{
    public required string SourceId { get; init; }

    public required string Kind { get; init; }

    public required string Title { get; init; }

    public string? Url { get; init; }

    public string? Creator { get; init; }

    public string? License { get; init; }

    public string? PublishedAt { get; init; }

    public string? Locator { get; init; }
}

public sealed class KnowledgeReviewEntry
{
    public required string Action { get; init; }

    public string? StatusFrom { get; init; }

    public required string StatusTo { get; init; }

    public string? Reviewer { get; init; }

    public string? Note { get; init; }

    public required string CreatedAt { get; init; }
}

public sealed class KnowledgeRecordSummary
{
    public required string Id { get; init; }

    public required string Subject { get; init; }

    public required string Category { get; init; }

    public required string Description { get; init; }

    public required string Status { get; init; }

    public required string SourceType { get; init; }

    public string? RevitVersion { get; init; }

    public required double Confidence { get; init; }

    public required IReadOnlyList<string> Verification { get; init; }

    public required IReadOnlyList<string> Tags { get; init; }

    public required int Version { get; init; }

    public required string UpdatedAt { get; init; }

    public required IReadOnlyList<KnowledgeProvenance> Provenance { get; init; }
}

public sealed class KnowledgeRecordDetail
{
    public required string Id { get; init; }

    public required string Subject { get; init; }

    public required string Category { get; init; }

    public required string Description { get; init; }

    public required string Body { get; init; }

    public required string SourceType { get; init; }

    public string? RevitVersion { get; init; }

    public required IReadOnlyList<string> Conditions { get; init; }

    public required IReadOnlyList<string> Procedure { get; init; }

    public required IReadOnlyList<string> ApiOperations { get; init; }

    public required IReadOnlyList<string> Constraints { get; init; }

    public required IReadOnlyList<string> Limitations { get; init; }

    public required double Confidence { get; init; }

    public required string Status { get; init; }

    public required IReadOnlyList<string> Verification { get; init; }

    public required IReadOnlyList<string> Tags { get; init; }

    public required int Version { get; init; }

    public string? SupersedesId { get; init; }

    public required string CreatedAt { get; init; }

    public required string UpdatedAt { get; init; }

    public string? ApprovedAt { get; init; }

    public string? ApprovedBy { get; init; }

    public required IReadOnlyList<KnowledgeProvenance> Provenance { get; init; }

    public required IReadOnlyList<KnowledgeReviewEntry> Reviews { get; init; }
}

public sealed class KnowledgeSearchParams
{
    public string Query { get; init; } = string.Empty;

    public IReadOnlyList<string>? Statuses { get; init; }

    public IReadOnlyList<string>? SourceTypes { get; init; }

    public string? RevitVersion { get; init; }

    public int Limit { get; init; } = 20;

    public int Offset { get; init; }
}

public sealed class KnowledgeSnippet
{
    public required string ChunkId { get; init; }

    public required string DocumentId { get; init; }

    public required string Title { get; init; }

    public required string Kind { get; init; }

    public string? Url { get; init; }

    public required string SourceId { get; init; }

    public required string Snippet { get; init; }
}

public sealed class KnowledgeSearchResult
{
    public required string Query { get; init; }

    public required IReadOnlyList<KnowledgeRecordSummary> Records { get; init; }

    public required IReadOnlyList<KnowledgeSnippet> Snippets { get; init; }

    public required int Total { get; init; }
}

public sealed class KnowledgeGetParams
{
    public required string RecordId { get; init; }
}

public sealed class KnowledgeGetResult
{
    public required KnowledgeRecordDetail Record { get; init; }
}

public sealed class KnowledgeReviewParams
{
    public required string RecordId { get; init; }

    public required string Action { get; init; }

    public string? Reviewer { get; init; }

    public string? Note { get; init; }
}

public sealed class KnowledgeReviewResult
{
    public required KnowledgeRecordDetail Record { get; init; }
}

public sealed class KnowledgeUpdateParams
{
    public required string RecordId { get; init; }

    public string? Subject { get; init; }

    public string? Category { get; init; }

    public string? Description { get; init; }

    public string? Body { get; init; }

    public IReadOnlyList<string>? Procedure { get; init; }

    public IReadOnlyList<string>? ApiOperations { get; init; }

    public IReadOnlyList<string>? Constraints { get; init; }

    public IReadOnlyList<string>? Limitations { get; init; }

    public IReadOnlyList<string>? Tags { get; init; }

    public string? Reviewer { get; init; }
}

public sealed class KnowledgeUpdateResult
{
    public required KnowledgeRecordDetail Record { get; init; }
}

public sealed class KnowledgeDeleteParams
{
    public required string RecordId { get; init; }

    public string? Reviewer { get; init; }

    public string? Note { get; init; }
}

public sealed class KnowledgeDeleteResult
{
    public required bool Deleted { get; init; }

    public required string RecordId { get; init; }
}

public sealed class KnowledgeStatsResult
{
    public required string Root { get; init; }

    public required string DatabasePath { get; init; }

    public required long DatabaseBytes { get; init; }

    public required int Sources { get; init; }

    public required int Documents { get; init; }

    public required int Chunks { get; init; }

    public required int Records { get; init; }

    public required IReadOnlyDictionary<string, int> RecordsByStatus { get; init; }

    public required int Projects { get; init; }

    public required int ProjectElements { get; init; }

    public required int Decisions { get; init; }

    public required int Benchmarks { get; init; }

    public required int SchemaVersion { get; init; }
}

public sealed class KnowledgeContextParams
{
    public string Query { get; init; } = string.Empty;

    public IReadOnlyList<string> ElementKinds { get; init; } = [];

    public string? RevitVersion { get; init; }

    public int Limit { get; init; } = 8;
}

public sealed class KnowledgeCitation
{
    public required string RecordId { get; init; }

    public required string Subject { get; init; }

    public required string Status { get; init; }

    public required IReadOnlyList<string> Sources { get; init; }
}

public sealed class KnowledgeContextResult
{
    public required string Query { get; init; }

    public required IReadOnlyList<KnowledgeRecordSummary> Records { get; init; }

    public required IReadOnlyList<KnowledgeCitation> Citations { get; init; }

    public required string Text { get; init; }

    public required string Note { get; init; }
}

public sealed class KnowledgeProjectImportParams
{
    public string? Path { get; init; }

    public JsonElement? Extraction { get; init; }
}

public sealed class KnowledgeProjectImportResult
{
    public required string ProjectId { get; init; }

    public required string SourceId { get; init; }

    public required bool Created { get; init; }

    public required int ElementCount { get; init; }

    public required IReadOnlyList<string> Warnings { get; init; }

    public required string Message { get; init; }
}

public sealed class KnowledgeBackupParams
{
    public string? Destination { get; init; }
}

public sealed class KnowledgeBackupResult
{
    public required string Path { get; init; }

    public required string Sha256 { get; init; }

    public required long Bytes { get; init; }

    public required string CreatedAt { get; init; }
}

public sealed class KnowledgeExportParams
{
    public string? Destination { get; init; }
}

public sealed class KnowledgeExportResult
{
    public required string Path { get; init; }

    public required long Bytes { get; init; }

    public required string CreatedAt { get; init; }
}

public sealed class KnowledgeDecisionAddParams
{
    public required string Task { get; init; }

    public string? Model { get; init; }

    public IReadOnlyList<string> RetrievedIds { get; init; } = [];

    public JsonElement? Plan { get; init; }

    public string Outcome { get; init; } = "recorded";
}

public sealed class KnowledgeDecisionAddResult
{
    public required string Id { get; init; }

    public required string CreatedAt { get; init; }
}

public sealed class KnowledgeBenchmarkAddParams
{
    public string? ProjectId { get; init; }

    public required string Method { get; init; }

    public JsonElement? Metrics { get; init; }
}

public sealed class KnowledgeBenchmarkAddResult
{
    public required string Id { get; init; }

    public required string CreatedAt { get; init; }
}
