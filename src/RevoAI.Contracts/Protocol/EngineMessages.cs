namespace RevoAI.Contracts.Protocol;

/// <summary>Parameters for the <c>initialize</c> handshake.</summary>
public sealed class InitializeParams
{
    public required string ClientName { get; init; }

    public required string ClientVersion { get; init; }

    /// <summary>Protocol version the client speaks, for example <c>1.0</c>.</summary>
    public required string ProtocolVersion { get; init; }

    /// <summary>Optional directory where the engine should write its log file.</summary>
    public string? LogDirectory { get; init; }

    /// <summary>
    /// Optional local knowledge root. Null lets the engine use its own default.
    /// </summary>
    public string? KnowledgeRoot { get; init; }
}

/// <summary>Result of a successful <c>initialize</c> handshake.</summary>
public sealed class InitializeResult
{
    public required string ServerVersion { get; init; }

    public required string ProtocolVersion { get; init; }

    public required string PythonVersion { get; init; }

    public required string Platform { get; init; }

    /// <summary>Methods the engine currently implements. Honest capability reporting.</summary>
    public required IReadOnlyList<string> Capabilities { get; init; }
}

public sealed class PingParams
{
    public string? Message { get; init; }
}

public sealed class PingResult
{
    public required string Message { get; init; }

    public required DateTimeOffset ServerTimeUtc { get; init; }

    public required string EngineVersion { get; init; }

    public required string PythonVersion { get; init; }
}

public sealed class ShutdownResult
{
    public required bool Ok { get; init; }
}
