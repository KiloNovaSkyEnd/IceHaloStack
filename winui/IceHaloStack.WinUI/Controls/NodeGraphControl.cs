using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.Numerics;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using IceHaloStack_WinUI.ViewModels;

namespace IceHaloStack_WinUI.Controls;

public sealed class NodeGraphControl : Canvas
{
    public static readonly DependencyProperty NodesProperty = DependencyProperty.Register(
        nameof(Nodes), typeof(ObservableCollection<NodeWorkflowNode>), typeof(NodeGraphControl),
        new PropertyMetadata(null, OnNodesChanged));

    private readonly List<Line> _links = [];
    private FrameworkElement? _dragged;
    private NodeWorkflowNode? _draggedNode;
    private Vector2 _pointerOrigin;
    private Vector2 _nodeOrigin;

    public ObservableCollection<NodeWorkflowNode>? Nodes
    {
        get => (ObservableCollection<NodeWorkflowNode>?)GetValue(NodesProperty);
        set => SetValue(NodesProperty, value);
    }

    public NodeGraphControl()
    {
        Background = new SolidColorBrush(ColorHelper.FromArgb(255, 20, 24, 31));
        MinWidth = 820;
        MinHeight = 470;
    }

    private static void OnNodesChanged(DependencyObject sender, DependencyPropertyChangedEventArgs args)
    {
        var graph = (NodeGraphControl)sender;
        if (args.OldValue is INotifyCollectionChanged oldCollection)
            oldCollection.CollectionChanged -= graph.OnCollectionChanged;
        if (args.NewValue is INotifyCollectionChanged newCollection)
            newCollection.CollectionChanged += graph.OnCollectionChanged;
        graph.Rebuild();
    }

    private void OnCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e) => Rebuild();

    private void Rebuild()
    {
        Children.Clear();
        _links.Clear();
        if (Nodes is null)
            return;
        for (var index = 0; index < Nodes.Count - 1; index++)
        {
            var link = new Line { Stroke = new SolidColorBrush(Colors.DodgerBlue), StrokeThickness = 2 };
            _links.Add(link);
            Children.Add(link);
        }
        foreach (var node in Nodes)
        {
            var title = new TextBlock
            {
                Text = node.Title, TextAlignment = TextAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
            };
            var card = new Border
            {
                Width = 116, Height = 64, CornerRadius = new CornerRadius(5), Child = title,
                BorderThickness = new Thickness(1), DataContext = node,
            };
            ApplyNodeStyle(card, node.IsEnabled);
            node.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName == nameof(NodeWorkflowNode.IsEnabled)) ApplyNodeStyle(card, node.IsEnabled);
            };
            card.Translation = new Vector3((float)node.X, (float)node.Y, 0);
            card.PointerPressed += OnPointerPressed;
            card.PointerMoved += OnPointerMoved;
            card.PointerReleased += OnPointerReleased;
            Children.Add(card);
        }
        UpdateLinks();
    }

    private static void ApplyNodeStyle(Border card, bool enabled)
    {
        card.Background = new SolidColorBrush(enabled
            ? ColorHelper.FromArgb(255, 0, 120, 212) : ColorHelper.FromArgb(255, 58, 58, 58));
        card.BorderBrush = new SolidColorBrush(enabled ? Colors.LightSkyBlue : Colors.Gray);
        card.Opacity = enabled ? 1 : .72;
    }

    private void OnPointerPressed(object sender, PointerRoutedEventArgs e)
    {
        _dragged = (FrameworkElement)sender;
        _draggedNode = (NodeWorkflowNode)_dragged.DataContext;
        var point = e.GetCurrentPoint(this).Position;
        _pointerOrigin = new Vector2((float)point.X, (float)point.Y);
        _nodeOrigin = new Vector2((float)_draggedNode.X, (float)_draggedNode.Y);
        _dragged.CapturePointer(e.Pointer);
        e.Handled = true;
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_dragged is null || _draggedNode is null || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            return;
        var point = e.GetCurrentPoint(this).Position;
        var next = _nodeOrigin + new Vector2((float)point.X, (float)point.Y) - _pointerOrigin;
        _dragged.Translation = new Vector3(Math.Max(0, next.X), Math.Max(0, next.Y), 0);
        UpdateLinks();
        e.Handled = true;
    }

    private void OnPointerReleased(object sender, PointerRoutedEventArgs e)
    {
        if (_dragged is not null && _draggedNode is not null)
        {
            _draggedNode.X = _dragged.Translation.X;
            _draggedNode.Y = _dragged.Translation.Y;
            _dragged.ReleasePointerCapture(e.Pointer);
        }
        _dragged = null;
        _draggedNode = null;
        e.Handled = true;
    }

    private void UpdateLinks()
    {
        if (Nodes is null)
            return;
        for (var index = 0; index < _links.Count; index++)
        {
            var first = Nodes[index];
            var second = Nodes[index + 1];
            _links[index].X1 = first.X + 58; _links[index].Y1 = first.Y + 32;
            _links[index].X2 = second.X + 58; _links[index].Y2 = second.Y + 32;
            if (_draggedNode == first) { _links[index].X1 = _dragged!.Translation.X + 58; _links[index].Y1 = _dragged.Translation.Y + 32; }
            if (_draggedNode == second) { _links[index].X2 = _dragged!.Translation.X + 58; _links[index].Y2 = _dragged.Translation.Y + 32; }
        }
    }
}
