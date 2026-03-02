# Conference Scheduler Structural Documentation (Recommended Updates)

```mermaid
flowchart LR

  subgraph FE["Next.js Frontend (/app)"]
    Home["Home / Attendee View<br/>app/page.tsx"]
    Admin["Admin UI<br/>app/admin/page.tsx"]
    DeptHead["Department Head UI<br/>app/department-head/page.tsx"]
    Faculty["Faculty UI<br/>app/faculty/page.tsx"]
    Student["Student UI (local-only today)<br/>app/student/page.tsx"]
    HealthWidget["Backend Status Widget<br/>app/components/backend-status.tsx"]
  end

  subgraph EP["FastAPI Event Routes (/api/events/*)"]
    PAdd["POST /add_symposium<br/>POST /add_department<br/>POST /add_class<br/>POST /add_students<br/>POST /add_presentation<br/>POST /add_request"]
    PUpd["PUT /update_timeframes<br/>PUT /update_student<br/>PUT /update_professor<br/>PUT /update_class<br/>PUT /update_department<br/>PUT /update_symposium<br/>PUT /update_presentation"]
    PGet["GET /symposiums<br/>GET /symposiums/{id}<br/>GET /departments<br/>GET /classes<br/>GET /students<br/>GET /presentations<br/>GET /professors<br/>GET /timeframes<br/>GET /requests"]
    PDel["DELETE /delete_symposium<br/>DELETE /delete_department<br/>DELETE /delete_class<br/>DELETE /delete_student<br/>DELETE /delete_professor<br/>DELETE /delete_presentation"]
    PHealth["GET /health"]
  end

  subgraph API["FastAPI Backend (/backend/app)"]
    Main["main.py<br/>mounts /api router + API key dependency"]
    Security["security.py<br/>require_api_key()"]
    Events["routers/events.py<br/>route handlers"]
    ReqSchemas["routers/request_schemas.py<br/>Pydantic request validation"]
    IORead["supabase_io/read.py"]
    IOWrite["supabase_io/write.py"]
    IODelete["supabase_io/delete.py<br/>cascading deletes"]
    SBSchemas["supabase_io/supabase_schemas.py<br/>table models"]
    SBClient["supabase_io/client.py<br/>global supabase client"]
  end

  subgraph DB["Supabase Tables (Postgres)"]
    Symposiums["symposiums"]
    Timeframes["timeframes (linked_id for symposium/user availability)"]
    Departments["departments"]
    Classes["classes"]
    Professors["professors"]
    Students["students"]
    Presentations["presentations"]
    PresentingStudents["presenting_students"]
    ProfRequests["prof_requests"]
  end

  Home --> PGet
  Admin --> PAdd
  Admin --> PGet
  Admin --> PDel
  Admin --> PUpd
  DeptHead --> PAdd
  DeptHead --> PGet
  DeptHead --> PUpd
  DeptHead --> PDel
  Faculty --> PAdd
  Faculty --> PUpd
  Faculty --> PGet
  Faculty --> PDel
  Student --> PGet
  Student --> PAdd
  Student --> PUpd
  Student --> PDel
  HealthWidget --> PHealth

  PAdd --> Main
  PUpd --> Main
  PGet --> Main
  PDel --> Main

  Main --> Security
  Main --> Events
  Events --> ReqSchemas
  Events --> SBSchemas
  Events --> IORead
  Events --> IOWrite
  Events --> IODelete
  Events --> SBClient

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

## Route Drift You Should Decide How To Resolve

The frontend currently calls some REST-style routes that are not implemented in `backend/app/routers/events.py`:

- `GET /api/events/symposiums/{id}`
- `PUT /api/events/symposiums/{id}`
- `DELETE /api/events/symposiums/{id}`
- `PUT /api/events/departments/{id}`
- `DELETE /api/events/departments/{id}`

Backend currently provides:

- `PUT /api/events/update_symposium`
- `DELETE /api/events/delete_symposium`
- `DELETE /api/events/delete_department`

No direct `GET /symposiums/{id}` or `PUT /departments/{id}` route exists right now.

## Data/Control Flow Notes

1. `main.py` applies `require_api_key()` to all `/api/events/*` routes.
2. `events.py` validates request models using `request_schemas.py`.
3. `events.py` uses `read.py`, `write.py`, and `delete.py`, and also performs direct `supabase.table(...)` calls for some operations.
4. `timeframes.linked_id` is reused for symposium windows and person/entity availability records, not only symposium records.
