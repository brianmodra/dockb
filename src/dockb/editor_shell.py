"""Serving the built editor from the backend, so it is same-origin with the API.

The packaged renderer used to be loaded from ``file://`` and talk to the API at
``http://localhost:8000``, which is cross-site: the browser withheld the
``SameSite=lax`` session cookie, so OAuth mode was unreachable from the editor.
Serving the built shell from the backend removes the cross-site request, and with
it the need for ``SameSite=None``, an https origin, and a CORS grant for the
``null`` origin — a grant that let any local ``file://`` page read the API as the
signed-in user. See ``README_auth.md`` §4 and §6.

The build output lives at ``frontend/dist`` and is gitignored, so a checkout that
has not run ``npm run build`` simply has no shell to serve. That is not an error:
the API is unaffected, and ``/editor`` 404s.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

EDITOR_MOUNT_PATH = "/editor"

_ENV_VAR = "DOCKB_FRONTEND_DIST"

# The repository root, so the default does not follow the working directory:
# main.py chdirs into run/ on startup, and by then this is the only anchor left.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DIST_DIR = _REPO_ROOT / "frontend" / "dist"


def resolve_editor_dist_dir() -> Path:
    """Return the directory holding the built renderer.

    ``DOCKB_FRONTEND_DIST`` wins; otherwise the frontend's own ``dist`` directory
    in this checkout. Resolved from this module's location rather than the
    working directory, so a ``chdir`` cannot move it.
    """
    configured = os.environ.get(_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DIST_DIR


def mount_editor_shell(application: FastAPI) -> None:
    """Serve the built renderer under ``/editor`` when it has been built.

    Mounted under its own prefix and only at the end of the router list, so it
    can never shadow an API route. Skipped silently when the build output is
    absent, which keeps a source checkout without ``npm run build`` fully usable
    over the API.
    """
    dist_dir = resolve_editor_dist_dir()
    if not dist_dir.is_dir():
        return
    application.mount(
        EDITOR_MOUNT_PATH,
        StaticFiles(directory=dist_dir, html=True),
        name="editor",
    )
