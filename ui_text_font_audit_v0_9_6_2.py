"""Runtime audit for English UI coverage and regular typography."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("icehalostack_audit", HERE / "icehalostack.py")
ihs = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(ihs)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def menu_texts(menu, prefix):
    out = []
    end = menu.index("end")
    if end is None:
        return out
    for index in range(int(end) + 1):
        try:
            kind = menu.type(index)
            if kind == "separator":
                continue
            label = menu.entrycget(index, "label")
            out.append((f"{prefix}.menu[{index}]", label))
            if kind == "cascade":
                submenu = menu.nametowidget(menu.entrycget(index, "menu"))
                out.extend(menu_texts(submenu, f"{prefix}.menu[{index}]"))
        except tk.TclError:
            pass
    return out


def visible_texts(root):
    out = []
    for widget in walk(root):
        path = str(widget)
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            out.append((path + ".title", widget.title()))
        try:
            text = widget.cget("text")
            if text:
                out.append((path + ".text", str(text)))
        except (tk.TclError, AttributeError):
            pass
        if isinstance(widget, (tk.Label, ttk.Label)):
            try:
                var_name = str(widget.cget("textvariable") or "")
                if var_name:
                    out.append((path + ".textvariable", str(widget.getvar(var_name))))
            except (tk.TclError, AttributeError):
                pass
        if isinstance(widget, tk.Listbox):
            for index in range(widget.size()):
                out.append((f"{path}.list[{index}]", widget.get(index)))
        if isinstance(widget, ttk.Combobox):
            out.append((path + ".current", widget.get()))
            for index, value in enumerate(widget.cget("values")):
                out.append((f"{path}.values[{index}]", str(value)))
        if isinstance(widget, ttk.Notebook):
            for tab in widget.tabs():
                out.append((f"{path}.tab[{tab}]", widget.tab(tab, "text")))
        if isinstance(widget, ttk.Treeview):
            for col in ("#0",) + tuple(widget.cget("columns")):
                out.append((f"{path}.heading[{col}]", widget.heading(col, "text")))
        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                if widget.type(item) == "text":
                    out.append((f"{path}.canvas[{item}]", widget.itemcget(item, "text")))
        if isinstance(widget, tk.Menu):
            out.extend(menu_texts(widget, path))
    return out


def actual_font(widget):
    spec_value = ""
    try:
        spec_value = widget.cget("font")
    except (tk.TclError, AttributeError):
        pass
    if not spec_value and isinstance(widget, ttk.Widget):
        style = ttk.Style(widget)
        style_name = str(widget.cget("style") or widget.winfo_class())
        spec_value = style.lookup(style_name, "font")
    if not spec_value:
        return None
    return tkfont.Font(root=widget, font=spec_value).actual()


def main():
    removed_key = "segoe" + "_variable"
    assert tuple(ihs.FONT_CHOICES) == ("dengxian", "yahei_ui", "system")
    assert removed_key not in ihs.FONT_CHOICES
    assert not ihs._font_candidates(removed_key)

    original_settings_path = ihs._settings_file_path
    with tempfile.TemporaryDirectory() as temp_dir:
        settings_path = pathlib.Path(temp_dir) / "settings.json"
        settings_path.write_text(json.dumps({"ui_font": removed_key}), encoding="utf-8")
        ihs._settings_file_path = lambda: settings_path
        assert ihs._load_ui_font_preference() == "system"
    ihs._settings_file_path = original_settings_path

    ihs._save_ui_setting = lambda *_args, **_kwargs: True
    ihs.App.detect_acceleration = lambda _self: None
    ihs.App._draw_curve_editor = lambda _self: None
    app = ihs.App()
    app.withdraw()
    node = ihs.TimelapseNodeWindow(app)
    node.withdraw()
    node.flows.append(node._new_flow("流程 2 副本"))
    node._refresh_flow_list()
    ihs._show_timelapse_details(node, show_dag=True)
    details = node._timelapse_details_window
    details.withdraw()
    ihs._apply_ui_language(app, "en")
    applied, _family = ihs._apply_ui_font_preference(app, "yahei_ui")
    assert applied
    app.update_idletasks()

    mode_combo = next(
        widget for widget in walk(node)
        if isinstance(widget, ttk.Combobox)
        and getattr(widget, "_ihs_i18n_combobox", {}).get("source") is not None
        and str(getattr(widget, "_ihs_i18n_combobox")["source"]) == str(node.mode)
    )
    assert node.mode.get() == "滑动窗口（推荐：观察变化）"
    assert mode_combo.get() == "Rolling Window (Recommended: Observe Changes)"
    mode_combo._ihs_i18n_combobox["proxy"].set("Centered Window (Centered on Time)")
    assert node.mode.get() == "中心窗口（按中央时刻理解）"
    node.mode.set("滑动窗口（推荐：观察变化）")
    assert tuple(node.flow_list.get(0, "end"))[-1].endswith("Flow 2 Copy")

    ihs._apply_ui_language(app, "zh_CN")
    app.update_idletasks()
    assert mode_combo.get() == "滑动窗口（推荐：观察变化）"
    assert tuple(node.flow_list.get(0, "end"))[-1].endswith("流程 2 副本")
    ihs._apply_ui_language(app, "en")
    app.update_idletasks()

    roots = [app]
    texts = []
    for root in roots:
        texts.extend(visible_texts(root))
    cjk = [(path, text) for path, text in texts if re.search(r"[\u3400-\u9fff]", text)]

    non_regular = []
    for root in roots:
        for widget in walk(root):
            try:
                font = actual_font(widget)
                if font and font.get("weight") != "normal":
                    non_regular.append((str(widget), font))
                if isinstance(widget, tk.Canvas):
                    for item in widget.find_all():
                        if widget.type(item) != "text":
                            continue
                        spec_value = widget.itemcget(item, "font")
                        if spec_value:
                            font = tkfont.Font(root=widget, font=spec_value).actual()
                            if font.get("weight") != "normal":
                                non_regular.append((f"{widget}.canvas[{item}]", font))
            except tk.TclError:
                pass

    family = tkfont.nametofont("TkDefaultFont", root=app).actual("family")
    print(f"VISIBLE_TEXT_RECORDS={len(texts)}")
    print(f"ENGLISH_CJK_COUNT={len(cjk)}")
    for path, text in cjk:
        print(f"CJK\t{path}\t{text!r}")
    print(f"FONT_FAMILY={family}")
    print(f"NON_REGULAR_FONT_COUNT={len(non_regular)}")
    for path, font in non_regular:
        print(f"FONT\t{path}\t{font}")
    print("COMBOBOX_SEMANTIC_ROUNDTRIP=PASS")
    print("FLOW_LIST_LANGUAGE_ROUNDTRIP=PASS")
    print("FONT_CHOICES=DengXian,Microsoft YaHei UI,System Default")
    print("REMOVED_FONT_KEY_MIGRATION=PASS")

    details.destroy()
    node.destroy()
    app.destroy()
    if cjk or non_regular:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
