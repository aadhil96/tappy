"""Entry point for the ``tappy`` console script.

Routing:
  * ``tappy`` (no args) or ``tappy ui``  -> launch the Textual management TUI.
  * ``tappy <command> …``                -> run the CLI (management + inspector).
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Launch the TUI when no command is given, or an explicit `ui`.
    if not argv or argv[0] == "ui":
        from .app import TappyApp

        TappyApp().run()
        return

    from . import cli

    # Unknown first token that isn't a flag -> let argparse show a helpful error.
    raise SystemExit(cli.run(argv))


if __name__ == "__main__":
    main()
