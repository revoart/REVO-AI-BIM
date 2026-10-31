using System.Collections.Concurrent;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.RevitApi;

/// <summary>
/// Marshals work from the modeless WPF window onto Revit's main thread through
/// <see cref="ExternalEvent"/>. No Revit API object is touched on the UI thread.
/// </summary>
public sealed class RevitTaskRunner : IExternalEventHandler
{
    private readonly ConcurrentQueue<Action<UIApplication>> _queue = new();
    private readonly ExternalEvent _externalEvent;

    public RevitTaskRunner()
    {
        _externalEvent = ExternalEvent.Create(this);
    }

    public Task<T> InvokeAsync<T>(Func<UIApplication, T> action)
    {
        ArgumentNullException.ThrowIfNull(action);

        var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);

        _queue.Enqueue(app =>
        {
            try
            {
                completion.TrySetResult(action(app));
            }
            catch (Exception ex)
            {
                completion.TrySetException(ex);
            }
        });

        _externalEvent.Raise();
        return completion.Task;
    }

    public Task InvokeAsync(Action<UIApplication> action) =>
        InvokeAsync(app =>
        {
            action(app);
            return true;
        });

    public void Execute(UIApplication app)
    {
        while (_queue.TryDequeue(out var work))
        {
            work(app);
        }
    }

    public string GetName() => "Revo AI BIM";
}
