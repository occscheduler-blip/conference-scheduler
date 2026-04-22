# Conference Scheduler Structural Documentation (Recommended Updates)

```mermaid
flowchart LR

  classDef unimplemented fill:#f0f4f8,stroke:#90a4ae,stroke-dasharray:6 4,color:#546e7a

  subgraph FE["Next.js Frontend (/app)"]
    Home["Home / Attendee View<br/>app/pages/home.tsx"]
    Admin["Admin UI<br/>app/pages/admin.tsx"]
    DeptHead["Department Head UI<br/>app/pages/department-head.tsx"]
    Professor["Professor UI<br/>app/pages/professor.tsx"]
    Student["Student UI (local-only today)<br/>app/pages/student.tsx"]
    HealthWidget["Backend Status Widget (defined, not mounted)<br/>app/components/backend-status.tsx"]
  end

  PHealth["GET /health<br/>(main.py, no auth)"]

  subgraph EP["FastAPI Event Routes (/api/events/*)"]
    PAdd["POST /add_symposium<br/>POST /add_department<br/>POST /add_class<br/>POST /add_students<br/>POST /add_presentation<br/>POST /add_request"]
    PUpd["PUT /update_timeframes<br/>PUT /update_student<br/>PUT /update_professor<br/>PUT /update_class<br/>PUT /update_department<br/>PUT /update_symposium<br/>PUT /update_presentation"]
    PGet["GET /symposia<br/>GET /symposia/{id}<br/>GET /departments<br/>GET /classes<br/>GET /students<br/>GET /presentations<br/>GET /professors<br/>GET /timeframes<br/>GET /requests"]
    PDel["DELETE /delete_symposium<br/>DELETE /delete_department<br/>DELETE /delete_class<br/>DELETE /delete_student<br/>DELETE /delete_professor<br/>DELETE /delete_presentation"]
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
    Scheduler["scheduler/ (planned)<br/>assign presentations to rooms + timeslots"]:::unimplemented
  end

  subgraph DB["Supabase Tables (Postgres)"]
    Symposia["symposia"]
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

  PHealth --> Main
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

  Events -.-> Scheduler

  IORead --> SBClient
  IOWrite --> SBClient
  IODelete --> SBClient
  Scheduler -.-> IORead
  Scheduler -.-> IOWrite

  SBClient --> Symposia
  SBClient --> Timeframes
  SBClient --> Departments
  SBClient --> Classes
  SBClient --> Professors
  SBClient --> Students
  SBClient --> Presentations
  SBClient --> PresentingStudents
  SBClient --> ProfRequests
```

## Scheduling Algorithm (Planned)

The scheduling logic is not yet implemented — this is expected at the current stage. When built, it should live at `backend/app/scheduler/` and be invoked by `events.py` (likely via a new `POST /api/events/schedule` route triggered from the Admin UI).

**Inputs it will need:**
- All presentations for a symposium (duration in minutes, assigned class/department)
- Available timeframes per professor/presenter (from `timeframes` table via `linked_id`)
- Symposium timeframes (start/end windows, number of rooms available from `symposia.rooms_available`)

**Output:**
- Write `start_time` and `end_time` back to each `presentations` row (fields already exist in the schema but are currently `null`)

**Constraints to resolve:**
- No two presentations in the same room overlap
- A presenter is not double-booked across rooms
- Each presentation fits within a valid symposium timeframe window
- Presenter availability windows are respected

Dashed arrows in the diagram indicate the planned (unimplemented) call path.

---

## Route Drift You Should Decide How To Resolve

The frontend currently calls some REST-style routes that are not implemented in `backend/app/routers/events.py`:

- `PUT /api/events/symposia/{id}`
- `DELETE /api/events/symposia/{id}`
- `PUT /api/events/departments/{id}`
- `DELETE /api/events/departments/{id}`

Backend currently provides action-style equivalents:

- `PUT /api/events/update_symposium`
- `DELETE /api/events/delete_symposium`
- `DELETE /api/events/delete_department`

Note: `GET /api/events/symposia/{id}` is implemented — it was previously listed here in error.

## Data/Control Flow Notes

1. `main.py` applies `require_api_key()` to all `/api/events/*` routes.
2. `events.py` validates request models using `request_schemas.py`.
3. `events.py` uses `read.py`, `write.py`, and `delete.py`, and also performs direct `supabase.table(...)` calls for some operations.
4. `timeframes.linked_id` is reused for symposium windows and person/entity availability records, not only symposium records.

## Citations

Diagram conventions and project references are listed in [../CITATIONS.md](../CITATIONS.md).
