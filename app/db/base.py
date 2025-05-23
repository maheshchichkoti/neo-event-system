from sqlalchemy.orm import declarative_base

# Only defines the declarative base. No engine or session here.
# Keeps this safe to import in both FastAPI and Alembic environments.
Base = declarative_base()