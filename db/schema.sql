-- SkyLens schema
-- Star schema for aviation occurrence and flight performance data.
-- Sources: Transport Canada CADORS, NTSB CAROL, BTS On-Time Performance,
--          OurAirports reference data.

-- =========================================================
-- DIMENSIONS
-- =========================================================

IF OBJECT_ID('dim_airport','U') IS NULL
CREATE TABLE dim_airport (
    airport_key        INT IDENTITY(1,1) PRIMARY KEY,
    ident              NVARCHAR(10)  NOT NULL UNIQUE,   -- ICAO, canonical identity
    iata_code          NVARCHAR(5)   NULL,
    local_code         NVARCHAR(10)  NULL,
    name               NVARCHAR(200) NOT NULL,
    airport_type       NVARCHAR(30)  NULL,              -- large_/medium_/small_airport, heliport
    latitude           FLOAT         NULL,
    longitude          FLOAT         NULL,
    elevation_ft       INT           NULL,
    iso_country        NVARCHAR(2)   NULL,
    iso_region         NVARCHAR(10)  NULL,
    municipality       NVARCHAR(100) NULL,
    runway_count       INT           NULL,
    longest_runway_ft  INT           NULL,
    -- Closed airports are retained deliberately. CYKZ and CYXD alone account
    -- for 2,465 CADORS records; filtering them would drop those coordinates.
    is_closed          BIT           NOT NULL DEFAULT 0
);

IF OBJECT_ID('dim_operator','U') IS NULL
CREATE TABLE dim_operator (
    operator_key  INT IDENTITY(1,1) PRIMARY KEY,
    name          NVARCHAR(200) NOT NULL,
    iata_code     NVARCHAR(5)   NULL,
    icao_code     NVARCHAR(5)   NULL,
    country       NVARCHAR(100) NULL
);

IF OBJECT_ID('dim_aircraft','U') IS NULL
CREATE TABLE dim_aircraft (
    aircraft_key     INT IDENTITY(1,1) PRIMARY KEY,
    registration     NVARCHAR(20)  NULL,   -- normalized: C- prefix restored
    type_designator  NVARCHAR(20)  NULL,
    manufacturer     NVARCHAR(100) NULL,
    model            NVARCHAR(100) NULL,
    year_built       INT           NULL
);

IF OBJECT_ID('dim_date','U') IS NULL
CREATE TABLE dim_date (
    date_key     INT PRIMARY KEY,          -- yyyymmdd
    full_date    DATE        NOT NULL,
    year         INT         NOT NULL,
    quarter      INT         NOT NULL,
    month        INT         NOT NULL,
    month_name   NVARCHAR(20) NOT NULL,
    day_of_week  INT         NOT NULL,
    season       NVARCHAR(10) NOT NULL
);

IF OBJECT_ID('dim_category','U') IS NULL
CREATE TABLE dim_category (
    category_key  INT IDENTITY(1,1) PRIMARY KEY,
    cictt_code    NVARCHAR(10)  NOT NULL UNIQUE,
    cictt_label   NVARCHAR(150) NOT NULL,
    plain_label   NVARCHAR(150) NULL,
    severity_tier NVARCHAR(10)  NULL,
    -- OTHR is 25% of CADORS and would dominate every breakdown chart.
    -- Counted in totals, excluded from category charts.
    exclude_from_charts BIT NOT NULL DEFAULT 0
);

IF OBJECT_ID('dim_source_authority','U') IS NULL
CREATE TABLE dim_source_authority (
    authority_key             INT IDENTITY(1,1) PRIMARY KEY,
    name                      NVARCHAR(100) NOT NULL,
    country                   NVARCHAR(2)   NOT NULL,
    coverage_description      NVARCHAR(500) NULL,
    reporting_threshold_notes NVARCHAR(500) NULL
);

IF OBJECT_ID('dim_theme','U') IS NULL
CREATE TABLE dim_theme (
    theme_key    INT IDENTITY(1,1) PRIMARY KEY,
    label        NVARCHAR(150) NOT NULL,
    airport_key  INT NULL,
    member_count INT NULL,
    growth_rate  FLOAT NULL
);

-- =========================================================
-- TAXONOMY MAPPING
-- Source of truth is db/map_source_category.csv, hand-built against
-- the CICTT v4.8 (May 2021) occurrence category definitions.
-- =========================================================

IF OBJECT_ID('map_source_category','U') IS NULL
CREATE TABLE map_source_category (
    map_key               INT IDENTITY(1,1) PRIMARY KEY,
    authority_key         INT NOT NULL,
    source_category_label NVARCHAR(200) NOT NULL,
    category_key          INT NOT NULL,
    mapping_confidence    NVARCHAR(20) NOT NULL,   -- exact | approximate | best-effort
    mapping_notes         NVARCHAR(1000) NULL
);

-- =========================================================
-- FACTS
-- =========================================================

IF OBJECT_ID('fact_occurrence','U') IS NULL
CREATE TABLE fact_occurrence (
    occurrence_key   BIGINT IDENTITY(1,1) PRIMARY KEY,
    authority_key    INT           NOT NULL,
    source_record_id NVARCHAR(50)  NOT NULL,
    date_key         INT           NULL,
    airport_key      INT           NULL,   -- NULL for en-route (21% of CADORS)
    operator_key     INT           NULL,
    aircraft_key     INT           NULL,
    category_key     INT           NULL,   -- NTSB rows populated by classifier
    occurrence_type  NVARCHAR(50)  NULL,   -- Incident / Accident
    phase_of_flight  NVARCHAR(50)  NULL,
    severity_tier    NVARCHAR(10)  NULL,
    fatalities       INT           NULL,
    injuries         INT           NULL,
    -- CADORS publishes no narrative text; source_text is NTSB ProbableCause.
    source_text      NVARCHAR(MAX) NULL,
    findings_l1      NVARCHAR(100) NULL,   -- NTSB Findings hierarchy, level 1
    narrative_plain  NVARCHAR(1000) NULL,  -- generated, precomputed
    citation_ids     NVARCHAR(200) NULL,
    flight_number    NVARCHAR(20)  NULL,   -- structured in CADORS, not extracted
    registration     NVARCHAR(20)  NULL,
    match_confidence NVARCHAR(20)  NULL,   -- exact_flight|registration|operator_route
    embedding        VARBINARY(MAX) NULL,
    theme_key        INT           NULL,
    -- 1 = counted in rates (12-month window aligned to BTS)
    -- 0 = text corpus only, never counted
    in_analysis_window BIT         NOT NULL DEFAULT 1,
    ingested_at      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_occurrence UNIQUE (authority_key, source_record_id)
);

IF OBJECT_ID('fact_flight_performance','U') IS NULL
CREATE TABLE fact_flight_performance (
    flight_key             BIGINT IDENTITY(1,1) PRIMARY KEY,
    date_key               INT NOT NULL,
    operator_key           INT NULL,
    flight_number          NVARCHAR(10) NULL,
    tail_number            NVARCHAR(20) NULL,
    origin_airport_key     INT NULL,
    dest_airport_key       INT NULL,
    sched_dep              TIME NULL,
    actual_dep             TIME NULL,
    dep_delay_min          INT NULL,
    taxi_out_min           INT NULL,
    wheels_off             TIME NULL,
    wheels_on              TIME NULL,
    taxi_in_min            INT NULL,
    sched_arr              TIME NULL,
    actual_arr             TIME NULL,
    arr_delay_min          INT NULL,
    air_time_min           INT NULL,
    distance_mi            INT NULL,
    cancelled              BIT NOT NULL DEFAULT 0,
    cancellation_code      NVARCHAR(5) NULL,
    diverted               BIT NOT NULL DEFAULT 0,
    div_airport            NVARCHAR(10) NULL,
    carrier_delay_min      INT NULL,
    weather_delay_min      INT NULL,
    nas_delay_min          INT NULL,
    security_delay_min     INT NULL,
    late_aircraft_delay_min INT NULL
);

-- Denominator for every rate. Without it, busy airports look dangerous.
IF OBJECT_ID('fact_airport_movements','U') IS NULL
CREATE TABLE fact_airport_movements (
    airport_key    INT NOT NULL,
    date_key       INT NOT NULL,
    movement_count INT NOT NULL,
    is_estimated   BIT NOT NULL DEFAULT 0,  -- 1 for Canadian size-band estimates
    CONSTRAINT pk_movements PRIMARY KEY (airport_key, date_key)
);

-- =========================================================
-- MART
-- =========================================================

IF OBJECT_ID('mart_airport_report','U') IS NULL
CREATE TABLE mart_airport_report (
    airport_key  INT PRIMARY KEY,
    payload      NVARCHAR(MAX) NOT NULL,
    generated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

-- =========================================================
-- GUARD VIEW
-- Every rate and count query reads this, never fact_occurrence directly.
-- Makes it structurally impossible for corpus rows to corrupt a rate.
-- =========================================================
GO
CREATE OR ALTER VIEW v_occurrence_analysis AS
SELECT * FROM fact_occurrence WHERE in_analysis_window = 1;
GO

-- =========================================================
-- INDEXES
-- =========================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_airport')
CREATE NONCLUSTERED INDEX ix_occ_airport ON fact_occurrence(airport_key) INCLUDE (date_key, category_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_date')
CREATE NONCLUSTERED INDEX ix_occ_date ON fact_occurrence(date_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_category')
CREATE NONCLUSTERED INDEX ix_occ_category ON fact_occurrence(category_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_window')
CREATE NONCLUSTERED INDEX ix_occ_window ON fact_occurrence(in_analysis_window);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_flight')
CREATE NONCLUSTERED INDEX ix_occ_flight ON fact_occurrence(flight_number);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_occ_reg')
CREATE NONCLUSTERED INDEX ix_occ_reg ON fact_occurrence(registration);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_perf_flight')
CREATE NONCLUSTERED INDEX ix_perf_flight ON fact_flight_performance(flight_number, origin_airport_key, dest_airport_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_perf_date')
CREATE NONCLUSTERED INDEX ix_perf_date ON fact_flight_performance(date_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_airport_ident')
CREATE NONCLUSTERED INDEX ix_airport_ident ON dim_airport(ident) INCLUDE (name, latitude, longitude);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_airport_iata')
CREATE NONCLUSTERED INDEX ix_airport_iata ON dim_airport(iata_code);