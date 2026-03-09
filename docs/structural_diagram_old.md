# Conference Scheduler Aspirational Structural Diagram

```mermaid
flowchart LR

  subgraph FE["Next.js Frontend (/app)"]
    User["Landing Page and Symposium Attendee view <br/>app/pages/home.tsx"]
    Admin["Admin UI<br/>app/pages/admin.tsx"]
    DeptHead["Department Head UI<br/>app/pages/department-head.tsx"]
    Professor["Professor UI<br/>app/pages/professor.tsx"]
    Student["Student UI<br/>app/pages/student.tsx"]
    HealthWidget["Backend Status Widget<br/>app/components/backend-status.tsx"]
  end

  subgraph EP["FastAPI Endpoints"]
    POST["POST: Create new data in the database"]
    PUT["PUT: Modify data in the database"]
    GET["GET: Read data from the database"]
    DELETE["DELETE: Remove data from the database"]
  end

  subgraph API["FastAPI Backend (/backend/app)"]
    Main["main.py<br/>FastAPI router mount"]
    Security["security.py<br/>require_api_key()"]
    Events["routers/events.py<br/>API endpoints"]
    ReqSchemas["routers/request_schemas.py<br/>Pydantic request validation"]
    IORead["supabase_io/read.py"]
    IOWrite["supabase_io/write.py"]
    IODelete["supabase_io/delete.py<br/>cascading delete logic"]
    SBClient["supabase_io/client.py<br/>create_client() from env"]
  end

  subgraph DB["Supabase Tables (Postgres)"]
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

  User --> Admin
  User --> DeptHead
  User --> Professor
  User --> Student
  User --> HealthWidget

  User --> GET

  Admin --> POST
  Admin --> PUT
  Admin --> GET
  Admin --> DELETE

  DeptHead --> POST
  DeptHead --> PUT
  DeptHead --> GET
  DeptHead --> DELETE

  Professor --> POST
  Professor --> PUT
  Professor --> GET
  Professor --> DELETE

  Student --> POST
  Student --> PUT
  Student --> GET
  Student --> DELETE


  POST --> Main
  PUT --> Main
  GET --> Main
  DELETE --> Main

  Main --> Security
  Main --> Events
  Events --> ReqSchemas
  Events --> IORead
  Events --> IOWrite
  Events --> IODelete
  IORead --> SBClient
  IOWrite --> SBClient
  IODelete --> SBClient

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
 
## Citations

Diagram conventions and project references are listed in [../CITATIONS.md](../CITATIONS.md).
