from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from deps import engine
from models import Base
from routers import alerts, auth, input, metrics, admin, db, etl, realtime, forecast


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from etl.scheduler import start_scheduler
    start_scheduler()
    yield
    from etl.scheduler import shutdown_scheduler
    shutdown_scheduler()


app = FastAPI(
    title="BI Platform API",
    description="Корпоративная система бизнес-аналитики — API для ввода данных, авторизации и метрик",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(input.router, prefix="/input", tags=["input"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(db.router, prefix="/db", tags=["db"])
app.include_router(etl.router, prefix="/etl", tags=["etl"])
app.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(forecast.router, prefix="/forecast", tags=["forecast"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
