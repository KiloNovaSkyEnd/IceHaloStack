using System.Text.Json;

namespace IceHaloStack.WinUI.Client;

/// <summary>Local state tracked for one remote task.</summary>
public enum IpcTaskState
{
    Unknown,
    Starting,
    Started,
    Running,
    Paused,
    FinishingCurrent,
    Cancelling,
    Completed,
    Cancelled,
    Failed,
}

/// <summary>One response envelope from AsyncJsonLineHost.</summary>
public sealed record IpcResponse(
    string RequestId,
    bool Ok,
    JsonElement? Result,
    string? Error);

/// <summary>Progress payload emitted by a running task.</summary>
public sealed record IpcProgressEvent(
    string TaskId,
    string Phase,
    int Completed,
    int Total,
    double? Fraction,
    string Message,
    JsonElement? Metadata);

/// <summary>Terminal payload emitted when a task completes, fails, or is cancelled.</summary>
public sealed record IpcTaskResult(
    string TaskId,
    bool Ok,
    bool Cancelled,
    string? Error,
    JsonElement? Result)
{
    public IpcTaskState State => Ok
        ? IpcTaskState.Completed
        : Cancelled
            ? IpcTaskState.Cancelled
            : IpcTaskState.Failed;
}

/// <summary>Acknowledgement returned by a task cancellation request.</summary>
public sealed record IpcCancelAck(string TaskId, IpcTaskState State, string RawState);

public class IpcClientException : Exception
{
    public IpcClientException(string message) : base(message) { }
    public IpcClientException(string message, Exception inner) : base(message, inner) { }
}

public class IpcTransportException : IpcClientException
{
    public IpcTransportException(string message) : base(message) { }
    public IpcTransportException(string message, Exception inner) : base(message, inner) { }
}

public sealed class IpcProcessExitedException : IpcTransportException
{
    public IpcProcessExitedException(string message) : base(message) { }
}

public sealed class IpcTimeoutException : IpcTransportException
{
    public IpcTimeoutException(string message) : base(message) { }
}

public sealed class IpcRemoteException : IpcClientException
{
    public IpcRemoteException(string message, string requestId) : base(message)
    {
        RequestId = requestId;
    }

    public string RequestId { get; }
}

public sealed class IpcProtocolException : IpcClientException
{
    public IpcProtocolException(string message) : base(message) { }
    public IpcProtocolException(string message, Exception inner) : base(message, inner) { }
}
