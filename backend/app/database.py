"""
اتصال قاعدة البيانات — نفس الكود يعمل على SQLite (تطوير) وPostgreSQL (إنتاج).
DATABASE_URL أمثلة:
  sqlite:///./dev.db
  postgresql+psycopg2://user:password@host:5432/excellence_platform

⚠️ غير مُختبر فعليًا في هذه البيئة (SQLAlchemy غير مثبَّتة، لا اتصال إنترنت).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
