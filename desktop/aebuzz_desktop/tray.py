"""AE Buzz tray app: watches Buzz toasts and forwards them to the paired phone.

Threads: tkinter owns the main thread (pairing window); pystray runs its own
thread; menu callbacks hand work to tkinter through a queue.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path

import httpx
import pystray
import qrcode
from PIL import Image, ImageEnhance, ImageOps, ImageTk

from .config import Config, config_path
from .listener import BuzzToastWatcher
from .local_server import LocalServer
from .relay import Forwarder, RelayClient

log = logging.getLogger(__name__)

APP_NAME = "AE Buzz"
PAIR_POLL_MS = 2000


ICON_PATH = Path(__file__).with_name("icon.png")


def _icon_image(active: bool) -> Image.Image:
    img = Image.open(ICON_PATH).convert("RGB").resize((64, 64), Image.LANCZOS)
    if not active:
        # Greyed out while paused or not paired.
        img = ImageEnhance.Brightness(ImageOps.grayscale(img).convert("RGB")).enhance(0.8)
    return img


class TrayApp:
    def __init__(self) -> None:
        self.config = Config.load()
        self.status = "Paired · forwarding" if self.config.paired else "Not paired"
        self._ui_tasks: queue.Queue = queue.Queue()
        self._root = tk.Tk()
        self._root.withdraw()
        self._pair_window: tk.Toplevel | None = None

        self.local_server = LocalServer(self.config)
        self.forwarder = Forwarder(self.config, RelayClient, self._set_status, self._handle_unpaired)
        self.watcher = BuzzToastWatcher(self.forwarder.submit, self._set_status)
        self.icon = pystray.Icon(APP_NAME, _icon_image(self.config.paired), APP_NAME, self._menu())

    # ---- menu -----------------------------------------------------------
    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: self._status_line(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pair phone…", lambda: self._ui(self._open_pair_window)),
            pystray.MenuItem(
                "Pause forwarding",
                self._toggle_pause,
                checked=lambda _: self.config.paused,
                enabled=lambda _: self.config.paired,
            ),
            pystray.MenuItem("Unpair", self._unpair, enabled=lambda _: self.config.paired),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _status_line(self) -> str:
        return "Paused" if self.config.paused and self.config.paired else self.status

    def _refresh_icon(self) -> None:
        self.icon.icon = _icon_image(self.config.paired and not self.config.paused)
        self.icon.title = f"{APP_NAME} — {self._status_line()}"
        self.icon.update_menu()

    def _set_status(self, text: str) -> None:
        self.status = text
        self._refresh_icon()

    def _toggle_pause(self) -> None:
        self.config.paused = not self.config.paused
        self.config.save()
        self._refresh_icon()

    def _unpair(self) -> None:
        cfg = self.config
        if cfg.paired:
            try:
                RelayClient(cfg.server_url).unpair(cfg.pair_id, cfg.desktop_secret)
            except httpx.HTTPError:
                log.warning("could not reach server to unpair; clearing locally")
        self._handle_unpaired()

    def _handle_unpaired(self) -> None:
        self.config.clear_pairing()
        self.config.save()
        self._set_status("Not paired")

    def _quit(self) -> None:
        self.watcher.stop()
        self.local_server.stop()
        self.icon.stop()
        self._ui(self._root.quit)

    def _start_local_server(self) -> None:
        if not self.local_server.enabled:
            return
        self._set_status("Starting server…")
        error = self.local_server.ensure_running()
        if error:
            log.error(error)
            self._set_status(error)
        else:
            self._set_status("Paired · forwarding" if self.config.paired else "Not paired")

    # ---- tkinter side ---------------------------------------------------
    def _ui(self, fn) -> None:
        self._ui_tasks.put(fn)

    def _drain_ui_tasks(self) -> None:
        while True:
            try:
                self._ui_tasks.get_nowait()()
            except queue.Empty:
                break
        self._root.after(200, self._drain_ui_tasks)

    def _open_pair_window(self) -> None:
        if self._pair_window is not None:
            self._pair_window.lift()
            return
        try:
            pairing = RelayClient(self.config.server_url).create_pairing()
        except httpx.HTTPError as exc:
            self._show_message(f"Can't reach the relay server at {self.config.server_url}.\n\n{exc}")
            return

        win = tk.Toplevel(self._root)
        win.title(f"{APP_NAME} — pair your phone")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        self._pair_window = win
        win.protocol("WM_DELETE_WINDOW", self._close_pair_window)

        qr_img = qrcode.make(pairing.qr_payload, box_size=8, border=2).get_image()
        photo = ImageTk.PhotoImage(qr_img)
        label = tk.Label(win, image=photo)
        label.image = photo  # keep a reference or tkinter drops the image
        label.pack(padx=16, pady=(16, 8))

        hint = "Open AE Buzz on your phone and scan this code.\nIt expires in 10 minutes."
        if pairing.phone_url.startswith(("http://127.", "http://localhost")):
            hint += (
                "\n\nWarning: the server has no public URL, so your phone can't reach it.\n"
                "Set AEBUZZ_PUBLIC_URL on the server (e.g. a cloudflared tunnel URL)."
            )
        status = tk.Label(win, text=hint, justify="center")
        status.pack(padx=16, pady=(0, 16))

        def poll() -> None:
            if self._pair_window is not win:
                return
            try:
                result = RelayClient(self.config.server_url).status(pairing.pair_id, pairing.desktop_secret)
            except httpx.HTTPError:
                result = {}
            if result and result.get("paired"):
                self.config.pair_id = pairing.pair_id
                self.config.desktop_secret = pairing.desktop_secret
                self.config.paused = False
                self.config.save()
                self._set_status("Paired · forwarding")
                status.config(text="Paired ✓  You can close this window.")
                win.after(2500, self._close_pair_window)
                return
            win.after(PAIR_POLL_MS, poll)

        win.after(PAIR_POLL_MS, poll)

    def _close_pair_window(self) -> None:
        if self._pair_window is not None:
            self._pair_window.destroy()
            self._pair_window = None

    def _show_message(self, text: str) -> None:
        win = tk.Toplevel(self._root)
        win.title(APP_NAME)
        win.attributes("-topmost", True)
        tk.Label(win, text=text, justify="left", wraplength=420).pack(padx=16, pady=16)
        tk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 12))

    # ---- run ------------------------------------------------------------
    def run(self) -> None:
        threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
        threading.Thread(target=self._start_local_server, name="local-server", daemon=True).start()
        self.forwarder.start()
        self.watcher.start()
        self._root.after(200, self._drain_ui_tasks)
        self._root.mainloop()


def _already_running() -> bool:
    """Named mutex so opening the shortcut twice doesn't create a second tray icon."""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    # Keep the handle for the life of the process; Windows frees it on exit.
    _already_running.handle = kernel32.CreateMutexW(None, False, "Local\\AEBuzzTray")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    log_path = config_path().with_name("tray.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # pythonw has no console, so logs go to a file next to config.json.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    if _already_running():
        log.info("AE Buzz is already running; exiting")
        return
    TrayApp().run()


if __name__ == "__main__":
    main()
