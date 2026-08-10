from importlib.metadata import PackageNotFoundError, version

APP_NAME = __name__

try:
    # Written at build/install time by hatch-vcs and holds the version derived
    # from git, including the short commit for dev builds.
    from ._version import __version__

    APP_VERSION = __version__
except ImportError:
    try:
        APP_VERSION = version(APP_NAME)
    except PackageNotFoundError:
        APP_VERSION = "0+unknown"
