using System.Text.Json;

namespace RevoAI.Contracts.Protocol;

/// <summary>
/// Version of the C#/Python engine protocol. The major component must match
/// between the add-in and the engine; minor versions are backward compatible.
/// </summary>
public static class ProtocolVersion
{
    public const string Current = "1.0";

    /// <summary>
    /// Returns true when <paramref name="version"/> has the same major version
    /// as <see cref="Current"/>.
    /// </summary>
    public static bool IsCompatible(string? version)
    {
        if (string.IsNullOrWhiteSpace(version))
        {
            return false;
        }

        var parts = version.Split('.', StringSplitOptions.TrimEntries);
        if (parts.Length == 0 || !int.TryParse(parts[0], out var major))
        {
            return false;
        }

        return major == Major;
    }

    public static int Major => int.Parse(Current.Split('.')[0], System.Globalization.CultureInfo.InvariantCulture);
}

/// <summary>JSON-RPC method names implemented by the engine.</summary>
public static class EngineMethods
{
    public const string Initialize = "initialize";
    public const string Ping = "ping";
    public const string Shutdown = "shutdown";
    public const string PointCloudImport = "pointcloud.import";
    public const string PointCloudInfo = "pointcloud.info";
    public const string PointCloudQuery = "pointcloud.query";
}

/// <summary>
/// Error codes used by the engine. The -326xx range follows JSON-RPC 2.0;
/// -320xx values are Revo AI BIM specific.
/// </summary>
public static class EngineErrorCodes
{
    public const int ParseError = -32700;
    public const int InvalidRequest = -32600;
    public const int MethodNotFound = -32601;
    public const int InvalidParams = -32602;
    public const int InternalError = -32603;

    public const int ProtocolVersionMismatch = -32010;
    public const int NotInitialized = -32011;
    public const int EngineUnavailable = -32012;
    public const int OperationCancelled = -32013;

    public const int FileNotFound = -32020;
    public const int UnsupportedFormat = -32021;
    public const int InvalidPointCloud = -32022;
    public const int ProcessingFailed = -32023;
    public const int StoreNotFound = -32024;
    public const int InvalidUnit = -32025;
}

/// <summary>Base shape of a JSON-RPC 2.0 request.</summary>
public sealed class RpcRequest
{
    public string JsonRpc { get; init; } = "2.0";

    public required string Id { get; init; }

    public required string Method { get; init; }

    public JsonElement? Params { get; init; }

    public static RpcRequest Create<T>(string id, string method, T parameters)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(id);
        ArgumentException.ThrowIfNullOrWhiteSpace(method);

        return new RpcRequest
        {
            Id = id,
            Method = method,
            Params = JsonSerializer.SerializeToElement(parameters, RevoAIJson.Options),
        };
    }

    public static RpcRequest Create(string id, string method)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(id);
        ArgumentException.ThrowIfNullOrWhiteSpace(method);

        return new RpcRequest { Id = id, Method = method };
    }
}

/// <summary>Base shape of a JSON-RPC 2.0 response.</summary>
public sealed class RpcResponse
{
    public string JsonRpc { get; init; } = "2.0";

    public string? Id { get; init; }

    public JsonElement? Result { get; init; }

    public RpcError? Error { get; init; }

    public bool IsSuccess => Error is null;

    public T GetResult<T>()
    {
        if (Error is not null)
        {
            throw new RevoAIEngineException(Error);
        }

        if (Result is null)
        {
            throw new RevoAIEngineException(new RpcError
            {
                Code = EngineErrorCodes.InternalError,
                Message = "Engine returned an empty result.",
            });
        }

        return Result.Value.Deserialize<T>(RevoAIJson.Options)
            ?? throw new RevoAIEngineException(new RpcError
            {
                Code = EngineErrorCodes.InternalError,
                Message = $"Engine result could not be read as {typeof(T).Name}.",
            });
    }
}

public sealed class RpcError
{
    public required int Code { get; init; }

    public required string Message { get; init; }

    public string? Data { get; init; }

    /// <summary>Human-readable remediation hint, when the engine can suggest one.</summary>
    public string? Remedy { get; init; }
}

/// <summary>Raised when the engine returns a JSON-RPC error.</summary>
public sealed class RevoAIEngineException : Exception
{
    public RevoAIEngineException(RpcError error)
        : base(error.Message)
    {
        Error = error;
    }

    public RevoAIEngineException(RpcError error, Exception innerException)
        : base(error.Message, innerException)
    {
        Error = error;
    }

    public RpcError Error { get; }

    public int Code => Error.Code;
}
