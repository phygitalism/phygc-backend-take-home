"""Create tables and seed two demo workspaces. Safe to run repeatedly.

Usage: python -m app.scripts.init_db
"""

from sqlalchemy import select

from app import billing
from app.db import Base, SessionLocal, engine
from app.models import Workspace

DEMO_WORKSPACES = (
    ("Alpha Studio", "ws_alpha_demo_key", 500),
    ("Beta Labs", "ws_beta_demo_key", 500),
)


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        for name, api_key, credits in DEMO_WORKSPACES:
            exists = session.scalar(select(Workspace).where(Workspace.api_key == api_key))
            if exists:
                continue
            workspace = Workspace(name=name, api_key=api_key, credits=0)
            session.add(workspace)
            session.flush()
            billing.top_up(session, workspace, credits, note="demo seed")
            print(f"created workspace {name!r} with API key {api_key}")
        session.commit()


if __name__ == "__main__":
    main()
