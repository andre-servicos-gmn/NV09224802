"""
FastAPI application for Nouvaris backend API.

Provides HTTP endpoints for:
- Webhook integrations (Shopify, etc.)
- Health checks
- Future: Admin API, Analytics, etc.

Security:
- CORS configured for specific origins only
- Rate limiting on sensitive endpoints
- Request logging with sensitive data redaction
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv
# Load .env from project root (parent of backend folder)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path)

from app.api.webhooks import router as webhooks_router
from app.api.chat import router as chat_router
from app.api.upload import router as upload_router
from app.api.tenants import router as tenants_router
from app.api.handoff import router as handoff_router
from app.api.conversations import router as conversations_router


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Nouvaris API server...")
    yield
    logger.info("Shutting down Nouvaris API server...")


# Create FastAPI app
app = FastAPI(
    title="Nouvaris API",
    description="Backend API for Nouvaris AI agents platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("DEBUG") else None,  # Disable docs in production
    redoc_url="/redoc" if os.getenv("DEBUG") else None,
)


# CORS configuration - restrict to known origins only
ALLOWED_ORIGINS = [
    "https://nouvaris.com",
    "https://app.nouvaris.com",
    "https://dashboard.nouvaris.com",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

# Add localhost for development
if os.getenv("DEBUG"):
    ALLOWED_ORIGINS.extend([
        # Extra debug origins if needed
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods including OPTIONS
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with sensitive data redaction."""
    # Redact sensitive headers
    safe_headers = {
        k: v if k.lower() not in ("authorization", "x-shopify-hmac-sha256") else "[REDACTED]"
        for k, v in request.headers.items()
    }
    
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"client={request.client.host if request.client else 'unknown'}"
    )
    
    response = await call_next(request)
    
    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"status={response.status_code}"
    )
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions without leaking internal details."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


from app.api.auth import router as auth_router

# Register routers
app.include_router(webhooks_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(tenants_router)
app.include_router(auth_router)
app.include_router(handoff_router)
app.include_router(conversations_router)

@app.post("/test-post")
async def test_post():
    return {"status": "ok"}

# Root endpoint
@app.get("/", summary="API root")
async def root():
    """API root endpoint."""
    return {
        "service": "Nouvaris API",
        "version": "1.0.0",
        "status": "running",
        "reloaded": True,
        "v": 2
    }


@app.get("/health", summary="Health check")
async def health():
    """Global health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "").lower() in ("true", "1")
    
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
    )
