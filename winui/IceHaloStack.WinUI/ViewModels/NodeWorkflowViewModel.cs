using System.Collections.ObjectModel;
using System.Collections.Specialized;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using IceHaloStack.WinUI.Client;
using Microsoft.UI.Xaml.Media.Imaging;

namespace IceHaloStack_WinUI.ViewModels;

public sealed partial class NodeWorkflowViewModel : ObservableObject, IAsyncDisposable
{
    private IpcClient? _client;
    private IpcTaskViewModel? _task;
    private bool _disposed;
    private readonly List<string> _previewFiles = [];

    public NodeWorkflowViewModel()
    {
        Flows.CollectionChanged += OnFlowsChanged;
        Flows.Add(new NodeFlowViewModel("流程 1"));
        SelectedFlow = Flows[0];
        Queue.Inputs.CollectionChanged += OnQueueChanged;
        Queue.Groups.CollectionChanged += OnQueueChanged;
    }

    public StackPageViewModel Queue { get; } = new();
    public ObservableCollection<NodeFlowViewModel> Flows { get; } = [];
    public IReadOnlyList<string> StackMethods { get; } = ["mean", "maximum"];

    [ObservableProperty] private NodeFlowViewModel? _selectedFlow;
    [ObservableProperty] private string _outputDirectory = string.Empty;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private bool _canCancel;
    [ObservableProperty] private double _progressPercent;
    [ObservableProperty] private string _phase = "准备就绪";
    [ObservableProperty] private string _status = "添加图像并建立分组，然后配置一个或多个节点流程。";
    [ObservableProperty] private string _error = string.Empty;
    [ObservableProperty] private bool _hasError;
    [ObservableProperty] private BitmapImage? _previewSource;
    [ObservableProperty] private bool _deflickerEnabled;
    [ObservableProperty] private bool _exposureSmoothingEnabled;
    [ObservableProperty] private bool _whiteBalanceSmoothingEnabled;
    [ObservableProperty] private int _referenceGroupIndex;

    private Dictionary<string, object?> ToEwbConfig() => new()
    {
        ["deflicker_enabled"] = DeflickerEnabled,
        ["exposure_enabled"] = ExposureSmoothingEnabled,
        ["wb_enabled"] = WhiteBalanceSmoothingEnabled,
    };

    public bool CanEdit => !_disposed && !IsBusy;
    public bool CanNavigate => CanEdit;
    public bool CanStart => CanEdit && Queue.Inputs.Count > 0 && Queue.Groups.Count > 0
        && Flows.Any(flow => flow.IsEnabled && (flow.SaveSequence || flow.SaveVideo))
        && !string.IsNullOrWhiteSpace(OutputDirectory);

    partial void OnOutputDirectoryChanged(string value) => RefreshCommands();
    partial void OnIsBusyChanged(bool value) => RefreshCommands();
    partial void OnSelectedFlowChanged(NodeFlowViewModel? value) => RefreshCommands();

    [RelayCommand]
    private void AddFlow()
    {
        if (!CanEdit) return;
        var flow = new NodeFlowViewModel($"流程 {Flows.Count + 1}");
        Flows.Add(flow);
        SelectedFlow = flow;
        Status = "已添加原生节点流程。";
        RefreshCommands();
    }

    [RelayCommand]
    private void RemoveFlow()
    {
        if (!CanEdit || SelectedFlow is null || Flows.Count <= 1) return;
        var index = Flows.IndexOf(SelectedFlow);
        Flows.Remove(SelectedFlow);
        SelectedFlow = Flows[Math.Min(index, Flows.Count - 1)];
        Status = "已移除节点流程。";
        RefreshCommands();
    }

    [RelayCommand]
    private void DuplicateFlow()
    {
        if (!CanEdit || SelectedFlow is null) return;
        var copy = SelectedFlow.Clone($"{SelectedFlow.Name} 副本");
        Flows.Insert(Flows.IndexOf(SelectedFlow) + 1, copy);
        SelectedFlow = copy;
        Status = "已复制当前节点流程。";
        RefreshCommands();
    }

    private void OnQueueChanged(object? sender, NotifyCollectionChangedEventArgs e) => RefreshCommands();
    private void OnFlowsChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.OldItems is not null)
            foreach (NodeFlowViewModel flow in e.OldItems) flow.PropertyChanged -= OnFlowChanged;
        if (e.NewItems is not null)
            foreach (NodeFlowViewModel flow in e.NewItems) flow.PropertyChanged += OnFlowChanged;
        RefreshCommands();
    }

    private void OnFlowChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e) => RefreshCommands();

    private void RefreshCommands()
    {
        OnPropertyChanged(nameof(CanEdit));
        OnPropertyChanged(nameof(CanNavigate));
        OnPropertyChanged(nameof(CanStart));
        StartExportCommand.NotifyCanExecuteChanged();
        GeneratePreviewCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
    }

    private void ShowError(string message)
    {
        Error = message;
        HasError = !string.IsNullOrWhiteSpace(message);
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;
        Queue.Inputs.CollectionChanged -= OnQueueChanged;
        Queue.Groups.CollectionChanged -= OnQueueChanged;
        Flows.CollectionChanged -= OnFlowsChanged;
        foreach (var flow in Flows) flow.PropertyChanged -= OnFlowChanged;
        _task?.Dispose();
        if (_client is not null) await _client.DisposeAsync().ConfigureAwait(false);
        await Queue.DisposeAsync().ConfigureAwait(false);
        foreach (var file in _previewFiles) { try { File.Delete(file); } catch { } }
    }
}
