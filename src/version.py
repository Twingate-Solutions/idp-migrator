"""Application version resolution.

The version is used as the build identity in the Twingate API attribution
``User-Agent`` header (see ``src/api/client.py``). It must survive the
delivery model: this project ships as a PyInstaller frozen binary built from
a ``v*`` git tag, where ``importlib.metadata`` is unreliable.

Resolution order:

1. ``APP_VERSION`` environment variable. In release builds this is injected
   at build time (``release.yml`` → ``migrator.spec`` runtime hook) so the
   frozen binary reports the real tag. It also lets developers override.
2. ``importlib.metadata`` — correct for a pip/editable install during dev.
3. ``"0.0.0-dev"`` — final fallback when nothing else is available.
"""

from __future__ import annotations

import os

_DEV_FALLBACK = "0.0.0-dev"
_DISTRIBUTION_NAME = "twingate-idp-migrator"


def get_version() -> str:
    """Resolve the application version string.

    Returns:
        The build version, or ``"0.0.0-dev"`` when it cannot be determined.
    """
    env_version = os.environ.get("APP_VERSION")
    if env_version:
        return env_version.lstrip("v")

    try:
        from importlib.metadata import version

        return version(_DISTRIBUTION_NAME)
    except Exception:  # noqa: BLE001 — any lookup failure falls back to dev
        return _DEV_FALLBACK
