# NeoFi Backend Challenge: Collaborative Event Management System

This project is a RESTful API for a collaborative event scheduling application, developed as a backend challenge for NeoFi. It allows users to create, manage, and share events with role-based permissions and maintains a comprehensive history of changes.

**Live Application URL (Render):** `https://neo-event-system.onrender.com`
**API Documentation (Swagger UI):** `https://neo-event-system.onrender.com/docs`
**API Documentation (ReDoc):** `https://neo-event-system.onrender.com/redoc`

## Features Implemented

**Core Requirements:**

- **Authentication & Authorization:**
  - Secure user registration (`/auth/register`).
  - Token-based authentication (JWT access and refresh tokens) via `/auth/login`.
  - Token refresh mechanism (`/auth/refresh`).
  - Conceptual user logout (`/auth/logout` - client-side token discard).
  - Role-Based Access Control (RBAC) with roles: `Owner`, `Editor`, `Viewer`.
- **Event Management:**
  - Full CRUD operations for events:
    - Create new event (`/events/`) - creator becomes Owner.
    - Get specific event by ID (`/events/{id}`).
    - Update event by ID (`/events/{id}`) - creates new version.
    - Delete event by ID (`/events/{id}`).
  - Support for recurring events using `rrule` patterns.
  - Listing events (`/events/`) with pagination and filtering (including date range filtering that expands recurring events).
  - Batch event creation (`/events/batch`).
- **Collaboration Features:**
  - Event sharing system with granular permissions (`Owner`, `Editor`, `Viewer`).
    - Share event (`/events/{id}/share`).
    - List permissions for an event (`/events/{id}/permissions`).
    - Update user permissions (`/events/{id}/permissions/{userId}`).
    - Remove user access (`/events/{id}/permissions/{userId}`).
  - Edit history with attribution (tracked via `EventVersion` records).
- **Advanced Features:**
  - Versioning system for events:
    - Get specific historical version of an event (`/events/{id}/history/{versionId}`).
    - Rollback event to a previous version (`/events/{id}/rollback/{versionId}`).
  - Changelog & Diff:
    - Get chronological changelog for an event (`/events/{id}/changelog`).
    - Get a diff between two event versions (`/events/{id}/diff/{versionId1}/{versionId2}`).
  - Atomic operations for critical database changes (e.g., event and its first version are created transactionally).

**Technical Requirements Met:**

- Built with Python and FastAPI.
- Data validation and error handling using Pydantic and FastAPI's mechanisms.
- Database schema designed to support all implemented features (PostgreSQL).
- Automatic API documentation via OpenAPI/Swagger (and ReDoc).
- Dockerized application for consistent environments and deployment.
- Alembic for database migrations.

**Features Not Implemented (or Partially Implemented):**

- **Conflict Detection for Overlapping Events:** This advanced feature was not fully implemented due to time constraints. Basic groundwork for time-based queries exists.
- **Event Conflict Resolution Strategies:** Dependent on conflict detection.
- **Real-time Notifications for Changes:** Considered out of scope for a standard REST API backend challenge unless WebSockets were explicitly requested.
- **Rate Limiting:** Not implemented in this version, but `slowapi` could be integrated.
- **MessagePack Serialization:** JSON is supported; MessagePack was a lower priority.
- **Caching:** Not implemented in this version.
- **Automated Tests:** Marked as optional in the challenge; not included in this submission.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy (with `asyncpg` for asynchronous operations)
- **Migrations:** Alembic
- **Data Validation/Serialization:** Pydantic
- **Authentication:** JWT (python-jose), Passlib (for password hashing)
- **Recurring Events:** python-dateutil (for rrule parsing and generation)
- **Diffing:** deepdiff
- **Containerization:** Docker, Docker Compose
- **Dependency Management:** Poetry

## Project Structure

Use code with caution.
Markdown
neo-event-system/
├── alembic/ # Alembic migration scripts and configuration
├── app/ # Main application source code
│ ├── api/ # API specific code (routers, dependencies)
│ │ └── v1/
│ │ ├── deps.py # FastAPI dependencies (e.g., get_current_user)
│ │ └── endpoints/ # API endpoint routers (auth, events, collaboration)
│ ├── core/ # Core components (config, security)
│ ├── crud/ # Database interaction logic (Create, Read, Update, Delete)
│ ├── db/ # Database setup (engine, session, Base) and models
│ ├── schemas/ # Pydantic schemas for data validation & serialization
│ └── main.py # FastAPI application entry point
├── .env.example # Example environment variables file
├── .gitignore
├── alembic.ini # Alembic main configuration
├── docker-compose.yml # Docker Compose setup for local development
├── Dockerfile # Dockerfile for the API service
├── poetry.lock # Poetry lock file
├── pyproject.toml # Poetry project & dependency definition
└── README.md # This file

## Setup and Running Locally

**Prerequisites:**

- Docker
- Docker Compose
- Poetry (for managing Python dependencies if you wish to run outside Docker or inspect)

**1. Clone the Repository:**

````bash
git clone https://github.com/[YOUR_GITHUB_USERNAME]/neo-event-system.git
cd neo-event-system
Use code with caution.
2. Configure Environment Variables:
Copy the example environment file and customize it if needed (though defaults should work for local Docker setup):
cp .env.example .env
Use code with caution.
Bash
The default .env is configured for the docker-compose setup using the service name db for the PostgreSQL host. Key variables:
DATABASE_URL: For the FastAPI application (e.g., postgresql+asyncpg://user:password@db:5432/neo_events_db)
SYNC_DATABASE_URL: For Alembic running locally (e.g., postgresql://user:password@localhost:5432/neo_events_db)
SECRET_KEY: A strong secret key for JWTs.
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB: Credentials for the PostgreSQL container.
3. Build and Run with Docker Compose:
This will build the API image and start the API and PostgreSQL database services.
docker-compose up --build -d
Use code with caution.
Bash
-d runs the containers in detached mode.
The API will be available at http://localhost:8000.
4. Apply Database Migrations:
Once the containers are running, apply the database migrations using Alembic. This command executes Alembic inside the running api container.
docker-compose exec api alembic upgrade head
Use code with caution.
Bash
You might need to wait a few seconds after docker-compose up for the database service to be fully ready before running migrations.
5. Accessing the API:
API Documentation (Swagger UI): http://localhost:8000/docs
API Documentation (ReDoc): http://localhost:8000/redoc
API Usage Highlights
Register a User:
POST /api/v1/auth/register
Body: { "username": "testuser", "email": "test@example.com", "password": "strongpassword" }
Login:
POST /api/v1/auth/login
Body (form-data): username=testuser&password=strongpassword
Response will contain access_token and refresh_token.
Authenticated Requests:
For all subsequent requests to protected endpoints, include the access_token in the Authorization header:
Authorization: Bearer <your_access_token>
Create an Event:
POST /api/v1/events/
Body:
{
  "title": "My New Event",
  "description": "Details about the event.",
  "start_time": "2024-07-01T10:00:00Z",
  "end_time": "2024-07-01T11:00:00Z",
  "location": "Conference Room A",
  "is_recurring": false,
  "recurrence_pattern": null
}
Use code with caution.
Json
List Events (with recurring expansion):
GET /api/v1/events/?startTime=2024-07-01T00:00:00Z&endTime=2024-07-07T23:59:59Z
Key Architectural Decisions
FastAPI: Chosen for its high performance, asynchronous capabilities, built-in data validation with Pydantic, and automatic OpenAPI documentation, making it ideal for modern API development.
PostgreSQL: A robust and feature-rich relational database well-suited for complex data relationships and transactional integrity required by this application.
SQLAlchemy with asyncpg: Provides a powerful ORM for Python with asynchronous support, enabling non-blocking database operations.
Alembic: Used for database schema migrations, allowing for version-controlled and manageable database evolution.
Event Versioning: Implemented by storing full snapshots of event data in a separate EventVersion table each time an event is modified. The main Event table points to the current active version. This facilitates rollback and diffing.
Recurring Events: Handled by storing an rrule string (RFC 5545) and expanding occurrences on-the-fly for list views with date filters using the python-dateutil library.
Modularity: The application is structured into logical components (API endpoints, CRUD operations, schemas, core services, database models) to promote separation of concerns and maintainability.
This README should provide a solid overview for anyone looking at your project. Remember to replace placeholders and confirm all details. Good luck with your submission!
**Key things to double-check and fill in for your `README.md`:**

*   **`[YOUR_GITHUB_USERNAME]`**: Update this in the clone URL.
*   **Deployed Links**: Confirm they are correct.
*   **Features Implemented/Not Implemented**: Make sure this list accurately reflects the final state of your project. Be honest about what you couldn't get to.
*   **`.env.example`**: Create this file in your project root. It should list all necessary environment variables with placeholder or example values, e.g.:
    ```ini
    # .env.example
    # For FastAPI Application (used by app/core/config.py)
    DATABASE_URL="postgresql+asyncpg://user:password@db:5432/neo_events_db"
    SECRET_KEY="a_very_strong_random_secret_key_for_jwt_please_change_in_production"
    ALGORITHM="HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES=30
    REFRESH_TOKEN_EXPIRE_DAYS=7

    # For Alembic (if SYNC_DATABASE_URL is used in alembic/env.py for local runs)
    # This is for running `alembic` commands directly on your host against the Dockerized DB
    SYNC_DATABASE_URL="postgresql://user:password@localhost:5432/neo_events_db"

    # For Docker Compose (used by docker-compose.yml to set up the DB container)
    POSTGRES_USER=user
    POSTGRES_PASSWORD=password
    POSTGRES_DB=neo_events_db
    ```
````
