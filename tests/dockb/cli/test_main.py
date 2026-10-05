"""Tests for the ``dockb`` command that dispatches to each tool.

The value here is that one command exists for all three tools. A regression that made
``dockb users`` unreachable would otherwise only show up as a broken install.
"""

# ``capsys`` is requested for its side effect: capturing what a command printed.

# pylint: disable=unused-argument

import pytest

from dockb.cli import main as dispatcher
from dockb.cli import users


class TestDispatch:
    def test_it_reaches_the_users_command(self, capsys):
        """`dockb users` and `python -m dockb.cli.users` must be one program.

        Asserted on what only the users command does — the account store's own
        configuration error — so this fails if the dispatcher stops reaching it.
        """
        assert dispatcher.main(["users", "list"]) == 1
        assert "DOCKB_SECRET_KEY" in capsys.readouterr().err

    def test_it_passes_the_remaining_arguments_through(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DOCKB_SECRET_KEY", "a-server-secret")
        monkeypatch.setattr(users, "resolve_document_base_dir", lambda *a, **k: tmp_path)
        assert dispatcher.main(["users", "create", "--username", "abby", "--email", "a@example.com"]) == 0
        assert "created abby" in capsys.readouterr().out

    @pytest.mark.parametrize("argv", [[], ["typo"], ["--help"]])
    def test_an_unknown_command_is_a_usage_error(self, argv, capsys):
        """2 is argparse's code for a malformed command line, so a typo reads like one."""
        assert dispatcher.main(argv) == 2

    def test_the_usage_lists_every_command(self, capsys):
        """A command nobody can discover is a command nobody will run."""
        dispatcher.main(["typo"])
        err = capsys.readouterr().err
        for command in ("users", "import-document", "reconstruct-chapter"):
            assert command in err
