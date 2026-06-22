"""PyInstaller runtime hook — load Windows CA certificates into certifi.

python-certifi-win32 normally activates via a .pth file at Python startup,
which PyInstaller does not execute in a frozen bundle. This hook replicates
that effect so SSL connections trust the Windows certificate store (including
corporate / internal CAs) when the app runs as a one-folder bundle.
"""
try:
    import certifi_win32.bootstrap
    certifi_win32.bootstrap.bootstrap()
except (ImportError, Exception):
    pass
