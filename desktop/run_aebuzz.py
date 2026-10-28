"""Entry point for the PyInstaller build (which can't run `-m aebuzz_desktop` directly)."""
from aebuzz_desktop.tray import main

if __name__ == "__main__":
    main()
