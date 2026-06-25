"""Backward-compatible entrypoint. Prefer running daily_pipeline.py directly."""

from daily_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
