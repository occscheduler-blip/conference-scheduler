# Conference Scheduler Structural Diagram

```mermaid
flowchart LR
  User["User Browser"]

  subgraph FE["Next.js Frontend (/app)"]
    Home["Home<br/>app/page.tsx"]
    Admin["Admin UI<br/>app/admin/page.tsx"]
    Faculty["Faculty UI<br/>app/faculty/page.tsx"]
    DeptHead["Department Head UI<br/>app/department-head/page.tsx"]
    Student["Student UI<br/>app/student/page.tsx"]
    HealthWidget["Backend Status Widget<br/>app/components/backend-status.tsx"]
  end

  subgraph API["FastAPI Backend (/backend/app)"]
    Main["main.py<br/>FastAPI app + CORS + router mount"]
    Security["security.py<br/>require_api_key()"]
    Events["routers/events.py<br/>CRUD + orchestration"]
    ReqSchemas["routers/request_schemas.py<br/>Pydantic request validation"]
    IORead["supabase_io/read.py"]
    IOWrite["supabase_io/write.py"]
    IODelete["supabase_io/delete.py<br/>cascading delete logic"]
    SBClient["supabase_io/client.py<br/>create_client() from env"]
  end

  subgraph DB["Supabase (Postgres tables)"]
    Symposiums["symposiums"]
    Timeframes["timeframes"]
    Departments["departments"]
    Classes["classes"]
    Professors["professors"]
    Students["students"]
    Presentations["presentations"]
    PresentingStudents["presenting_students"]
    ProfRequests["prof_requests"]
  end

  User --> Home
  Home --> Admin
  Home --> Faculty
  Home --> DeptHead
  Home --> Student
  Home --> HealthWidget

  Admin -->|"GET /api/events/symposiums"| Main
  Admin -->|"GET /api/events/timeframes?linked_id=..."| Main
  Admin -->|"POST /api/events/add_symposium"| Main
  Admin -->|"POST /api/events/add_department"| Main
  Faculty -->|"GET /api/events/professors/classes/departments/symposiums"| Main
  Faculty -->|"GET /api/events/timeframes?linked_id=..."| Main
  Faculty -.->|"POST /api/events/upload-students-csv (not implemented in router)"| Main
  DeptHead -->|"GET /api/events/symposiums"| Main
  DeptHead -->|"GET /api/events/departments?symposium_id=..."| Main
  DeptHead -->|"POST /api/events/add_class"| Main
  DeptHead -->|"DELETE /api/events/delete_professor"| Main
  DeptHead -->|"DELETE /api/events/delete_class"| Main
  HealthWidget -->|"GET /health"| Main

  Main --> Security
  Main --> Events
  Events --> ReqSchemas
  Events --> IORead
  Events --> IOWrite
  Events --> IODelete
  IORead --> SBClient
  IOWrite --> SBClient
  IODelete --> SBClient
  Events --> SBClient

  SBClient --> Symposiums
  SBClient --> Timeframes
  SBClient --> Departments
  SBClient --> Classes
  SBClient --> Professors
  SBClient --> Students
  SBClient --> Presentations
  SBClient --> PresentingStudents
  SBClient --> ProfRequests
```

## Data and Control Flow

1. Frontend pages call backend endpoints using `NEXT_PUBLIC_BACKEND_URL`; protected API calls include `X-API-Key` from `NEXT_PUBLIC_BACKEND_API_KEY`.
2. `backend/app/main.py` mounts `/api/events/*` with a dependency on `require_api_key`, so all event routes are API-key protected.
3. `routers/events.py` validates request payloads via `request_schemas.py`, then performs table operations through:
   - `supabase_io/write.py` for inserts
   - `supabase_io/read.py` for queries
   - `supabase_io/delete.py` for recursive/cascading deletes
4. Data is persisted in Supabase tables, with `symposiums -> departments -> classes -> (professors, students, presentations)` and join-like helper tables (`presenting_students`, `prof_requests`).

## Notable Integration Gaps (Current Code)

1. Frontend calls `POST /api/events/upload-students-csv`, but `backend/app/routers/events.py` does not define this route.
2. Department Head page expects `professor_ids` from `POST /api/events/add_class`, but backend currently returns no `professor_ids`.
