from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.app.config import settings
from backend.app.database.schema import Base

# Determine our target database URL
# If DATABASE_URL points to postgres default, we will automatically try to create orx_outreach database
target_db_url = settings.DATABASE_URL
if "localhost:5432/postgres" in target_db_url:
    # Try to create orx_outreach database
    try:
        temp_engine = create_engine("postgresql://aziz@localhost:5432/postgres", isolation_level="AUTOCOMMIT")
        with temp_engine.connect() as conn:
            conn.execute(text("CREATE DATABASE orx_outreach"))
        print("Database 'orx_outreach' created successfully.")
    except Exception as e:
        # DB already exists or cannot create
        pass
    # Override settings for standard local postgres setup
    target_db_url = target_db_url.replace("/postgres", "/orx_outreach")

engine = create_engine(target_db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Create all tables in the database
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized.")
