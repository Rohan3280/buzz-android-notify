"""Run with: python -m aebuzz_server  (binds 127.0.0.1:8000 by default)."""
import os

import uvicorn

from .app import create_app

if __name__ == "__main__":
    uvicorn.run(
        create_app(),
        host=os.environ.get("AEBUZZ_HOST", "127.0.0.1"),
        port=int(os.environ.get("AEBUZZ_PORT", "8000")),
    )
