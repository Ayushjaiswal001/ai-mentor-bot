import os
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def app_version() -> str:
    """Return the running build identifier.

    Prefers $APP_VERSION (set by CI/CD). Falls back to short git SHA when
    running from a checkout. Returns 'unknown' when neither is available.
    """
    env_value = os.environ.get("APP_VERSION")
    if env_value:
        return env_value.strip()
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if sha:
            return sha
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return "unknown"
