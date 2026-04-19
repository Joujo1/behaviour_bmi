-- =============================================================================
-- BMI Closed-Loop — Full Schema
-- =============================================================================
-- Normal use (safe to re-run on existing DB):
--   psql <DSN> -f db/schema.sql
--
-- Fresh reset (drops everything and recreates):
--   psql <DSN> -v RESET=1 -f db/schema.sql
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Optional reset: uncomment the block below OR run with -v RESET=1
-- ---------------------------------------------------------------------------

\if :{?RESET}
    DROP TABLE IF EXISTS trial_results        CASCADE;
    DROP TABLE IF EXISTS recordings           CASCADE;
    DROP TABLE IF EXISTS sessions             CASCADE;
    DROP TABLE IF EXISTS subjects             CASCADE;
    DROP TABLE IF EXISTS training_substages   CASCADE;
    DROP TABLE IF EXISTS training_stages      CASCADE;
\endif


-- ---------------------------------------------------------------------------
-- Training curriculum
--
-- training_stages   — top-level groupings, e.g. "Habituation", "Easy clicks"
-- training_substages — one row per level; carries the trial definition and
--                      advancement rules. task_config is the JSON sent to the Pi.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS training_stages (
    id          SERIAL PRIMARY KEY,
    name        TEXT   NOT NULL UNIQUE,
    description TEXT,
    sort_order  INT    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS training_substages (
    id                       SERIAL  PRIMARY KEY,
    stage_id                 INT     NOT NULL REFERENCES training_stages(id) ON DELETE RESTRICT,
    substage_number          INT     NOT NULL,
    label                    TEXT    NOT NULL,
    -- Full trial definition (states, transitions, actions) sent to the Pi
    task_config              JSONB   NOT NULL DEFAULT '{}',
    -- Advancement rules. Format: {"type": "pct_correct", "window": 20, "threshold": 0.80}
    -- NULL = no automatic transition, manual override only.
    advance_criteria         JSONB,
    fallback_criteria        JSONB,
    -- Where to go when criteria are met. NULL = end of curriculum / no fallback.
    advance_to_substage_id   INT     REFERENCES training_substages(id) ON DELETE SET NULL,
    fallback_to_substage_id  INT     REFERENCES training_substages(id) ON DELETE SET NULL,
    retired                  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (stage_id, substage_number)
);


-- ---------------------------------------------------------------------------
-- Subjects (animals)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subjects (
    id                  SERIAL       PRIMARY KEY,
    code                TEXT         NOT NULL UNIQUE,   -- e.g. "R001"
    sex                 CHAR(1)      CHECK (sex IN ('M', 'F')),
    dob                 DATE,
    weight_g            NUMERIC(6,1),
    water_restricted    BOOLEAN      NOT NULL DEFAULT FALSE,
    enrolled_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    current_substage_id INT          REFERENCES training_substages(id) ON DELETE SET NULL,
    substage_entered_at TIMESTAMPTZ,                    -- when the current substage was last entered
    notes               TEXT
);
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS substage_entered_at TIMESTAMPTZ;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS species             TEXT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS strain              TEXT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS experiment_nr       TEXT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS reference_weight_g  NUMERIC;


-- ---------------------------------------------------------------------------
-- Sessions
-- One row per sitting. Links an animal to a cage on a given day.
-- substage_id is snapshotted at session-open time so the record is stable
-- even if the animal advances mid-session.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sessions (
    id             SERIAL       PRIMARY KEY,
    cage_id        INT,
    session_number INT,
    researcher     TEXT,
    notes          TEXT,
    subject_id     INT          REFERENCES subjects(id),
    substage_id    INT          REFERENCES training_substages(id),
    weight_g       NUMERIC(6,1),
    water_ml       NUMERIC(5,1),
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    closed_at      TIMESTAMPTZ,
    UNIQUE (subject_id, session_number)
);

-- Idempotent migrations for existing databases
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS cage_id        INT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_number INT;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'sessions_subject_id_session_number_key'
    ) THEN
        ALTER TABLE sessions ADD CONSTRAINT sessions_subject_id_session_number_key
            UNIQUE (subject_id, session_number);
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- Welfare scoresheet entries
-- One row per daily welfare check per subject.  Auto-created on session open;
-- researchers fill in scores, weight, and notes via the scoresheet UI.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS welfare_entries (
    id                  SERIAL      PRIMARY KEY,
    subject_id          INT         NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    session_id          INT         REFERENCES sessions(id),
    entry_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
    entry_time          TIME        NOT NULL DEFAULT CURRENT_TIME,
    days_in_experiment  INT,
    procedure_nr        TEXT,
    procedure_details   TEXT,
    weight_g            NUMERIC,
    weight_change_pct   NUMERIC,
    score_a             SMALLINT    NOT NULL DEFAULT 0 CHECK (score_a IN (0,1,2)),
    score_b             SMALLINT    NOT NULL DEFAULT 0 CHECK (score_b IN (0,1,2)),
    score_c             SMALLINT    NOT NULL DEFAULT 0 CHECK (score_c IN (0,1,2)),
    score_d             SMALLINT    NOT NULL DEFAULT 0 CHECK (score_d IN (0,1,2)),
    medication          TEXT,
    remarks             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- Trial results
-- One row per trial completion or abort received from the Pi.
-- session_id and substage_id are NULL for one-shot/dev runs that bypass
-- the session workflow.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trial_results (
    id           SERIAL      PRIMARY KEY,
    cage_id      INT         NOT NULL,
    trial_id     TEXT        NOT NULL,
    outcome      TEXT        NOT NULL CHECK (outcome IN ('correct', 'wrong', 'aborted')),
    events       JSONB       NOT NULL DEFAULT '[]',
    session_id   INT         REFERENCES sessions(id),
    substage_id  INT         REFERENCES training_substages(id),
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- Recordings
-- Written by frame_writer.py in chunks of config.DB_CHUNK_SIZE frames.
-- Each row covers one chunk of a binary recording file for one cage.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recordings (
    id                 BIGSERIAL   PRIMARY KEY,
    cage_id            INT         NOT NULL,
    chunk_start_frame  INT,
    chunk_end_frame    INT,
    chunk_start_ts     BIGINT,     -- microsecond timestamp from Pi
    chunk_end_ts       BIGINT,
    chunk_byte_offset  BIGINT,
    chunk_frame_count  INT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_trial_results_cage       ON trial_results (cage_id);
CREATE INDEX IF NOT EXISTS idx_trial_results_session    ON trial_results (session_id);
CREATE INDEX IF NOT EXISTS idx_trial_results_substage   ON trial_results (substage_id);
CREATE INDEX IF NOT EXISTS idx_trial_results_completed  ON trial_results (completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_subjects_substage        ON subjects (current_substage_id);
CREATE INDEX IF NOT EXISTS idx_substages_stage          ON training_substages (stage_id);
CREATE INDEX IF NOT EXISTS idx_recordings_cage          ON recordings (cage_id);
CREATE INDEX IF NOT EXISTS idx_sessions_subject         ON sessions (subject_id);
CREATE INDEX IF NOT EXISTS idx_welfare_subject          ON welfare_entries (subject_id);
CREATE INDEX IF NOT EXISTS idx_welfare_session          ON welfare_entries (session_id);


