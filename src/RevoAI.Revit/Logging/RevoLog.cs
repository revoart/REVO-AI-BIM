using System.IO;
using System.Text;
using System.Text.Json;

namespace RevoAI.Revit;

/// <summary>
/// Minimal, dependency-free structured logger. Writes JSON Lines to
/// <c>%LOCALAPPDATA%\RevoAI\logs</c> by default so the add-in does not need to
/// ship a third-party logging framework into Revit's AppDomain.
/// </summary>
public static class RevoLog
{
    private static readonly object Gate = new();
    private static StreamWriter? _writer;
    private static string? _filePath;

    public static string Directory { get; private set; } = DefaultDirectory;

    public static string? CurrentLogFilePath
    {
        get { lock (Gate) { return _filePath; } }
    }

    public static string DefaultDirectory =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "RevoAI",
            "logs");

    public static void Initialize(string? directory = null)
    {
        lock (Gate)
        {
            if (_writer is not null)
            {
                return;
            }

            Directory = string.IsNullOrWhiteSpace(directory) ? DefaultDirectory : directory;
            System.IO.Directory.CreateDirectory(Directory);

            _filePath = Path.Combine(Directory, $"revoai-{DateTime.UtcNow:yyyyMMdd}.log");
            _writer = new StreamWriter(
                new FileStream(_filePath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite),
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: false))
            {
                AutoFlush = true,
            };
        }
    }

    public static void Debug(string message) => Write("DEBUG", message, null);

    public static void Info(string message) => Write("INFO", message, null);

    public static void Warn(string message) => Write("WARN", message, null);

    public static void Error(string message, Exception? exception = null) => Write("ERROR", message, exception);

    public static void Shutdown()
    {
        lock (Gate)
        {
            _writer?.Dispose();
            _writer = null;
        }
    }

    private static void Write(string level, string message, Exception? exception)
    {
        try
        {
            Initialize();

            var record = new
            {
                ts = DateTimeOffset.UtcNow,
                level,
                message,
                exception = exception?.ToString(),
            };

            var line = JsonSerializer.Serialize(record);

            lock (Gate)
            {
                _writer?.WriteLine(line);
            }
        }
        catch
        {
            // Logging must never take down Revit or the engine client.
        }
    }
}
