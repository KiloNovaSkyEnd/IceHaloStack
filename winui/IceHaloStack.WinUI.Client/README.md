# IceHaloStack WinUI 3 IPC client layer

This small `net8.0` class library is the WinUI-facing side of the local
`ihs.services.ipc.AsyncJsonLineHost` protocol. It has no `Microsoft.UI`
dependency, so it can be referenced by a WinUI 3 app while remaining easy to
unit-test. The Python service is started with `python -m ihs.services.ipc` by
default; pass the packaged executable and arguments to `IpcClient` for a
release build.

## Start a task

```csharp
var client = new IpcClient(
    executable: "python",
    arguments: new[] { "-m", "ihs.services.ipc" },
    workingDirectory: projectRoot);

await client.StartAsync();
await client.PingAsync();

var taskId = await client.StartTaskAsync(
    "process_file",
    new Dictionary<string, object?>
    {
        ["input_path"] = inputPath,
        ["output_path"] = outputPath,
        ["config"] = new Dictionary<string, object?> { ["stretch"] = true },
    },
    taskId: "task-42");

var result = await client.WaitForTaskAsync(taskId);
await client.CloseAsync();
```

If the page needs every early progress event, construct `IpcTaskViewModel`
with the explicit `taskId` before calling `StartTaskAsync`, or call the
view-model's `StartAsync` method directly after wiring the dispatcher.

`CancelTaskAsync(taskId)` only waits for the cancellation acknowledgement.
The terminal result arrives asynchronously and has `Cancelled == true`.
`ProgressReceived` and `TaskCompleted` are raised from the transport reader
thread, so WinUI code must marshal property updates to `DispatcherQueue`.

Add this project as a normal project reference from the WinUI application:

```xml
<ProjectReference Include="..\IceHaloStack.WinUI.Client\IceHaloStack.WinUI.Client.csproj" />
```

## Bind progress to XAML

`IpcTaskViewModel` implements `INotifyPropertyChanged` and exposes
`Phase`, `Message`, `Completed`, `Total`, `ProgressPercent`, `StateLabel`,
`IsBusy`, `CanCancel`, `Error`, and `Result`.

```csharp
var dispatcher = new Func<Action, Task>(action =>
{
    var completion = new TaskCompletionSource(
        TaskCreationOptions.RunContinuationsAsynchronously);
    if (!DispatcherQueue.TryEnqueue(() =>
    {
        try { action(); completion.SetResult(); }
        catch (Exception error) { completion.SetException(error); }
    }))
        completion.SetException(new InvalidOperationException("UI dispatcher is closed."));
    return completion.Task;
});

TaskProgress = new IpcTaskViewModel(client, taskId, dispatcher);
```

```xml
<StackPanel Spacing="8">
  <TextBlock Text="{x:Bind TaskProgress.Phase, Mode=OneWay}" />
  <TextBlock Text="{x:Bind TaskProgress.Message, Mode=OneWay}" />
  <ProgressBar Minimum="0" Maximum="100"
               Value="{x:Bind TaskProgress.ProgressPercent, Mode=OneWay}" />
  <Button Content="Cancel"
          IsEnabled="{x:Bind TaskProgress.CanCancel, Mode=OneWay}"
          Click="Cancel_Click" />
</StackPanel>
```

Keep the client alive for the lifetime of the page/workspace and call
`CloseAsync` during window shutdown. Do not call blocking `.Result` or
`.Wait()` from the WinUI UI thread.
