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

MAX_VISIBLE = 8
ROW_H = 32
WIDGET_W = 340
TITLE_H = 36
COG_SIZE = 20

# Warm green/emerald palette
C = {
    "bg":         (0.078, 0.118, 0.102),   # #141e1a
    "accent":     (0.345, 0.765, 0.545),   # #58c38b
    "cream":      (0.847, 0.910, 0.878),   # #d8e8e0
    "label":      (0.380, 0.478, 0.427),   # #617a6d
    "dim":        (0.180, 0.243, 0.212),   # #2e3e36
    "bar_empty":  (0.145, 0.196, 0.173),   # #25322c
    "red":        (1.000, 0.373, 0.333),   # #ff5f55
    "tag_bg":     (0.200, 0.290, 0.247),   # #334a3f
    "pin":        (0.910, 0.733, 0.298),   # #e8bb4c
}


def load_settings():
    defaults = {"opacity": 0.90, "x": -1, "y": -1}
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
    outer = radius
    inner = radius * 0.55
    tooth_half = math.pi / teeth / 2.2
    cr.new_path()
    for i in range(teeth):
        angle = 2 * math.pi * i / teeth
        cr.line_to(cx + outer * math.cos(angle - tooth_half),
                   cy + outer * math.sin(angle - tooth_half))
        cr.line_to(cx + outer * math.cos(angle + tooth_half),
                   cy + outer * math.sin(angle + tooth_half))
        na = 2 * math.pi * (i + 0.5) / teeth
        cr.line_to(cx + inner * math.cos(na - tooth_half),
                   cy + inner * math.sin(na - tooth_half))
        cr.line_to(cx + inner * math.cos(na + tooth_half),
                   cy + inner * math.sin(na + tooth_half))
    cr.close_path()
    cr.fill()
    cr.set_source_rgba(*C["bg"], alpha)
    cr.arc(cx, cy, radius * 0.25, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


class PromptVaultWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.settings = load_settings()
        self.alpha = self.settings["opacity"]
        self.vault = load_vault()  # [{name, text, tags[], created}]
        self.drag_offset = None
        self.cog_hover = False
        self.hover_row = -1
        self.scroll_offset = 0
        self.content_h = 200
        self.search_text = ""
        self.add_hover = False

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

        overlay = Gtk.Overlay()
        self.add(overlay)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(WIDGET_W, 200)
        self.canvas.connect("draw", self.on_draw)
        self.canvas.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.SCROLL_MASK
        )
        self.canvas.connect("button-press-event", self.on_press)
        self.canvas.connect("button-release-event", self.on_release)
        self.canvas.connect("motion-notify-event", self.on_motion)
        self.canvas.connect("scroll-event", self.on_scroll)
        overlay.add(self.canvas)

        self.cog_anchor = Gtk.Label()
        self.cog_anchor.set_halign(Gtk.Align.END)
        self.cog_anchor.set_valign(Gtk.Align.START)
        self.cog_anchor.set_margin_end(10)
        self.cog_anchor.set_margin_top(10)
        self.cog_anchor.set_size_request(1, 1)
        overlay.add_overlay(self.cog_anchor)

        # Add button anchor (top left area, below title)
        self.add_anchor = Gtk.Label()
        self.add_anchor.set_halign(Gtk.Align.START)
        self.add_anchor.set_valign(Gtk.Align.START)
        self.add_anchor.set_margin_start(14)
        self.add_anchor.set_margin_top(TITLE_H + 2)
        self.add_anchor.set_size_request(1, 1)
        overlay.add_overlay(self.add_anchor)

        self._build_settings_popover(screen)
        self._build_add_popover()
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.show_all()

    def _build_settings_popover(self, screen):
        self.popover = Gtk.Popover()
        self.popover.set_relative_to(self.cog_anchor)
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        self.popover.connect("closed", lambda _: setattr(self, '_pop_open', False))
        self._pop_open = False

        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pop_box.set_margin_start(12)
        pop_box.set_margin_end(12)
        pop_box.set_margin_top(10)
        pop_box.set_margin_bottom(10)

        lbl = Gtk.Label(label="Opacity")
        lbl.set_halign(Gtk.Align.START)
        pop_box.pack_start(lbl, False, False, 0)

        self.opacity_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.2, 1.0, 0.05
        )
        self.opacity_slider.set_value(self.alpha)
        self.opacity_slider.set_size_request(160, -1)
        self.opacity_slider.set_draw_value(True)
        self.opacity_slider.set_value_pos(Gtk.PositionType.RIGHT)
        self.opacity_slider.connect("value-changed", self.on_opacity_changed)
        pop_box.pack_start(self.opacity_slider, False, False, 0)

        auto_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        auto_lbl = Gtk.Label(label="Auto Start")
        auto_lbl.set_halign(Gtk.Align.START)
        auto_box.pack_start(auto_lbl, True, True, 0)
        self.auto_switch = Gtk.Switch()
        self.auto_switch.set_active(AUTOSTART_FILE.exists())
        self.auto_switch.connect("state-set", self.on_autostart_toggled)
        auto_box.pack_end(self.auto_switch, False, False, 0)
        pop_box.pack_start(auto_box, False, False, 0)

        attr_btn = Gtk.LinkButton.new_with_label(
            "https://boutabyte.com", "Built by Boutabyte"
        )
        attr_btn.set_halign(Gtk.Align.CENTER)
        pop_box.pack_start(attr_btn, False, False, 4)

        quit_btn = Gtk.Button(label="Quit Widget")
        quit_btn.connect("clicked", lambda _: Gtk.main_quit())
        pop_box.pack_start(quit_btn, False, False, 4)

        self.popover.add(pop_box)
        self.popover.show_all()
        self.popover.hide()

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background-color: transparent; }
            popover, popover * { background-color: #141e1a; color: #d8e8e0; }
            popover label { color: #617a6d; }
            scale trough { background-color: #25322c; min-height: 4px; border-radius: 2px; }
            scale highlight { background-color: #58c38b; min-height: 4px; border-radius: 2px; }
            scale slider { background-color: #d8e8e0; min-width: 14px; min-height: 14px; border-radius: 7px; }
            button { background-color: #2e3e36; color: #d8e8e0; border: 1px solid #2e3e36; border-radius: 4px; padding: 4px 12px; }
            button:hover { background-color: #58c38b; color: #141e1a; }
            entry { background-color: #2e3e36; color: #d8e8e0; border: 1px solid #334a3f; border-radius: 4px; padding: 4px 8px; caret-color: #58c38b; }
            entry:focus { border-color: #58c38b; }
            textview, textview text { background-color: #2e3e36; color: #d8e8e0; }
            *:link, button:link { color: #617a6d; background: transparent; border: none; padding: 0; font-size: 9px; }
            *:link:hover, button:link:hover { color: #58c38b; background: transparent; }
            switch { background-color: #2e3e36; border-radius: 12px; min-height: 20px; min-width: 40px; }
            switch:checked { background-color: #58c38b; }
            switch slider { background-color: #d8e8e0; border-radius: 10px; min-height: 16px; min-width: 16px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_add_popover(self):
        self.add_popover = Gtk.Popover()
        self.add_popover.set_relative_to(self.add_anchor)
        self.add_popover.set_position(Gtk.PositionType.BOTTOM)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        name_lbl = Gtk.Label(label="Name")
        name_lbl.set_halign(Gtk.Align.START)
        box.pack_start(name_lbl, False, False, 0)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("e.g. Code Review")
        self.name_entry.set_size_request(220, -1)
        box.pack_start(self.name_entry, False, False, 0)

        tags_lbl = Gtk.Label(label="Tags (comma separated)")
        tags_lbl.set_halign(Gtk.Align.START)
        box.pack_start(tags_lbl, False, False, 0)

        self.tags_entry = Gtk.Entry()
        self.tags_entry.set_placeholder_text("e.g. review, code, dev")
        box.pack_start(self.tags_entry, False, False, 0)

        prompt_lbl = Gtk.Label(label="Prompt")
        prompt_lbl.set_halign(Gtk.Align.START)
        box.pack_start(prompt_lbl, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(220, 100)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.prompt_view = Gtk.TextView()
        self.prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.prompt_view)
        box.pack_start(scroll, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        paste_btn = Gtk.Button(label="Paste from Clipboard")
        paste_btn.connect("clicked", self.on_paste_prompt)
        btn_row.pack_start(paste_btn, True, True, 0)
        box.pack_start(btn_row, False, False, 0)

        save_btn = Gtk.Button(label="Save Prompt")
        save_btn.connect("clicked", self.on_save_prompt)
        box.pack_start(save_btn, False, False, 4)

        self.add_popover.add(box)
        self.add_popover.show_all()
        self.add_popover.hide()

    def _cog_rect(self):
        return (WIDGET_W - 14 - COG_SIZE, 8, COG_SIZE, COG_SIZE)

    def _in_cog(self, x, y):
        cx, cy, cw, ch = self._cog_rect()
        return cx <= x <= cx + cw and cy <= y <= cy + ch

    def _add_btn_rect(self):
        return (WIDGET_W - 14 - COG_SIZE - 28, 8, 20, 20)

    def _in_add_btn(self, x, y):
        bx, by, bw, bh = self._add_btn_rect()
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _row_y_start(self):
        return TITLE_H + 14

    def _row_rect(self, row_index):
        y_start = self._row_y_start() + row_index * ROW_H
        return (14, y_start, WIDGET_W - 28, ROW_H)

    def _del_btn_rect(self, row_index):
        y_start = self._row_y_start() + row_index * ROW_H
        return (WIDGET_W - 14 - 14, y_start + 8, 14, 14)

    def _filtered_vault(self):
        if not self.search_text:
            return self.vault
        q = self.search_text.lower()
        return [p for p in self.vault
                if q in p.get("name", "").lower()
                or q in p.get("text", "").lower()
                or any(q in t.lower() for t in p.get("tags", []))]

    def _visible_items(self):
        filtered = self._filtered_vault()
        return filtered[self.scroll_offset:self.scroll_offset + MAX_VISIBLE]

    # ── Input ──
    def on_press(self, widget, event):
        if event.button == 1:
            if self._in_cog(event.x, event.y):
                self._pop_open = not self._pop_open
                if self._pop_open:
                    self.popover.popup()
                else:
                    self.popover.popdown()
                return True

            if self._in_add_btn(event.x, event.y):
                self.add_popover.popup()
                return True

            # Check row clicks
            visible = self._visible_items()
            for i, item in enumerate(visible):
                # Delete button
                dx, dy, dw, dh = self._del_btn_rect(i)
                if dx <= event.x <= dx + dw and dy <= event.y <= dy + dh:
                    self.vault.remove(item)
                    save_vault(self.vault)
                    self.canvas.queue_draw()
                    return True

                rx, ry, rw, rh = self._row_rect(i)
                if rx <= event.x <= rx + rw and ry <= event.y <= ry + rh:
                    # Copy prompt to clipboard
                    self.clipboard.set_text(item["text"], -1)
                    self.clipboard.store()
                    self.canvas.queue_draw()
                    return True

            if event.y <= TITLE_H:
                self.drag_offset = (event.x_root, event.y_root,
                                    *self.get_position())
        return True

    def on_release(self, widget, event):
        if self.drag_offset:
            self.drag_offset = None
            x, y = self.get_position()
            self.settings["x"] = x
            self.settings["y"] = y
            save_settings(self.settings)
        return True

    def on_motion(self, widget, event):
        if self.drag_offset:
            ox, oy, wx, wy = self.drag_offset
            self.move(int(wx + event.x_root - ox),
                      int(wy + event.y_root - oy))
        else:
            was_cog = self.cog_hover
            self.cog_hover = self._in_cog(event.x, event.y)

            was_add = self.add_hover
            self.add_hover = self._in_add_btn(event.x, event.y)

            old_row = self.hover_row
            self.hover_row = -1
            visible = self._visible_items()
            for i in range(len(visible)):
                rx, ry, rw, rh = self._row_rect(i)
                if rx <= event.x <= rx + rw and ry <= event.y <= ry + rh:
                    self.hover_row = i
                    break

            if was_cog != self.cog_hover or old_row != self.hover_row or was_add != self.add_hover:
                self.canvas.queue_draw()
        return True

    def on_scroll(self, widget, event):
        filtered = self._filtered_vault()
        if event.direction == Gdk.ScrollDirection.DOWN:
            max_off = max(0, len(filtered) - MAX_VISIBLE)
            self.scroll_offset = min(self.scroll_offset + 1, max_off)
        elif event.direction == Gdk.ScrollDirection.UP:
            self.scroll_offset = max(0, self.scroll_offset - 1)
        self.canvas.queue_draw()
        return True

    # ── Settings ──
    def on_opacity_changed(self, scale):
        self.alpha = round(scale.get_value(), 2)
        self.settings["opacity"] = self.alpha
        save_settings(self.settings)
        self.canvas.queue_draw()

    def on_autostart_toggled(self, switch, state):
        if state:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(
                f"[Desktop Entry]\nType=Application\n"
                f"Name=BB Widget: Prompt Vault\n"
                f"Comment=AI prompt snippet manager\n"
                f"Exec=python3 {WIDGET_SCRIPT}\n"
                f"Hidden=false\nNoDisplay=false\n"
                f"X-GNOME-Autostart-enabled=true\n"
                f"X-GNOME-Autostart-Delay=5\n"
            )
        else:
            if AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
        return False

    def on_paste_prompt(self, btn):
        text = self.clipboard.wait_for_text()
        if text:
            buf = self.prompt_view.get_buffer()
            buf.set_text(text)

    def on_save_prompt(self, btn):
        name = self.name_entry.get_text().strip()
        tags_str = self.tags_entry.get_text().strip()
        buf = self.prompt_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()

        if not name or not text:
            return

        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        self.vault.insert(0, {
            "name": name,
            "text": text,
            "tags": tags,
            "created": time.time(),
        })
        save_vault(self.vault)

        self.name_entry.set_text("")
        self.tags_entry.set_text("")
        buf.set_text("")
        self.add_popover.popdown()
        self.canvas.queue_draw()

    # ── Drawing ──
    def on_draw(self, widget, cr):
        a = self.alpha
        alloc = widget.get_allocation()
        w = alloc.width

        visible = self._visible_items()
        vis_count = len(visible)
        needed_h = TITLE_H + 14 + max(vis_count, 1) * ROW_H + 16
        if not self.vault:
            needed_h = TITLE_H + 60

        cr.set_operator(0)
        cr.paint()
        cr.set_operator(2)

        rounded_rect(cr, 0, 0, w, needed_h, 10)
        cr.set_source_rgba(*C["bg"], a)
        cr.fill()

        rounded_rect(cr, 0.5, 0.5, w - 1, needed_h - 1, 10)
        cr.set_source_rgba(*C["dim"], a * 0.5)
        cr.set_line_width(1)
        cr.stroke()

        pad = 14
        y = 18

        # Title
        cr.select_font_face("JetBrains Mono", 0, 1)
        cr.set_font_size(13)
        cr.set_source_rgba(*C["accent"], a)
        cr.move_to(pad, y)
        cr.show_text("prompt")
        tx = cr.get_current_point()[0]
        cr.select_font_face("JetBrains Mono", 0, 0)
        cr.set_source_rgba(*C["cream"], a)
        cr.move_to(tx, y)
        cr.show_text(" vault")

        # Count
        cr.set_font_size(9)
        count_str = f"{len(self.vault)} prompts"
        ext = cr.text_extents(count_str)
        cr.set_source_rgba(*C["label"], a)
        cr.move_to(w - pad - COG_SIZE - 28 - 8 - ext.width, y)
        cr.show_text(count_str)

        # Add button (+)
        ax, ay, aw, ah = self._add_btn_rect()
        add_color = C["accent"] if self.add_hover else C["label"]
        cr.set_font_size(16)
        cr.set_source_rgba(*add_color, a)
        cr.move_to(ax + 2, ay + 16)
        cr.show_text("+")

        # Cog
        cog_cx = WIDGET_W - pad - COG_SIZE / 2
        cog_cy = y - 4
        cog_color = C["accent"] if self.cog_hover else C["label"]
        draw_cog(cr, cog_cx, cog_cy, 8, cog_color, a)

        # Divider
        y += 8
        cr.set_source_rgba(*C["dim"], a * 0.6)
        cr.set_line_width(0.5)
        cr.move_to(pad, y)
        cr.line_to(w - pad, y)
        cr.stroke()

        if not self.vault:
            cr.select_font_face("JetBrains Mono", 0, 0)
            cr.set_font_size(10)
            cr.set_source_rgba(*C["label"], a)
            cr.move_to(pad, y + 24)
            cr.show_text("Click + to save your first prompt")
            self.canvas.set_size_request(WIDGET_W, needed_h)
            return

        # Rows
        for i, item in enumerate(visible):
            row_y = self._row_y_start() + i * ROW_H
            is_hover = (self.hover_row == i)

            if is_hover:
                rounded_rect(cr, pad - 4, row_y, w - pad * 2 + 8, ROW_H - 2, 4)
                cr.set_source_rgba(*C["accent"], a * 0.08)
                cr.fill()

            # Name
            cr.select_font_face("JetBrains Mono", 0, 1)
            cr.set_font_size(10)
            cr.set_source_rgba(*C["cream"], a)
            name = item.get("name", "Untitled")
            if len(name) > 20:
                name = name[:19] + "…"
            cr.move_to(pad, row_y + 14)
            cr.show_text(name)

            # Tags
            tags = item.get("tags", [])
            tag_x = pad + 140
            cr.set_font_size(7)
            for tag in tags[:3]:
                tag_text = tag[:8]
                te = cr.text_extents(tag_text)
                tag_w = te.width + 8
                rounded_rect(cr, tag_x, row_y + 5, tag_w, 14, 3)
                cr.set_source_rgba(*C["tag_bg"], a)
                cr.fill()
                cr.set_source_rgba(*C["accent"], a * 0.8)
                cr.move_to(tag_x + 4, row_y + 14)
                cr.show_text(tag_text)
                tag_x += tag_w + 3

            # Preview of prompt text
            cr.set_font_size(8)
            cr.set_source_rgba(*C["label"], a)
            preview = item.get("text", "")[:40].replace("\n", " ")
            cr.move_to(pad, row_y + 26)
            cr.show_text(preview + ("…" if len(item.get("text", "")) > 40 else ""))

            # Delete X (on hover)
            if is_hover:
                dx, dy, dw, dh = self._del_btn_rect(i)
                cr.set_font_size(9)
                cr.set_source_rgba(*C["red"], a * 0.7)
                cr.move_to(dx + 1, dy + 10)
                cr.show_text("✕")

        # Scroll indicator
        filtered = self._filtered_vault()
        total = len(filtered)
        if total > MAX_VISIBLE:
            bar_h = max(20, int(needed_h * 0.4 * MAX_VISIBLE / total))
            track_h = needed_h - TITLE_H - 30
            bar_y = TITLE_H + 10 + int((track_h - bar_h) * self.scroll_offset / max(1, total - MAX_VISIBLE))
            rounded_rect(cr, w - 6, bar_y, 3, bar_h, 1.5)
            cr.set_source_rgba(*C["dim"], a * 0.5)
            cr.fill()

        if needed_h != self.content_h:
            self.content_h = needed_h
            self.canvas.set_size_request(WIDGET_W, needed_h)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    w = PromptVaultWidget()
    w.connect("destroy", Gtk.main_quit)
    Gtk.main()
