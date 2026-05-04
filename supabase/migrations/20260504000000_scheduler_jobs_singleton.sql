-- Prevent more than one in-flight scheduler job per symposium.
-- The partial predicate means terminal jobs (completed/failed) don't count,
-- so a fresh job can be started after the previous one finishes.
CREATE UNIQUE INDEX IF NOT EXISTS scheduler_jobs_active_singleton
    ON public.scheduler_jobs (symposium_id)
    WHERE status IN ('pending', 'running');
