-- Add updated_at columns to entity tables, plus a BEFORE UPDATE trigger that
-- bumps it. Used by the optimistic-concurrency check in update_* routers
-- (request body's expected_updated_at must match the row's current value).

CREATE OR REPLACE FUNCTION public.tg_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

ALTER TABLE public.symposiums    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.departments   ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.classes       ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.professors    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.students      ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.presentations ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DROP TRIGGER IF EXISTS trg_set_updated_at_symposiums    ON public.symposiums;
CREATE TRIGGER trg_set_updated_at_symposiums    BEFORE UPDATE ON public.symposiums
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_departments   ON public.departments;
CREATE TRIGGER trg_set_updated_at_departments   BEFORE UPDATE ON public.departments
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_classes       ON public.classes;
CREATE TRIGGER trg_set_updated_at_classes       BEFORE UPDATE ON public.classes
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_professors    ON public.professors;
CREATE TRIGGER trg_set_updated_at_professors    BEFORE UPDATE ON public.professors
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_students      ON public.students;
CREATE TRIGGER trg_set_updated_at_students      BEFORE UPDATE ON public.students
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_presentations ON public.presentations;
CREATE TRIGGER trg_set_updated_at_presentations BEFORE UPDATE ON public.presentations
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();
