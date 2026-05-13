-- Track who last modified each entity row. Combined with the audit log /
-- request-id middleware (P2 #12), this answers "who clobbered whom" cleanly.

ALTER TABLE public.symposiums    ADD COLUMN IF NOT EXISTS last_modified_by uuid;
ALTER TABLE public.departments   ADD COLUMN IF NOT EXISTS last_modified_by uuid;
ALTER TABLE public.classes       ADD COLUMN IF NOT EXISTS last_modified_by uuid;
ALTER TABLE public.professors    ADD COLUMN IF NOT EXISTS last_modified_by uuid;
ALTER TABLE public.students      ADD COLUMN IF NOT EXISTS last_modified_by uuid;
ALTER TABLE public.presentations ADD COLUMN IF NOT EXISTS last_modified_by uuid;
