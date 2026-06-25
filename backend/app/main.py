from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.analyze import router as analyze_router

app = FastAPI(
    title="GitPreview AI Backend",
    description="API for repository analysis and metadata preview.",
    version="0.1.0",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://git-preview-ai.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(health_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "GitPreview AI backend is running."
    }