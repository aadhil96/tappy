"""Entry point for the ``tappy`` console script."""

from __future__ import annotations


def main() -> None:
    from .app import TappyApp

    TappyApp().run()


if __name__ == "__main__":
    main()
