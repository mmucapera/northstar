# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# MAGIC %%configure
# MAGIC {
# MAGIC   "defaultLakehouse": {
# MAGIC     "name": "lkh_001"
# MAGIC   }
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS bronze;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS silver;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS gold;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS log;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS interface;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.cash_call_event
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     PartnerId STRING,
# MAGIC     FieldId STRING,
# MAGIC     Stage STRING,
# MAGIC     EventTimestamp TIMESTAMP,
# MAGIC     Note STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.completion
# MAGIC (
# MAGIC     CompletionId STRING,
# MAGIC     WellboreId STRING,
# MAGIC     WellId STRING,
# MAGIC     CompletionType STRING,
# MAGIC     ReservoirUnit STRING,
# MAGIC     PerforationTopM DECIMAL(18,2),
# MAGIC     PerforationBaseM DECIMAL(18,2),
# MAGIC     ArtificialLift STRING,
# MAGIC     CompletionDate DATE,
# MAGIC     IsActive BOOLEAN,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.downtime
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     CauseId STRING,
# MAGIC     Hours DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.downtime_cause
# MAGIC (
# MAGIC     CauseId STRING,
# MAGIC     CauseName STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.drilling_telemetry
# MAGIC (
# MAGIC     ReportId STRING,
# MAGIC     WellId STRING,
# MAGIC     WellboreId STRING,
# MAGIC     ReportDate DATE,
# MAGIC     DepthM DECIMAL(18,2),
# MAGIC     RopMPerHr DECIMAL(9,2),
# MAGIC     WobKlbs DECIMAL(9,2),
# MAGIC     Rpm DECIMAL(9,2),
# MAGIC     MudWeightPpg DECIMAL(9,2),
# MAGIC     FlowRateGpm DECIMAL(9,2),
# MAGIC     Npt BOOLEAN,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.facility
# MAGIC (
# MAGIC     FacilityId STRING,
# MAGIC     FacilityName STRING,
# MAGIC     FacilityType STRING,
# MAGIC     FieldId STRING,
# MAGIC     ExportPoint STRING,
# MAGIC     CapacityBopd DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.field
# MAGIC (
# MAGIC     FieldId STRING,
# MAGIC     FieldName STRING,
# MAGIC     ExportPoint STRING,
# MAGIC     WellsTotal INT,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.hse_exposure
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     HoursWorked DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.hse_incidents
# MAGIC (
# MAGIC     IncidentId STRING,
# MAGIC     PeriodId STRING,
# MAGIC     IncidentDate DATE,
# MAGIC     FieldId STRING,
# MAGIC     Severity STRING,
# MAGIC     Recordable BOOLEAN,
# MAGIC     Description STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.partner
# MAGIC (
# MAGIC     PartnerId STRING,
# MAGIC     PartnerName STRING,
# MAGIC     PartnerRole STRING,
# MAGIC     EquityPct DECIMAL(6,3),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.period
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     Period DATE,
# MAGIC     Label STRING,
# MAGIC     Year INT,
# MAGIC     Quarter INT,
# MAGIC     MonthNumber INT,
# MAGIC     MonthName STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.production
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     FieldId STRING,
# MAGIC     ActualBopd DECIMAL(18,2),
# MAGIC     ForecastBopd DECIMAL(18,2),
# MAGIC     WellsOnline INT,
# MAGIC     UptimePct DECIMAL(9,2),
# MAGIC     OpsStatus STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.production_volume
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     WellId STRING,
# MAGIC     FieldId STRING,
# MAGIC     FacilityId STRING,
# MAGIC     OilBbl DECIMAL(18,2),
# MAGIC     GasMscf DECIMAL(18,2),
# MAGIC     WaterBbl DECIMAL(18,2),
# MAGIC     OnstreamHours DECIMAL(9,2),
# MAGIC     WaterCutPct DECIMAL(9,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.reconciliation
# MAGIC (
# MAGIC     PeriodId STRING,
# MAGIC     FieldId STRING,
# MAGIC     PartnerId STRING,
# MAGIC     AllocatedBbl DECIMAL(18,2),
# MAGIC     LiftedBbl DECIMAL(18,2),
# MAGIC     CashCallStatus STRING,
# MAGIC     CashCallUsd DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.well
# MAGIC (
# MAGIC     WellId STRING,
# MAGIC     WellName STRING,
# MAGIC     FieldId STRING,
# MAGIC     FacilityId STRING,
# MAGIC     PartnerId STRING,
# MAGIC     WellType STRING,
# MAGIC     Status STRING,
# MAGIC     SpudDate DATE,
# MAGIC     TotalDepthM DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.well_test
# MAGIC (
# MAGIC     TestId STRING,
# MAGIC     TestDate DATE,
# MAGIC     PeriodId STRING,
# MAGIC     WellId STRING,
# MAGIC     CompletionId STRING,
# MAGIC     DurationHours DECIMAL(9,2),
# MAGIC     OilRateBopd DECIMAL(18,2),
# MAGIC     GasRateMscfd DECIMAL(18,2),
# MAGIC     WaterCutPct DECIMAL(9,2),
# MAGIC     GorScf DECIMAL(18,2),
# MAGIC     ChokeSize64ths INT,
# MAGIC     ThpPsi DECIMAL(18,2),
# MAGIC     Validity STRING,
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE bronze.wellbore
# MAGIC (
# MAGIC     WellboreId STRING,
# MAGIC     WellId STRING,
# MAGIC     WellboreName STRING,
# MAGIC     Trajectory STRING,
# MAGIC     IsSidetrack BOOLEAN,
# MAGIC     MeasuredDepthM DECIMAL(18,2),
# MAGIC     TrueVerticalDepthM DECIMAL(18,2),
# MAGIC     Sourcefile STRING,
# MAGIC     Manifest_package STRING,
# MAGIC     Manifest_file STRING,
# MAGIC     Load_date DATE,
# MAGIC     Load_timestamp TIMESTAMP,
# MAGIC     Partitionkey STRING,
# MAGIC     ins_batchid INT,
# MAGIC     upd_batchid INT,
# MAGIC     Exportdate TIMESTAMP,
# MAGIC     valid_from TIMESTAMP,
# MAGIC     valid_to TIMESTAMP,
# MAGIC     is_current BOOLEAN
# MAGIC )
# MAGIC USING delta;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.cash_call_event AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.PartnerId,
# MAGIC T.FieldId,
# MAGIC T.Stage,
# MAGIC T.EventTimestamp,
# MAGIC T.Note,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.cash_call_event T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.completion AS
# MAGIC SELECT DISTINCT
# MAGIC T.CompletionId,
# MAGIC T.WellboreId,
# MAGIC T.WellId,
# MAGIC T.CompletionType,
# MAGIC T.ReservoirUnit,
# MAGIC T.PerforationTopM,
# MAGIC T.PerforationBaseM,
# MAGIC T.ArtificialLift,
# MAGIC T.CompletionDate,
# MAGIC T.IsActive,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.completion T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.downtime AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.CauseId,
# MAGIC T.Hours,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.downtime T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.downtime_cause AS
# MAGIC SELECT DISTINCT
# MAGIC T.CauseId,
# MAGIC T.CauseName,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.downtime_cause T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.drilling_telemetry AS
# MAGIC SELECT DISTINCT
# MAGIC T.ReportId,
# MAGIC T.WellId,
# MAGIC T.WellboreId,
# MAGIC T.ReportDate,
# MAGIC T.DepthM,
# MAGIC T.RopMPerHr,
# MAGIC T.WobKlbs,
# MAGIC T.Rpm,
# MAGIC T.MudWeightPpg,
# MAGIC T.FlowRateGpm,
# MAGIC T.Npt,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.drilling_telemetry T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.facility AS
# MAGIC SELECT DISTINCT
# MAGIC T.FacilityId,
# MAGIC T.FacilityName,
# MAGIC T.FacilityType,
# MAGIC T.FieldId,
# MAGIC T.ExportPoint,
# MAGIC T.CapacityBopd,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.facility T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.field AS
# MAGIC SELECT DISTINCT
# MAGIC T.FieldId,
# MAGIC T.FieldName,
# MAGIC T.ExportPoint,
# MAGIC T.WellsTotal,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.field T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.hse_exposure AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.HoursWorked,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.hse_exposure T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.hse_incidents AS
# MAGIC SELECT DISTINCT
# MAGIC T.IncidentId,
# MAGIC T.PeriodId,
# MAGIC T.IncidentDate,
# MAGIC T.FieldId,
# MAGIC T.Severity,
# MAGIC T.Recordable,
# MAGIC T.Description,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.hse_incidents T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.partner AS
# MAGIC SELECT DISTINCT
# MAGIC T.PartnerId,
# MAGIC T.PartnerName,
# MAGIC T.PartnerRole,
# MAGIC T.EquityPct,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.partner T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.period AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.Period,
# MAGIC T.Label,
# MAGIC T.Year,
# MAGIC T.Quarter,
# MAGIC T.MonthNumber,
# MAGIC T.MonthName,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.period T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.production AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.FieldId,
# MAGIC T.ActualBopd,
# MAGIC T.ForecastBopd,
# MAGIC T.WellsOnline,
# MAGIC T.UptimePct,
# MAGIC T.OpsStatus,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.production T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.production_volume AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.WellId,
# MAGIC T.FieldId,
# MAGIC T.FacilityId,
# MAGIC T.OilBbl,
# MAGIC T.GasMscf,
# MAGIC T.WaterBbl,
# MAGIC T.OnstreamHours,
# MAGIC T.WaterCutPct,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.production_volume T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.reconciliation AS
# MAGIC SELECT DISTINCT
# MAGIC T.PeriodId,
# MAGIC T.FieldId,
# MAGIC T.PartnerId,
# MAGIC T.AllocatedBbl,
# MAGIC T.LiftedBbl,
# MAGIC T.CashCallStatus,
# MAGIC T.CashCallUsd,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.reconciliation T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.well AS
# MAGIC SELECT DISTINCT
# MAGIC T.WellId,
# MAGIC T.WellName,
# MAGIC T.FieldId,
# MAGIC T.FacilityId,
# MAGIC T.PartnerId,
# MAGIC T.WellType,
# MAGIC T.Status,
# MAGIC T.SpudDate,
# MAGIC T.TotalDepthM,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.well T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.well_test AS
# MAGIC SELECT DISTINCT
# MAGIC T.TestId,
# MAGIC T.TestDate,
# MAGIC T.PeriodId,
# MAGIC T.WellId,
# MAGIC T.CompletionId,
# MAGIC T.DurationHours,
# MAGIC T.OilRateBopd,
# MAGIC T.GasRateMscfd,
# MAGIC T.WaterCutPct,
# MAGIC T.GorScf,
# MAGIC T.ChokeSize64ths,
# MAGIC T.ThpPsi,
# MAGIC T.Validity,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate
# MAGIC FROM bronze.well_test T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE silver.wellbore AS
# MAGIC SELECT DISTINCT
# MAGIC T.WellboreId,
# MAGIC T.WellId,
# MAGIC T.WellboreName,
# MAGIC T.Trajectory,
# MAGIC T.IsSidetrack,
# MAGIC T.MeasuredDepthM,
# MAGIC T.TrueVerticalDepthM,
# MAGIC T.Sourcefile,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file,
# MAGIC T.Load_date,
# MAGIC T.Load_timestamp,
# MAGIC T.Partitionkey,
# MAGIC T.ins_batchid,
# MAGIC T.upd_batchid,
# MAGIC T.Exportdate,
# MAGIC T.valid_from,
# MAGIC T.valid_to,
# MAGIC T.is_current
# MAGIC FROM bronze.wellbore T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_completion AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(CompletionId) AS BIGINT) AS CompletionId_key,
# MAGIC T.CompletionId,
# MAGIC CAST(xxhash64(WellboreId) AS BIGINT) AS WellboreId_key,
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC T.CompletionType,
# MAGIC T.ReservoirUnit,
# MAGIC T.PerforationTopM,
# MAGIC T.PerforationBaseM,
# MAGIC T.ArtificialLift,
# MAGIC T.CompletionDate,
# MAGIC T.IsActive
# MAGIC FROM silver.completion T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_downtime_cause AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(CauseId) AS BIGINT) AS CauseId_key,
# MAGIC T.CauseId,
# MAGIC T.CauseName
# MAGIC FROM silver.downtime_cause T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_facility AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(FacilityId) AS BIGINT) AS FacilityId_key,
# MAGIC T.FacilityId,
# MAGIC T.FacilityName,
# MAGIC T.FacilityType,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC T.ExportPoint,
# MAGIC T.CapacityBopd
# MAGIC FROM silver.facility T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_field AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC T.FieldId,
# MAGIC T.FieldName,
# MAGIC T.ExportPoint,
# MAGIC T.WellsTotal
# MAGIC FROM silver.field T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_partner AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PartnerId) AS BIGINT) AS PartnerId_key,
# MAGIC T.PartnerId,
# MAGIC T.PartnerName,
# MAGIC T.PartnerRole,
# MAGIC T.EquityPct
# MAGIC FROM silver.partner T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_period AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC T.PeriodId,
# MAGIC T.Period,
# MAGIC T.Label,
# MAGIC T.Year,
# MAGIC T.Quarter,
# MAGIC T.MonthNumber,
# MAGIC T.MonthName
# MAGIC FROM silver.period T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_well AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC T.WellId,
# MAGIC T.WellName,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC CAST(xxhash64(FacilityId) AS BIGINT) AS FacilityId_key,
# MAGIC CAST(xxhash64(PartnerId) AS BIGINT) AS PartnerId_key,
# MAGIC T.WellType,
# MAGIC T.Status,
# MAGIC T.SpudDate,
# MAGIC T.TotalDepthM
# MAGIC FROM silver.well T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.dim_wellbore AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(WellboreId) AS BIGINT) AS WellboreId_key,
# MAGIC T.WellboreId,
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC T.WellboreName,
# MAGIC T.Trajectory,
# MAGIC T.IsSidetrack,
# MAGIC T.MeasuredDepthM,
# MAGIC T.TrueVerticalDepthM
# MAGIC FROM silver.wellbore T
# MAGIC WHERE (T.Is_current = 1);

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_cash_call_event AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(PartnerId) AS BIGINT) AS PartnerId_key,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC T.Stage,
# MAGIC T.EventTimestamp,
# MAGIC T.Note,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.cash_call_event T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_downtime AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(CauseId) AS BIGINT) AS CauseId_key,
# MAGIC T.Hours,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.downtime T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_drilling_telemetry AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC CAST(xxhash64(WellboreId) AS BIGINT) AS WellboreId_key,
# MAGIC T.ReportDate,
# MAGIC T.DepthM,
# MAGIC T.RopMPerHr,
# MAGIC T.WobKlbs,
# MAGIC T.Rpm,
# MAGIC T.MudWeightPpg,
# MAGIC T.FlowRateGpm,
# MAGIC T.Npt,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.drilling_telemetry T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_hse_exposure AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC T.HoursWorked,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.hse_exposure T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_hse_incidents AS
# MAGIC SELECT DISTINCT
# MAGIC T.IncidentId,
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC T.IncidentDate,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC T.Severity,
# MAGIC T.Recordable,
# MAGIC T.Description,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.hse_incidents T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_production AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC T.ActualBopd,
# MAGIC T.ForecastBopd,
# MAGIC CASE WHEN ForecastBopd = 0 THEN NULL ELSE (ActualBopd - ForecastBopd) / ForecastBopd * 100 END AS ForecastVariancePct,
# MAGIC T.WellsOnline,
# MAGIC T.UptimePct,
# MAGIC T.OpsStatus,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.production T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_production_volume AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC CAST(xxhash64(FacilityId) AS BIGINT) AS FacilityId_key,
# MAGIC T.OilBbl,
# MAGIC T.GasMscf,
# MAGIC T.WaterBbl,
# MAGIC T.OnstreamHours,
# MAGIC T.WaterCutPct,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.production_volume T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_reconciliation AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
# MAGIC CAST(xxhash64(PartnerId) AS BIGINT) AS PartnerId_key,
# MAGIC T.AllocatedBbl,
# MAGIC T.LiftedBbl,
# MAGIC T.LiftedBbl - AllocatedBbl AS VarianceBbl,
# MAGIC CASE WHEN AllocatedBbl = 0 THEN NULL ELSE (LiftedBbl - AllocatedBbl) / AllocatedBbl * 100 END AS VariancePct,
# MAGIC CASE WHEN AllocatedBbl = 0 THEN NULL WHEN ABS((LiftedBbl - AllocatedBbl) / AllocatedBbl * 100) >= 3 THEN 'investigate' WHEN ABS((LiftedBbl - AllocatedBbl) / AllocatedBbl * 100) >= 1.5 THEN 'watch' ELSE 'within-tolerance' END AS Flag,
# MAGIC T.CashCallStatus,
# MAGIC T.CashCallUsd,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.reconciliation T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE OR REPLACE TABLE gold.fact_well_test AS
# MAGIC SELECT DISTINCT
# MAGIC CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
# MAGIC CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
# MAGIC CAST(xxhash64(CompletionId) AS BIGINT) AS CompletionId_key,
# MAGIC T.TestDate,
# MAGIC T.DurationHours,
# MAGIC T.OilRateBopd,
# MAGIC T.GasRateMscfd,
# MAGIC T.WaterCutPct,
# MAGIC T.GorScf,
# MAGIC T.ChokeSize64ths,
# MAGIC T.ThpPsi,
# MAGIC T.Validity,
# MAGIC T.Manifest_package,
# MAGIC T.Manifest_file
# MAGIC FROM silver.well_test T;

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }
