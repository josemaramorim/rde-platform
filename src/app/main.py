from fastapi import FastAPI
from src.app.routes import auth, dashboard, websocket, broker
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings

app = FastAPI(title="RDE API - Previsualização")

# ✅ CORS Configuration - Whitelist only allowed origins  
allowed_origins = settings.get_allowed_origins_list()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
app.include_router(broker.router, prefix="/broker", tags=["Broker"])


@app.get("/")
def root():
    return {"message": "RDE API Running"}

@app.get("/health")
def health():
    """Health check endpoint for Kubernetes and monitoring."""
    return {"status": "ok"}
