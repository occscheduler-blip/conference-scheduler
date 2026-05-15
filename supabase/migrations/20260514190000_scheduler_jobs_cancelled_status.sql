-- Allow 'cancelled' as a terminal status for scheduler_jobs, so an admin can
-- abort a long-running schedule run from the UI and the backend can record it.
ALTER TABLE "public"."scheduler_jobs"
    DROP CONSTRAINT IF EXISTS "scheduler_jobs_status_check";

ALTER TABLE "public"."scheduler_jobs"
    ADD CONSTRAINT "scheduler_jobs_status_check"
    CHECK (("status" = ANY (ARRAY[
        'pending'::"text",
        'running'::"text",
        'completed'::"text",
        'failed'::"text",
        'cancelled'::"text"
    ])));
