"""Application entry point."""

# pylint: disable=invalid-name

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from dockb.app_factory import create_app
from dockb.composition import unwire, wire
from dockb.infrastructure.neo4j.session_factory import SessionFactory

app = create_app()

_session_factory: SessionFactory | None = None


@app.on_event("startup")
async def startup() -> None:
    """Load environment, change to run directory, initialise Neo4j, and wire services."""
    # pylint: disable=global-statement
    global _session_factory  # noqa: PLW0603
    load_dotenv()
    os.chdir(Path(__file__).resolve().parent.parent / "run")
    _session_factory = SessionFactory(
        uri=os.environ["NEO4J_URL"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    wire(_session_factory)


@app.on_event("shutdown")
async def shutdown() -> None:
    """Release Neo4j connection pool and unwire services."""
    unwire()
    if _session_factory is not None:
        _session_factory.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
