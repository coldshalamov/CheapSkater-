import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import from app
from app.dashboard import app, get_session
from app.storage.models_sql import Base, Store

def test_florida_ingest_region_fix():
    """Verify that ingesting a FL deal sets the store region to FL."""
    
    # 1. Setup in-memory DB
    engine = create_engine(
        "sqlite:///:memory:", 
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    
    # DEBUG: Check tables
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        print(f"DEBUG: Created tables in memory DB: {tables}")

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_db

    try:
        client = TestClient(app)

        payload = {
            "source": "test_script",
            "deals": [
                {
                    "store_id": "1109",
                    "store_name": "Lowe's of Stuart, FL (#1109)",
                    "product_url": "https://www.lowes.com/pd/Test-Item/50012345",
                    "title": "Florida Palm Tree",
                    "price": 50.0,
                    "was_price": 100.0,
                    "pct_off": 0.50,
                    "found_at": "2026-01-21T12:00:00Z"
                }
            ]
        }

        response = client.post("/api/ingest", json=payload)
        assert response.status_code == 200, f"Ingest failed: {response.text}"

        db = TestingSessionLocal()
        store = db.query(Store).filter(Store.id == "1109").first()

        assert store is not None, "Store was not created"
        print(f"Store: {store.name}, State: {store.state}, Region: {store.region}")

        assert store.state == "FL", f"Expected state FL, got {store.state}"
        assert store.region == "FL", f"Expected region FL, got {store.region} - FIX FAILED"

        db.close()
    finally:
        app.dependency_overrides.pop(get_session, None)
