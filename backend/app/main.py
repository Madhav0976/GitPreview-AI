from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter
from app.api.health import router as health_router
from app.api.analyze import router as analyze_router
from app.api.run_analysis import router as run_analysis_router

app = FastAPI(
    title="GitPreview AI Backend",
    description="API for repository analysis, metadata preview, and run analysis.",
    version="0.2.0",
)

# Connect slowapi limiter
app.state.limiter = limiter


def rate_limit_custom_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler returning clear JSON error conforming to standard API detail schema."""
    response = JSONResponse(
        {"detail": f"Rate limit exceeded: {exc.detail}. Please try again later."},
        status_code=429,
    )
    if hasattr(request.state, "view_rate_limit") and hasattr(request.app.state, "limiter"):
        response = request.app.state.limiter._inject_headers(
            response, request.state.view_rate_limit
        )
    return response


app.add_exception_handler(RateLimitExceeded, rate_limit_custom_handler)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://git-preview-ai.vercel.app",
        "https://gitpreview-ai.vercel.app",
    ],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(run_analysis_router, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "GitPreview AI backend is running."
    }