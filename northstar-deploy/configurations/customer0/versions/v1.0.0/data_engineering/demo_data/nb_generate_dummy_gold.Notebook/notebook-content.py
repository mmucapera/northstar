# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
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

# Writes synthetic, FK-linked star-schema data straight into gold.* - no
# bronze/silver hop, no daily refresh. This is demo/investor-data only: one
# manual run populates gold once so the frontend and semantic model have
# something real to query. Row-generation logic (partners/fields/periods,
# _stable_rand, reconciliation/production/cash-call formulas) is ported
# directly from nb_generate_dummy_bronze.Notebook, proven against real
# Fabric/local Spark already - only the output shape changed (gold's natural
# keys + computed columns, no SCD/audit columns beyond Manifest_package/file,
# per the gold/*.yaml models).
#
# Star-schema discipline: dims get BOTH an integer surrogate key
# (`<X>Id_key`, xxhash64 of the natural key - matching the same expression
# every gold/*.yaml model uses) and the plain natural-key/text attributes;
# facts get ONLY the `_key` columns for anything that references a dim, never
# the natural-key text itself - see gold/fact_*.yaml. Computed here with
# Spark's own xxhash64() (not a Python hash) so values match exactly what the
# YAML-driven bronze->silver->gold transform notebooks would produce for the
# same input, in case that path is ever run for real instead of this direct
# generator.

from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType,
    DateType, TimestampType, BooleanType,
)
from pyspark.sql.functions import xxhash64, col as _col
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib

PERIOD_MONTHS = 24  # rolling window - matches roughly 2 years of monthly history

partners = [
    {"PartnerId": "customer0", "PartnerName": "CUSTOMER0 Upstream", "PartnerRole": "State participant", "EquityPct": 55.0},
    {"PartnerId": "shoreline", "PartnerName": "Shoreline E&P", "PartnerRole": "Operator", "EquityPct": 20.0},
    {"PartnerId": "atlantic", "PartnerName": "Atlantic Petroleum", "PartnerRole": "Non-operating partner", "EquityPct": 12.5},
    {"PartnerId": "creek", "PartnerName": "Creek Energy", "PartnerRole": "Non-operating partner", "EquityPct": 7.5},
    {"PartnerId": "meridian", "PartnerName": "Meridian Resources", "PartnerRole": "Non-operating partner", "EquityPct": 5.0},
]

fields = [
    {"FieldId": "obago", "FieldName": "Obago", "ExportPoint": "Bonny", "WellsTotal": 42},
    {"FieldId": "ekpo", "FieldName": "Ekpo North", "ExportPoint": "Qua Iboe", "WellsTotal": 28},
    {"FieldId": "warri-sw", "FieldName": "Warri SW", "ExportPoint": "Forcados", "WellsTotal": 35},
    {"FieldId": "ibeno", "FieldName": "Ibeno Deep", "ExportPoint": "Qua Iboe", "WellsTotal": 19},
    {"FieldId": "brass-c", "FieldName": "Brass Creek", "ExportPoint": "Brass", "WellsTotal": 24},
]

downtime_causes = [
    {"CauseId": "facility-maintenance", "CauseName": "Facility maintenance"},
    {"CauseId": "flowline-integrity", "CauseName": "Flowline integrity"},
    {"CauseId": "power-generation", "CauseName": "Power / generation"},
    {"CauseId": "third-party-export-deferral", "CauseName": "Third-party export deferral"},
    {"CauseId": "unplanned-shut-in", "CauseName": "Unplanned shut-in"},
]

severities = ["First aid", "Medical treatment", "Restricted work", "Lost time"]
incident_descriptions = [
    "Dropped object during lifting operation",
    "Hand injury while handling valve assembly",
    "Slip on wet deck near separator skid",
    "Minor hydrocarbon release, contained",
    "Vehicle incident on access road",
    "Heat exhaustion during flowline inspection",
]

def _stable_rand(*parts, low=0.0, high=1.0):
    """Deterministic pseudo-random float in [low, high), seeded by the given parts -
    so the same partner/field/period combination gets the same value every run
    rather than drifting between runs, keeping trends readable."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    frac = int(h[:8], 16) / 0xFFFFFFFF
    return low + frac * (high - low)


well_types = ["Oil producer", "Oil producer", "Oil producer", "Gas producer", "Water injector", "Gas injector"]
well_statuses_weighted = [
    ("Producing", 0.78), ("Shut-in", 0.09), ("Suspended", 0.07), ("Drilling", 0.06),
]
completion_types = ["Single string", "Dual string", "Gas lift", "ESP", "Natural flow"]
trajectories = ["Vertical", "Deviated", "Horizontal", "Deviated"]
reservoirs = ["Agbada D-1", "Agbada E-3", "Benin Sand B", "Akata Lower", "Agbada C-7"]

operator_partner_id = next(p["PartnerId"] for p in partners if p["PartnerRole"] == "Operator")

# ---- facilities: export terminals (shared, no FieldId) + a flowstation
# (and sometimes a gas plant) per field, matching the bronze generator -----
facilities = []
terminals = sorted({f["ExportPoint"] for f in fields})
for i, t in enumerate(terminals):
    facilities.append({
        "FacilityId": f"fac-term-{t.lower().replace(' ', '-')}",
        "FacilityName": f"{t} Export Terminal",
        "FacilityType": "Export terminal",
        "FieldId": None,
        "ExportPoint": t,
        "CapacityBopd": 220000 + i * 45000,
    })
flowstation_by_field = {}
for i, f in enumerate(fields):
    flow_id = f"fac-{f['FieldId']}-flow"
    facilities.append({
        "FacilityId": flow_id,
        "FacilityName": f"{f['FieldName']} Flowstation",
        "FacilityType": "Flowstation",
        "FieldId": f["FieldId"],
        "ExportPoint": f["ExportPoint"],
        "CapacityBopd": round(45000 + _stable_rand("fac_cap", f["FieldId"]) * 30000),
    })
    flowstation_by_field[f["FieldId"]] = flow_id
    if i % 2 == 0:
        facilities.append({
            "FacilityId": f"fac-{f['FieldId']}-gas",
            "FacilityName": f"{f['FieldName']} Gas Plant",
            "FacilityType": "Gas plant",
            "FieldId": f["FieldId"],
            "ExportPoint": f["ExportPoint"],
            "CapacityBopd": 0,
        })

wells = []
for f in fields:
    for w in range(f["WellsTotal"]):
        well_id = f"WEL-{f['FieldId']}-{w + 1:03d}"
        a = _stable_rand("well_type", well_id)
        b = _stable_rand("well_status", well_id)
        c = _stable_rand("well_spud", well_id)
        cum = 0.0
        status = well_statuses_weighted[-1][0]
        for name, weight in well_statuses_weighted:
            cum += weight
            if b <= cum:
                status = name
                break
        spud_year = 2005 + int(c * 18)
        spud_month = 1 + int(_stable_rand("well_spud_m", well_id) * 12)
        spud_day = 1 + int(_stable_rand("well_spud_d", well_id) * 27)
        wells.append({
            "WellId": well_id,
            "WellName": f"{f['FieldName'].split(' ')[0]}-{w + 1:02d}",
            "FieldId": f["FieldId"],
            "FacilityId": flowstation_by_field[f["FieldId"]],
            "PartnerId": operator_partner_id,
            "WellType": well_types[int(a * len(well_types))],
            "Status": status,
            "SpudDate": date(spud_year, spud_month, spud_day),
            "TotalDepthM": round(2400 + _stable_rand("well_depth", well_id) * 1900, 1),
        })

wellbores = []
for w in wells:
    count = 2 if _stable_rand("wb_count", w["WellId"]) > 0.72 else 1
    for b in range(count):
        wb_id = f"{w['WellId']}-B{b + 1}"
        traj = trajectories[int(_stable_rand("wb_traj", wb_id) * len(trajectories))]
        base_md = float(w["TotalDepthM"])
        factor = 1.35 if traj == "Horizontal" else (1.12 if traj == "Deviated" else 1.0)
        md = round(base_md * factor + b * 240, 1)
        wellbores.append({
            "WellboreId": wb_id,
            "WellId": w["WellId"],
            "WellboreName": f"{w['WellName']}{'' if b == 0 else f'ST{b}'}",
            "Trajectory": traj,
            "IsSidetrack": b > 0,
            "MeasuredDepthM": md,
            "TrueVerticalDepthM": base_md,
        })

completions = []
for wb in wellbores:
    c_id = f"{wb['WellboreId']}-C1"
    r = _stable_rand("comp_top", c_id)
    top = round(float(wb["TrueVerticalDepthM"]) * (0.82 + r * 0.08), 1)
    ctype = completion_types[int(_stable_rand("comp_type", c_id) * len(completion_types))]
    comp_year = 2010 + int(_stable_rand("comp_year", c_id) * 15)
    comp_month = 1 + int(_stable_rand("comp_month", c_id) * 12)
    completions.append({
        "CompletionId": c_id,
        "WellboreId": wb["WellboreId"],
        "WellId": wb["WellId"],
        "CompletionType": ctype,
        "ReservoirUnit": reservoirs[int(_stable_rand("comp_res", c_id) * len(reservoirs))],
        "PerforationTopM": top,
        "PerforationBaseM": round(top + 20 + _stable_rand("comp_base", c_id) * 90, 1),
        "ArtificialLift": "Electric submersible pump" if ctype == "ESP" else ("Continuous gas lift" if ctype == "Gas lift" else "None"),
        "CompletionDate": date(comp_year, comp_month, 15),
        "IsActive": (not wb["IsSidetrack"]) or _stable_rand("comp_active", c_id) > 0.4,
    })

wells_by_field = {}
for w in wells:
    wells_by_field.setdefault(w["FieldId"], []).append(w)

completion_by_well = {}
for c in completions:
    completion_by_well.setdefault(c["WellId"], c)

wellbore_by_well = {}
for wb in wellbores:
    wellbore_by_well.setdefault(wb["WellId"], wb)


def _field_actual_bopd(p, f):
    """Mirrors write_fact_production's formula, without a table read-back -
    used to derive well-level production_volume shares for the same period."""
    forecast = round(34000 + fields.index(f) * 8500, 2)
    seasonal = 1 + 0.04 * _stable_rand("prod_season", p["PeriodId"], f["FieldId"], low=-1, high=1)
    wells_offline = int(_stable_rand("wells_off", p["PeriodId"], f["FieldId"], low=0, high=4))
    wells_online = max(f["WellsTotal"] - wells_offline, 1)
    uptime_pct = round((wells_online / f["WellsTotal"]) * (96 + _stable_rand("uptime", p["PeriodId"], f["FieldId"], low=0, high=4)), 1)
    actual = round(forecast * seasonal * (uptime_pct / 100) * (0.97 + _stable_rand("actual", p["PeriodId"], f["FieldId"], low=0, high=0.07)), 2)
    return actual


# Rolling window of periods, most recent = current month
today = date.today().replace(day=1)
periods = []
for i in range(PERIOD_MONTHS - 1, -1, -1):
    m = today.month - i
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    p = date(y, m, 1)
    periods.append({
        "PeriodId": p.strftime("%Y-%m"),
        "Period": p,
        "Label": p.strftime("%b %Y"),
        "Year": p.year,
        "Quarter": (p.month - 1) // 3 + 1,
        "MonthNumber": p.month,
        "MonthName": p.strftime("%B"),
    })

# ---- schemas ----------------------------------------------------------------
# Gold keeps only Manifest_package/Manifest_file from the audit set, and no
# SCD columns at all (gold/*.yaml models only ever select the business
# columns) - explicit StructTypes, same reasoning as the bronze generator:
# createDataFrame(rows) without a schema fails on any all-null column.

_MANIFEST_FIELDS = [
    StructField("Manifest_package", StringType()),
    StructField("Manifest_file", StringType()),
]

SCHEMAS = {
    "dim_partner": StructType([
        StructField("PartnerId", StringType()),
        StructField("PartnerName", StringType()),
        StructField("PartnerRole", StringType()),
        StructField("EquityPct", DecimalType(6, 3)),
    ]),
    "dim_field": StructType([
        StructField("FieldId", StringType()),
        StructField("FieldName", StringType()),
        StructField("ExportPoint", StringType()),
        StructField("WellsTotal", IntegerType()),
    ]),
    "dim_period": StructType([
        StructField("PeriodId", StringType()),
        StructField("Period", DateType()),
        StructField("Label", StringType()),
        StructField("Year", IntegerType()),
        StructField("Quarter", IntegerType()),
        StructField("MonthNumber", IntegerType()),
        StructField("MonthName", StringType()),
    ]),
    "dim_downtime_cause": StructType([
        StructField("CauseId", StringType()),
        StructField("CauseName", StringType()),
    ]),
    "fact_reconciliation": StructType([
        StructField("PeriodId", StringType()),
        StructField("FieldId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("AllocatedBbl", DecimalType(18, 2)),
        StructField("LiftedBbl", DecimalType(18, 2)),
        StructField("VarianceBbl", DecimalType(18, 2)),
        StructField("VariancePct", DecimalType(9, 3)),
        StructField("Flag", StringType()),
        StructField("CashCallStatus", StringType()),
        StructField("CashCallUsd", DecimalType(18, 2)),
    ] + _MANIFEST_FIELDS),
    "fact_production": StructType([
        StructField("PeriodId", StringType()),
        StructField("FieldId", StringType()),
        StructField("ActualBopd", DecimalType(18, 2)),
        StructField("ForecastBopd", DecimalType(18, 2)),
        StructField("ForecastVariancePct", DecimalType(9, 3)),
        StructField("WellsOnline", IntegerType()),
        StructField("UptimePct", DecimalType(9, 2)),
        StructField("OpsStatus", StringType()),
    ] + _MANIFEST_FIELDS),
    "fact_downtime": StructType([
        StructField("PeriodId", StringType()),
        StructField("CauseId", StringType()),
        StructField("Hours", DecimalType(18, 2)),
    ] + _MANIFEST_FIELDS),
    "fact_hse_exposure": StructType([
        StructField("PeriodId", StringType()),
        StructField("HoursWorked", DecimalType(18, 2)),
    ] + _MANIFEST_FIELDS),
    "fact_hse_incidents": StructType([
        StructField("IncidentId", StringType()),
        StructField("PeriodId", StringType()),
        StructField("IncidentDate", DateType()),
        StructField("FieldId", StringType()),
        StructField("Severity", StringType()),
        StructField("Recordable", BooleanType()),
        StructField("Description", StringType()),
    ] + _MANIFEST_FIELDS),
    "fact_cash_call_event": StructType([
        StructField("PeriodId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("FieldId", StringType()),
        StructField("Stage", StringType()),
        StructField("EventTimestamp", TimestampType()),
        StructField("Note", StringType()),
    ] + _MANIFEST_FIELDS),
    "dim_facility": StructType([
        StructField("FacilityId", StringType()),
        StructField("FacilityName", StringType()),
        StructField("FacilityType", StringType()),
        StructField("FieldId", StringType(), nullable=True),
        StructField("ExportPoint", StringType()),
        StructField("CapacityBopd", DecimalType(18, 2)),
    ]),
    "dim_well": StructType([
        StructField("WellId", StringType()),
        StructField("WellName", StringType()),
        StructField("FieldId", StringType()),
        StructField("FacilityId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("WellType", StringType()),
        StructField("Status", StringType()),
        StructField("SpudDate", DateType()),
        StructField("TotalDepthM", DecimalType(18, 2)),
    ]),
    "dim_wellbore": StructType([
        StructField("WellboreId", StringType()),
        StructField("WellId", StringType()),
        StructField("WellboreName", StringType()),
        StructField("Trajectory", StringType()),
        StructField("IsSidetrack", BooleanType()),
        StructField("MeasuredDepthM", DecimalType(18, 2)),
        StructField("TrueVerticalDepthM", DecimalType(18, 2)),
    ]),
    "dim_completion": StructType([
        StructField("CompletionId", StringType()),
        StructField("WellboreId", StringType()),
        StructField("WellId", StringType()),
        StructField("CompletionType", StringType()),
        StructField("ReservoirUnit", StringType()),
        StructField("PerforationTopM", DecimalType(18, 2)),
        StructField("PerforationBaseM", DecimalType(18, 2)),
        StructField("ArtificialLift", StringType()),
        StructField("CompletionDate", DateType()),
        StructField("IsActive", BooleanType()),
    ]),
    "fact_production_volume": StructType([
        StructField("PeriodId", StringType()),
        StructField("WellId", StringType()),
        StructField("FieldId", StringType()),
        StructField("FacilityId", StringType()),
        StructField("OilBbl", DecimalType(18, 2)),
        StructField("GasMscf", DecimalType(18, 2)),
        StructField("WaterBbl", DecimalType(18, 2)),
        StructField("OnstreamHours", DecimalType(9, 2)),
        StructField("WaterCutPct", DecimalType(9, 2)),
    ] + _MANIFEST_FIELDS),
    "fact_well_test": StructType([
        StructField("TestDate", DateType()),
        StructField("PeriodId", StringType()),
        StructField("WellId", StringType()),
        StructField("CompletionId", StringType()),
        StructField("DurationHours", DecimalType(9, 2)),
        StructField("OilRateBopd", DecimalType(18, 2)),
        StructField("GasRateMscfd", DecimalType(18, 2)),
        StructField("WaterCutPct", DecimalType(9, 2)),
        StructField("GorScf", DecimalType(18, 2)),
        StructField("ChokeSize64ths", IntegerType()),
        StructField("ThpPsi", DecimalType(18, 2)),
        StructField("Validity", StringType()),
    ] + _MANIFEST_FIELDS),
    "fact_drilling_telemetry": StructType([
        StructField("WellId", StringType()),
        StructField("WellboreId", StringType()),
        StructField("ReportDate", DateType()),
        StructField("DepthM", DecimalType(18, 2)),
        StructField("RopMPerHr", DecimalType(9, 2)),
        StructField("WobKlbs", DecimalType(9, 2)),
        StructField("Rpm", DecimalType(9, 2)),
        StructField("MudWeightPpg", DecimalType(9, 2)),
        StructField("FlowRateGpm", DecimalType(9, 2)),
        StructField("Npt", BooleanType()),
    ] + _MANIFEST_FIELDS),
}


def _manifest_cols(source_name: str):
    return {
        "Manifest_package": "DUMMY_GOLD_DIRECT",
        "Manifest_file": f"{source_name}_manifest.json",
    }




def _write(table: str, rows: list, hash_keys: dict | None = None, drop_hashed: bool = False) -> int:
    """hash_keys maps a natural-key column already in `rows` to the new
    integer surrogate key column name (e.g. {"PartnerId": "PartnerId_key"}).
    drop_hashed=True removes the natural-key column afterward - use for
    facts (which should carry only the key, per gold/fact_*.yaml), not for
    dims (which keep both the key and the natural-key/text attributes)."""
    df = spark.createDataFrame(rows, schema=SCHEMAS[table])
    if hash_keys:
        for natural_col, key_col in hash_keys.items():
            df = df.withColumn(key_col, xxhash64(_col(natural_col)).cast("bigint"))
        if drop_hashed:
            df = df.drop(*hash_keys.keys())
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"gold.{table}")
    return len(rows)


# ---- dimensions -------------------------------------------------------------

def write_dim_partner():
    rows = [Row(**{**p, "EquityPct": Decimal(str(p["EquityPct"]))}) for p in partners]
    return _write("dim_partner", rows, hash_keys={"PartnerId": "PartnerId_key"})


def write_dim_field():
    rows = [Row(**f) for f in fields]
    return _write("dim_field", rows, hash_keys={"FieldId": "FieldId_key"})


def write_dim_period():
    rows = [Row(**p) for p in periods]
    return _write("dim_period", rows, hash_keys={"PeriodId": "PeriodId_key"})


def write_dim_downtime_cause():
    rows = [Row(**c) for c in downtime_causes]
    return _write("dim_downtime_cause", rows, hash_keys={"CauseId": "CauseId_key"})


def write_dim_facility():
    rows = [
        Row(
            FacilityId=fc["FacilityId"], FacilityName=fc["FacilityName"], FacilityType=fc["FacilityType"],
            FieldId=fc["FieldId"], ExportPoint=fc["ExportPoint"], CapacityBopd=Decimal(str(fc["CapacityBopd"])),
        )
        for fc in facilities
    ]
    df = spark.createDataFrame(rows, schema=SCHEMAS["dim_facility"])
    df = df.withColumn("FacilityId_key", xxhash64(_col("FacilityId")).cast("bigint"))
    df = df.withColumn("FieldId_key", xxhash64(_col("FieldId")).cast("bigint"))
    df = df.drop("FieldId")
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.dim_facility")
    return len(rows)


def write_dim_well():
    rows = [
        Row(
            WellId=w["WellId"], WellName=w["WellName"], FieldId=w["FieldId"], FacilityId=w["FacilityId"],
            PartnerId=w["PartnerId"], WellType=w["WellType"], Status=w["Status"], SpudDate=w["SpudDate"],
            TotalDepthM=Decimal(str(w["TotalDepthM"])),
        )
        for w in wells
    ]
    df = spark.createDataFrame(rows, schema=SCHEMAS["dim_well"])
    df = df.withColumn("WellId_key", xxhash64(_col("WellId")).cast("bigint"))
    df = df.withColumn("FieldId_key", xxhash64(_col("FieldId")).cast("bigint"))
    df = df.withColumn("FacilityId_key", xxhash64(_col("FacilityId")).cast("bigint"))
    df = df.withColumn("PartnerId_key", xxhash64(_col("PartnerId")).cast("bigint"))
    df = df.drop("FieldId", "FacilityId", "PartnerId")
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.dim_well")
    return len(rows)


def write_dim_wellbore():
    rows = [
        Row(
            WellboreId=wb["WellboreId"], WellId=wb["WellId"], WellboreName=wb["WellboreName"],
            Trajectory=wb["Trajectory"], IsSidetrack=wb["IsSidetrack"],
            MeasuredDepthM=Decimal(str(wb["MeasuredDepthM"])), TrueVerticalDepthM=Decimal(str(wb["TrueVerticalDepthM"])),
        )
        for wb in wellbores
    ]
    df = spark.createDataFrame(rows, schema=SCHEMAS["dim_wellbore"])
    df = df.withColumn("WellboreId_key", xxhash64(_col("WellboreId")).cast("bigint"))
    df = df.withColumn("WellId_key", xxhash64(_col("WellId")).cast("bigint"))
    df = df.drop("WellId")
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.dim_wellbore")
    return len(rows)


def write_dim_completion():
    rows = [
        Row(
            CompletionId=c["CompletionId"], WellboreId=c["WellboreId"], WellId=c["WellId"],
            CompletionType=c["CompletionType"], ReservoirUnit=c["ReservoirUnit"],
            PerforationTopM=Decimal(str(c["PerforationTopM"])), PerforationBaseM=Decimal(str(c["PerforationBaseM"])),
            ArtificialLift=c["ArtificialLift"], CompletionDate=c["CompletionDate"], IsActive=c["IsActive"],
        )
        for c in completions
    ]
    df = spark.createDataFrame(rows, schema=SCHEMAS["dim_completion"])
    df = df.withColumn("CompletionId_key", xxhash64(_col("CompletionId")).cast("bigint"))
    df = df.withColumn("WellboreId_key", xxhash64(_col("WellboreId")).cast("bigint"))
    df = df.withColumn("WellId_key", xxhash64(_col("WellId")).cast("bigint"))
    df = df.drop("WellboreId", "WellId")
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.dim_completion")
    return len(rows)


# ---- facts --------------------------------------------------------------
# Reconciliation and cash-call events are generated together in one pass -
# cash-call events are derived from each reconciliation record's own status,
# same as the bronze generator, but without a table read-back in between.

def write_facts_reconciliation_and_cash_call():
    review_notes = [
        "Allocation statement matched against terminal lifting log.",
        "Awaiting operator confirmation of export point measurement.",
        "Second-tier review triggered by variance band.",
        "Volumes re-checked after meter proving report.",
    ]
    dispute_notes = [
        "Partner contests lifted volume at the export terminal.",
        "Variance exceeds tolerance; joint measurement review requested.",
        "Cargo timing dispute across period cut-off.",
    ]
    settle_notes = [
        "Funds received, statement closed.",
        "Settled net of prior period credit.",
        "Settled in full against the revised statement.",
    ]

    recon_rows = []
    cash_call_rows = []

    for p in periods:
        for f in fields:
            base_bopd = 30000 + fields.index(f) * 6000
            for partner in partners:
                share = base_bopd * (partner["EquityPct"] / 100.0) * 30  # monthly bbl for this partner's share
                seasonal = 1 + 0.05 * _stable_rand("season", p["PeriodId"], f["FieldId"], low=-1, high=1)
                allocated = round(share * seasonal, 2)
                drift = _stable_rand("drift", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=-0.03, high=0.03)
                lifted = round(allocated * (1 + drift), 2)
                variance_bbl = round(lifted - allocated, 2)
                variance_pct = round((lifted - allocated) / allocated * 100, 3) if allocated else None
                # Flag thresholds match Project Spark's VARIANCE_TOLERANCE
                # constant exactly (src/data/delta-basin.ts) - see
                # gold/fact_reconciliation.yaml.
                if variance_pct is None:
                    flag = None
                elif abs(variance_pct) >= 3:
                    flag = "investigate"
                elif abs(variance_pct) >= 1.5:
                    flag = "watch"
                else:
                    flag = "within-tolerance"

                r = _stable_rand("status", p["PeriodId"], f["FieldId"], partner["PartnerId"])
                if variance_pct is not None and abs(variance_pct) >= 3 and r > 0.4:
                    status = "disputed"
                elif p["PeriodId"] == periods[-1]["PeriodId"] and r > 0.55:
                    status = "pending"
                else:
                    status = "settled"
                cash_call_usd = round(allocated * 11.4, 2)

                recon_rows.append(Row(
                    PeriodId=p["PeriodId"], FieldId=f["FieldId"], PartnerId=partner["PartnerId"],
                    AllocatedBbl=Decimal(str(allocated)), LiftedBbl=Decimal(str(lifted)),
                    VarianceBbl=Decimal(str(variance_bbl)),
                    VariancePct=Decimal(str(variance_pct)) if variance_pct is not None else None,
                    Flag=flag, CashCallStatus=status, CashCallUsd=Decimal(str(cash_call_usd)),
                    **_manifest_cols("fct_reconciliation"),
                ))

                # Cash calls are raised the month after the production period.
                y, m = p["Year"], p["MonthNumber"]
                m += 1
                if m > 12:
                    m = 1
                    y += 1
                submitted_day = 2 + int(_stable_rand("cc_submit", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=4))
                review_day = submitted_day + 1 + int(_stable_rand("cc_review_gap", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=4))
                close_day = review_day + 2 + int(_stable_rand("cc_close_gap", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=8))

                def _dt(day, hour):
                    day = min(day, 28)
                    return datetime(y, m, day, hour, 0, 0)

                events = [
                    ("submitted", _dt(submitted_day, 9), f"Cash call raised for {p['PeriodId']} on {f['FieldId']}."),
                    ("under-review", _dt(review_day, 11), review_notes[int(_stable_rand("cc_review_note", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=len(review_notes)))]),
                ]
                if status == "disputed":
                    events.append(("disputed", _dt(close_day, 15), dispute_notes[int(_stable_rand("cc_dispute_note", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=len(dispute_notes)))]))
                elif status == "settled":
                    events.append(("settled", _dt(close_day, 14), settle_notes[int(_stable_rand("cc_settle_note", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=0, high=len(settle_notes)))]))
                # "pending" status -> only submitted + under-review

                for stage, ts, note in events:
                    cash_call_rows.append(Row(
                        PeriodId=p["PeriodId"], PartnerId=partner["PartnerId"], FieldId=f["FieldId"],
                        Stage=stage, EventTimestamp=ts, Note=note,
                        **_manifest_cols("fct_cash_call_event"),
                    ))

    recon_keys = {"PeriodId": "PeriodId_key", "FieldId": "FieldId_key", "PartnerId": "PartnerId_key"}
    n1 = _write("fact_reconciliation", recon_rows, hash_keys=recon_keys, drop_hashed=True)
    n2 = _write("fact_cash_call_event", cash_call_rows, hash_keys=recon_keys, drop_hashed=True)
    return n1, n2


def write_fact_production():
    rows = []
    for p in periods:
        for f in fields:
            forecast = round(34000 + fields.index(f) * 8500, 2)
            seasonal = 1 + 0.04 * _stable_rand("prod_season", p["PeriodId"], f["FieldId"], low=-1, high=1)
            wells_offline = int(_stable_rand("wells_off", p["PeriodId"], f["FieldId"], low=0, high=4))
            wells_online = max(f["WellsTotal"] - wells_offline, 1)
            uptime_pct = round((wells_online / f["WellsTotal"]) * (96 + _stable_rand("uptime", p["PeriodId"], f["FieldId"], low=0, high=4)), 1)
            actual = round(forecast * seasonal * (uptime_pct / 100) * (0.97 + _stable_rand("actual", p["PeriodId"], f["FieldId"], low=0, high=0.07)), 2)
            forecast_variance_pct = round((actual - forecast) / forecast * 100, 3) if forecast else None
            status = "down" if uptime_pct < 88 else ("watch" if (uptime_pct < 94 or actual < forecast * 0.93) else "normal")
            rows.append(Row(
                PeriodId=p["PeriodId"], FieldId=f["FieldId"],
                ActualBopd=Decimal(str(actual)), ForecastBopd=Decimal(str(forecast)),
                ForecastVariancePct=Decimal(str(forecast_variance_pct)) if forecast_variance_pct is not None else None,
                WellsOnline=wells_online, UptimePct=Decimal(str(uptime_pct)), OpsStatus=status,
                **_manifest_cols("fct_production"),
            ))
    return _write(
        "fact_production", rows,
        hash_keys={"PeriodId": "PeriodId_key", "FieldId": "FieldId_key"},
        drop_hashed=True,
    )


def write_fact_downtime():
    rows = []
    for p in periods:
        for c in downtime_causes:
            base = 60 + downtime_causes.index(c) * 40
            hours = round(base + _stable_rand("downtime", p["PeriodId"], c["CauseId"], low=0, high=300), 2)
            rows.append(Row(
                PeriodId=p["PeriodId"], CauseId=c["CauseId"], Hours=Decimal(str(hours)),
                **_manifest_cols("fct_downtime"),
            ))
    return _write(
        "fact_downtime", rows,
        hash_keys={"PeriodId": "PeriodId_key", "CauseId": "CauseId_key"},
        drop_hashed=True,
    )


def write_fact_hse_exposure():
    rows = []
    for p in periods:
        hours = round(410000 + _stable_rand("exposure", p["PeriodId"], low=0, high=90000), 2)
        rows.append(Row(PeriodId=p["PeriodId"], HoursWorked=Decimal(str(hours)), **_manifest_cols("fct_hse_exposure")))
    return _write(
        "fact_hse_exposure", rows,
        hash_keys={"PeriodId": "PeriodId_key"},
        drop_hashed=True,
    )


def write_fact_hse_incidents():
    rows = []
    for p in periods:
        count = int(_stable_rand("incident_count", p["PeriodId"], low=0, high=4))
        for i in range(count):
            day = 2 + int(_stable_rand("incident_day", p["PeriodId"], i, low=0, high=26))
            severity = severities[int(_stable_rand("severity", p["PeriodId"], i, low=0, high=len(severities)))]
            field = fields[int(_stable_rand("incident_field", p["PeriodId"], i, low=0, high=len(fields)))]
            desc = incident_descriptions[int(_stable_rand("incident_desc", p["PeriodId"], i, low=0, high=len(incident_descriptions)))]
            rows.append(Row(
                IncidentId=f"{p['PeriodId']}-{i}",
                PeriodId=p["PeriodId"],
                IncidentDate=date(p["Year"], p["MonthNumber"], min(day, 28)),
                FieldId=field["FieldId"],
                Severity=severity,
                Recordable=(severity != "First aid"),
                Description=desc,
                **_manifest_cols("fct_hse_incidents"),
            ))
    return _write(
        "fact_hse_incidents", rows,
        hash_keys={"PeriodId": "PeriodId_key", "FieldId": "FieldId_key"},
        drop_hashed=True,
    )


def write_fact_production_volume():
    """Well-level monthly production volume - shares the field's computed
    ActualBopd (same formula as write_fact_production) across its producing/
    shut-in wells. Different grain than fact_production, not a duplicate."""
    HOURS_PER_MONTH = 730
    rows = []
    for p in periods:
        for f in fields:
            actual_bopd = _field_actual_bopd(p, f)
            field_wells = wells_by_field.get(f["FieldId"], [])
            producers = [w for w in field_wells if w["Status"] in ("Producing", "Shut-in")]
            share = actual_bopd / max(1, len(producers))
            for w in field_wells:
                key = (p["PeriodId"], w["WellId"])
                shut = w["Status"] != "Producing"
                onstream_hours = round(_stable_rand("pv_hours", *key, low=0, high=180) if shut
                                        else HOURS_PER_MONTH * (0.9 + _stable_rand("pv_hours2", *key, low=0, high=0.1)), 1)
                is_injector = w["WellType"] in ("Water injector", "Gas injector")
                factor = 0.0 if is_injector else 1.0
                bopd = factor * share * (0.7 + _stable_rand("pv_rate", *key, low=0, high=0.6)) * (onstream_hours / HOURS_PER_MONTH)
                oil_bbl = round(bopd * 30, 1)
                water_cut = round(12 + _stable_rand("pv_wc", *key, low=0, high=55), 1)
                gas_mscf = round(oil_bbl * (0.6 + _stable_rand("pv_gas", *key, low=0, high=1.4)), 1)
                water_bbl = round((oil_bbl * water_cut) / max(1, 100 - water_cut), 1)
                rows.append(Row(
                    PeriodId=p["PeriodId"], WellId=w["WellId"], FieldId=f["FieldId"], FacilityId=w["FacilityId"],
                    OilBbl=Decimal(str(oil_bbl)), GasMscf=Decimal(str(gas_mscf)), WaterBbl=Decimal(str(water_bbl)),
                    OnstreamHours=Decimal(str(onstream_hours)), WaterCutPct=Decimal(str(water_cut)),
                    **_manifest_cols("fct_production_volume"),
                ))
    return _write(
        "fact_production_volume", rows,
        hash_keys={"PeriodId": "PeriodId_key", "WellId": "WellId_key", "FieldId": "FieldId_key", "FacilityId": "FacilityId_key"},
        drop_hashed=True,
    )


def write_fact_well_test():
    """One well test per well per quarter, correlated to that well's implied
    production share for the same period (mirrors write_fact_production_volume's
    formula rather than reading gold back, since gold facts are written
    independently in this direct-to-gold generator)."""
    HOURS_PER_MONTH = 730
    quarter_periods = [p for i, p in enumerate(periods) if i % 3 == 2]
    rows = []
    for f in fields:
        field_wells = wells_by_field.get(f["FieldId"], [])
        producers = [w for w in field_wells if w["Status"] in ("Producing", "Shut-in")]
        for w in field_wells:
            completion = completion_by_well.get(w["WellId"])
            if completion is None:
                continue
            for p in quarter_periods:
                key = (w["WellId"], p["PeriodId"])
                actual_bopd = _field_actual_bopd(p, f)
                share = actual_bopd / max(1, len(producers))
                shut = w["Status"] != "Producing"
                onstream_hours = HOURS_PER_MONTH * (0.9 + _stable_rand("pv_hours2", p["PeriodId"], w["WellId"], low=0, high=0.1)) if not shut else _stable_rand("pv_hours", p["PeriodId"], w["WellId"], low=0, high=180)
                is_injector = w["WellType"] in ("Water injector", "Gas injector")
                factor = 0.0 if is_injector else 1.0
                bopd = factor * share * (0.7 + _stable_rand("pv_rate", p["PeriodId"], w["WellId"], low=0, high=0.6)) * (onstream_hours / HOURS_PER_MONTH)
                oil_bbl = bopd * 30
                base_wc = 12 + _stable_rand("pv_wc", p["PeriodId"], w["WellId"], low=0, high=55)
                base_rate = oil_bbl / 30
                oil_rate = round(base_rate * (0.92 + _stable_rand("wt_rate", *key, low=0, high=0.18)), 1)
                water_cut = round(max(0.0, base_wc + (_stable_rand("wt_wc", *key, low=0, high=1) - 0.5) * 6), 1)
                r_valid = _stable_rand("wt_valid", *key)
                validity = "Rejected" if r_valid > 0.93 else ("Suspect" if r_valid > 0.84 else "Valid")
                test_day = 6 + int(_stable_rand("wt_day", *key, low=0, high=18))
                rows.append(Row(
                    TestDate=date(p["Year"], p["MonthNumber"], min(test_day, 28)),
                    PeriodId=p["PeriodId"], WellId=w["WellId"], CompletionId=completion["CompletionId"],
                    DurationHours=Decimal(str(6 + int(_stable_rand("wt_dur", *key, low=0, high=12)))),
                    OilRateBopd=Decimal(str(oil_rate)),
                    GasRateMscfd=Decimal(str(round(oil_rate * (0.6 + _stable_rand("wt_gas", *key, low=0, high=1.6)), 1))),
                    WaterCutPct=Decimal(str(water_cut)),
                    GorScf=Decimal(str(round(500 + _stable_rand("wt_gor", *key, low=0, high=1400), 1))),
                    ChokeSize64ths=16 + int(_stable_rand("wt_choke", *key, low=0, high=40)),
                    ThpPsi=Decimal(str(round(600 + _stable_rand("wt_thp", *key, low=0, high=1800), 1))),
                    Validity=validity,
                    **_manifest_cols("fct_well_test"),
                ))
    return _write(
        "fact_well_test", rows,
        hash_keys={"PeriodId": "PeriodId_key", "WellId": "WellId_key", "CompletionId": "CompletionId_key"},
        drop_hashed=True,
    )


def write_fact_drilling_telemetry():
    """Daily drilling report telemetry for wells currently in Drilling status
    only - a 30-day trailing window ending at the current load date."""
    rows = []
    drilling_wells = [w for w in wells if w["Status"] == "Drilling"]
    for w in drilling_wells:
        wb = wellbore_by_well.get(w["WellId"])
        if wb is None:
            continue
        depth = 600 + round(_stable_rand("dt_start", w["WellId"]) * 400)
        for d in range(30):
            key = (w["WellId"], d)
            npt = _stable_rand("dt_npt", *key) > 0.88
            rop = round(_stable_rand("dt_rop", *key, low=0, high=2), 1) if npt else round(6 + _stable_rand("dt_rop2", *key, low=0, high=18), 1)
            depth = min(float(wb["MeasuredDepthM"]), depth + rop * 20)
            report_date = today - timedelta(days=(30 - d))
            rows.append(Row(
                WellId=w["WellId"], WellboreId=wb["WellboreId"], ReportDate=report_date,
                DepthM=Decimal(str(round(depth, 1))), RopMPerHr=Decimal(str(rop)),
                WobKlbs=Decimal(str(round(12 + _stable_rand("dt_wob", *key, low=0, high=28), 1))),
                Rpm=Decimal(str(round(60 + _stable_rand("dt_rpm", *key, low=0, high=100), 1))),
                MudWeightPpg=Decimal(str(round(9.2 + _stable_rand("dt_mud", *key, low=0, high=3), 1))),
                FlowRateGpm=Decimal(str(round(420 + _stable_rand("dt_flow", *key, low=0, high=380), 1))),
                Npt=npt,
                **_manifest_cols("fct_drilling_telemetry"),
            ))
    return _write(
        "fact_drilling_telemetry", rows,
        hash_keys={"WellId": "WellId_key", "WellboreId": "WellboreId_key"},
        drop_hashed=True,
    )


# ---- run ------------------------------------------------------------------

print("=" * 70)
print("DUMMY GOLD DATA GENERATOR - customer0 (direct to gold, no daily refresh)")
print(f"Periods: {periods[0]['PeriodId']} .. {periods[-1]['PeriodId']}")
print("=" * 70)

spark.sql("CREATE SCHEMA IF NOT EXISTS gold")

counts = {}
counts["dim_partner"] = write_dim_partner()
counts["dim_field"] = write_dim_field()
counts["dim_period"] = write_dim_period()
counts["dim_downtime_cause"] = write_dim_downtime_cause()
counts["dim_facility"] = write_dim_facility()
counts["dim_well"] = write_dim_well()
counts["dim_wellbore"] = write_dim_wellbore()
counts["dim_completion"] = write_dim_completion()
counts["fact_reconciliation"], counts["fact_cash_call_event"] = write_facts_reconciliation_and_cash_call()
counts["fact_production"] = write_fact_production()
counts["fact_downtime"] = write_fact_downtime()
counts["fact_hse_exposure"] = write_fact_hse_exposure()
counts["fact_hse_incidents"] = write_fact_hse_incidents()
counts["fact_production_volume"] = write_fact_production_volume()
counts["fact_well_test"] = write_fact_well_test()
counts["fact_drilling_telemetry"] = write_fact_drilling_telemetry()

print("\nRows written:")
for table, n in counts.items():
    print(f"  gold.{table:<20} {n:>8,}")
print(f"\nTotal: {sum(counts.values()):,} rows across {len(counts)} tables")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
