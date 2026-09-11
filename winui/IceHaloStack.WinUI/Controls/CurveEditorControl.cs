using System.Collections.Specialized;
using System.ComponentModel;
using IceHaloStack_WinUI.ViewModels;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;

namespace IceHaloStack_WinUI.Controls;

/// <summary>Native multi-channel curve surface with direct point manipulation.</summary>
public sealed class CurveEditorControl : Canvas
{
    private readonly HashSet<CurvePointViewModel> _subscribedPoints = [];
    private CurvePointViewModel? _draggedPoint;

    public CurveEditorControl()
    {
        Background = new SolidColorBrush(Colors.Black);
        MinHeight = 220;
        SizeChanged += (_, _) => RenderCurve();
        PointerPressed += OnPointerPressed;
        PointerMoved += OnPointerMoved;
        PointerReleased += OnPointerReleased;
        PointerCanceled += OnPointerReleased;
    }

    public CurveEditorViewModel? ViewModel
    {
        get => (CurveEditorViewModel?)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty = DependencyProperty.Register(
        nameof(ViewModel), typeof(CurveEditorViewModel), typeof(CurveEditorControl),
        new PropertyMetadata(null, OnViewModelChanged));

    public void Refresh() => RenderCurve();

    private static void OnViewModelChanged(DependencyObject sender, DependencyPropertyChangedEventArgs args)
        => ((CurveEditorControl)sender).Attach(args.OldValue as CurveEditorViewModel, args.NewValue as CurveEditorViewModel);

    private void Attach(CurveEditorViewModel? oldValue, CurveEditorViewModel? newValue)
    {
        if (oldValue is not null)
        {
            oldValue.PropertyChanged -= OnEditorChanged;
            foreach (var channel in oldValue.Channels)
                channel.Points.CollectionChanged -= OnPointsChanged;
        }
        DetachPoints();
        if (newValue is not null)
        {
            newValue.PropertyChanged += OnEditorChanged;
            foreach (var channel in newValue.Channels)
                channel.Points.CollectionChanged += OnPointsChanged;
            AttachPoints(newValue.SelectedChannel);
        }
        RenderCurve();
    }

    private void OnEditorChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName == nameof(CurveEditorViewModel.SelectedChannel) && ViewModel is not null)
        {
            DetachPoints();
            AttachPoints(ViewModel.SelectedChannel);
        }
        RenderCurve();
    }

    private void OnPointsChanged(object? sender, NotifyCollectionChangedEventArgs args)
    {
        DetachPoints();
        if (ViewModel is not null)
            AttachPoints(ViewModel.SelectedChannel);
        RenderCurve();
    }

    private void AttachPoints(CurveChannelViewModel channel)
    {
        foreach (var point in channel.Points)
            if (_subscribedPoints.Add(point))
                point.PropertyChanged += OnPointChanged;
    }

    private void DetachPoints()
    {
        foreach (var point in _subscribedPoints)
            point.PropertyChanged -= OnPointChanged;
        _subscribedPoints.Clear();
    }

    private void OnPointChanged(object? sender, PropertyChangedEventArgs args) => RenderCurve();

    private void OnPointerPressed(object sender, PointerRoutedEventArgs args)
    {
        if (ViewModel is null || ActualWidth <= 0 || ActualHeight <= 0)
            return;
        var current = args.GetCurrentPoint(this);
        var nearest = FindNearest(current.Position, 12);
        if (current.Properties.IsRightButtonPressed)
        {
            if (nearest is not null && !IsEndpoint(nearest) && ViewModel.SelectedChannel.Points.Count > 2)
                ViewModel.SelectedChannel.Points.Remove(nearest);
            args.Handled = true;
            return;
        }
        _draggedPoint = nearest ?? AddPoint(current.Position);
        CapturePointer(args.Pointer);
        args.Handled = true;
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        if (_draggedPoint is null || ViewModel is null)
            return;
        var position = args.GetCurrentPoint(this).Position;
        var points = ViewModel.SelectedChannel.Points.OrderBy(point => point.Input).ToArray();
        var index = Array.IndexOf(points, _draggedPoint);
        var minimum = index <= 0 ? 0.0 : points[index - 1].Input + 0.002;
        var maximum = index >= points.Length - 1 ? 1.0 : points[index + 1].Input - 0.002;
        if (!IsEndpoint(_draggedPoint))
            _draggedPoint.Input = Math.Clamp(position.X / ActualWidth, minimum, maximum);
        _draggedPoint.Output = Math.Clamp(1.0 - position.Y / ActualHeight, 0.0, 1.0);
        args.Handled = true;
    }

    private void OnPointerReleased(object sender, PointerRoutedEventArgs args)
    {
        _draggedPoint = null;
        ReleasePointerCapture(args.Pointer);
    }

    private CurvePointViewModel AddPoint(Point position)
    {
        var point = new CurvePointViewModel(
            Math.Clamp(position.X / ActualWidth, 0.002, 0.998),
            Math.Clamp(1.0 - position.Y / ActualHeight, 0.0, 1.0));
        var collection = ViewModel!.SelectedChannel.Points;
        var index = collection.TakeWhile(existing => existing.Input < point.Input).Count();
        collection.Insert(index, point);
        return point;
    }

    private CurvePointViewModel? FindNearest(Point position, double radius)
        => ViewModel?.SelectedChannel.Points
            .Select(point => (Point: point, Distance: Math.Pow(point.Input * ActualWidth - position.X, 2)
                + Math.Pow((1 - point.Output) * ActualHeight - position.Y, 2)))
            .Where(item => item.Distance <= radius * radius)
            .OrderBy(item => item.Distance)
            .Select(item => item.Point)
            .FirstOrDefault();

    private static bool IsEndpoint(CurvePointViewModel point)
        => point.Input <= 0.0001 || point.Input >= 0.9999;

    private void RenderCurve()
    {
        Children.Clear();
        if (ActualWidth <= 0 || ActualHeight <= 0)
            return;
        DrawGrid();
        if (ViewModel is null)
            return;
        var stroke = ChannelBrush(ViewModel.SelectedChannel.Name);
        var polyline = new Polyline { Stroke = stroke, StrokeThickness = 2, IsHitTestVisible = false };
        foreach (var point in ViewModel.SelectedChannel.Points.OrderBy(point => point.Input))
            polyline.Points.Add(new Point(point.Input * ActualWidth, (1 - point.Output) * ActualHeight));
        Children.Add(polyline);
        foreach (var point in ViewModel.SelectedChannel.Points)
        {
            var marker = new Ellipse
            {
                Width = 10, Height = 10, Fill = new SolidColorBrush(Colors.Black), Stroke = stroke,
                StrokeThickness = 2, IsHitTestVisible = false,
            };
            SetLeft(marker, point.Input * ActualWidth - 5);
            SetTop(marker, (1 - point.Output) * ActualHeight - 5);
            Children.Add(marker);
        }
    }

    private void DrawGrid()
    {
        var gridBrush = new SolidColorBrush(ColorHelper.FromArgb(90, 150, 150, 150));
        for (var index = 1; index < 4; index++)
        {
            var x = ActualWidth * index / 4;
            var y = ActualHeight * index / 4;
            Children.Add(new Line { X1 = x, X2 = x, Y1 = 0, Y2 = ActualHeight, Stroke = gridBrush, IsHitTestVisible = false });
            Children.Add(new Line { X1 = 0, X2 = ActualWidth, Y1 = y, Y2 = y, Stroke = gridBrush, IsHitTestVisible = false });
        }
    }

    private static Brush ChannelBrush(string channel) => new SolidColorBrush(channel switch
    {
        "红色" => Colors.OrangeRed, "绿色" => Colors.LimeGreen, "蓝色" => Colors.DodgerBlue,
        "亮度" => Colors.Gold, _ => Colors.White,
    });
}
