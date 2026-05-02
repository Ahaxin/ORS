from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import Base

engine = create_engine("sqlite:///ors.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

def create_tables():
    Base.metadata.create_all(engine)

def get_db():
    with SessionLocal() as session:
        yield session
