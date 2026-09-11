using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class StackPageViewModel
{
    [ObservableProperty] private bool _isPaused;

    public bool CanPause => _task is { IsBusy: true } && _task.State != IceHaloStack.WinUI.Client.IpcTaskState.FinishingCurrent;
    public bool CanUseCurrent => _task is { IsBusy: true } && _task.State != IceHaloStack.WinUI.Client.IpcTaskState.FinishingCurrent && ProgressPercent > 0;
    public string PauseLabel => IsPaused ? "继续" : "暂停";

    [RelayCommand(CanExecute = nameof(CanPause))]
    private async Task TogglePauseAsync()
    {
        if (_task is null) return;
        try
        {
            var pause = !IsPaused;
            await _task.SetPausedAsync(pause).ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                IsPaused = pause;
                Phase = pause ? "已暂停" : "处理";
                Status = pause ? "堆栈已在安全帧边界暂停。" : "堆栈已继续。";
                RefreshControlCommands();
            }).ConfigureAwait(false);
        }
        catch (Exception exception) { await DispatchToUiAsync(() => ShowError(exception.Message)).ConfigureAwait(false); }
    }

    [RelayCommand(CanExecute = nameof(CanUseCurrent))]
    private async Task UseCurrentAsync()
    {
        if (_task is null) return;
        try
        {
            await _task.UseCurrentAsync().ConfigureAwait(false);
            await DispatchToUiAsync(() =>
            {
                IsPaused = false; Phase = "收尾";
                Status = "正在使用已累积的帧生成当前 Master…";
                RefreshControlCommands();
            }).ConfigureAwait(false);
        }
        catch (Exception exception) { await DispatchToUiAsync(() => ShowError(exception.Message)).ConfigureAwait(false); }
    }

    partial void OnIsPausedChanged(bool value) => OnPropertyChanged(nameof(PauseLabel));

    private void RefreshControlCommands()
    {
        OnPropertyChanged(nameof(CanPause)); OnPropertyChanged(nameof(CanUseCurrent));
        TogglePauseCommand.NotifyCanExecuteChanged(); UseCurrentCommand.NotifyCanExecuteChanged();
    }
}
