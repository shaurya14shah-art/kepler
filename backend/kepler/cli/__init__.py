"""Kepler command-line interface."""


def main(argv=None):
    from .commands import main as _main
    return _main(argv)
