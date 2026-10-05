"""Tests for serving the built editor shell from the backend.

The packaged renderer is loaded from the backend rather than ``file://`` so it is
same-origin with the API and the ``SameSite=Strict`` session cookie is sent.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from dockb.app_factory import create_app

_INDEX_HTML = '<!doctype html><html><head><script type="module" src="./assets/index-abc123.js"></script></head><body></body></html>'


def _write_dist(directory) -> None:
    """Create a built-frontend directory with an index and a hashed asset."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    assets = directory / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "index-abc123.js").write_text("export const x = 1;\n", encoding="utf-8")


class TestResolveEditorDistDir:
    def test_defaults_to_the_built_frontend_in_the_repo(self, monkeypatch):
        from pathlib import Path

        from dockb.editor_shell import resolve_editor_dist_dir

        monkeypatch.delenv("DOCKB_FRONTEND_DIST", raising=False)

        resolved = resolve_editor_dist_dir()

        assert resolved == Path(__file__).resolve().parents[2] / "frontend" / "dist"

    def test_the_default_is_absolute_so_a_chdir_cannot_move_it(self, monkeypatch):
        """main.py chdirs into run/ on startup, so a relative default would break."""
        from dockb.editor_shell import resolve_editor_dist_dir

        monkeypatch.delenv("DOCKB_FRONTEND_DIST", raising=False)
        monkeypatch.chdir("/")

        assert resolve_editor_dist_dir().is_absolute()

    def test_honours_the_configured_directory(self, tmp_path, monkeypatch):
        from dockb.editor_shell import resolve_editor_dist_dir

        target = tmp_path / "somewhere" / "dist"
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(target))

        assert resolve_editor_dist_dir() == target


class TestMountEditorShell:
    def test_create_app_serves_the_shell_without_a_separate_mount_call(self, tmp_path, monkeypatch):
        """create_app is what main.py runs, so it has to register the mount itself.

        Calling mount_editor_shell explicitly elsewhere would leave this
        untested, and the app would serve no shell in production.
        """
        dist = tmp_path / "dist"
        _write_dist(dist)
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(dist))

        response = TestClient(create_app()).get("/editor/")

        assert response.status_code == 200
        assert "index-abc123.js" in response.text

    def test_serves_the_built_index(self, tmp_path, monkeypatch):
        from dockb.editor_shell import mount_editor_shell

        dist = tmp_path / "dist"
        _write_dist(dist)
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(dist))
        app = create_app()
        mount_editor_shell(app)

        response = TestClient(app).get("/editor/")

        assert response.status_code == 200
        assert "index-abc123.js" in response.text

    def test_serves_the_hashed_assets_the_index_references(self, tmp_path, monkeypatch):
        from dockb.editor_shell import mount_editor_shell

        dist = tmp_path / "dist"
        _write_dist(dist)
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(dist))
        app = create_app()
        mount_editor_shell(app)

        response = TestClient(app).get("/editor/assets/index-abc123.js")

        assert response.status_code == 200
        assert "export const x" in response.text

    def test_the_mount_does_not_shadow_the_api(self, tmp_path, monkeypatch):
        from dockb.editor_shell import mount_editor_shell

        dist = tmp_path / "dist"
        _write_dist(dist)
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(dist))
        app = create_app()
        mount_editor_shell(app)

        client = TestClient(app)
        assert client.get("/editor/").status_code == 200
        assert client.get("/api/auth/config").status_code == 200

    def test_a_built_file_cannot_take_over_a_real_route(self, tmp_path, monkeypatch):
        """Whatever the shell directory contains, it is served under /editor only.

        Static hosting that resolved paths against the site root would let a
        build artefact shadow ``/api/auth/config`` and answer in its place.
        """
        from dockb.editor_shell import mount_editor_shell

        dist = tmp_path / "dist"
        _write_dist(dist)
        # A build that emitted something named like a real route.
        (dist / "api").mkdir(exist_ok=True)
        (dist / "api" / "auth").mkdir(parents=True, exist_ok=True)
        (dist / "api" / "auth" / "config").write_text('{"login_required": false}', encoding="utf-8")
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(dist))
        app = create_app()
        mount_editor_shell(app)

        client = TestClient(app)
        assert client.get("/api/auth/config").json() != {"login_required": False}
        assert client.get("/editor/api/auth/config").text == '{"login_required": false}'


class TestMountPath:  # pylint: disable=too-few-public-methods
    def test_the_frontend_and_the_backend_name_the_same_path(self):
        """The window loads /editor/ and the backend mounts /editor.

        The path is written down twice, once in each language, and nothing else
        ties them together: if they drift the window loads a 404 with no error
        anywhere. This reads the TypeScript constant.
        """
        import re
        from pathlib import Path

        from dockb.editor_shell import EDITOR_MOUNT_PATH

        source = Path(__file__).resolve().parents[2] / "frontend" / "src" / "main" / "main.ts"
        match = re.search(r'const EDITOR_PATH = "([^"]+)"', source.read_text(encoding="utf-8"))
        assert match is not None, "EDITOR_PATH not found in frontend/src/main/main.ts"
        assert match.group(1) == f"{EDITOR_MOUNT_PATH}/"


class TestUnbuiltShell:
    def test_no_mount_when_the_directory_is_missing(self, tmp_path, monkeypatch):
        from dockb.editor_shell import mount_editor_shell

        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(tmp_path / "never-built"))
        app = create_app()

        mount_editor_shell(app)  # must not raise

        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert not any(p.startswith("/editor") for p in paths)

    def test_create_app_alone_serves_no_shell_when_it_is_unbuilt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(tmp_path / "never-built"))

        assert TestClient(create_app()).get("/editor/").status_code == 404

    def test_the_api_still_works_without_a_built_frontend(self, tmp_path, monkeypatch):
        from dockb.editor_shell import mount_editor_shell

        monkeypatch.setenv("DOCKB_FRONTEND_DIST", str(tmp_path / "never-built"))
        app = create_app()
        mount_editor_shell(app)

        client = TestClient(app)
        assert client.get("/api/auth/config").status_code == 200
        assert client.get("/editor/").status_code == 404
