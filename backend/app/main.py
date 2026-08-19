from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database.connection import init_db
from backend.app.routes import leads, analytics

app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set CORS origins to allow React dev server requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development we can allow all, or configure to localhost:5173
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup Database Init
@app.on_event("startup")
def on_startup():
    init_db()

# Register Routers
app.include_router(leads.router, prefix=settings.API_V1_STR)
app.include_router(analytics.router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": "1.0.0"
    }
