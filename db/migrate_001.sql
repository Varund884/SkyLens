-- Migration 001
-- Adds support for occurrences with multiple CICTT categories and multiple
-- aircraft, plus columns needed downstream. Additive and idempotent.
--
-- Why: in the 2025-07..2026-06 window, 5,816 of 23,277 CADORS occurrences
-- carry 2-7 CICTT categories (CICTT permits multiple coding), and 2,078 of
-- 15,263 occurrences with aircraft involve 2-23 aircraft. A single
-- category_key / aircraft per row would either drop data or duplicate
-- occurrences and inflate counts.
--
-- fact_occurrence stays at one row per occurrence. category_key on it holds
-- the primary category (first non-OTHR). Full detail lives in the two tables
-- below.

-- =========================================================
-- New columns on fact_occurrence
-- =========================================================
IF COL_LENGTH('fact_occurrence','occurrence_time_utc') IS NULL
    ALTER TABLE fact_occurrence ADD occurrence_time_utc TIME NULL;

IF COL_LENGTH('fact_occurrence','occurrence_country') IS NULL
    ALTER TABLE fact_occurrence ADD occurrence_country NVARCHAR(2) NULL;

-- Semicolon-joined event names from both CADORS event tables. Input to the
-- plain-language summaries, since CADORS publishes no narrative text.
IF COL_LENGTH('fact_occurrence','event_names') IS NULL
    ALTER TABLE fact_occurrence ADD event_names NVARCHAR(500) NULL;

IF COL_LENGTH('fact_occurrence','aircraft_count') IS NULL
    ALTER TABLE fact_occurrence ADD aircraft_count INT NULL;

IF COL_LENGTH('fact_occurrence','operator_name') IS NULL
    ALTER TABLE fact_occurrence ADD operator_name NVARCHAR(150) NULL;

IF COL_LENGTH('fact_occurrence','damage') IS NULL
    ALTER TABLE fact_occurrence ADD damage NVARCHAR(30) NULL;

-- Full NTSB Findings hierarchy text. The strongest classifier feature;
-- findings_l1 holds only the top-level classes.
IF COL_LENGTH('fact_occurrence','findings') IS NULL
    ALTER TABLE fact_occurrence ADD findings NVARCHAR(MAX) NULL;

-- Where each movement count came from: 'bts' today; official all-traffic
-- counts (Statistics Canada, FAA ATADS) can be added alongside.
IF COL_LENGTH('fact_airport_movements','source') IS NULL
    ALTER TABLE fact_airport_movements ADD source NVARCHAR(20) NULL;

-- =========================================================
-- Occurrence -> CICTT categories (many-to-many)
-- =========================================================
IF OBJECT_ID('bridge_occurrence_category','U') IS NULL
CREATE TABLE bridge_occurrence_category (
    occurrence_key BIGINT NOT NULL,
    category_key   INT    NOT NULL,
    CONSTRAINT pk_bridge_occ_cat PRIMARY KEY (occurrence_key, category_key)
);

-- =========================================================
-- Occurrence -> aircraft involved (one row per aircraft)
-- =========================================================
IF OBJECT_ID('fact_occurrence_aircraft','U') IS NULL
CREATE TABLE fact_occurrence_aircraft (
    occurrence_key  BIGINT        NOT NULL,
    aircraft_seq    INT           NOT NULL,
    flight_number   NVARCHAR(20)  NULL,
    registration    NVARCHAR(20)  NULL,
    operator_name   NVARCHAR(150) NULL,
    phase_of_flight NVARCHAR(50)  NULL,
    damage          NVARCHAR(30)  NULL,
    make            NVARCHAR(80)  NULL,
    model           NVARCHAR(60)  NULL,
    year_built      INT           NULL,
    CONSTRAINT pk_occ_aircraft PRIMARY KEY (occurrence_key, aircraft_seq)
);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occair_flight')
CREATE NONCLUSTERED INDEX ix_occair_flight ON fact_occurrence_aircraft(flight_number);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occair_reg')
CREATE NONCLUSTERED INDEX ix_occair_reg ON fact_occurrence_aircraft(registration);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_bridge_cat')
CREATE NONCLUSTERED INDEX ix_bridge_cat ON bridge_occurrence_category(category_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_perf_tail')
CREATE NONCLUSTERED INDEX ix_perf_tail ON fact_flight_performance(tail_number);

-- =========================================================
-- A SELECT * view keeps the column list it was created with. Recreate it so
-- it picks up the columns added above.
-- =========================================================
GO
CREATE OR ALTER VIEW v_occurrence_analysis AS
SELECT * FROM fact_occurrence WHERE in_analysis_window = 1;
GO
