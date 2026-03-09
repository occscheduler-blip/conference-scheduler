# Test Suite Documentation

All tests live under `tests/` and are run with `make test`, which executes mypy followed by pytest.

There are two categories of test:

- **Unit / mock tests** (`test_*.py` except `test_integration.py`) — patch the Supabase client with a generic `MagicMock` via the `mock_supabase` fixture. Fast and isolated; no real database connection required.
- **Integration tests** (`test_integration.py`) — patch the Supabase client with a fully in-memory `FakeSupabaseClient` (see `fake_supabase.py`) via the `fake_supabase` and `integration_client` fixtures. Real data flows through the router → supabase_io → in-memory storage, catching bugs that mocks cannot.

---

## `test_config.py` — Settings & CORS

Tests for `app.config.Settings`, which loads environment variables via Pydantic Settings.

| Test | What it checks |
|---|---|
| `TestSettings::test_default_values` | Default field values (`app_name`, `app_env`, `app_port`, `supabase_events_table`) are correct when no env vars are set. |
| `TestSettings::test_cors_origins_single` | A single origin string is returned as a one-element list. |
| `TestSettings::test_cors_origins_multiple` | A comma-separated origins string is split and whitespace-stripped into a list. |
| `TestSettings::test_cors_origins_strips_empty` | Empty tokens (e.g. `,,`) in the origins string are discarded. |

---

## `test_security.py` — API Key Authentication

Tests for `app.security.require_api_key`, the FastAPI dependency that guards all `/api/*` routes.

| Test | What it checks |
|---|---|
| `TestRequireApiKey::test_valid_key` | The correct API key returns `None` (no exception). |
| `TestRequireApiKey::test_missing_key` | A missing key raises `HTTPException` with status 401. |
| `TestRequireApiKey::test_wrong_key` | An incorrect key raises `HTTPException` with status 401. |
| `TestRequireApiKey::test_unconfigured_backend_key` | If `BACKEND_API_KEY` is empty on the server, any request raises 500. |

---

## `test_helpers.py` — Router Helper Functions

Unit tests for the private helper functions in `app.routers.events`.

### `_serialize_update_fields`

Converts a dict of update fields into a JSON-serializable form by converting UUID values to strings.

| Test | What it checks |
|---|---|
| `test_uuid_converted_to_str` | UUID values are replaced with their string representation; other values are unchanged. |
| `test_empty_dict` | An empty dict returns an empty dict. |
| `test_non_uuid_values_unchanged` | Integers, strings, and `None` pass through without modification. |

### `_rows_affected`

Extracts a row count from a Supabase response object or plain dict. Falls back to a provided default when the count cannot be determined.

| Test | What it checks |
|---|---|
| `test_dict_with_count` | A dict with a `"count"` key returns that integer. |
| `test_dict_with_data_list` | A dict with a `"data"` list returns the list length. |
| `test_dict_with_data_dict` | A dict with a single-item `"data"` dict returns 1. |
| `test_dict_fallback` | A dict with neither field returns the fallback. |
| `test_object_with_count` | A `SimpleNamespace` with `.count` attribute returns that integer. |
| `test_object_with_data_list` | A `SimpleNamespace` with a `.data` list returns the list length. |
| `test_object_with_data_dict` | A `SimpleNamespace` with a single-item `.data` dict returns 1. |
| `test_object_fallback` | A `SimpleNamespace` with no relevant attributes returns the fallback. |
| `test_negative_count_ignored` | A negative `count` is ignored and the fallback is used. |
| `test_none_data_uses_fallback` | `data=None` is treated as absent and the fallback is used. |

### `_normalize_counts`

Sanitises an arbitrary dict into a `dict[str, int]`, filtering out negative values, and falling back to a default when the input is unusable.

| Test | What it checks |
|---|---|
| `test_valid_dict` | A dict of non-negative ints is returned as-is. |
| `test_filters_negative` | Keys with negative values are removed from the result. |
| `test_none_returns_fallback` | `None` input returns the fallback dict. |
| `test_empty_dict_returns_fallback` | An empty dict (no valid entries) returns the fallback. |
| `test_all_invalid_returns_fallback` | All-negative input returns the fallback. |
| `test_non_dict_returns_fallback` | A non-dict (e.g. a string) returns the fallback. |

### `_sum_counts`

Sums all values across one or more `dict[str, int]` groups, ignoring non-integer and negative values.

| Test | What it checks |
|---|---|
| `test_single_group` | Sums all values in one dict. |
| `test_multiple_groups` | Sums values across multiple dicts. |
| `test_empty` | No arguments returns 0. |
| `test_ignores_negative` | Negative values are not included in the sum. |
| `test_ignores_non_int` | Non-integer values (e.g. strings) are skipped. |

---

## `test_read.py` — Supabase Read Queries

Unit tests for `app.supabase_io.read`. Each test verifies that the correct Supabase table is queried and that filters are applied properly.

| Class | Table | Tests |
|---|---|---|
| `TestGetSymposiums` | `symposiums` | Calls the table with no filter. |
| `TestGetDepartments` | `departments` | No filter; filtered by `symposium_id`. |
| `TestGetClasses` | `classes` | No filter; single UUID filter; list UUID filter; invalid type raises `ValueError`. |
| `TestGetStudents` | `students` | No filter; invalid type raises `ValueError`. |
| `TestGetProfessors` | `professors` | No filter; invalid type raises `ValueError`. |
| `TestGetTimeframes` | `timeframes` | No filter; single UUID filter; invalid type raises `ValueError`. |
| `TestGetPresentingStudents` | `presenting_students` | No filter. |
| `TestGetRequests` | `requests` | No filter; invalid type raises `ValueError`. |

### `TestGetPresentationsEnrichment`

Tests the enrichment logic in `get_presentations`, which joins `presenting_students` and `students` rows onto each presentation record.

| Test | What it checks |
|---|---|
| `test_enriches_presentations_with_students` | Given a presentation, a matching `presenting_students` row, and a matching `students` row (all linked by string UUIDs), the returned `SimpleNamespace` contains the student data nested under `presenting_students` on each presentation. |
| `test_empty_presentations` | When no presentations exist the response has an empty `data` list. |

---

## `test_write.py` — Supabase Insert

Tests for `app.supabase_io.write`.

### `_to_json_scalar`

Converts a single value to a JSON-safe scalar before sending it to Supabase.

| Test | What it checks |
|---|---|
| `test_uuid_to_str` | A `UUID` is converted to its string representation. |
| `test_datetime_to_iso` | A `datetime` is converted to an ISO 8601 string. |
| `test_date_to_iso` | A `date` is converted to an ISO 8601 date string. |
| `test_timestamp_to_iso` | A `pd.Timestamp` is converted to an ISO 8601 string. |
| `test_na_to_none` | `pd.NA` and `float("nan")` are converted to `None`. |
| `test_plain_values_unchanged` | Plain integers, strings, and `None` are returned unchanged. |

### `insert`

| Test | What it checks |
|---|---|
| `test_calls_supabase_table` | Calling `insert("my_table", data)` passes `"my_table"` to `supabase.table()`. |
| `test_serializes_uuid_and_datetime` | UUIDs and datetimes in the data dict are serialized before being passed to Supabase. |
| `test_no_raw_uuids_or_datetimes_sent_to_supabase` | Captures the actual rows passed to `.insert()` via a wrapping side-effect and asserts that no `UUID`, `datetime`, `date`, or `pd.Timestamp` objects remain — every value is a JSON-safe scalar. |

---

## `test_delete.py` — Supabase Delete & Cascade

Tests for `app.supabase_io.delete`, which performs cascading deletes across related tables.

### `_rows_affected`

Same semantics as the events router version — handles both response objects and plain dicts.

| Test | What it checks |
|---|---|
| `test_dict_count` | A dict `{"count": 3}` returns 3. |
| `test_object_data_list` | A `SimpleNamespace(data=[1, 2])` returns 2. |
| `test_fallback` | A `SimpleNamespace()` with no relevant attributes returns the fallback. |

### `_merge_counts`

Accumulates counts from a source dict into a target dict in-place.

| Test | What it checks |
|---|---|
| `test_merge_into_empty` | Merging into an empty dict produces the source dict. |
| `test_merge_accumulates` | Existing keys are summed, new keys are added. |
| `test_none_source_is_noop` | A `None` source leaves the target unchanged. |
| `test_negative_values_ignored` | Negative values in the source are not merged. |

### `_safe_count`

Clamps a value to a non-negative integer, returning 0 for negatives or non-integers.

| Test | What it checks |
|---|---|
| `test_positive_int` | A positive integer is returned unchanged. |
| `test_zero` | Zero is returned as-is. |
| `test_negative` | A negative integer returns 0. |
| `test_non_int` | A non-integer (e.g. a string) returns 0 without raising. |

### Cascade delete functions

Each cascade function is tested with a mocked Supabase client that returns empty result sets.

| Class | Function | Tests |
|---|---|---|
| `TestDeleteTimeframes` | `delete_timeframes` | Counts the rows before deleting and returns the count; correctly calls `.eq("linked_id", ...)`. |
| `TestDeleteStudent` | `delete_student` | Returns a dict with keys `students`, `presenting_students`, `prof_requests`, `timeframes`. |
| `TestDeleteProfessor` | `delete_professor` | Returns a dict with keys `professors`, `prof_requests`, `timeframes`. |
| `TestDeletePresentation` | `delete_presentation` | Returns a dict with keys `presentations`, `presenting_students`, `timeframes`. |
| `TestDeleteClass` | `delete_class` | Cascades through an empty class (no students/professors/presentations) and includes `classes` key; dispatches to `delete_multiple_classes` when given a list. |
| `TestDeleteDepartment` | `delete_department` | Cascades through an empty department and includes `departments` key; dispatches to `delete_multiple_departments` when given a list. |
| `TestDeleteSymposium` | `delete_symposium` | Cascades through an empty symposium and includes both `symposiums` and `timeframes` keys. |

---

## `test_request_schemas.py` — Pydantic Request Schema Validation

Tests that each request schema enforces its validation rules. No database or HTTP calls are made — schemas are instantiated directly.

### `TimeframeWindow`

| Test | What it checks |
|---|---|
| `test_valid` | A window with `end_time > start_time` is accepted. |
| `test_end_before_start_raises` | `end_time < start_time` raises `ValidationError` mentioning "start time must come before". |
| `test_equal_times_accepted` | Equal start and end times are allowed. |

### `AddSymposiumRequest`

| Test | What it checks |
|---|---|
| `test_valid_minimal` | A minimal valid request is accepted; `symposium_id` defaults to `None`. |
| `test_with_optional_id` | An explicit `symposium_id` UUID is stored. |
| `test_empty_name_raises` | A blank `symposium_name` raises `ValidationError` mentioning "empty". |
| `test_too_many_rooms_raises` | `rooms_available > MAX_ROOMS` raises `ValidationError` mentioning "rooms". |
| `test_max_rooms_accepted` | Exactly `MAX_ROOMS` is accepted. |

### `AddDepartmentRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid department request is accepted and the email is stored. |
| `test_empty_dept_name_raises` | An empty `department_name` raises `ValidationError`. |
| `test_empty_head_name_raises` | A whitespace-only `department_head_name` raises `ValidationError`. |
| `test_non_hamilton_email_raises` | An email not ending in `@hamilton.edu` raises `ValidationError`. |
| `test_email_normalized_lowercase` | The email is lowercased and stripped of whitespace. |

### `AddClassRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid class request is accepted. |
| `test_empty_name_raises` | A whitespace-only `name` raises `ValidationError`. |

### `StudentInit`

| Test | What it checks |
|---|---|
| `test_valid` | A valid name and Hamilton email are accepted. |
| `test_empty_name_raises` | A whitespace-only name raises `ValidationError`. |
| `test_bad_email_raises` | A non-Hamilton email raises `ValidationError` mentioning "hamilton". |

### `AddStudentsRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid student list is accepted. |

### `AddPresentationRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid presentation is accepted. |
| `test_empty_title_raises` | An empty `title` raises `ValidationError`. |
| `test_minutes_too_low` | `minutes < 1` raises `ValidationError`. |
| `test_minutes_too_high` | `minutes > MAX_TIME` raises `ValidationError`. |
| `test_too_many_presenting_students` | More than `MAX_PRESENTING_STUDENTS` raises `ValidationError` mentioning "present". |

### `AddReqRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid professor request is accepted. |
| `test_empty_name_raises` | A whitespace-only name raises `ValidationError`. |
| `test_bad_email_raises` | A non-Hamilton email raises `ValidationError`. |

### Update Schemas

All update schemas require every field — the ID field plus all mutable fields. Providing only the ID raises a `ValidationError` for missing fields.

#### `UpdateStudentRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields (`student_id`, `name`, `email`, `class_id`, `presentation_id`) accepted. |
| `test_missing_fields_raises` | Omitting update fields raises `ValidationError`. |
| `test_email_validation` | A non-Hamilton email raises `ValidationError` mentioning "hamilton". |

#### `UpdateProfessorRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields (`professor_id`, `name`, `email`, `class_id`) accepted. |
| `test_missing_fields_raises` | Omitting update fields raises `ValidationError`. |

#### `UpdateClassRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields (`class_id`, `name`, `department_id`) accepted. |
| `test_missing_fields_raises` | Omitting update fields raises `ValidationError`. |

#### `UpdateSymposiumRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields (`symposium_id`, `symposium_name`, `rooms_available`) accepted. |
| `test_missing_fields_raises` | Omitting update fields raises `ValidationError`. |
| `test_rooms_over_max` | `rooms_available > MAX_ROOMS` raises `ValidationError` mentioning "rooms". |

#### `UpdateDepartmentRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields accepted. |
| `test_empty_name_raises` | An empty `department_name` raises `ValidationError`. |

#### `UpdatePresentationRequest`

| Test | What it checks |
|---|---|
| `test_valid` | All required fields (`presentation_id`, `title`, `class_id`, `minutes`, `presenting_students`) accepted. |
| `test_missing_fields_raises` | Omitting update fields raises `ValidationError`. |
| `test_minutes_out_of_range` | `minutes > MAX_TIME` raises `ValidationError`. |
| `test_too_many_students` | More than `MAX_PRESENTING_STUDENTS` raises `ValidationError`. |

#### `UpdateTimeframesRequest`

| Test | What it checks |
|---|---|
| `test_valid` | A valid linked ID and timeframe list are accepted. |

---

## `test_events_api.py` — API Integration Tests

End-to-end HTTP tests using FastAPI's `TestClient`. Every request goes through the full middleware stack (CORS, auth). The Supabase client is patched so no real database calls occur.

### `TestHealthCheck`

| Test | What it checks |
|---|---|
| `test_health_ok` | `GET /health` returns 200 with `{"status": "ok"}` and an `environment` field. Auth is not required. |

### `TestAuth`

| Test | What it checks |
|---|---|
| `test_missing_key_returns_401` | A request to an `/api/` route without `X-API-Key` returns 401. |
| `test_wrong_key_returns_401` | An incorrect `X-API-Key` returns 401. |
| `test_valid_key_passes` | The correct `X-API-Key` returns 200. |

### POST endpoints

| Class | Endpoint | Tests |
|---|---|---|
| `TestAddSymposium` | `POST /api/events/add_symposium` | New symposium inserted (status "saved", response includes `symposium_id` and `records_inserted`); existing UUID triggers an update instead of insert; empty `symposium_name` returns 422. |
| `TestAddDepartment` | `POST /api/events/add_department` | Valid department inserted (status "Inserted"); non-Hamilton email returns 422. |
| `TestAddClass` | `POST /api/events/add_class` | Valid class with two professors inserted; response includes two `professor_ids`; empty class name returns 422. |
| `TestAddStudents` | `POST /api/events/add_students` | Valid student list inserted (status "inserted"). |
| `TestAddPresentation` | `POST /api/events/add_presentation` | Valid presentation inserted; response includes `presentation_id`; `minutes > MAX_TIME` returns 422. |
| `TestAddRequest` | `POST /api/events/add_request` | Valid professor request inserted (status "inserted"). |

### GET endpoints

Each GET test verifies that a 200 is returned. Filtered variants pass a query parameter.

| Class | Endpoint | Tests |
|---|---|---|
| `TestGetSymposiums` | `GET /api/events/symposiums` | Returns 200 with `"symposiums"` key. |
| `TestGetSymposiumById` | `GET /api/events/symposiums/{id}` | Found: returns 200 with `"symposium"` and `"timeframes"` keys. Not found: returns 404. |
| `TestGetDepartments` | `GET /api/events/departments` | Unfiltered and filtered by `symposium_id` both return 200. |
| `TestGetClasses` | `GET /api/events/classes` | Returns 200. |
| `TestGetStudents` | `GET /api/events/students` | Returns 200. |
| `TestGetPresentations` | `GET /api/events/presentations` | Returns 200. |
| `TestGetProfessors` | `GET /api/events/professors` | Returns 200. |
| `TestGetTimeframes` | `GET /api/events/timeframes` | Returns 200. |
| `TestGetRequests` | `GET /api/events/requests` | Returns 200. |

### PUT endpoints

| Class | Endpoint | Tests |
|---|---|---|
| `TestUpdateTimeframes` | `PUT /api/events/update_timeframes` | Valid payload returns 200 with status "updated". |
| `TestUpdateStudent` | `PUT /api/events/update_student` | All required fields returns 200; `"name"` appears in `fields_updated`. Missing fields returns 422. |
| `TestUpdateProfessor` | `PUT /api/events/update_professor` | All required fields returns 200. |
| `TestUpdateClass` | `PUT /api/events/update_class` | All required fields returns 200. |
| `TestUpdateDepartment` | `PUT /api/events/update_department` | All required fields returns 200. |
| `TestUpdateSymposium` | `PUT /api/events/update_symposium` | Updating name: 200, `"name"` in `fields_updated`. Updating rooms: 200. |
| `TestUpdatePresentation` | `PUT /api/events/update_presentation` | Updating title with empty `presenting_students`: 200, `presenting_students_updated` is `True`. Updating students: 200, `presenting_students_updated` is `True`. |

### DELETE endpoints

Each delete test verifies status 200 and `{"status": "deleted"}` in the response body.

| Class | Endpoint |
|---|---|
| `TestDeleteSymposium` | `DELETE /api/events/delete_symposium?symposium_id=...` |
| `TestDeleteDepartment` | `DELETE /api/events/delete_department?department_id=...` |
| `TestDeleteClass` | `DELETE /api/events/delete_class?class_id=...` |
| `TestDeleteStudent` | `DELETE /api/events/delete_student?student_id=...` |
| `TestDeleteProfessor` | `DELETE /api/events/delete_professor?professor_id=...` |
| `TestDeletePresentation` | `DELETE /api/events/delete_presentation?presentation_id=...` |

---

## `fake_supabase.py` — In-Memory Supabase Client

Not a test file itself, but a support module used by the integration test fixtures. Provides a drop-in replacement for the real `supabase-py` client that stores all data in Python `list[dict]` objects.

### `FakeQueryBuilder`

Accumulates filter calls (`eq`, `in_`, `limit`) and executes them against an in-memory list on `.execute()`. All ID comparisons are normalised to strings so UUID objects and string UUIDs match correctly.

| Operation | Behaviour |
|---|---|
| `select` | Returns matching rows; if `count=` was passed to `select()`, sets `.count` on the response. |
| `insert` | Appends rows to the list, auto-assigning an `id` if absent; returns inserted rows. |
| `update` | Applies the payload dict to all matching rows in-place; returns updated rows. |
| `delete` | Removes matching rows from the list; returns deleted rows. |

### `FakeTable`

Returned by `FakeSupabaseClient.table(name)`. Has `select`, `insert`, `update`, and `delete` methods, each returning a `FakeQueryBuilder`.

### `FakeSupabaseClient`

| Method | Purpose |
|---|---|
| `table(name)` | Returns a `FakeTable` backed by the named list (auto-created if missing). |
| `seed(table, rows)` | Appends pre-built rows to a table before a test. |
| `rows(table)` | Returns a snapshot of current rows for assertion. |
| `count(table)` | Returns the number of rows currently in the table. |
| `reset()` | Wipes all tables (called implicitly by the fixture between tests). |

---

## `test_integration.py` — End-to-End Integration Tests

Uses the `integration_client` and `fake_supabase` fixtures. HTTP requests travel through the full router → supabase_io → `FakeSupabaseClient` stack so that real insertion, retrieval, enrichment, and cascade logic is exercised.

### `TestSymposiumLifecycle`

| Test | What it checks |
|---|---|
| `test_post_and_get_all` | POST a symposium then GET `/symposiums` — the row is present with the correct name and room count. |
| `test_get_by_id_returns_symposium_and_timeframes` | POST with two timeframe windows, then GET by ID — the response includes the symposium row and both timeframe rows. |
| `test_get_by_id_not_found` | GET with an unknown ID returns 404. |
| `test_upsert_same_id_updates_not_duplicates` | POST the same `symposium_id` twice — only one row exists after the second call, and its `name` and `rooms_available` reflect the update. |
| `test_post_inserts_timeframes` | POSTing with two timeframe windows results in exactly two rows in the `timeframes` table. |

### `TestTimeframeReplacement`

| Test | What it checks |
|---|---|
| `test_put_replaces_all_timeframes` | Seeds two existing timeframe rows, then PUT update_timeframes with one new slot — the two old rows are deleted and the new row is inserted, leaving exactly one row linked to the correct ID. |

### `TestCascadeDeleteClass`

| Test | What it checks |
|---|---|
| `test_delete_class_removes_class_row` | After deleting a class, the `classes` table is empty. |
| `test_delete_class_removes_professors` | After deleting a class, the `professors` table is empty. |
| `test_delete_class_removes_students` | After adding two students to a class and deleting the class, the `students` table is empty. |
| `test_delete_class_count_response` | The `records_deleted` dict includes `classes ≥ 1` and `professors ≥ 1`; `lines_edited` is an integer ≥ 2. |

### `TestPresentationEnrichment`

| Test | What it checks |
|---|---|
| `test_presentations_include_presenting_students` | Creates a class, adds two students, creates a presentation referencing both student IDs, then GET `/presentations` — the single presentation row contains a `presenting_students` list with both students' names. |
| `test_presentations_empty_when_no_data` | GET `/presentations` on an empty database returns `{"data": []}`. |

### `TestStudentUpdate`

| Test | What it checks |
|---|---|
| `test_update_student_persists_to_db` | Creates a student via POST, then PUT update_student with a new name and email — the in-memory row is mutated and reflects the new values. |
