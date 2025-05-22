# app/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession # Keep this for the health check example

# from app.db.base import engine, Base # Not strictly needed here if Alembic handles everything
# from app.core.config import settings # Not strictly needed here
# from app.db import models # Models are used by Alembic and CRUD/Schemas, not directly here usually

# Import the get_db dependency for the health check
from app.db.base import get_db

# Import API routers
from app.api.v1.endpoints import auth as auth_router
from app.api.v1.endpoints import events as events_router # ADD THIS IMPORT
from app.api.v1.endpoints import collaboration as collaboration_router # ADD THIS

# Create an instance of the FastAPI class
app = FastAPI(
    title="NeoFi Collaborative Event Management API",
    version="0.1.0",
    description="API for creating, managing, and sharing events collaboratively.",
    # openapi_url="/api/v1/openapi.json" # Optional: Custom OpenAPI path
    # root_path="/api/v1" # Optional: if you deploy behind a proxy that strips /api/v1
)

# Startup event: This should be REMOVED or COMMENTED OUT
# Alembic is now responsible for database schema management.
# @app.on_event("startup")
# async def startup_event():
#     async with engine.begin() as conn:
#         # await conn.run_sync(Base.metadata.drop_all) # Use with caution
#         await conn.run_sync(Base.metadata.create_all) # REMOVE THIS LINE


@app.get("/")
async def read_root():
    """
    Root endpoint for the API.
    """
    return {"message": "Welcome to the NeoFi Event Management API!"}


@app.get("/health", tags=["Health"]) # Added a tag for better organization in docs
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Perform a health check of the API and database connection.
    """
    try:
        # Example: A simple query to check DB connection
        # from sqlalchemy import text
        # result = await db.execute(text("SELECT 1"))
        # if result.scalar_one() != 1:
        #     raise HTTPException(status_code=503, detail="Database connectivity issue: Query failed")
        return {"status": "ok", "message": "API is healthy and database connection seems okay."}
    except ConnectionRefusedError: # More specific error for DB connection refusal
         raise HTTPException(status_code=503, detail="Database connection refused.")
    except Exception as e:
        # In a real scenario, log the error `e`
        # logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"API health check failed: An error occurred with the database connection.")


# Include API routers
# The prefix here means all routes in auth_router will start with /api/v1/auth
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(events_router.router, prefix="/api/v1/events", tags=["Events"]) # Uncomment when events router is ready
app.include_router(collaboration_router.router, prefix="/api/v1", tags=["Collaboration"]) # Prefix is /api/v1 because routes are /events/{id}/...

# This block is useful if you want to run this file directly with `python app/main.py`
# However, Uvicorn is typically run from the command line for more control:
# `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
if __name__ == "__main__":
    import uvicorn
    # Note: --reload should generally not be used in this __main__ block for production.
    # It's better controlled via the CLI command.
    uvicorn.run(app, host="0.0.0.0", port=8000)

    