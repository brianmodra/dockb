"""Tests for SessionFactory."""

from unittest.mock import MagicMock, patch

from dockb.infrastructure.neo4j.session_factory import SessionFactory


class TestSessionFactoryCreate:  # pylint: disable=too-few-public-methods
    def test_creates_driver_with_uri_and_auth(self):
        with patch("dockb.infrastructure.neo4j.session_factory.GraphDatabase.driver") as mock_driver:
            factory = SessionFactory("bolt://localhost:7687", user="neo4j", password="test")
            mock_driver.assert_called_once_with("bolt://localhost:7687", auth=("neo4j", "test"))
            factory.close()


class TestSessionFactorySession:
    def test_session_context_manager_yields_session(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        with patch(
            "dockb.infrastructure.neo4j.session_factory.GraphDatabase.driver",
            return_value=mock_driver,
        ):
            factory = SessionFactory("bolt://localhost:7687", user="neo4j", password="test")
            with factory.session() as session:
                assert session is mock_session

            factory.close()

    def test_session_context_manager_enters_and_exits(self):
        mock_driver = MagicMock()
        mock_context = MagicMock()
        mock_driver.session.return_value = mock_context

        with patch(
            "dockb.infrastructure.neo4j.session_factory.GraphDatabase.driver",
            return_value=mock_driver,
        ):
            factory = SessionFactory("bolt://localhost:7687", user="neo4j", password="test")
            with factory.session():
                pass

            mock_driver.session.assert_called_once_with()
            mock_context.__enter__.assert_called_once()
            mock_context.__exit__.assert_called_once()
            factory.close()


class TestSessionFactoryClose:
    def test_close_closes_driver(self):
        mock_driver = MagicMock()

        with patch(
            "dockb.infrastructure.neo4j.session_factory.GraphDatabase.driver",
            return_value=mock_driver,
        ):
            factory = SessionFactory("bolt://localhost:7687", user="neo4j", password="test")
            factory.close()
            mock_driver.close.assert_called_once()

    def test_close_is_idempotent(self):
        mock_driver = MagicMock()

        with patch(
            "dockb.infrastructure.neo4j.session_factory.GraphDatabase.driver",
            return_value=mock_driver,
        ):
            factory = SessionFactory("bolt://localhost:7687", user="neo4j", password="test")
            factory.close()
            factory.close()
            mock_driver.close.assert_called_once()
