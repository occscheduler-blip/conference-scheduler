-- Defense-in-depth schema constraints. Most concurrency races are guarded
-- by application-level locks now; these constraints turn the residual races
-- into loud IntegrityError responses instead of silent corruption.

-- presenting_students: a student should appear at most once per presentation.
ALTER TABLE public.presenting_students
    DROP CONSTRAINT IF EXISTS presenting_students_uniq_presentation_student;
ALTER TABLE public.presenting_students
    ADD CONSTRAINT presenting_students_uniq_presentation_student
    UNIQUE (presentation_id, student_id);

-- Per-class email uniqueness for students and professors. Case-insensitive
-- via a unique index on lower(email) so "Alice@Hamilton.edu" and
-- "alice@hamilton.edu" collide.
DROP INDEX IF EXISTS public.students_uniq_class_email;
CREATE UNIQUE INDEX students_uniq_class_email
    ON public.students (class_id, lower(email));

DROP INDEX IF EXISTS public.professors_uniq_class_email;
CREATE UNIQUE INDEX professors_uniq_class_email
    ON public.professors (class_id, lower(email));

-- Time ranges must be non-degenerate.
ALTER TABLE public.timeframes
    DROP CONSTRAINT IF EXISTS timeframes_end_after_start;
ALTER TABLE public.timeframes
    ADD CONSTRAINT timeframes_end_after_start CHECK (end_time > start_time);

ALTER TABLE public.temporary_timeframes
    DROP CONSTRAINT IF EXISTS temporary_timeframes_end_after_start;
ALTER TABLE public.temporary_timeframes
    ADD CONSTRAINT temporary_timeframes_end_after_start CHECK (end_time > start_time);

-- Presentation invariants.
ALTER TABLE public.presentations
    DROP CONSTRAINT IF EXISTS presentations_minutes_positive;
ALTER TABLE public.presentations
    ADD CONSTRAINT presentations_minutes_positive CHECK (minutes > 0);

ALTER TABLE public.presentations
    DROP CONSTRAINT IF EXISTS presentations_buffer_nonneg;
ALTER TABLE public.presentations
    ADD CONSTRAINT presentations_buffer_nonneg CHECK (buffer IS NULL OR buffer >= 0);

ALTER TABLE public.presentations
    DROP CONSTRAINT IF EXISTS presentations_room_nonneg;
ALTER TABLE public.presentations
    ADD CONSTRAINT presentations_room_nonneg CHECK (room IS NULL OR room >= 0);

ALTER TABLE public.presentations
    DROP CONSTRAINT IF EXISTS presentations_temp_room_nonneg;
ALTER TABLE public.presentations
    ADD CONSTRAINT presentations_temp_room_nonneg CHECK (temporary_room IS NULL OR temporary_room >= 0);

-- Symposium invariants.
ALTER TABLE public.symposiums
    DROP CONSTRAINT IF EXISTS symposiums_rooms_positive;
ALTER TABLE public.symposiums
    ADD CONSTRAINT symposiums_rooms_positive CHECK (rooms_available > 0);
