"""Entry point: ``python -m mdf_viewer``."""

import sys


def main() -> int:
    """Launch the MDF-Viewer application."""
    from mdf_viewer.app import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
