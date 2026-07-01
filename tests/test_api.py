import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.main import app
from api.models import Base, BiUser, DimAccount, DimCurrency, DimDepartment
from api.deps import get_db
from api.config import settings

TEST_DATABASE_URL = "sqlite:///./test_bi.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Seed test data
    db.add_all([
        DimCurrency(currency_code="RUB", currency_name="Рубль"),
        DimCurrency(currency_code="USD", currency_name="Доллар"),
        DimDepartment(department_name="Продажи", department_code="SALES"),
        DimAccount(account_code="OPEX-005", account_name="Канцелярия", account_type="opex", pnl_section="operating_profit"),
    ])
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_and_login():
    # Register
    r = client.post("/auth/register", json={
        "username": "testuser",
        "email": "test@local",
        "password": "secret123",
        "full_name": "Test User",
        "role": "admin"
    })
    assert r.status_code == 200
    # Login
    r = client.post("/auth/token", data={"username": "testuser", "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert len(token) > 0
    return token


def test_create_expense():
    token = test_register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/input/expenses", json={
        "expense_date": "2024-06-01",
        "account_id": 1,
        "expense_category": "Канцелярия",
        "expense_item": "Бумага А4",
        "currency_id": 1,
        "amount_original": "1500.00",
        "description": "Офисная бумага"
    }, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["expense_id"] is not None
    assert float(data["amount_rub"]) == 1500.0


def test_metrics_unauthorized():
    r = client.get("/metrics/pnl")
    assert r.status_code == 401


def test_metrics_pnl():
    token = test_register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/metrics/pnl?year=2024", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
