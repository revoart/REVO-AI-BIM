using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using RevoAI.Contracts.Protocol;
using RevoAI.Revit.Configuration;

namespace RevoAI.Revit.Engine;

/// <summary>
/// Owns the local Python engine process and speaks newline-delimited JSON-RPC
/// 2.0 with it over stdin/stdout. All calls are serialized: the engine is
/// single-threaded by design, which keeps the protocol simple and deterministic.
/// </summary>
public sealed class PythonEngineClient : IAsyncDisposable
{
    private const string ModuleName = "revoai_engine.service";
    private const string ClientName = "RevoAI.Revit";

    private readonly Process _process;
    private readonly StreamWriter _stdin;
    private readonly StreamReader _stdout;
    private readonly StringBuilder _stderr = new();
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly TimeSpan _requestTimeout;

    private int _nextRequestId;
    private bool _disposed;
    private bool _disposeStarted;

    private PythonEngineClient(Process process, TimeSpan requestTimeout)
    {
        _process = process;
        _requestTimeout = requestTimeout;
        _stdin = process.StandardInput;
        _stdout = process.StandardOutput;
    }

    public InitializeResult? Handshake { get; private set; }

    public bool IsRunning => !_disposed && !_process.HasExited;

    public static async Task<PythonEngineClient> StartAsync(
        RevoConfig config,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);

        var plan = config.CreateLaunchPlan();
        var startInfo = CreateStartInfo(plan);

        var process = new Process
        {
            StartInfo = startInfo,
            EnableRaisingEvents = true,
        };

        try
        {
            if (!process.Start())
            {
                throw new InvalidOperationException("The Python engine process did not start.");
            }
        }
        catch (Exception ex)
        {
            process.Dispose();
            throw new InvalidOperationException(
                $"Could not start the Python engine using '{plan.Executable}'. " +
                $"Verify the interpreter and that '{plan.EngineRoot}\\.venv' exists. {ex.Message}", ex);
        }

        var client = new PythonEngineClient(
            process,
            TimeSpan.FromSeconds(config.RequestTimeoutSeconds));

        client.PumpStandardError();

        try
        {
            client.Handshake = await client.InitializeAsync(
                TimeSpan.FromSeconds(config.StartupTimeoutSeconds),
                cancellationToken);

            return client;
        }
        catch
        {
            await client.DisposeAsync();
            throw;
        }
    }

    public Task<InitializeResult> InitializeAsync(
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        InitializeCoreAsync(timeout ?? _requestTimeout, cancellationToken);

    public async Task<PingResult> PingAsync(
        string? message = null,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var request = RpcRequest.Create(
            NextId(),
            EngineMethods.Ping,
            new PingParams { Message = message });

        var response = await SendAsync(request, timeout ?? _requestTimeout, cancellationToken);
        return response.GetResult<PingResult>();
    }

    /// <summary>
    /// Imports a point cloud into a local chunked store. Imports can take
    /// minutes for large scans, so the default timeout is deliberately longer
    /// than the normal request timeout.
    /// </summary>
    public Task<PointCloudImportResult> ImportPointCloudAsync(
        PointCloudImportParams parameters,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<PointCloudImportResult>(
            EngineMethods.PointCloudImport,
            parameters,
            timeout ?? TimeSpan.FromMinutes(30),
            cancellationToken);

    public Task<PointCloudInfoResult> GetPointCloudInfoAsync(
        string storePath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<PointCloudInfoResult>(
            EngineMethods.PointCloudInfo,
            new PointCloudInfoParams { StorePath = storePath },
            timeout ?? _requestTimeout,
            cancellationToken);

    public Task<PointCloudQueryResult> QueryPointCloudAsync(
        PointCloudQueryParams parameters,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<PointCloudQueryResult>(
            EngineMethods.PointCloudQuery,
            parameters,
            timeout ?? _requestTimeout,
            cancellationToken);

    /// <summary>
    /// Runs the geometric segmentation baseline. Analysis can take minutes on
    /// large scans, so it uses the same long timeout as import.
    /// </summary>
    public Task<SegmentationResult> RunSegmentationAsync(
        SegmentationRunParams parameters,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<SegmentationResult>(
            EngineMethods.SegmentationRun,
            parameters,
            timeout ?? TimeSpan.FromMinutes(30),
            cancellationToken);

    public Task<SegmentationResult> GetSegmentationInfoAsync(
        string storePath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<SegmentationResult>(
            EngineMethods.SegmentationInfo,
            new SegmentationInfoParams { StorePath = storePath },
            timeout ?? _requestTimeout,
            cancellationToken);

    public Task<ReconstructionPlanResult> CreateReconstructionPlanAsync(
        ReconstructionPlanParams parameters,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default) =>
        CallAsync<ReconstructionPlanResult>(
            EngineMethods.ReconstructionPlan,
            parameters,
            timeout ?? TimeSpan.FromMinutes(5),
            cancellationToken);

    public async Task<ShutdownResult> ShutdownAsync(CancellationToken cancellationToken = default)
    {
        if (_disposed || _process.HasExited)
        {
            return new ShutdownResult { Ok = true };
        }

        try
        {
            var request = RpcRequest.Create(NextId(), EngineMethods.Shutdown);
            var response = await SendAsync(request, TimeSpan.FromSeconds(5), cancellationToken);
            return response.GetResult<ShutdownResult>();
        }
        catch (Exception ex) when (ex is RevoAIEngineException or TimeoutException or IOException or ObjectDisposedException)
        {
            RevoLog.Warn($"Engine shutdown request failed: {ex.Message}");
            return new ShutdownResult { Ok = false };
        }
    }

    /// <summary>
    /// Sends an arbitrary protocol request. Used by future capabilities and by
    /// tests that need to assert engine-side error behaviour.
    /// </summary>
    public async Task<JsonElement?> CallAsync(
        string method,
        object? parameters = null,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var request = parameters is null
            ? RpcRequest.Create(NextId(), method)
            : RpcRequest.Create(NextId(), method, parameters);

        var response = await SendAsync(request, timeout ?? _requestTimeout, cancellationToken);
        return response.Result;
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposeStarted)
        {
            return;
        }

        _disposeStarted = true;

        try
        {
            if (!_process.HasExited)
            {
                await ShutdownAsync(CancellationToken.None);
            }

            using var waitCts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            try
            {
                await _process.WaitForExitAsync(waitCts.Token);
            }
            catch (OperationCanceledException)
            {
                // Fall through to a hard kill.
            }

            if (!_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        catch (Exception ex)
        {
            RevoLog.Warn($"Error while stopping the Python engine: {ex.Message}");
        }
        finally
        {
            _disposed = true;
            _stdin.Dispose();
            _stdout.Dispose();
            _process.Dispose();
            _gate.Dispose();
        }
    }

    private async Task<T> CallAsync<T>(
        string method,
        object parameters,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var request = RpcRequest.Create(NextId(), method, parameters);
        var response = await SendAsync(request, timeout, cancellationToken);
        return response.GetResult<T>();
    }

    private async Task<InitializeResult> InitializeCoreAsync(
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var request = RpcRequest.Create(
            NextId(),
            EngineMethods.Initialize,
            new InitializeParams
            {
                ClientName = ClientName,
                ClientVersion = BuildInfo.Version,
                ProtocolVersion = ProtocolVersion.Current,
                LogDirectory = RevoLog.Directory,
            });

        var response = await SendAsync(request, timeout, cancellationToken);
        var result = response.GetResult<InitializeResult>();

        if (!ProtocolVersion.IsCompatible(result.ProtocolVersion))
        {
            throw new RevoAIEngineException(new RpcError
            {
                Code = EngineErrorCodes.ProtocolVersionMismatch,
                Message =
                    $"Engine protocol {result.ProtocolVersion} is incompatible with add-in protocol {ProtocolVersion.Current}.",
                Remedy = "Install matching Revo AI BIM add-in and engine versions.",
            });
        }

        return result;
    }

    private async Task<RpcResponse> SendAsync(
        RpcRequest request,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);

        try
        {
            EnsureRunning();

            var payload = RevoAIJson.Serialize(request);
            RevoLog.Debug($"-> {payload}");

            await _stdin.WriteLineAsync(payload.AsMemory(), cancellationToken);
            await _stdin.FlushAsync(cancellationToken);

            using var timeoutCts = new CancellationTokenSource(timeout);
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(
                cancellationToken,
                timeoutCts.Token);

            while (true)
            {
                string? line;

                try
                {
                    line = await _stdout.ReadLineAsync(linked.Token);
                }
                catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
                {
                    throw new TimeoutException(
                        $"The engine did not answer '{request.Method}' within {timeout.TotalSeconds:0.#} s.");
                }

                if (line is null)
                {
                    throw EngineUnavailable(
                        $"The engine exited while waiting for '{request.Method}'.");
                }

                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                RevoLog.Debug($"<- {line}");

                RpcResponse? response;
                try
                {
                    response = RevoAIJson.Deserialize<RpcResponse>(line);
                }
                catch (JsonException ex)
                {
                    RevoLog.Warn($"Ignoring non-JSON engine output: {ex.Message}");
                    continue;
                }

                if (response.Id is null)
                {
                    // Notification (for example a future progress event). Not used yet.
                    RevoLog.Debug($"Engine notification: {line}");
                    continue;
                }

                if (!string.Equals(response.Id, request.Id, StringComparison.Ordinal))
                {
                    RevoLog.Warn(
                        $"Ignoring response for unexpected request id '{response.Id}' (expected '{request.Id}').");
                    continue;
                }

                if (!response.IsSuccess)
                {
                    throw new RevoAIEngineException(response.Error!);
                }

                return response;
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    private void EnsureRunning()
    {
        if (_process.HasExited)
        {
            throw EngineUnavailable(
                $"The engine process exited with code {_process.ExitCode}.");
        }
    }

    private RevoAIEngineException EngineUnavailable(string message)
    {
        var stderr = StandardErrorTail();
        return new RevoAIEngineException(new RpcError
        {
            Code = EngineErrorCodes.EngineUnavailable,
            Message = stderr.Length == 0 ? message : $"{message} Engine stderr: {stderr}",
            Remedy = "Check the Revo AI BIM log and verify the Python environment.",
        });
    }

    private string StandardErrorTail()
    {
        lock (_stderr)
        {
            var text = _stderr.ToString().Trim();
            return text.Length <= 2000 ? text : text[^2000..];
        }
    }

    private void PumpStandardError()
    {
        _ = Task.Run(async () =>
        {
            try
            {
                while (await _process.StandardError.ReadLineAsync() is { } line)
                {
                    lock (_stderr)
                    {
                        _stderr.AppendLine(line);
                    }

                    RevoLog.Debug($"engine: {line}");
                }
            }
            catch (Exception ex) when (ex is IOException or ObjectDisposedException or InvalidOperationException)
            {
                // Process exited; nothing left to drain.
            }
        });
    }

    private string NextId() =>
        Interlocked.Increment(ref _nextRequestId).ToString(System.Globalization.CultureInfo.InvariantCulture);

    private static ProcessStartInfo CreateStartInfo(EngineLaunchPlan plan)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = plan.Executable,
            WorkingDirectory = plan.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            StandardInputEncoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
        };

        foreach (var argument in plan.Arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        startInfo.ArgumentList.Add("-m");
        startInfo.ArgumentList.Add(ModuleName);

        var pythonPath = string.Join(
            Path.PathSeparator,
            Path.Combine(plan.EngineRoot, "src", "RevoAI.Engine"),
            Path.Combine(plan.EngineRoot, "src", "RevoAI.Geometry"));

        startInfo.Environment["PYTHONPATH"] = pythonPath;
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
        startInfo.Environment["PYTHONUNBUFFERED"] = "1";
        startInfo.Environment["REVOAI_PROTOCOL_VERSION"] = ProtocolVersion.Current;

        return startInfo;
    }
}
