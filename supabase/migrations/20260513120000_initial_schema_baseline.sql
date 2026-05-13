-- Baseline snapshot of the production schema as of 2026-05-13.
-- Generated via `supabase db dump --schema public --linked` against the
-- original project (ref: yrwhkzrurozsfdmkazxn), with `app_runtime` role
-- grants stripped (the role was unused — backend connects via service-role
-- key + the postgres pooler user, never `app_runtime`).
--
-- The per-feature migrations that preceded this baseline live in
-- ../migrations_archive/ for historical reference. They were superseded
-- because the live remote schema had drifted from those migrations
-- (renamed FK/PK constraints, dropped legacy columns, added NOT NULLs,
-- RLS enabled on every table, etc.).

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE OR REPLACE FUNCTION "public"."tg_set_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."tg_set_updated_at"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."admins" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" "text" NOT NULL,
    "password_hash" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT ("now"() AT TIME ZONE 'est'::"text") NOT NULL,
    "is_superadmin" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."admins" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."attendee_itinerary" (
    "attendee_id" "uuid" NOT NULL,
    "presentation_id" "uuid" NOT NULL
);


ALTER TABLE "public"."attendee_itinerary" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."attendees" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."attendees" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."classes" (
    "id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "department_id" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid"
);


ALTER TABLE "public"."classes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."departments" (
    "id" "uuid" NOT NULL,
    "department_name" "text" NOT NULL,
    "department_head_name" "text" NOT NULL,
    "email" "text" NOT NULL,
    "symposium_id" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid",
    "emailed" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."departments" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."otp_tokens" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" "text" NOT NULL,
    "token_hash" "text" NOT NULL,
    "role" "text" NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "used" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."otp_tokens" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."presentation_professors" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "presentation_id" "uuid" NOT NULL,
    "professor_id" "uuid" NOT NULL
);


ALTER TABLE "public"."presentation_professors" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."presentations" (
    "id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "class_id" "uuid" NOT NULL,
    "minutes" smallint NOT NULL,
    "buffer" smallint NOT NULL,
    "room" smallint,
    "temporary_room" smallint,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid",
    CONSTRAINT "presentations_buffer_nonneg" CHECK ((("buffer" IS NULL) OR ("buffer" >= 0))),
    CONSTRAINT "presentations_minutes_positive" CHECK (("minutes" > 0)),
    CONSTRAINT "presentations_room_nonneg" CHECK ((("room" IS NULL) OR ("room" >= 0))),
    CONSTRAINT "presentations_temp_room_nonneg" CHECK ((("temporary_room" IS NULL) OR ("temporary_room" >= 0)))
);


ALTER TABLE "public"."presentations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."presenting_students" (
    "id" "uuid" NOT NULL,
    "student_id" "uuid" NOT NULL,
    "presentation_id" "uuid" NOT NULL
);


ALTER TABLE "public"."presenting_students" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."professors" (
    "id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "email" "text" NOT NULL,
    "class_id" "uuid" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid",
    "emailed" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."professors" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."requests" (
    "id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "email" "text" NOT NULL,
    "student_id" "uuid" NOT NULL
);


ALTER TABLE "public"."requests" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."scheduler_jobs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "symposium_id" "uuid" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "result" "jsonb",
    "error" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "scheduler_jobs_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'running'::"text", 'completed'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."scheduler_jobs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."students" (
    "id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "email" "text" NOT NULL,
    "class_id" "uuid" NOT NULL,
    "presentation_id" "uuid",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid",
    "emailed" boolean DEFAULT false NOT NULL
);


ALTER TABLE "public"."students" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."symposiums" (
    "id" "uuid" NOT NULL,
    "created_at" timestamp without time zone NOT NULL,
    "name" "text" NOT NULL,
    "rooms_available" smallint NOT NULL,
    "default_buffer" smallint,
    "room_names" "text"[],
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_modified_by" "uuid",
    CONSTRAINT "symposiums_rooms_positive" CHECK (("rooms_available" > 0))
);


ALTER TABLE "public"."symposiums" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."temporary_timeframes" (
    "id" "uuid" NOT NULL,
    "linked_id" "uuid" NOT NULL,
    "start_time" timestamp without time zone NOT NULL,
    "end_time" timestamp without time zone NOT NULL,
    "symposium_id" "uuid" NOT NULL,
    CONSTRAINT "temporary_timeframes_end_after_start" CHECK (("end_time" > "start_time"))
);


ALTER TABLE "public"."temporary_timeframes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."timeframes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "start_time" timestamp without time zone NOT NULL,
    "end_time" timestamp without time zone NOT NULL,
    "linked_id" "uuid" NOT NULL,
    CONSTRAINT "timeframes_end_after_start" CHECK (("end_time" > "start_time"))
);


ALTER TABLE "public"."timeframes" OWNER TO "postgres";


ALTER TABLE ONLY "public"."admins"
    ADD CONSTRAINT "admins_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."attendee_itinerary"
    ADD CONSTRAINT "attendee_itinerary_pkey" PRIMARY KEY ("attendee_id", "presentation_id");



ALTER TABLE ONLY "public"."attendees"
    ADD CONSTRAINT "attendees_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."attendees"
    ADD CONSTRAINT "attendees_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."classes"
    ADD CONSTRAINT "classes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."departments"
    ADD CONSTRAINT "dept_heads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."otp_tokens"
    ADD CONSTRAINT "otp_tokens_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."presentation_professors"
    ADD CONSTRAINT "presentation_professors_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."presentation_professors"
    ADD CONSTRAINT "presentation_professors_presentation_id_professor_id_key" UNIQUE ("presentation_id", "professor_id");



ALTER TABLE ONLY "public"."presentations"
    ADD CONSTRAINT "presentations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."presenting_students"
    ADD CONSTRAINT "presenting_students_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."presenting_students"
    ADD CONSTRAINT "presenting_students_uniq_presentation_student" UNIQUE ("presentation_id", "student_id");



ALTER TABLE ONLY "public"."requests"
    ADD CONSTRAINT "prof_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."professors"
    ADD CONSTRAINT "professors_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."scheduler_jobs"
    ADD CONSTRAINT "scheduler_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "students_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."symposiums"
    ADD CONSTRAINT "symposiums_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."temporary_timeframes"
    ADD CONSTRAINT "temporary_timeframes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."timeframes"
    ADD CONSTRAINT "timeframes_pkey" PRIMARY KEY ("id");



CREATE INDEX "attendee_itinerary_attendee_idx" ON "public"."attendee_itinerary" USING "btree" ("attendee_id");



CREATE INDEX "attendees_email_idx" ON "public"."attendees" USING "btree" ("email");



CREATE INDEX "classes_department_id_idx" ON "public"."classes" USING "btree" ("department_id");



CREATE INDEX "departments_symposium_id_idx" ON "public"."departments" USING "btree" ("symposium_id");



CREATE INDEX "presentation_professors_presentation_id_idx" ON "public"."presentation_professors" USING "btree" ("presentation_id");



CREATE INDEX "presentation_professors_professor_id_idx" ON "public"."presentation_professors" USING "btree" ("professor_id");



CREATE INDEX "presentations_class_id_idx" ON "public"."presentations" USING "btree" ("class_id");



CREATE INDEX "presenting_students_presentation_id_idx" ON "public"."presenting_students" USING "btree" ("presentation_id");



CREATE INDEX "presenting_students_student_id_idx" ON "public"."presenting_students" USING "btree" ("student_id");



CREATE INDEX "professors_class_id_idx" ON "public"."professors" USING "btree" ("class_id");



CREATE UNIQUE INDEX "professors_uniq_class_email" ON "public"."professors" USING "btree" ("class_id", "lower"("email"));



CREATE INDEX "requests_student_id_idx" ON "public"."requests" USING "btree" ("student_id");



CREATE UNIQUE INDEX "scheduler_jobs_active_singleton" ON "public"."scheduler_jobs" USING "btree" ("symposium_id") WHERE ("status" = ANY (ARRAY['pending'::"text", 'running'::"text"]));



CREATE INDEX "scheduler_jobs_created_at_idx" ON "public"."scheduler_jobs" USING "btree" ("created_at");



CREATE INDEX "scheduler_jobs_symposium_id_idx" ON "public"."scheduler_jobs" USING "btree" ("symposium_id");



CREATE INDEX "students_class_id_idx" ON "public"."students" USING "btree" ("class_id");



CREATE INDEX "students_presentation_id_idx" ON "public"."students" USING "btree" ("presentation_id");



CREATE UNIQUE INDEX "students_uniq_class_email" ON "public"."students" USING "btree" ("class_id", "lower"("email"));



CREATE INDEX "timeframes_linked_id_idx" ON "public"."timeframes" USING "btree" ("linked_id");



CREATE OR REPLACE TRIGGER "trg_set_updated_at_classes" BEFORE UPDATE ON "public"."classes" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_set_updated_at_departments" BEFORE UPDATE ON "public"."departments" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_set_updated_at_presentations" BEFORE UPDATE ON "public"."presentations" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_set_updated_at_professors" BEFORE UPDATE ON "public"."professors" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_set_updated_at_students" BEFORE UPDATE ON "public"."students" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



CREATE OR REPLACE TRIGGER "trg_set_updated_at_symposiums" BEFORE UPDATE ON "public"."symposiums" FOR EACH ROW EXECUTE FUNCTION "public"."tg_set_updated_at"();



ALTER TABLE ONLY "public"."attendee_itinerary"
    ADD CONSTRAINT "attendee_itinerary_attendee_id_fkey" FOREIGN KEY ("attendee_id") REFERENCES "public"."attendees"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."attendee_itinerary"
    ADD CONSTRAINT "attendee_itinerary_presentation_id_fkey" FOREIGN KEY ("presentation_id") REFERENCES "public"."presentations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."classes"
    ADD CONSTRAINT "fk_classes_department" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id");



ALTER TABLE ONLY "public"."departments"
    ADD CONSTRAINT "fk_departments_symposium" FOREIGN KEY ("symposium_id") REFERENCES "public"."symposiums"("id");



ALTER TABLE ONLY "public"."presentations"
    ADD CONSTRAINT "fk_presentations_class" FOREIGN KEY ("class_id") REFERENCES "public"."classes"("id");



ALTER TABLE ONLY "public"."presenting_students"
    ADD CONSTRAINT "fk_presenting_students_presentation" FOREIGN KEY ("presentation_id") REFERENCES "public"."presentations"("id");



ALTER TABLE ONLY "public"."presenting_students"
    ADD CONSTRAINT "fk_presenting_students_student" FOREIGN KEY ("student_id") REFERENCES "public"."students"("id");



ALTER TABLE ONLY "public"."professors"
    ADD CONSTRAINT "fk_professors_class" FOREIGN KEY ("class_id") REFERENCES "public"."classes"("id");



ALTER TABLE ONLY "public"."requests"
    ADD CONSTRAINT "fk_requests_student" FOREIGN KEY ("student_id") REFERENCES "public"."students"("id");



ALTER TABLE ONLY "public"."students"
    ADD CONSTRAINT "fk_students_class" FOREIGN KEY ("class_id") REFERENCES "public"."classes"("id");



ALTER TABLE ONLY "public"."presentation_professors"
    ADD CONSTRAINT "presentation_professors_presentation_id_fkey" FOREIGN KEY ("presentation_id") REFERENCES "public"."presentations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."presentation_professors"
    ADD CONSTRAINT "presentation_professors_professor_id_fkey" FOREIGN KEY ("professor_id") REFERENCES "public"."professors"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."scheduler_jobs"
    ADD CONSTRAINT "scheduler_jobs_symposium_id_fkey" FOREIGN KEY ("symposium_id") REFERENCES "public"."symposiums"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."temporary_timeframes"
    ADD CONSTRAINT "temporary_timeframes_symposium_id_fkey" FOREIGN KEY ("symposium_id") REFERENCES "public"."symposiums"("id") ON DELETE CASCADE;



CREATE POLICY "Everything" ON "public"."students" TO "supabase_admin", "postgres" USING (true);



ALTER TABLE "public"."admins" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."attendee_itinerary" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."attendees" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."classes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."departments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."otp_tokens" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."presentation_professors" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."presentations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."presenting_students" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."professors" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."requests" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."scheduler_jobs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."students" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."symposiums" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."temporary_timeframes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."timeframes" ENABLE ROW LEVEL SECURITY;


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."tg_set_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."tg_set_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."tg_set_updated_at"() TO "service_role";



GRANT ALL ON TABLE "public"."admins" TO "anon";
GRANT ALL ON TABLE "public"."admins" TO "authenticated";
GRANT ALL ON TABLE "public"."admins" TO "service_role";



GRANT ALL ON TABLE "public"."attendee_itinerary" TO "anon";
GRANT ALL ON TABLE "public"."attendee_itinerary" TO "authenticated";
GRANT ALL ON TABLE "public"."attendee_itinerary" TO "service_role";



GRANT ALL ON TABLE "public"."attendees" TO "anon";
GRANT ALL ON TABLE "public"."attendees" TO "authenticated";
GRANT ALL ON TABLE "public"."attendees" TO "service_role";



GRANT ALL ON TABLE "public"."classes" TO "anon";
GRANT ALL ON TABLE "public"."classes" TO "authenticated";
GRANT ALL ON TABLE "public"."classes" TO "service_role";



GRANT ALL ON TABLE "public"."departments" TO "anon";
GRANT ALL ON TABLE "public"."departments" TO "authenticated";
GRANT ALL ON TABLE "public"."departments" TO "service_role";



GRANT ALL ON TABLE "public"."otp_tokens" TO "anon";
GRANT ALL ON TABLE "public"."otp_tokens" TO "authenticated";
GRANT ALL ON TABLE "public"."otp_tokens" TO "service_role";



GRANT ALL ON TABLE "public"."presentation_professors" TO "anon";
GRANT ALL ON TABLE "public"."presentation_professors" TO "authenticated";
GRANT ALL ON TABLE "public"."presentation_professors" TO "service_role";



GRANT ALL ON TABLE "public"."presentations" TO "anon";
GRANT ALL ON TABLE "public"."presentations" TO "authenticated";
GRANT ALL ON TABLE "public"."presentations" TO "service_role";



GRANT ALL ON TABLE "public"."presenting_students" TO "anon";
GRANT ALL ON TABLE "public"."presenting_students" TO "authenticated";
GRANT ALL ON TABLE "public"."presenting_students" TO "service_role";



GRANT ALL ON TABLE "public"."professors" TO "anon";
GRANT ALL ON TABLE "public"."professors" TO "authenticated";
GRANT ALL ON TABLE "public"."professors" TO "service_role";



GRANT ALL ON TABLE "public"."requests" TO "anon";
GRANT ALL ON TABLE "public"."requests" TO "authenticated";
GRANT ALL ON TABLE "public"."requests" TO "service_role";



GRANT ALL ON TABLE "public"."scheduler_jobs" TO "anon";
GRANT ALL ON TABLE "public"."scheduler_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."scheduler_jobs" TO "service_role";



GRANT ALL ON TABLE "public"."students" TO "anon";
GRANT ALL ON TABLE "public"."students" TO "authenticated";
GRANT ALL ON TABLE "public"."students" TO "service_role";



GRANT ALL ON TABLE "public"."symposiums" TO "anon";
GRANT ALL ON TABLE "public"."symposiums" TO "authenticated";
GRANT ALL ON TABLE "public"."symposiums" TO "service_role";



GRANT ALL ON TABLE "public"."temporary_timeframes" TO "anon";
GRANT ALL ON TABLE "public"."temporary_timeframes" TO "authenticated";
GRANT ALL ON TABLE "public"."temporary_timeframes" TO "service_role";



GRANT ALL ON TABLE "public"."timeframes" TO "anon";
GRANT ALL ON TABLE "public"."timeframes" TO "authenticated";
GRANT ALL ON TABLE "public"."timeframes" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";







