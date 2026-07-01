from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from etl.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def close_db(db: Session) -> None:
    db.close()
