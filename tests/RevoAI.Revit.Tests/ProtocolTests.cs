using System.Text.Json;
using RevoAI.Contracts.Protocol;
using Xunit;

namespace RevoAI.Revit.Tests;

public sealed class ProtocolTests
{
    [Fact]
    public void CurrentVersionIsCompatibleWithItself()
    {
        Assert.True(ProtocolVersion.IsCompatible(ProtocolVersion.Current));
    }

    [Theory]
    [InlineData("1.0", true)]
    [InlineData("1.7", true)]
    [InlineData("2.0", false)]
    [InlineData("0.9", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    [InlineData("abc", false)]
    public void CompatibilityIsDecidedByMajorVersion(string? version, bool expected)
    {
        Assert.Equal(expected, ProtocolVersion.IsCompatible(version));
    }

    [Fact]
    public void InitializeRequestUsesCamelCaseWireNames()
    {
        var request = RpcRequest.Create(
            "req-1",
            EngineMethods.Initialize,
            new InitializeParams
            {
                ClientName = "RevoAI.Revit",
                ClientVersion = "0.1.0",
                ProtocolVersion = "1.0",
                LogDirectory = @"C:\logs",
            });

        using var document = JsonDocument.Parse(RevoAIJson.Serialize(request));
        var root = document.RootElement;

        Assert.Equal("2.0", root.GetProperty("jsonRpc").GetString());
        Assert.Equal("req-1", root.GetProperty("id").GetString());
        Assert.Equal("initialize", root.GetProperty("method").GetString());
        Assert.Equal("RevoAI.Revit", root.GetProperty("params").GetProperty("clientName").GetString());
        Assert.Equal("1.0", root.GetProperty("params").GetProperty("protocolVersion").GetString());
    }

    [Fact]
    public void ErrorResponseIsSurfacedAsTypedException()
    {
        const string json = """
            {"jsonRpc":"2.0","id":"7","error":{"code":-32011,"message":"not initialized","remedy":"call initialize"}}
            """;

        var response = RevoAIJson.Deserialize<RpcResponse>(json);

        Assert.False(response.IsSuccess);
        Assert.NotNull(response.Error);
        Assert.Equal(EngineErrorCodes.NotInitialized, response.Error!.Code);
        Assert.Equal("call initialize", response.Error.Remedy);

        var exception = Assert.Throws<RevoAIEngineException>(() => response.GetResult<PingResult>());
        Assert.Equal(EngineErrorCodes.NotInitialized, exception.Code);
    }

    [Fact]
    public void SuccessfulPingResultDeserializes()
    {
        const string json = """
            {"jsonRpc":"2.0","id":"1","result":{"message":"pong","serverTimeUtc":"2026-10-31T12:00:00.000Z","engineVersion":"0.1.0","pythonVersion":"3.14.7"}}
            """;

        var response = RevoAIJson.Deserialize<RpcResponse>(json);
        var result = response.GetResult<PingResult>();

        Assert.Equal("pong", result.Message);
        Assert.Equal("0.1.0", result.EngineVersion);
        Assert.Equal(2026, result.ServerTimeUtc.Year);
    }

    [Fact]
    public void UnknownJsonFieldsAreIgnoredForForwardCompatibility()
    {
        const string json = """
            {"jsonRpc":"2.0","id":"1","result":{"message":"pong","serverTimeUtc":"2026-10-31T12:00:00Z","engineVersion":"0.1.0","pythonVersion":"3.14.7","futureField":42}}
            """;

        var response = RevoAIJson.Deserialize<RpcResponse>(json);

        Assert.True(response.IsSuccess);
    }
}
