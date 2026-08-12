"""``python -m gateway`` — start the REST API gateway."""

from __future__ import annotations

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
