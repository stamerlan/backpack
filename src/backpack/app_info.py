from importlib.metadata import PackageNotFoundError, version

APP_NAME = "backpack"

try:
    from backpack._version import __version__
    APP_VERSION = __version__
except ImportError:
    try:
        APP_VERSION = version(APP_NAME)
    except PackageNotFoundError:
        APP_VERSION = "0+unknown"
