#!/usr/bin/env python3
"""Prompt Vault Desktop Widget
Save, tag, search, and reuse AI prompt snippets. Click to copy.
Stores locally in JSON. Purely local, no cloud.
Built by Boutabyte — https://boutabyte.com
"""

import json
import math
import signal
import time
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

APP_NAME = "Prompt Vault"
CONFIG_DIR = Path.home() / ".config" / "prompt-vault-widget"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
VAULT_FILE = CONFIG_DIR / "vault.json"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "bb-prompt-vault.desktop"
WIDGET_SCRIPT = Path(__file__).resolve()

ROW_H = 32
MIN_W = 280
MIN_H = 120
TITLE_H = 36
COG_SIZE = 20
RESIZE_MARGIN = 8

# Warm green/emerald palette
C = {
    "bg":         (0.078, 0.118, 0.102),
    "accent":     (0.345, 0.765, 0.545),
    "cream":      (0.847, 0.910, 0.878),
    "label":      (0.380, 0.478, 0.427),
    "dim":        (0.180, 0.243, 0.212),
    "bar_empty":  (0.145, 0.196, 0.173),
    "red":        (1.000, 0.373, 0.333),
    "tag_bg":     (0.200, 0.290, 0.247),
    "pin":        (0.910, 0.733, 0.298),
}

CSS_TEMPLATE = """
window {{ background-color: transparent; }}
.settings-window {{ background-color: {bg_hex}; border: 1px solid #ffffff; border-radius: 8px; }}
.settings-window * {{ color: {text_hex}; }}
.settings-window label {{ color: {label_hex}; font-size: 12px; }}
scale trough {{ background-color: {dim_hex}; min-height: 4px; border-radius: 2px; }}
scale highlight {{ background-color: {accent_hex}; min-height: 4px; border-radius: 2px; }}
scale slider {{ background-color: {text_hex}; min-width: 14px; min-height: 14px; border-radius: 7px; }}
button {{ background-color: {dim_hex}; color: {text_hex}; border: 1px solid {dim_hex}; border-radius: 4px; padding: 6px 14px; font-size: 11px; font-weight: bold; }}
button:hover {{ background-color: {accent_hex}; color: {bg_hex}; }}
.close-x {{ background: transparent; border: none; padding: 4px 10px; font-size: 16px; font-weight: bold; color: #ffffff; min-width: 24px; }}
.close-x:hover {{ color: {red_hex}; background: transparent; }}
.quit-btn {{ background-color: transparent; color: {red_hex}; border: 1px solid {red_hex}; }}
.quit-btn:hover {{ background-color: {red_hex}; color: {bg_hex}; }}
*:link, button:link {{ color: {label_hex}; background: transparent; border: none; padding: 0; font-size: 9px; }}
*:link:hover, button:link:hover {{ color: {accent_hex}; background: transparent; }}
switch {{ background-color: {dim_hex}; border-radius: 12px; min-height: 20px; min-width: 40px; }}
switch:checked {{ background-color: {accent_hex}; }}
switch slider {{ background-color: {text_hex}; border-radius: 10px; min-height: 16px; min-width: 16px; }}
entry {{ background-color: {dim_hex}; color: {text_hex}; border: 1px solid {dim_hex}; border-radius: 4px; padding: 4px 8px; caret-color: {accent_hex}; }}
entry:focus {{ border-color: {accent_hex}; }}
textview, textview text {{ background-color: {dim_hex}; color: {text_hex}; }}
"""


def load_settings():
    defaults = {"opacity": 0.90, "x": -1, "y": -1, "w": 340, "h": 320, "font_size": 10}
    if SETTINGS_FILE.exists():
        try:
            defaults.update(json.loads(SETTINGS_FILE.read_text()))
        except Exception:
            pass
    return defaults


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings))


def load_vault():
    if VAULT_FILE.exists():
        try:
            return json.loads(VAULT_FILE.read_text())
        except Exception:
            pass
    return []


def save_vault(vault):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_FILE.write_text(json.dumps(vault, indent=2))


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, h / 2, w / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def draw_cog(cr, cx, cy, radius, color, alpha=1.0):
    cr.save()
    cr.set_source_rgba(*color, alpha)
    teeth = 6
    outer, inner = radius, radius * 0.55
    th = math.pi / teeth / 2.2
    cr.new_path()
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        cr.line_to(cx + outer * math.cos(a - th), cy + outer * math.sin(a - th))
        cr.line_to(cx + outer * math.cos(a + th), cy + outer * math.sin(a + th))
        na = 2 * math.pi * (i + 0.5) / teeth
        cr.line_to(cx + inner * math.cos(na - th), cy + inner * math.sin(na - th))
        cr.line_to(cx + inner * math.cos(na + th), cy + inner * math.sin(na + th))
    cr.close_path()
    cr.fill()
    cr.set_source_rgba(*C["bg"], alpha)
    cr.arc(cx, cy, radius * 0.25, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


class SettingsWindow(Gtk.Window):
    def __init__(self, widget_app):
        super().__init__(title=f"{APP_NAME} Settings")
        self.app = widget_app
        self.set_default_size(300, 340)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        wx, wy = widget_app.get_position()
        self.move(wx + widget_app.widget_w // 2 - 150, wy + 30)
        self.get_style_context().add_class("settings-window")
        self.connect("delete-event", self.on_close)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(14)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label()
        title.set_markup('<span font_desc="12" weight="bold">Settings</span>')
        title.set_halign(Gtk.Align.START)
        header.pack_start(title, True, True, 0)
        close_btn = Gtk.Button(label="✕")
        close_btn.get_style_context().add_class("close-x")
        close_btn.connect("clicked", lambda _: self.on_close(None, None))
        header.pack_end(close_btn, False, False, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        lbl = Gtk.Label(label="Opacity")
        lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)
        self.opacity_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.2, 1.0, 0.05)
        self.opacity_slider.set_value(self.app.alpha)
        self.opacity_slider.set_draw_value(True)
        self.opacity_slider.set_value_pos(Gtk.PositionType.RIGHT)
        self.opacity_slider.connect("value-changed", self.on_opacity)
        vbox.pack_start(self.opacity_slider, False, False, 0)

        ts_lbl = Gtk.Label(label="Text Size")
        ts_lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(ts_lbl, False, False, 0)
        self.text_size_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 7, 16, 1)
        self.text_size_slider.set_value(self.app.font_size)
        self.text_size_slider.set_draw_value(True)
        self.text_size_slider.set_digits(0)
        self.text_size_slider.set_value_pos(Gtk.PositionType.RIGHT)
        self.text_size_slider.connect("value-changed", self.on_text_size)
        vbox.pack_start(self.text_size_slider, False, False, 0)

        auto_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        auto_lbl = Gtk.Label(label="Auto Start")
        auto_lbl.set_halign(Gtk.Align.START)
        auto_box.pack_start(auto_lbl, True, True, 0)
        self.auto_switch = Gtk.Switch()
        self.auto_switch.set_active(AUTOSTART_FILE.exists())
        self.auto_switch.connect("state-set", self.on_autostart)
        auto_box.pack_end(self.auto_switch, False, False, 0)
        vbox.pack_start(auto_box, False, False, 0)

        attr = Gtk.LinkButton.new_with_label("https://boutabyte.com", "Built by Boutabyte")
        attr.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(attr, False, False, 6)

        quit_btn = Gtk.Button(label="Quit Widget")
        quit_btn.get_style_context().add_class("quit-btn")
        quit_btn.connect("clicked", lambda _: Gtk.main_quit())
        vbox.pack_start(quit_btn, False, False, 2)

        self.add(vbox)
        self.show_all()

    def on_close(self, *args):
        self.hide()
        self.app.settings_win = None
        return True

    def on_opacity(self, scale):
        self.app.alpha = round(scale.get_value(), 2)
        self.app.settings["opacity"] = self.app.alpha
        save_settings(self.app.settings)
        self.app.canvas.queue_draw()

    def on_text_size(self, scale):
        self.app.font_size = int(scale.get_value())
        self.app.settings["font_size"] = self.app.font_size
        save_settings(self.app.settings)
        self.app.canvas.queue_draw()

    def on_autostart(self, switch, state):
        if state:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(
                f"[Desktop Entry]\nType=Application\n"
                f"Name=BB Widget: Prompt Vault\nComment=AI prompt snippet manager\n"
                f"Exec=python3 {WIDGET_SCRIPT}\nHidden=false\nNoDisplay=false\n"
                f"X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=5\n"
            )
        else:
            if AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
        return False


class AddPromptWindow(Gtk.Window):
    """Standalone add-prompt window."""
    def __init__(self, widget_app):
        super().__init__(title="Add Prompt")
        self.app = widget_app
        self.set_default_size(320, 340)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        wx, wy = widget_app.get_position()
        self.move(wx + widget_app.widget_w // 2 - 160, wy + 30)
        self.get_style_context().add_class("settings-window")
        self.connect("delete-event", self.on_close)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(14)
        vbox.set_margin_end(14)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(14)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label()
        title.set_markup('<span font_desc="12" weight="bold">Add Prompt</span>')
        title.set_halign(Gtk.Align.START)
        header.pack_start(title, True, True, 0)
        close_btn = Gtk.Button(label="✕")
        close_btn.get_style_context().add_class("close-x")
        close_btn.connect("clicked", lambda _: self.on_close(None, None))
        header.pack_end(close_btn, False, False, 0)
        vbox.pack_start(header, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 4)

        name_lbl = Gtk.Label(label="Name")
        name_lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(name_lbl, False, False, 0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("e.g. Code Review")
        vbox.pack_start(self.name_entry, False, False, 0)

        tags_lbl = Gtk.Label(label="Tags (comma separated)")
        tags_lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(tags_lbl, False, False, 0)
        self.tags_entry = Gtk.Entry()
        self.tags_entry.set_placeholder_text("e.g. review, code, dev")
        vbox.pack_start(self.tags_entry, False, False, 0)

        prompt_lbl = Gtk.Label(label="Prompt")
        prompt_lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(prompt_lbl, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 100)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.prompt_view)
        vbox.pack_start(scroll, True, True, 0)

        paste_btn = Gtk.Button(label="Paste from Clipboard")
        paste_btn.connect("clicked", self.on_paste)
        vbox.pack_start(paste_btn, False, False, 2)

        save_btn = Gtk.Button(label="Save Prompt")
        save_btn.connect("clicked", self.on_save)
        vbox.pack_start(save_btn, False, False, 4)

        self.add(vbox)
        self.show_all()

    def on_close(self, *args):
        self.hide()
        self.app.add_win = None
        return True

    def on_paste(self, btn):
        text = self.app.clipboard.wait_for_text()
        if text:
            self.prompt_view.get_buffer().set_text(text)

    def on_save(self, btn):
        name = self.name_entry.get_text().strip()
        tags_str = self.tags_entry.get_text().strip()
        buf = self.prompt_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if not name or not text:
            return
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        self.app.vault.insert(0, {"name": name, "text": text, "tags": tags, "created": time.time()})
        save_vault(self.app.vault)
        self.name_entry.set_text("")
        self.tags_entry.set_text("")
        buf.set_text("")
        self.on_close()
        self.app.canvas.queue_draw()


class PromptVaultWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.settings = load_settings()
        self.alpha = self.settings["opacity"]
        self.font_size = self.settings.get("font_size", 10)
        self.vault = load_vault()
        self.drag_offset = None
        self.resize_edge = None
        self.cog_hover = False
        self.add_hover = False
        self.hover_row = -1
        self.scroll_offset = 0
        self.settings_win = None
        self.add_win = None
        self.widget_w = self.settings.get("w", 340)
        self.widget_h = self.settings.get("h", 320)

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_below(True)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        if self.settings["x"] >= 0 and self.settings["y"] >= 0:
            self.move(self.settings["x"], self.settings["y"])
        else:
            display = Gdk.Display.get_default()
            mon = display.get_primary_monitor() or display.get_monitor(0)
            geom = mon.get_geometry()
            self.move(geom.x + geom.width - 400, geom.y + 60)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(self.widget_w, self.widget_h)
        self.canvas.connect("draw", self.on_draw)
        self.canvas.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK
        )
        self.canvas.connect("button-press-event", self.on_press)
        self.canvas.connect("button-release-event", self.on_release)
        self.canvas.connect("motion-notify-event", self.on_motion)
        self.canvas.connect("scroll-event", self.on_scroll)
        self.add(self.canvas)

        css = Gtk.CssProvider()
        css.load_from_data(CSS_TEMPLATE.format(
            bg_hex="#141e1a", text_hex="#d8e8e0", label_hex="#617a6d",
            dim_hex="#2e3e36", accent_hex="#58c38b", red_hex="#ff5f55",
        ).encode())
        Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.show_all()

    def _max_visible(self):
        usable = self.widget_h - TITLE_H - 14 - 6
        return max(1, usable // ROW_H)

    def _cog_rect(self):
        return (self.widget_w - 14 - COG_SIZE, 8, COG_SIZE, COG_SIZE)

    def _in_cog(self, x, y):
        cx, cy, cw, ch = self._cog_rect()
        return cx <= x <= cx + cw and cy <= y <= cy + ch

    def _add_btn_rect(self):
        return (self.widget_w - 14 - COG_SIZE - 28, 8, 20, 20)

    def _in_add_btn(self, x, y):
        bx, by, bw, bh = self._add_btn_rect()
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _row_y_start(self):
        return TITLE_H + 14

    def _row_rect(self, i):
        return (14, self._row_y_start() + i * ROW_H, self.widget_w - 28, ROW_H)

    def _del_btn_rect(self, i):
        return (self.widget_w - 14 - 14, self._row_y_start() + i * ROW_H + 8, 14, 14)

    def _visible_items(self):
        return self.vault[self.scroll_offset:self.scroll_offset + self._max_visible()]

    def _resize_edge_at(self, x, y):
        w, h = self.widget_w, self.widget_h
        m = RESIZE_MARGIN
        left, right = x <= m, x >= w - m
        top, bottom = y <= m, y >= h - m
        if right and bottom: return "se"
        if left and bottom: return "sw"
        if right and top: return "ne"
        if left and top: return "nw"
        if right: return "e"
        if left: return "w"
        if bottom: return "s"
        if top and y > 0: return "n"
        return None

    def on_press(self, widget, event):
        if event.button == 1:
            edge = self._resize_edge_at(event.x, event.y)
            if edge:
                self.resize_edge = edge
                wx, wy = self.get_position()
                self.drag_offset = (event.x_root, event.y_root, self.widget_w, self.widget_h, wx, wy)
                return True
            if self._in_cog(event.x, event.y):
                if not self.settings_win:
                    self.settings_win = SettingsWindow(self)
                else:
                    self.settings_win.present()
                return True
            if self._in_add_btn(event.x, event.y):
                if not self.add_win:
                    self.add_win = AddPromptWindow(self)
                else:
                    self.add_win.present()
                return True
            visible = self._visible_items()
            for i, item in enumerate(visible):
                dx, dy, dw, dh = self._del_btn_rect(i)
                if dx <= event.x <= dx + dw and dy <= event.y <= dy + dh:
                    self.vault.remove(item)
                    save_vault(self.vault)
                    self.canvas.queue_draw()
                    return True
                rx, ry, rw, rh = self._row_rect(i)
                if rx <= event.x <= rx + rw and ry <= event.y <= ry + rh:
                    self.clipboard.set_text(item["text"], -1)
                    self.clipboard.store()
                    self.canvas.queue_draw()
                    return True
            if event.y <= TITLE_H:
                self.drag_offset = (event.x_root, event.y_root, *self.get_position(), 0, 0)
                self.resize_edge = None
        return True

    def on_release(self, widget, event):
        if self.resize_edge:
            x, y = self.get_position()
            self.settings.update({"w": self.widget_w, "h": self.widget_h, "x": x, "y": y})
            save_settings(self.settings)
            self.resize_edge = None
            self.drag_offset = None
        elif self.drag_offset:
            self.drag_offset = None
            x, y = self.get_position()
            self.settings["x"] = x
            self.settings["y"] = y
            save_settings(self.settings)
        return True

    def on_motion(self, widget, event):
        if self.resize_edge and self.drag_offset:
            ox, oy, ow, oh, owx, owy = self.drag_offset
            dx, dy = event.x_root - ox, event.y_root - oy
            nw, nh, nx, ny = ow, oh, owx, owy
            e = self.resize_edge
            if "e" in e: nw = max(MIN_W, int(ow + dx))
            if "w" in e: nw = max(MIN_W, int(ow - dx)); nx = owx + (ow - nw)
            if "s" in e: nh = max(MIN_H, int(oh + dy))
            if "n" in e: nh = max(MIN_H, int(oh - dy)); ny = owy + (oh - nh)
            self.widget_w, self.widget_h = nw, nh
            self.canvas.set_size_request(nw, nh)
            self.resize(nw, nh)
            self.move(nx, ny)
            self.canvas.queue_draw()
        elif self.drag_offset and not self.resize_edge:
            ox, oy, wx, wy = self.drag_offset[:4]
            self.move(int(wx + event.x_root - ox), int(wy + event.y_root - oy))
        else:
            was_cog = self.cog_hover
            self.cog_hover = self._in_cog(event.x, event.y)
            was_add = self.add_hover
            self.add_hover = self._in_add_btn(event.x, event.y)
            old_row = self.hover_row
            self.hover_row = -1
            for i in range(len(self._visible_items())):
                rx, ry, rw, rh = self._row_rect(i)
                if rx <= event.x <= rx + rw and ry <= event.y <= ry + rh:
                    self.hover_row = i
                    break
            edge = self._resize_edge_at(event.x, event.y)
            win = self.get_window()
            if win:
                cmap = {"se":"se-resize","sw":"sw-resize","ne":"ne-resize","nw":"nw-resize",
                        "e":"e-resize","w":"w-resize","s":"s-resize","n":"n-resize"}
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), cmap[edge]) if edge in cmap else None)
            if was_cog != self.cog_hover or old_row != self.hover_row or was_add != self.add_hover:
                self.canvas.queue_draw()
        return True

    def on_scroll(self, widget, event):
        mv = self._max_visible()
        if event.direction == Gdk.ScrollDirection.DOWN:
            self.scroll_offset = min(self.scroll_offset + 1, max(0, len(self.vault) - mv))
        elif event.direction == Gdk.ScrollDirection.UP:
            self.scroll_offset = max(0, self.scroll_offset - 1)
        self.canvas.queue_draw()
        return True

    def on_draw(self, widget, cr):
        a = self.alpha
        fs = self.font_size
        w = self.widget_w
        h = self.widget_h

        cr.set_operator(0); cr.paint(); cr.set_operator(2)
        rounded_rect(cr, 0, 0, w, h, 10)
        cr.set_source_rgba(*C["bg"], a); cr.fill()
        rounded_rect(cr, 0.5, 0.5, w - 1, h - 1, 10)
        cr.set_source_rgba(*C["dim"], a * 0.5); cr.set_line_width(1); cr.stroke()

        pad = 14
        y = 18

        # Title
        cr.select_font_face("JetBrains Mono", 0, 1)
        cr.set_font_size(fs + 3)
        cr.set_source_rgba(*C["accent"], a)
        cr.move_to(pad, y); cr.show_text("prompt")
        tx = cr.get_current_point()[0]
        cr.select_font_face("JetBrains Mono", 0, 0)
        cr.set_source_rgba(*C["cream"], a)
        cr.move_to(tx, y); cr.show_text(" vault")

        # Count
        cr.set_font_size(fs - 1)
        cs = f"{len(self.vault)} prompts"
        ext = cr.text_extents(cs)
        cr.set_source_rgba(*C["label"], a)
        cr.move_to(w - pad - COG_SIZE - 28 - 8 - ext.width, y); cr.show_text(cs)

        # Add button (+)
        ax, ay, aw, ah = self._add_btn_rect()
        cr.set_font_size(16)
        cr.set_source_rgba(*C["accent"] if self.add_hover else C["label"], a)
        cr.move_to(ax + 2, ay + 16); cr.show_text("+")

        # Cog
        cog_color = C["accent"] if self.cog_hover else C["label"]
        draw_cog(cr, w - pad - COG_SIZE / 2, y - 4, 8, cog_color, a)

        y += 8
        cr.set_source_rgba(*C["dim"], a * 0.6); cr.set_line_width(0.5)
        cr.move_to(pad, y); cr.line_to(w - pad, y); cr.stroke()

        if not self.vault:
            cr.set_font_size(fs); cr.set_source_rgba(*C["label"], a)
            cr.move_to(pad, y + 24); cr.show_text("Click + to save your first prompt")
            for dx in range(3):
                for dy in range(3 - dx):
                    cr.set_source_rgba(*C["label"], a * 0.3)
                    cr.arc(w - 8 + dx * 3, h - 8 + dy * 3, 1, 0, 2 * math.pi); cr.fill()
            return

        visible = self._visible_items()
        for i, item in enumerate(visible):
            row_y = self._row_y_start() + i * ROW_H
            if row_y + ROW_H > h - 10:
                break
            is_hover = (self.hover_row == i)

            if is_hover:
                rounded_rect(cr, pad - 4, row_y, w - pad * 2 + 8, ROW_H - 2, 4)
                cr.set_source_rgba(*C["accent"], a * 0.08); cr.fill()

            # Name
            cr.select_font_face("JetBrains Mono", 0, 1)
            cr.set_font_size(fs)
            cr.set_source_rgba(*C["cream"], a)
            name = item.get("name", "Untitled")
            max_name = max(8, (w - 180) // 7)
            if len(name) > max_name:
                name = name[:max_name - 1] + "…"
            cr.move_to(pad, row_y + 14); cr.show_text(name)

            # Tags
            tags = item.get("tags", [])
            tag_x = pad + max_name * 7 + 10
            cr.set_font_size(fs - 3)
            for tag in tags[:3]:
                tag_text = tag[:8]
                te = cr.text_extents(tag_text)
                tag_w = te.width + 8
                if tag_x + tag_w > w - 30:
                    break
                rounded_rect(cr, tag_x, row_y + 3, tag_w, 14, 3)
                cr.set_source_rgba(*C["tag_bg"], a); cr.fill()
                cr.set_source_rgba(*C["accent"], a * 0.8)
                cr.move_to(tag_x + 4, row_y + 13); cr.show_text(tag_text)
                tag_x += tag_w + 3

            # Preview
            cr.set_font_size(fs - 2)
            cr.set_source_rgba(*C["label"], a)
            max_preview = max(10, (w - 40) // 6)
            preview = item.get("text", "")[:max_preview].replace("\n", " ")
            cr.move_to(pad, row_y + 26); cr.show_text(preview + ("…" if len(item.get("text", "")) > max_preview else ""))

            # Delete X on hover
            if is_hover:
                dx, dy, dw, dh = self._del_btn_rect(i)
                cr.set_font_size(fs - 1)
                cr.set_source_rgba(*C["red"], a * 0.7)
                cr.move_to(dx + 1, dy + 10); cr.show_text("✕")

        # Resize grip
        for dx in range(3):
            for dy in range(3 - dx):
                cr.set_source_rgba(*C["label"], a * 0.3)
                cr.arc(w - 8 + dx * 3, h - 8 + dy * 3, 1, 0, 2 * math.pi); cr.fill()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    w = PromptVaultWidget()
    w.connect("destroy", Gtk.main_quit)
    Gtk.main()
