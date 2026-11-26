"""Entry point for the PyInstaller build (which can't run `-m aebuzz_desktop` directly).

`AE Buzz.exe` opens the tray app; `AE Buzz.exe --relay-server` runs the bundled relay
server, which the tray app starts by itself.
"""
import os
import sys

from aebuzz_desktop.local_server import RELAY_SERVER_FLAG


def run_relay_server() -> None:
    if sys.stdout is None:  # the windowed build has no console; log to the file the tray chose
        log = open(os.environ.get("AEBUZZ_SERVER_LOG", os.devnull), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    from aebuzz_server.__main__ import main

    main()


if __name__ == "__main__":
    if RELAY_SERVER_FLAG in sys.argv[1:]:
        run_relay_server()
    else:
        from aebuzz_desktop.tray import main

        main()
