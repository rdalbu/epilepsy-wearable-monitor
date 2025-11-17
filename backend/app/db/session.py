from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Conexão com PostgreSQL local
# Formato: postgresql://usuario:senha@host:porta/nome_do_banco
DATABASE_URL = "postgresql://postgres:123456@localhost:5432/pulseira"

engine = create_engine(
    DATABASE_URL,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

Base = declarative_base()


def get_db():
  from sqlalchemy.orm import Session

  db: Session = SessionLocal()
  try:
      yield db
  finally:
      db.close()

