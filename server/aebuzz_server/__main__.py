"""Run with: python -m aebuzz_server  (binds 127.0.0.1:8000 by default).

AE Buzz.exe also runs this server itself (see desktop/run_aebuzz.py).
"""
import logging
import os

import uvicorn

from .app import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        # Connect to Firebase right away when credentials are set, so the first notification is fast.
        create_app(warm_up=bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))),
        host=os.environ.get("AEBUZZ_HOST", "127.0.0.1"),
        port=int(os.environ.get("AEBUZZ_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
