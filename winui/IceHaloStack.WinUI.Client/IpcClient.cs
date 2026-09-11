using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace IceHaloStack.WinUI.Client;

/// <summary>
/// WinUI-facing transport for the Python AsyncJsonLineHost.
///
/// The class has no Microsoft.UI dependency, so it can be tested in a plain
/// .NET process and referenced by a WinUI 3 application. Events are raised by
/// the stdout reader thread; binders should marshal them to DispatcherQueue.
/// </summary>
public sealed class IpcClient : IAsyncDisposable
{
    private readonly string _executable;
    private readonly IReadOnlyList<string> _arguments;
    private readonly string? _workingDirectory;
    private readonly IDictionary<string, string>? _environment;
    private readonly TimeSpan _defaultTimeout;
    private readonly Process _process;
    private readonly SemaphoreSlim _writeGate = new(1, 1);
    private readonly CancellationTokenSource _lifetime = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource<IpcResponse>> _pending = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource<IpcTaskResult>> _taskWaiters = new();
    private readonly ConcurrentDictionary<string, IpcTaskResult> _taskResults = new();
    private readonly ConcurrentDictionary<string, IpcTaskState> _taskStates = new();
    private readonly ConcurrentQueue<string> _stderr = new();
    private readonly object _stateGate = new();
    private StreamWriter? _stdin;
    private Task? _stdoutLoop;
    private Task? _stderrLoop;
    private Exception? _terminalError;
    private bool _started;
    private bool _closing;
    private bool _closed;
    private int _requestNumber;
    private int _taskNumber;

    public IpcClient(
        string executable = "python",
        IEnumerable<string>? arguments = null,
        string? workingDirectory = null,
        IDictionary<string, string>? environment = null,
        TimeSpan? requestTimeout = null)
    {
        if (string.IsNullOrWhiteSpace(executable))
            throw new ArgumentException("IPC 可执行文件不能为空。", nameof(executable));

        var timeout = requestTimeout ?? TimeSpan.FromSeconds(30);
        if (timeout <= TimeSpan.Zero)
            throw new ArgumentOutOfRangeException(nameof(requestTimeout));

        _executable = executable;
        _arguments = (arguments ?? new[] { "-m", "ihs.services.ipc" }).ToArray();
        _workingDirectory = workingDirectory;
        _environment = environment;
        _defaultTimeout = timeout;
        _process = new Process
        {
            StartInfo = CreateStartInfo(),
            EnableRaisingEvents = true,
        };
    }

    public event Action<IpcProgressEvent>? ProgressReceived;
    public event Action<IpcTaskResult>? TaskCompleted;
    public event Action<Exception>? TransportError;
    public event Action<JsonElement>? UnmatchedMessageReceived;

    public bool IsStarted => _started;
    public bool IsAlive => _started && !_process.HasExited;
    public int? ExitCode => !_started || !_process.HasExited ? null : _process.ExitCode;
    public Exception? TerminalError => _terminalError;

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (_stateGate)
        {
            if (_closed)
                throw new IpcTransportException("IPC 客户端已经关闭。");
            if (_started)
            {
                if (_process.HasExited)
                    throw GetTerminalError();
                return;
            }

            try
            {
                if (!_process.Start())
                    throw new IpcTransportException("IPC 服务进程启动失败。");
            }
            catch (IpcTransportException)
            {
                throw;
            }
            catch (Exception ex)
            {
                throw new IpcTransportException($"无法启动 IPC 服务进程：{ex.Message}", ex);
            }

            _stdin = _process.StandardInput;
            _stdin.AutoFlush = true;
            _started = true;
            _stdoutLoop = ReadStdoutAsync(_process);
            _stderrLoop = ReadStderrAsync(_process);
        }

        await Task.CompletedTask;
    }

    public async Task<JsonElement?> RequestAsync(
        string method,
        object? parameters = null,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(method))
            throw new IpcProtocolException("IPC method 不能为空。");

        EnsureStarted();
        var requestId = $"winui-{Interlocked.Increment(ref _requestNumber)}";
        var waiter = new TaskCompletionSource<IpcResponse>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        if (!_pending.TryAdd(requestId, waiter))
            throw new IpcProtocolException($"IPC request_id 冲突：{requestId}。");

        try
        {
            var envelope = new Dictionary<string, object?>
            {
                ["id"] = requestId,
                ["method"] = method.Trim(),
                ["params"] = parameters ?? new Dictionary<string, object?>(),
            };
            await SendAsync(envelope, cancellationToken).ConfigureAwait(false);
            var response = await WaitResponseAsync(waiter.Task, requestId, method, timeout, cancellationToken)
                .ConfigureAwait(false);
            if (!response.Ok)
                throw new IpcRemoteException(response.Error ?? "远程服务调用失败。", requestId);
            return response.Result;
        }
        finally
        {
            _pending.TryRemove(requestId, out _);
        }
    }

    public Task<JsonElement?> PingAsync(
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
        => RequestAsync("ping", timeout: timeout, cancellationToken: cancellationToken);

    public async Task<string> StartTaskAsync(
        string operation,
        object? parameters = null,
        string? taskId = null,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(operation))
            throw new IpcProtocolException("任务 operation 不能为空。");

        taskId = string.IsNullOrWhiteSpace(taskId)
            ? $"task-{Interlocked.Increment(ref _taskNumber)}"
            : taskId.Trim();
        if (!_taskWaiters.TryAdd(
                taskId,
                new TaskCompletionSource<IpcTaskResult>(TaskCreationOptions.RunContinuationsAsynchronously)))
        {
            throw new IpcProtocolException($"task_id 已在本客户端运行：{taskId}。");
        }
        // No waiter means the previous task (if any) has reached a terminal
        // result, so reusing its id starts a fresh state sequence.
        _taskStates[taskId] = IpcTaskState.Starting;
        _taskResults.TryRemove(taskId, out _);

        try
        {
            var result = await RequestAsync(
                "start",
                new Dictionary<string, object?>
                {
                    ["task_id"] = taskId,
                    ["operation"] = operation.Trim(),
                    ["params"] = parameters ?? new Dictionary<string, object?>(),
                },
                timeout,
                cancellationToken).ConfigureAwait(false);

            if (result is null || !result.Value.TryGetProperty("task_id", out var responseTaskId)
                || !string.Equals(responseTaskId.GetString(), taskId, StringComparison.Ordinal))
                throw new IpcProtocolException("start 响应中的 task_id 不匹配。");

            var acknowledgedState = ParseTaskState(
                result.Value.TryGetProperty("state", out var state) ? state.GetString() : "started");
            UpdateTaskState(taskId, acknowledgedState);
            return taskId;
        }
        catch
        {
            _taskStates.TryRemove(taskId, out _);
            _taskWaiters.TryRemove(taskId, out _);
            throw;
        }
    }

    public async Task<IpcCancelAck> CancelTaskAsync(
        string taskId,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(taskId))
            throw new IpcProtocolException("task_id 不能为空。");
        taskId = taskId.Trim();
        return await ControlTaskAsync("cancel", taskId, timeout, cancellationToken).ConfigureAwait(false);
    }

    public Task<IpcCancelAck> PauseTaskAsync(string taskId, TimeSpan? timeout = null, CancellationToken cancellationToken = default)
        => ControlTaskAsync("pause", taskId, timeout, cancellationToken);

    public Task<IpcCancelAck> ResumeTaskAsync(string taskId, TimeSpan? timeout = null, CancellationToken cancellationToken = default)
        => ControlTaskAsync("resume", taskId, timeout, cancellationToken);

    public Task<IpcCancelAck> UseCurrentTaskAsync(string taskId, TimeSpan? timeout = null, CancellationToken cancellationToken = default)
        => ControlTaskAsync("use_current", taskId, timeout, cancellationToken);

    private async Task<IpcCancelAck> ControlTaskAsync(string method, string taskId, TimeSpan? timeout, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(taskId)) throw new IpcProtocolException("task_id 不能为空。");
        taskId = taskId.Trim();
        var result = await RequestAsync(
            method,
            new Dictionary<string, object?> { ["task_id"] = taskId },
            timeout,
            cancellationToken).ConfigureAwait(false);
        if (result is null)
            throw new IpcProtocolException($"{method} 响应为空。");

        var responseTaskId = GetRequiredString(result.Value, "task_id");
        if (!string.Equals(responseTaskId, taskId, StringComparison.Ordinal))
            throw new IpcProtocolException($"{method} 响应中的 task_id 不匹配。");
        var rawState = result.Value.TryGetProperty("state", out var state)
            ? state.GetString() ?? "cancelling"
            : "cancelling";
        var parsed = ParseTaskState(rawState);
        UpdateTaskState(taskId, parsed);
        return new IpcCancelAck(taskId, parsed, rawState);
    }

    public async Task<IpcTaskResult> WaitForTaskAsync(
        string taskId,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(taskId))
            throw new IpcProtocolException("task_id 不能为空。");
        taskId = taskId.Trim();
        if (_taskResults.TryGetValue(taskId, out var cached))
            return cached;
        if (!_taskWaiters.TryGetValue(taskId, out var waiter))
            throw new IpcProtocolException($"不存在的 task_id：{taskId}。");

        var effective = timeout ?? _defaultTimeout;
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, _lifetime.Token);
        linked.CancelAfter(effective);
        try
        {
            return await waiter.Task.WaitAsync(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            throw new IpcTransportException("IPC 客户端已关闭。");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new IpcTimeoutException($"任务超时：task_id={taskId}。");
        }
    }

    public IpcTaskState GetTaskState(string taskId)
        => _taskStates.TryGetValue(taskId.Trim(), out var state) ? state : IpcTaskState.Unknown;

    public bool TryGetTaskResult(string taskId, out IpcTaskResult result)
    {
        if (string.IsNullOrWhiteSpace(taskId))
        {
            result = default!;
            return false;
        }
        if (_taskResults.TryGetValue(taskId.Trim(), out var cached))
        {
            result = cached;
            return true;
        }
        result = default!;
        return false;
    }

    public string GetStderrTail(int maxCharacters = 4000)
    {
        var text = string.Concat(_stderr);
        return text.Length <= maxCharacters ? text : text[^maxCharacters..];
    }

    public async ValueTask DisposeAsync()
    {
        await CloseAsync().ConfigureAwait(false);
        GC.SuppressFinalize(this);
    }

    public async Task CloseAsync(TimeSpan? timeout = null)
    {
        lock (_stateGate)
        {
            if (_closed)
                return;
            _closing = true;
            _closed = true;
        }

        _lifetime.Cancel();
        var closeError = new IpcTransportException("IPC 客户端已关闭。");
        foreach (var pending in _pending.Values)
            pending.TrySetException(closeError);
        foreach (var waiter in _taskWaiters.Values)
            waiter.TrySetException(closeError);

        if (_started)
        {
            try { _stdin?.Close(); } catch (IOException) { }
            var wait = timeout ?? TimeSpan.FromSeconds(2);
            try
            {
                await _process.WaitForExitAsync().WaitAsync(wait).ConfigureAwait(false);
            }
            catch (TimeoutException)
            {
                try
                {
                    if (!_process.HasExited)
                        _process.Kill(entireProcessTree: true);
                }
                catch (InvalidOperationException) { }
                catch (NotSupportedException) { }
                try { await _process.WaitForExitAsync().ConfigureAwait(false); }
                catch (InvalidOperationException) { }
            }

            foreach (var loop in new[] { _stdoutLoop, _stderrLoop })
            {
                if (loop is null)
                    continue;
                try { await loop.WaitAsync(TimeSpan.FromSeconds(1)).ConfigureAwait(false); }
                catch (TimeoutException) { }
                catch (Exception) { }
            }
            _process.Dispose();
        }
        _writeGate.Dispose();
        _lifetime.Dispose();
    }

    private ProcessStartInfo CreateStartInfo()
    {
        var info = new ProcessStartInfo
        {
            FileName = _executable,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = _workingDirectory ?? string.Empty,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var argument in _arguments)
            info.ArgumentList.Add(argument);
        if (_environment is not null)
        {
            foreach (var pair in _environment)
                info.Environment[pair.Key] = pair.Value;
        }
        return info;
    }

    private void EnsureStarted()
    {
        lock (_stateGate)
        {
            if (_closed)
                throw new IpcTransportException("IPC 客户端已经关闭。");
            if (!_started)
                throw new IpcTransportException("请先调用 StartAsync() 启动 IPC 服务。");
            if (_process.HasExited)
                throw GetTerminalError();
            if (_terminalError is not null)
                throw _terminalError;
        }
    }

    private IpcTransportException GetTerminalError()
        => _terminalError as IpcTransportException
            ?? new IpcProcessExitedException($"IPC 服务进程已退出（code={_process.ExitCode}）。");

    private async Task SendAsync(
        IReadOnlyDictionary<string, object?> payload,
        CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(payload);
        await _writeGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_stdin is null)
                throw new IpcTransportException("IPC stdin 不可用。");
            await _stdin.WriteLineAsync(json).WaitAsync(cancellationToken).ConfigureAwait(false);
            await _stdin.FlushAsync().WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is IOException or ObjectDisposedException or InvalidOperationException)
        {
            var error = new IpcTransportException($"写入 IPC 请求失败：{ex.Message}", ex);
            SetTerminalError(error);
            throw error;
        }
        finally
        {
            _writeGate.Release();
        }
    }

    private async Task<IpcResponse> WaitResponseAsync(
        Task<IpcResponse> task,
        string requestId,
        string method,
        TimeSpan? timeout,
        CancellationToken cancellationToken)
    {
        var effective = timeout ?? _defaultTimeout;
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, _lifetime.Token);
        linked.CancelAfter(effective);
        try
        {
            return await task.WaitAsync(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            throw new IpcTransportException("IPC 客户端已关闭。");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new IpcTimeoutException(
                $"IPC 请求超时：method={method}，id={requestId}。");
        }
    }

    private async Task ReadStdoutAsync(Process process)
    {
        try
        {
            while (true)
            {
                var line = await process.StandardOutput.ReadLineAsync()
                    .WaitAsync(_lifetime.Token).ConfigureAwait(false);
                if (line is null)
                    break;
                if (!string.IsNullOrWhiteSpace(line))
                    HandleLine(line);
            }
        }
        catch (OperationCanceledException) when (_closing || _lifetime.IsCancellationRequested) { }
        catch (Exception ex)
        {
            SetTerminalError(ex is IpcClientException
                ? ex
                : new IpcProtocolException($"读取 IPC 输出失败：{ex.Message}", ex));
        }
        finally
        {
            if (!_closing && !_lifetime.IsCancellationRequested && _terminalError is null)
                SetTerminalError(new IpcProcessExitedException(
                    $"IPC 服务进程已退出（code={process.HasExited switch { true => process.ExitCode, _ => -1 }}）。"));
        }
    }

    private async Task ReadStderrAsync(Process process)
    {
        try
        {
            while (true)
            {
                var line = await process.StandardError.ReadLineAsync()
                    .WaitAsync(_lifetime.Token).ConfigureAwait(false);
                if (line is null)
                    break;
                _stderr.Enqueue(line + Environment.NewLine);
                while (_stderr.Count > 80)
                    _stderr.TryDequeue(out _);
            }
        }
        catch (OperationCanceledException) when (_closing || _lifetime.IsCancellationRequested) { }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
    }

    private void HandleLine(string line)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(line);
        }
        catch (JsonException ex)
        {
            throw new IpcProtocolException($"IPC 返回无效 JSON：{ex.Message}", ex);
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                throw new IpcProtocolException("IPC 返回必须是 JSON 对象。");

            var type = root.TryGetProperty("type", out var typeElement)
                ? typeElement.GetString()
                : null;
            if (type == "progress" && root.TryGetProperty("task_id", out _))
            {
                HandleProgress(root);
                return;
            }
            if (type == "result" && root.TryGetProperty("task_id", out _))
            {
                HandleResult(root);
                return;
            }

            if (root.TryGetProperty("id", out var idElement))
            {
                var requestId = ReadId(idElement);
                if (_pending.TryRemove(requestId, out var waiter))
                    waiter.TrySetResult(ParseResponse(root, requestId));
                else
                    InvokeSafe(UnmatchedMessageReceived, root.Clone());
                return;
            }

            InvokeSafe(UnmatchedMessageReceived, root.Clone());
        }
    }

    private void HandleProgress(JsonElement root)
    {
        var taskId = GetRequiredString(root, "task_id");
        if (!root.TryGetProperty("event", out var data)
            || data.ValueKind != JsonValueKind.Object)
            throw new IpcProtocolException("progress 缺少 event 对象。");
        var phase = data.TryGetProperty("phase", out var phaseElement)
            ? phaseElement.GetString() ?? string.Empty
            : string.Empty;
        var completed = ReadInt(data, "completed");
        var total = ReadInt(data, "total");
        double? fraction = null;
        if (data.TryGetProperty("fraction", out var fractionElement)
            && fractionElement.ValueKind == JsonValueKind.Number
            && fractionElement.TryGetDouble(out var fractionValue))
            fraction = fractionValue;
        var message = data.TryGetProperty("message", out var messageElement)
            ? messageElement.GetString() ?? string.Empty
            : string.Empty;
        var metadata = data.TryGetProperty("metadata", out var metadataElement)
            ? metadataElement.Clone()
            : (JsonElement?)null;
        var progress = new IpcProgressEvent(
            taskId, phase, completed, total, fraction, message, metadata);
        UpdateTaskState(taskId, IpcTaskState.Running);
        InvokeSafe(ProgressReceived, progress);
    }

    private void HandleResult(JsonElement root)
    {
        var taskId = GetRequiredString(root, "task_id");
        var ok = ReadRequiredBool(root, "ok");
        var cancelled = root.TryGetProperty("cancelled", out var cancelledElement)
            && cancelledElement.ValueKind == JsonValueKind.True;
        var error = root.TryGetProperty("error", out var errorElement)
            ? errorElement.GetString()
            : null;
        var result = root.TryGetProperty("result", out var resultElement)
            ? resultElement.Clone()
            : (JsonElement?)null;
        var terminal = new IpcTaskResult(taskId, ok, cancelled, error, result);
        _taskResults[taskId] = terminal;
        UpdateTaskState(taskId, terminal.State);
        // A terminal result is cached above, so the waiter no longer needs to
        // remain in the dictionary. Removing it also permits a later task to
        // reuse the same task_id without inheriting a completed TCS.
        if (_taskWaiters.TryRemove(taskId, out var waiter))
            waiter.TrySetResult(terminal);
        InvokeSafe(TaskCompleted, terminal);
    }

    private static IpcResponse ParseResponse(JsonElement root, string requestId)
    {
        var ok = ReadRequiredBool(root, "ok");
        var result = root.TryGetProperty("result", out var resultElement)
            ? resultElement.Clone()
            : (JsonElement?)null;
        var error = root.TryGetProperty("error", out var errorElement)
            ? errorElement.GetString()
            : null;
        return new IpcResponse(requestId, ok, result, error);
    }

    private void SetTerminalError(Exception exception)
    {
        var error = exception as IpcTransportException
            ?? new IpcTransportException(exception.Message, exception);
        lock (_stateGate)
        {
            if (_terminalError is not null)
                return;
            _terminalError = error;
        }
        foreach (var pending in _pending.Values)
            pending.TrySetException(error);
        foreach (var waiter in _taskWaiters.Values)
            waiter.TrySetException(error);
        InvokeSafe(TransportError, error);
    }

    private static string ReadId(JsonElement element)
        => element.ValueKind switch
        {
            JsonValueKind.String => element.GetString() ?? string.Empty,
            JsonValueKind.Number => element.GetRawText(),
            _ => throw new IpcProtocolException("IPC 响应 id 必须是字符串或数字。"),
        };

    private static string GetRequiredString(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var element)
            || element.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(element.GetString()))
            throw new IpcProtocolException($"IPC 消息缺少字符串字段：{name}。");
        return element.GetString()!;
    }

    private static bool ReadRequiredBool(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var element)
            || (element.ValueKind != JsonValueKind.True && element.ValueKind != JsonValueKind.False))
            throw new IpcProtocolException($"IPC 消息缺少布尔字段：{name}。");
        return element.GetBoolean();
    }

    private static int ReadInt(JsonElement root, string name)
        => root.TryGetProperty(name, out var element)
            && element.ValueKind == JsonValueKind.Number
            && element.TryGetInt32(out var value)
                ? value
                : 0;

    private static IpcTaskState ParseTaskState(string? state)
        => state?.Trim().ToLowerInvariant() switch
        {
            "starting" => IpcTaskState.Starting,
            "started" => IpcTaskState.Started,
            "running" => IpcTaskState.Running,
            "paused" => IpcTaskState.Paused,
            "finishing-current" => IpcTaskState.FinishingCurrent,
            "cancelling" => IpcTaskState.Cancelling,
            "completed" => IpcTaskState.Completed,
            "cancelled" => IpcTaskState.Cancelled,
            "failed" => IpcTaskState.Failed,
            _ => IpcTaskState.Unknown,
        };

    private void UpdateTaskState(string taskId, IpcTaskState incoming)
    {
        _taskStates.AddOrUpdate(
            taskId,
            incoming,
            (_, current) => ShouldAdvance(current, incoming));
    }

    private static IpcTaskState ShouldAdvance(IpcTaskState current, IpcTaskState incoming)
    {
        if (current == IpcTaskState.Unknown)
            return incoming;
        if (IsTerminal(current))
            return current;
        if (IsTerminal(incoming))
            return incoming;
        if (current == IpcTaskState.Cancelling
            && incoming is IpcTaskState.Starting or IpcTaskState.Started or IpcTaskState.Running)
            return current;
        if (current == IpcTaskState.Running
            && incoming is IpcTaskState.Starting or IpcTaskState.Started)
            return current;
        if (current == IpcTaskState.Started && incoming == IpcTaskState.Starting)
            return current;
        return incoming;
    }

    private static bool IsTerminal(IpcTaskState state)
        => state is IpcTaskState.Completed or IpcTaskState.Cancelled or IpcTaskState.Failed;

    private static void InvokeSafe<T>(Action<T>? handler, T value)
    {
        try { handler?.Invoke(value); }
        catch { /* UI observers must not kill the stdout reader. */ }
    }
}
