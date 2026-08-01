from importlib.metadata import PackageNotFoundError, version

APP_NAME = __name__

try:
    APP_VERSION = version(APP_NAME)
except PackageNotFoundError:
    APP_VERSION = "0"
