using System.ComponentModel;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace IceHaloStack_WinUI.Controls;

/// <summary>Lightweight native trend plot; redraws only when table or selection changes.</summary>
public sealed class EwbTrendChartControl : Canvas
{
    private EwbWorkspaceViewModel? _viewModel;

    public EwbTrendChartControl()
    {
        MinHeight = 110;
        Background = new SolidColorBrush(ColorHelper.FromArgb(255, 20, 20, 20));
        DataContextChanged += (_, args) => Attach(args.NewValue as EwbWorkspaceViewModel);
        Loaded += (_, _) => Attach(DataContext as EwbWorkspaceViewModel);
        SizeChanged += (_, _) => Redraw();
        Unloaded += (_, _) => Attach(null);
    }

    private void Attach(EwbWorkspaceViewModel? value)
    {
        if (_viewModel is not null) _viewModel.PropertyChanged -= ViewModel_PropertyChanged;
        _viewModel = value;
        if (_viewModel is not null) _viewModel.PropertyChanged += ViewModel_PropertyChanged;
        Redraw();
    }

    private void ViewModel_PropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(EwbWorkspaceViewModel.ExposureMetricSeries)
            or nameof(EwbWorkspaceViewModel.TemperatureMetricSeries)
            or nameof(EwbWorkspaceViewModel.TintMetricSeries)
            or nameof(EwbWorkspaceViewModel.SelectedFrame)) Redraw();
    }

    private void Redraw()
    {
        Children.Clear();
        if (_viewModel is null || ActualWidth < 30 || ActualHeight < 30) return;
        var panels = new[]
        {
            ("曝光 EV", _viewModel.ExposureMetricSeries, _viewModel.ExposureSmoothSeries, _viewModel.ExposureTargetSeries, Colors.CornflowerBlue),
            ("白平衡 冷↔暖", _viewModel.TemperatureMetricSeries, _viewModel.TemperatureSmoothSeries, _viewModel.TemperatureTargetSeries, Colors.Orange),
            ("白平衡 绿↔洋红", _viewModel.TintMetricSeries, _viewModel.TintSmoothSeries, _viewModel.TintTargetSeries, Colors.MediumOrchid),
        };
        var count = panels.Max(panel => panel.Item2.Count);
        if (count < 2) return;
        const double left = 92; const double right = 8;
        var panelHeight = ActualHeight / panels.Length;
        for (var panelIndex = 0; panelIndex < panels.Length; panelIndex++)
        {
            var (label, raw, smooth, target, targetColor) = panels[panelIndex];
            var values = raw.Concat(smooth).Concat(target).Where(double.IsFinite).ToArray();
            if (values.Length == 0) continue;
            var min = values.Min(); var max = values.Max();
            if (Math.Abs(max - min) < 1e-9) { min -= 0.5; max += 0.5; }
            var top = panelIndex * panelHeight + 5; var bottom = (panelIndex + 1) * panelHeight - 5;
            var caption = new TextBlock { Text = label, Foreground = new SolidColorBrush(Colors.Gainsboro), FontSize = 11 };
            SetLeft(caption, 5); SetTop(caption, top); Children.Add(caption);
            Children.Add(new Line { X1 = left, X2 = ActualWidth - right, Y1 = bottom, Y2 = bottom,
                Stroke = new SolidColorBrush(ColorHelper.FromArgb(70, 255, 255, 255)), StrokeThickness = 1 });
            AddSeries(raw, count, min, max, Colors.Gray, left, right, top, bottom, null);
            AddSeries(smooth, count, min, max, Colors.DeepSkyBlue, left, right, top, bottom, [4, 2]);
            AddSeries(target, count, min, max, targetColor, left, right, top, bottom, null, 2);
        }
        if (_viewModel.SelectedFrame is { } selected)
        {
            var x = left + selected.Index * (ActualWidth - left - right) / Math.Max(1, count - 1);
            Children.Add(new Line { X1 = x, X2 = x, Y1 = 3, Y2 = ActualHeight - 3,
                Stroke = new SolidColorBrush(Colors.White), StrokeThickness = 1 });
        }
    }

    private void AddSeries(IReadOnlyList<double> series, int count, double min, double max, Windows.UI.Color color,
        double left, double right, double top, double bottom, DoubleCollection? dash, double thickness = 1)
    {
        if (series.Count < 2) return;
        var points = new PointCollection();
        for (var i = 0; i < series.Count; i++)
        {
            var x = left + i * (ActualWidth - left - right) / Math.Max(1, count - 1);
            var y = bottom - (series[i] - min) * (bottom - top) / (max - min);
            points.Add(new Windows.Foundation.Point(x, y));
        }
        Children.Add(new Polyline { Points = points, Stroke = new SolidColorBrush(color), StrokeThickness = thickness, StrokeDashArray = dash });
    }
}
