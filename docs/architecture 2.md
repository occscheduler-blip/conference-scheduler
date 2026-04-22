# Conference Scheduler — Architecture & Code Reference

> Generated on 2026-03-03. Last updated 2026-04-01 — some file references may be outdated after cleanup refactors.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Tech Stack](#tech-stack)
3. [Frontend (Detailed)](#frontend-detailed)
4. [Backend (Detailed)](#backend-detailed)
   - [Entry Point & Middleware](#entry-point--middleware)
   - [Configuration](#configuration)
   - [Authentication](#authentication)
   - [Logging](#logging)
   - [Database Schemas](#database-schemas)
   - [Supabase I/O Layer](#supabase-io-layer)
   - [Request Schemas](#request-schemas)
   - [API Endpoints](#api-endpoints)
5. [Data Model & Relationships](#data-model--relationships)
6. [Environment & Startup](#environment--startup)

---

## Project Overview

A full-stack web application for scheduling academic conference/symposium presentations at Hamilton College. Different user roles (Admin, Department Head, Professor, Student) each have a dedicated interface for managing their part of the scheduling workflow.

**High-level data hierarchy:**

```
Symposium
└── Departments
    └── Classes
        ├── Professors
        └── Students
            └── Presentations (groups of students)
```

Timeframes (available time windows) attach polymorphically to Symposia, Professors, and Students via a shared `linked_id` foreign key.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4 |
| Backend | Python, FastAPI, Pydantic v2 |
| Database | Supabase (hosted Postgres) |
| Auth | Static API key via `X-API-Key` header |
| Testing | pytest |

---

## Frontend (Detailed)

The frontend lives in `/app` and uses the **Next.js 16 App Router** with file-based routing. Every page is a self-contained `"use client"` component with local React state and inline `fetch` logic. There is no external state management library.

### Common Patterns

**API calls** — all pages read two environment variables and attach the API key as a header:
```typescript
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const apiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";

const res = await fetch(`${backendUrl}/api/events/symposia`, {
  headers: { "X-API-Key": apiKey }
});
```

**Response normalization** — the backend sometimes returns `{data: [...]}` and sometimes a raw array. Pages handle both:
```typescript
const raw = await res.json();
const items = Array.isArray(raw) ? raw : (raw?.data ?? []);
```

**Shared utilities** (duplicated in each page file):
- `parseBackendDateTime(str)` — converts ISO timestamp strings to `Date` objects, clamping timezone offsets
- `toMessage(err)` — extracts a human-readable string from various error shapes
- `normalizeId(id)` — lowercases and trims IDs for comparison
- `buildCalendarDates(start, end)` — returns array of `Date` objects between two dates
- `buildTimeframesFromGrid(grid, days)` — converts a 2D boolean grid to `[start_time, end_time]` pairs
- `gridFromTimeframes(timeframes, days)` — inverse: converts timeframe array back to 2D grid
- `formatTimeLabel(slotIndex)` — converts 0–31 slot index to a human-readable time (9:00 AM → 5:00 PM in 15-min steps)

**Calendar grid** — the main UI primitive shared by admin, professor, and student pages. It is a 32-row × N-day boolean grid representing 15-minute slots from 9 AM to 5 PM. Users click and drag to toggle cells. Cells are styled green (available), red (unavailable), or gray (non-editable).

---

### `app/layout.tsx`

Root layout. Wraps all pages with standard HTML boilerplate and the `antialiased` Tailwind class. Sets page metadata. No state, no API calls.

---

### `app/page.tsx` — Public Schedule View (`/`)

The public-facing page where anyone can browse scheduled presentations.

#### State Variables

| Variable | Type | Purpose |
|---|---|---|
| `symposia` | `{id, name}[]` | Dropdown options |
| `selectedSymposiumId` | `string` | Currently viewed symposium |
| `timeframes` | `{id, start_time, end_time}[]` | Available days/slots |
| `departments` | `object[]` | Departments in symposium |
| `classes` | `object[]` | Classes across all departments |
| `presentations` | `object[]` | Presentations with student names |
| `roomsAvailable` | `number` | Concurrent room count |
| `selectedDay` | `string` | YYYY-MM-DD key of viewed day |
| `searchQuery` | `string` | Text search filter |
| `locationFilter` | `string` | Room filter |
| `professorFilter` | `string` | Professor/advisor filter |
| `departmentFilter` | `string` | Department filter |
| `message` | `string` | Error/status message |
| `isLoggedIn` | `boolean` | Derived from URL search params — shows admin nav links |

#### Functions

- `loadSymposia()` — on mount, fetches all symposia and pre-selects the first one
- `loadSymposiumDetails(id)` — on symposium change, runs parallel fetches for departments, classes, presentations, students, and timeframes; merges them into state
- `parseBackendDateTime()`, `dayKey()`, `dayLabel()`, `timeLabel()` — date/time formatting helpers
- `normalizeId()` — used when matching department/class IDs across API responses

**Memoized values** (`useMemo`):
- `calendarDays` — unique days derived from timeframe data
- `filteredCards` — presentation cards after applying all 4 filters
- `locationOptions`, `professorOptions`, `departmentOptions` — dropdown option lists built from loaded data

#### API Calls

| Endpoint | When |
|---|---|
| `GET /api/events/symposia` | On mount |
| `GET /api/events/symposia/{id}` | On symposium select (gets rooms + timeframes) |
| `GET /api/events/departments?symposium_id={id}` | On symposium select |
| `GET /api/events/classes?department_id={id}` | After departments load (one call per department) |
| `GET /api/events/presentations?class_id={id}` | After classes load (one call per class) |
| `GET /api/events/students?class_id={id}` | After classes load (for presenter names) |

#### UI

- Header: "OCC THESIS SYMPOSIUM" with navigation links (admin, department-head, professor, student)
- Symposium dropdown
- Day selection tab bar
- Search box + three filter dropdowns (location, professor/advisor, department)
- Presentation cards arranged in a grid, each showing:
  - Time range (e.g., "9:00 AM – 9:30 AM")
  - Room label (Room 1, Room 2, … — assigned by cycling through `roomsAvailable` using modulo)
  - Presentation title
  - Presenter names (or "Presenters TBD")
  - Department and department head name
- Empty/error states: "No departments registered", "No matches found", "Select a day"
- Timezone note at bottom of page

---

### `app/admin/page.tsx` — Admin Panel (`/admin`)

Two-tab interface: **Create** (new symposium) and **Edit** (existing symposium). Also contains a department management section within the Edit tab.

#### State Variables

**Create tab:**

| Variable | Purpose |
|---|---|
| `createSymposiumName` | Name input |
| `createRooms` | Room count input |
| `createStartDate`, `createEndDate` | Date range inputs |
| `createAvailability` | 2D boolean grid (days × 32 slots) |
| `isCreateDragging`, `createDragValue` | Drag interaction state |
| `isSavingCreate` | Loading state for save button |
| `createSaveMessage` | Success/error message |

**Edit tab:**

| Variable | Purpose |
|---|---|
| `selectedSymposiumId` | Symposium being edited |
| `symposiumOptions` | Dropdown list |
| `editSymposiumName`, `editRooms`, `editStartDate`, `editEndDate` | Editable fields |
| `editAvailability` | 2D boolean grid |
| `isEditDragging`, `editDragValue` | Drag state |
| `isSavingSymposiumEdit`, `isDeletingSymposium` | Operation states |
| `symposiumEditMessage` | Status message |

**Departments section:**

| Variable | Purpose |
|---|---|
| `departments` | List of departments for selected symposium |
| `departmentAction` | `"add"` or `"edit"` mode |
| `departmentToEditId` | ID of department being edited |
| `departmentName`, `departmentHeadName`, `departmentHeadEmail` | Form fields |
| `isSavingDepartment` | Loading state |
| `deletingDepartmentId` | ID of department being deleted |
| `departmentMessage`, `departmentMessageKind` | Status message + severity |

#### Functions

- `fetchSymposia()` — loads symposium list for dropdown
- `fetchSymposiumDetails(id)` — loads fields + timeframes, converts timeframes back to grid via `gridFromTimeframes()`
- `fetchDepartments(id)` — loads departments for selected symposium
- `handleCreateEventSubmit()` — POSTs new symposium with timeframes built from grid; resets form on success
- `handleSaveEditedEvent()` — PUTs updated fields; if timeframes changed, calls `POST /add_symposium` with the existing `symposium_id` to replace timeframes
- `handleDeleteEvent()` — DELETEs symposium after confirmation; resets edit tab state
- `handleDepartmentSubmit()` — POSTs new department or PUTs existing one depending on `departmentAction`
- `handleDeleteDepartment(id)` — DELETEs department, refreshes list
- `handleDeployEvent()` — placeholder; shows a "deployed" message but has no backend call
- `setCreateCell(day, slot, val)`, `setEditCell(...)` — update individual grid cells
- `handleCellMouseDown()`, `handleCellMouseEnter()` — implement click-and-drag to set/unset ranges of cells

#### API Calls

| Endpoint | When |
|---|---|
| `GET /api/events/symposia` | On mount, after create/delete |
| `GET /api/events/symposia/{id}` | On symposium select in Edit tab |
| `POST /api/events/add_symposium` | Create tab submit; also used to replace timeframes on edit |
| `PUT /api/events/update_symposium?symposium_id=` | Edit tab save (name/rooms) |
| `DELETE /api/events/delete_symposium?symposium_id=` | Delete button |
| `GET /api/events/departments?symposium_id=` | After selecting symposium in Edit tab |
| `POST /api/events/add_department` | Department add form submit |
| `PUT /api/events/update_department?department_id=` | Department edit form submit |
| `DELETE /api/events/delete_department?department_id=` | Department delete button |

#### UI

**Create tab:** symposium name + rooms inputs → date range pickers → interactive calendar grid → Save button

**Edit tab:** symposium dropdown → auto-loaded fields → same grid → Save / Delete buttons → departments list with inline Add/Edit/Delete

**Calendar grid details:**
- 32 rows = slots 0–31, representing 9:00 AM to 4:45 PM in 15-minute increments
- Columns = days between `startDate` and `endDate`
- Green cell = available, default/white = unavailable
- Click-and-drag sets the `dragValue` (true/false) from the first cell clicked, then applies that value to all subsequently hovered cells until mouse up

---

### `app/department-head/page.tsx` — Department Head (`/department-head`)

Manages classes and professor assignments for a department.

#### State Variables

| Variable | Purpose |
|---|---|
| `symposiumIdFromLink`, `departmentIdFromLink` | Pre-selected IDs from URL search params |
| `selectedSymposiumId`, `selectedDepartmentId` | Current cascade selections |
| `className` | Class name form input |
| `professors` | Array of `{localId, name, email}` rows in the "add" form |
| `savedClasses` | Array of classes loaded from backend, each with nested professors |
| `deployedClassIds` | Set of class IDs marked as deployed (persisted in `localStorage`) |
| `editingLocalId` | Which saved class is in inline-edit mode |
| `editingClassName`, `editingDepartmentId`, `editingProfessors` | Inline edit form state |
| `loading`, `saving`, `deletingLocalId`, `updatingLocalId` | Operation loading states |

#### Functions

- `loadSymposia()` — fetches symposia and departments on mount
- `loadSymposiumData(symposiumId, departmentId)` — fetches departments, classes, and professors; merges professors into class objects as `savedClasses`
- `setProfessorField(localId, field, value)` — updates a single field in the professor add-form rows
- `addProfessorRow()` — appends a blank `{localId, name:"", email:""}` row
- `removeProfessorRow(localId)` — removes a row (minimum 1 enforced)
- `startEditSavedClass(cls)` — copies class data into edit state variables
- `saveEditedClass()` — PUTs updated class + each modified professor, then reloads data
- `submitProfessors()` — validates and POSTs new class with professors
- `removeSavedClass(classId)` — DELETEs class (backend cascades to professors), removes from local state
- `handleDeployClasses()` — moves pending class IDs into `deployedClassIds` in localStorage; no backend call

#### API Calls

| Endpoint | When |
|---|---|
| `GET /api/events/symposia` | On mount |
| `GET /api/events/departments` | On mount and on symposium select |
| `GET /api/events/classes?department_id=` | On department select |
| `GET /api/events/professors?class_id=` | After loading classes |
| `POST /api/events/add_class` | Add class form submit |
| `PUT /api/events/update_class?class_id=` | Inline edit save |
| `PUT /api/events/update_professor?professor_id=` | Inline edit save (per professor) |
| `DELETE /api/events/delete_class?class_id=` | Delete button |
| `DELETE /api/events/delete_professor?professor_id=` | Delete individual professor in edit mode |

#### UI

- Symposium + Department cascade dropdowns
- Add Class form: class name input + dynamic professor table (name/email per row, add/remove rows)
- Saved Classes section split into two lists — **Pending** and **Deployed**
- Each saved class card shows class name and professor list with Edit/Delete buttons
- Edit mode: inline form replaces the card with editable inputs and Save/Cancel buttons
- Deploy button moves all pending classes to deployed (localStorage only)

---

### `app/professor/page.tsx` — Professor View (`/professor`)

Two-tab interface for professors: **Availability** (calendar grid) and **Students** (upload, group, deploy).

#### State Variables

**Identity & availability:**

| Variable | Purpose |
|---|---|
| `professorOptions` | Dropdown list of all professors |
| `selectedProfessorId` | Currently selected professor |
| `professorName`, `classId`, `className`, `symposiumName` | Resolved identity info |
| `availability` | 2D boolean grid (professor's available slots) |
| `editableSlots` | 2D boolean grid (which slots fall within the symposium timeframes — others are grayed out) |
| `calendarDays` | Array of `{key, label}` objects from symposium timeframes |
| `isDragging`, `dragValue` | Drag interaction state |
| `savingAvailability` | Loading state |

**CSV/student upload:**

| Variable | Purpose |
|---|---|
| `csvFile` | Selected file object |
| `csvUploading` | Loading state |
| `csvMessage` | Status message |
| `uploadedStudents` | Students loaded for the class |
| `selectedUploadedStudentKeys` | Set of student IDs checked for grouping |
| `deletingStudentIds` | Set of student IDs currently being deleted |

**Presentations:**

| Variable | Purpose |
|---|---|
| `presentationGroups` | Draft presentation groups (not yet deployed) |
| `deployedPresentationGroups` | Presentations already saved to backend |
| `defaultPresentationDuration` | Fallback duration in minutes |
| `usePerPresentationDuration` | Toggle between per-group or default duration |

#### Functions

- `loadProfessorOptions()` — fetches all professors for dropdown
- `loadIdentity(professorId)` — comprehensive load: fetches professor → class → department → symposium → symposium timeframes → professor timeframes → students → presentations. Builds `calendarDays`, `editableSlots`, and pre-fills `availability` grid from existing professor timeframes
- `handleSaveAvailability()` — PUTs updated timeframes by calling `PUT /api/events/update_timeframes` with the grid converted to `[start, end]` pairs
- `parseCsvLine(line)` — parses a single CSV line handling quoted fields with commas inside
- `handleCsvUpload()` — reads the file, parses CSV rows (expects headers: "Student Name", "Student ID", "Class Level", "Preferred Email"), POSTs each student to backend
- `handleManualStudentAdd(name, email)` — POSTs a single manually-entered student
- `deleteUploadedStudent(id)` — DELETEs student, removes from local list
- `handleMakePresentationGroup()` — creates a local draft group from selected student checkboxes; does not call backend until deploy
- `handleDeletePresentationGroup(groupId)` — removes draft group from local state, or DELETEs from backend if already deployed
- `setCell()`, `handleCellMouseDown()`, `handleCellMouseEnter()` — drag-to-select grid interaction (identical pattern to admin page)
- `buildCandidateUrls(path)` — generates alternative URL variants to handle cases where `/api` is duplicated in the base URL

#### API Calls

| Endpoint | When |
|---|---|
| `GET /api/events/professors` | On mount |
| `GET /api/events/classes` | On professor select (resolves class) |
| `GET /api/events/departments` | On professor select (resolves department) |
| `GET /api/events/symposia` | On professor select (resolves symposium) |
| `GET /api/events/timeframes?linked_id={symposium_id}` | On professor select (builds editable slots) |
| `GET /api/events/timeframes?linked_id={professor_id}` | On professor select (loads saved availability) |
| `GET /api/events/students?class_id=` | On professor select |
| `GET /api/events/presentations?class_id=` | On professor select |
| `PUT /api/events/update_timeframes` | Availability save |
| `POST /api/events/add_students` | CSV upload or manual add |
| `DELETE /api/events/delete_student?student_id=` | Delete student button |
| `DELETE /api/events/delete_presentation?presentation_id=` | Delete deployed presentation |

#### UI

**Availability tab:**
- Calendar grid with the same 32-slot × N-day layout
- Gray cells = outside symposium timeframes (non-editable)
- Green = professor marked available
- Red = professor marked unavailable
- Save Availability button

**Students tab:**
- CSV upload input (file picker + upload button) — expected CSV columns: "Student Name", "Student ID", "Class Level", "Preferred Email"
- Manual entry form (name + email)
- Uploaded students list with checkboxes + delete buttons
- "Make Presentation Group" button (enabled when ≥1 student selected)
- Draft presentation group cards: student names, title input, duration input
- Deployed Presentations section with delete buttons

---

### `app/student/page.tsx` — Student View (`/student`)

Two-tab interface: **Availability** (calendar grid) and **Preferences** (professor preference requests).

#### State Variables

| Variable | Purpose |
|---|---|
| `studentOptions` | Dropdown list of all students |
| `selectedStudentId` | Currently selected student |
| `activeTab` | `"availability"` or `"preferences"` |
| `availability` | 2D boolean grid |
| `editableSlots` | 2D boolean grid (symposium timeframes only) |
| `calendarDays` | Array of `{key, label}` objects |
| `isDragging`, `dragValue` | Drag state |
| `studentName`, `className`, `symposiumName`, `presentationName` | Resolved identity info |
| `preferredProfessorName`, `preferredProfessorEmail` | Preference form inputs |
| `savedProfessorRequests` | Existing professor requests for this student |
| `savingPreferences` | Loading state |
| `loadingIdentity` | Loading state while resolving student data |

#### Functions

- `loadStudentOptions()` — fetches all students for dropdown on mount
- `loadStudent(studentId)` — full identity resolution chain: student → class → department → symposium → symposium timeframes → student timeframes → presentations → requests. Builds `calendarDays`, `editableSlots`, pre-fills `availability`, resolves `presentationName` by finding which presentation the student belongs to
- `handleSavePreferences()` — POSTs a new professor request; appends to `savedProfessorRequests` on success; clears form inputs
- `setCell()`, `handleCellMouseDown()`, `handleCellMouseEnter()` — drag-to-select (same pattern as other pages)

**Note:** The Save Availability button is rendered but `handleSaveAvailability` is not implemented — it exists as a stub. The availability grid can be interacted with but changes are not persisted.

#### API Calls

| Endpoint | When |
|---|---|
| `GET /api/events/students` | On mount |
| `GET /api/events/classes` | On student select |
| `GET /api/events/departments` | On student select |
| `GET /api/events/symposia` | On student select |
| `GET /api/events/timeframes?linked_id={symposium_id}` | On student select (editable slots) |
| `GET /api/events/timeframes?linked_id={student_id}` | On student select (saved availability) |
| `GET /api/events/presentations?class_id=` | On student select (find presentation name) |
| `GET /api/events/requests?student_id=` | On student select |
| `POST /api/events/add_request` | Preferences form submit |

#### UI

**Identity section** (always visible):
- Student dropdown
- "Hello, [Name]!" greeting
- Resolved Symposium, Class, and Presentation names

**Availability tab:**
- Same 32-slot × N-day calendar grid
- Gray = outside symposium window, Green = available, Red = unavailable
- Save button (currently non-functional)
- Color legend

**Preferences tab:**
- Name + Email inputs for a preferred professor
- Save button → POSTs request, clears form
- "Saved Requests" list showing all submitted requests (professor name + email)

---

## Backend (Detailed)

The backend lives in `/backend/app/`.

```
backend/
├── app/
│   ├── main.py              # FastAPI app, middleware, routers
│   ├── config.py            # Settings (env vars)
│   ├── logging_config.py    # Logging setup
│   ├── utils.py             # force_uuid helper
│   ├── supabase_client.py   # Supabase client factory
│   ├── routers/
│   │   ├── events.py        # All API route handlers (~1000 lines)
│   │   └── request_schemas.py  # Pydantic request validation models
│   └── supabase_io/
│       ├── client.py        # Supabase singleton client
│       ├── supabase_schemas.py  # Python data models matching DB tables
│       ├── read.py          # All SELECT queries
│       ├── write.py         # All INSERT operations
│       └── delete.py        # Cascade DELETE operations
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_events_api.py
    ├── test_read.py
    ├── test_write.py
    ├── test_delete.py
    └── test_request_schemas.py
```

---

### Entry Point & Middleware

**`app/main.py`**

Creates the FastAPI application and wires everything together.

```python
app = FastAPI(title=settings.app_name)
```

**CORS Middleware** — allows requests from the configured frontend origins:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Request Logging Middleware** — logs every request with method, path, response status, and duration:
```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.1f}ms)")
    return response
```

**Health Check** — unauthenticated endpoint to verify the service is running:
```
GET /health
→ {"status": "ok", "environment": "development"}
```

**Router Registration** — all business routes are mounted under `/api/events` and require API key auth:
```python
app.include_router(events_router, prefix="/api/events", dependencies=[Depends(require_api_key)])
```

---

### Configuration

**`app/config.py`**

A Pydantic `BaseSettings` class that reads from environment variables (case-insensitive). All config is accessed via a global `settings` singleton.

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `app_name` | `APP_NAME` | `"Conference Scheduler API"` | App name for docs/logging |
| `app_env` | `APP_ENV` | `"development"` | `development` or `production` |
| `app_port` | `APP_PORT` | `8000` | Port to bind |
| `backend_cors_origins` | `BACKEND_CORS_ORIGINS` | `"http://localhost:3000"` | Comma-separated allowed origins |
| `backend_api_key` | `BACKEND_API_KEY` | `""` | Required — API key for auth |
| `supabase_url` | `SUPABASE_URL` | `""` | Required — Supabase project URL |
| `supabase_key` | `SUPABASE_KEY` | `""` | Required — Supabase anon/service key |
| `supabase_db_url` | `SUPABASE_DB_URL` | `""` | Direct DB URL (for migrations) |
| `log_level` | `LOG_LEVEL` | `"INFO"` | Logging verbosity |
| `supabase_events_table` | `SUPABASE_EVENTS_TABLE` | `"events"` | Table name overrides |
| `supabase_symposia_table` | — | `"symposia"` | — |
| `supabase_departments_table` | — | `"departments"` | — |
| `supabase_timeframes_table` | — | `"timeframes"` | — |
| `supabase_students_table` | — | `"students"` | — |

---

### Authentication

*`security.py` was removed — API key validation is now handled inline in the router middleware.*

---

### Logging

**`app/logging_config.py`**

Configures Python's standard `logging` module with a consistent format:

```
2026-03-03T12:00:00.000Z [INFO] app.routers.events: Created symposium abc123
```

- Output: stdout
- Format: ISO 8601 timestamp, level, logger name, message
- Level: controlled by `LOG_LEVEL` env var (default `INFO`)
- Called once at import time via `setup_logging()`

---

### Database Schemas

**`app/supabase_io/supabase_schemas.py`**

Python dataclasses that mirror the Supabase/Postgres tables. Used as typed containers when constructing insert payloads.

#### `Symposium`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | Primary key |
| `created_at` | `datetime` | Auto-set |
| `name` | `str` | Display name |
| `rooms_available` | `int` | Concurrent rooms |

#### `Department`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `department_name` | `str` | |
| `department_head_name` | `str` | |
| `email` | `str` | Must be `@hamilton.edu` |
| `symposium_id` | `UUID` | FK → Symposium |

#### `Class`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `name` | `str` | Course name |
| `department_id` | `UUID` | FK → Department |

#### `Professor`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `name` | `str` | |
| `email` | `str` | |
| `class_id` | `UUID` | FK → Class |

#### `Student`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `name` | `str` | |
| `email` | `str` | |
| `class_id` | `UUID` | FK → Class |
| `presentation_id` | `UUID \| None` | FK → Presentation (nullable) |

#### `Presentation`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `title` | `str` | |
| `class_id` | `UUID` | FK → Class |
| `minutes` | `int` | Duration (1–60) |
| `start_time` | `datetime \| None` | Scheduled start |
| `end_time` | `datetime \| None` | Scheduled end |

#### `Timeframe`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `linked_id` | `UUID` | Polymorphic FK — can point to Symposium, Professor, or Student |
| `start_time` | `datetime` | Window start |
| `end_time` | `datetime` | Window end |

#### `PresentingStudents` (join table)
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `presentation_id` | `UUID` | FK → Presentation |
| `student_id` | `UUID` | FK → Student |

#### `Request`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `name` | `str` | Professor name being requested |
| `email` | `str` | Professor email (`@hamilton.edu`) |
| `student_id` | `UUID` | FK → Student |

---

### Supabase I/O Layer

#### `supabase_io/client.py`

Creates and caches the Supabase Python client as a module-level singleton:

```python
_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    return _supabase_client
```

---

#### `supabase_io/read.py`

All SELECT queries. Each function accepts optional filter IDs and returns the raw Supabase response (list of dicts).

| Function | Filters | Notes |
|---|---|---|
| `get_symposia()` | none | Returns all symposia |
| `get_departments(symposium_id)` | optional `symposium_id` | |
| `get_classes(department_id)` | optional `department_id` (single or list) | |
| `get_students(class_id)` | optional `class_id` (single or list) | |
| `get_professors(class_id)` | optional `class_id` (single or list) | |
| `get_presentations(class_id)` | optional `class_id` (single or list) | **Enriched** — see below |
| `get_presenting_students(presentation_id)` | optional `presentation_id` (single or list) | |
| `get_timeframes(linked_id)` | optional `linked_id` | |
| `get_requests(student_id)` | optional `student_id` (single or list) | |

**`get_presentations()` Enrichment:** This function performs 3 queries and merges the results:
1. Fetch presentations (filtered by class)
2. Fetch `presenting_students` rows for those presentation IDs
3. Fetch student details for those student IDs
4. Attach a `presenting_students` array (with full student objects) to each presentation dict

---

#### `supabase_io/write.py`

A single generic `insert(table_name, data)` function used for all INSERT operations.

- Accepts a dataclass instance or a dict
- Serializes types: `UUID` → `str`, `datetime` → ISO 8601 string, pandas `NaN` → `None`
- Calls `supabase.table(table_name).insert(payload).execute()`
- Returns the Supabase response
- Logs the table name and number of rows inserted

---

#### `supabase_io/delete.py`

Cascade delete functions. Each returns a `dict[str, int]` mapping table name to rows deleted.

| Function | What it deletes |
|---|---|
| `delete_timeframes(linked_id)` | All timeframes with matching `linked_id` |
| `delete_student(student_id)` | Student + their `presenting_students` entries + requests + timeframes |
| `delete_professor(prof_id)` | Professor + their requests + timeframes |
| `delete_presentation(presentation_id)` | Presentation + its `presenting_students` entries |
| `delete_class(class_id)` | All students (cascade) + all professors (cascade) + all presentations (cascade) + the class row |
| `delete_department(department_id)` | All classes (cascade) + the department row |
| `delete_symposium(symposium_id)` | All departments (cascade) + symposium timeframes + the symposium row |

All counts from nested cascade calls are merged and returned as a single dict.

---

### Request Schemas

**`app/routers/request_schemas.py`**

Pydantic v2 models used to validate the body of POST and PUT requests. Invalid requests return `422 Unprocessable Entity`.

#### Helper Types

**`TimeframeWindow`**
```python
start_time: datetime
end_time: datetime  # must be after start_time
```

**`ProfessorInit`**
```python
name: str  # non-empty after strip
email: str
```

**`StudentInit`**
```python
name: str
email: str
```

---

#### POST Request Bodies

**`AddSymposiumRequest`**

| Field | Type | Validation |
|---|---|---|
| `symposium_id` | `UUID \| None` | Optional — if provided, updates existing |
| `symposium_name` | `str` | Required, non-empty |
| `rooms_available` | `int` | 1–100 |
| `timeframes` | `list[TimeframeWindow]` | List of time windows |

**`AddDepartmentRequest`**

| Field | Type | Validation |
|---|---|---|
| `symposium_id` | `UUID` | Required |
| `department_name` | `str` | Required, non-empty |
| `department_head_name` | `str` | Required, non-empty |
| `email` | `str` | Required, must end with `@hamilton.edu` |

**`AddClassRequest`**

| Field | Type | Validation |
|---|---|---|
| `name` | `str` | Required, non-empty |
| `department_id` | `UUID` | Required |
| `professors` | `list[ProfessorInit]` | One or more professors |

**`AddStudentsRequest`**

| Field | Type | Validation |
|---|---|---|
| `class_id` | `UUID` | Required |
| `students` | `list[StudentInit]` | One or more students |

**`AddPresentationRequest`**

| Field | Type | Validation |
|---|---|---|
| `title` | `str` | Required, non-empty |
| `class_id` | `UUID` | Required |
| `minutes` | `int` | 1–60 |
| `presenting_students` | `list[UUID]` | 1–10 student IDs |

**`AddReqRequest`** (professor request from student)

| Field | Type | Validation |
|---|---|---|
| `name` | `str` | Required, non-empty |
| `email` | `str` | Required, must be `@hamilton.edu` |
| `student_id` | `UUID` | Required |

---

#### PUT Request Bodies

Each `Update*` schema has all fields optional — only provided fields are applied.

| Schema | Updatable Fields |
|---|---|
| `UpdateSymposiumRequest` | `symposium_name`, `rooms_available` |
| `UpdateDepartmentRequest` | `department_name`, `department_head_name`, `email`, `symposium_id` |
| `UpdateClassRequest` | `name`, `department_id` |
| `UpdateStudentRequest` | `name`, `email`, `class_id`, `presentation_id` |
| `UpdateProfessorRequest` | `name`, `email`, `class_id` |
| `UpdatePresentationRequest` | `title`, `minutes`, `start_time`, `end_time`, `presenting_students` |
| `UpdateTimeframesRequest` | `linked_id`, `timeframes` (replaces all existing) |

---

### API Endpoints

All endpoints below are prefixed with `/api/events` and require `X-API-Key` header.

#### Helper Utilities (internal, `events.py`)

- `_serialize_update_fields(fields)` — converts UUID objects to strings for Supabase compatibility
- `_rows_affected(response)` — extracts row count from Supabase response object
- `_normalize_counts(counts)` — ensures counts value is a valid `dict[str, int]`
- `_sum_counts(counts)` — sums all values in a counts dict

---

#### Symposia

| Method | Path | Body | Description |
|---|---|---|---|
| `GET` | `/symposia` | — | List all symposia |
| `GET` | `/symposia/{symposium_id}` | — | Single symposium with its timeframes |
| `POST` | `/add_symposium` | `AddSymposiumRequest` | Create symposium + timeframes. If `symposium_id` is provided, replaces that symposium's timeframes instead of creating new |
| `PUT` | `/update_symposium` | `UpdateSymposiumRequest` + `?symposium_id=` | Update name or room count |
| `DELETE` | `/delete_symposium` | — + `?symposium_id=` | Cascade delete entire symposium hierarchy |

---

#### Departments

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/departments` | `?symposium_id=` (optional) | — | List all departments, optionally filtered |
| `POST` | `/add_department` | — | `AddDepartmentRequest` | Create department |
| `PUT` | `/update_department` | `?department_id=` | `UpdateDepartmentRequest` | Update department fields |
| `DELETE` | `/delete_department` | `?department_id=` | — | Cascade delete department + classes |

---

#### Classes

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/classes` | `?department_id=` (optional) | — | List all classes, optionally filtered |
| `POST` | `/add_class` | — | `AddClassRequest` | Create class + professors |
| `PUT` | `/update_class` | `?class_id=` | `UpdateClassRequest` | Update class name or department |
| `DELETE` | `/delete_class` | `?class_id=` | — | Cascade delete class + students, professors, presentations |

---

#### Students

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/students` | `?class_id=` (optional) | — | List students, optionally filtered by class |
| `POST` | `/add_students` | — | `AddStudentsRequest` | Bulk add students to a class |
| `PUT` | `/update_student` | `?student_id=` | `UpdateStudentRequest` | Update a student's fields |
| `DELETE` | `/delete_student` | `?student_id=` | — | Delete student + their presenting_students, requests, timeframes |

---

#### Professors

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/professors` | `?class_id=` (optional) | — | List professors, optionally filtered by class |
| `PUT` | `/update_professor` | `?professor_id=` | `UpdateProfessorRequest` | Update professor fields |
| `DELETE` | `/delete_professor` | `?professor_id=` | — | Delete professor + their requests, timeframes |

---

#### Presentations

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/presentations` | `?class_id=` (optional) | — | List presentations enriched with presenting student details |
| `POST` | `/add_presentation` | — | `AddPresentationRequest` | Create presentation + insert presenting_students join rows |
| `PUT` | `/update_presentation` | `?presentation_id=` | `UpdatePresentationRequest` | Update presentation fields. If `presenting_students` is included, replaces the entire join table for that presentation |
| `DELETE` | `/delete_presentation` | `?presentation_id=` | — | Delete presentation + presenting_students join rows |

---

#### Timeframes

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/timeframes` | `?linked_id=` (optional) | — | List timeframes, optionally filtered by linked entity |
| `PUT` | `/update_timeframes` | — | `UpdateTimeframesRequest` | **Replace** all timeframes for a `linked_id`: deletes existing, inserts new list |

---

#### Requests (Professor Preferences)

| Method | Path | Query Params | Body | Description |
|---|---|---|---|---|
| `GET` | `/requests` | `?student_id=` (optional) | — | List professor requests, optionally filtered by student |
| `POST` | `/add_request` | — | `AddReqRequest` | Student submits a professor preference request |

---

## Data Model & Relationships

```
Symposium (1) ──────────────────────── (N) Timeframe  [linked_id]
    │
    └── (N) Department
              │
              └── (N) Class
                        │
                        ├── (N) Professor
                        │         │
                        │         ├── (N) Timeframe  [linked_id]
                        │         └── (N) Request
                        │
                        ├── (N) Student
                        │         │
                        │         ├── (N) Timeframe  [linked_id]
                        │         ├── (N) Request
                        │         └── (N) PresentingStudents ──┐
                        │                                       │
                        └── (N) Presentation ──────────────────┘
                                  └── (N) PresentingStudents
```

**Key design notes:**
- `Timeframe.linked_id` is polymorphic — it can reference a Symposium, Professor, or Student. There is no DB-level foreign key constraint enforcing this; the application layer manages the relationship.
- `Student.presentation_id` provides a direct shortcut from a student to their current presentation, but the authoritative many-to-many relationship lives in `PresentingStudents`.
- All cascade deletes are implemented in application code (`delete.py`), not at the database level.

---

## Environment & Startup

### Environment Variables

**Backend (`.env`):**
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-key
BACKEND_API_KEY=your-secret-api-key
BACKEND_CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
APP_ENV=development
```

**Frontend (`.env.local`):**
```bash
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_BACKEND_API_KEY=your-secret-api-key
```

### Running Locally

**Backend:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
npm install
npm run dev
# Runs on http://localhost:3000
```

**Backend interactive docs:** http://localhost:8000/docs (Swagger UI, auto-generated by FastAPI)
