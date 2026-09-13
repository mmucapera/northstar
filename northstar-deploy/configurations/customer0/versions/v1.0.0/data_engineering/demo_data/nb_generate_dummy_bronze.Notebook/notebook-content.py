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

from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType,
    DateType, TimestampType, BooleanType,
)
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib

# ---- config ---------------------------------------------------------------
LOAD_TS = datetime.now(timezone.utc).replace(tzinfo=None)
# ins_batchid/upd_batchid are INT (32-bit, max ~2.1B) in the real bronze
# schema - a full YYYYMMDDHHMM batch id overflows that. yymmddHH (8 digits,
# hour granularity) fits comfortably and is unique enough for a once-daily job.
BATCH_ID = int(LOAD_TS.strftime("%y%m%d%H"))
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
    rather than drifting daily, keeping day-over-day trends readable."""
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

# Operator partner for well/dim_well FK - the partner with role "Operator"
# (dim_well references the *existing* dim_partner, not a new dim_operator).
operator_partner_id = next(p["PartnerId"] for p in partners if p["PartnerRole"] == "Operator")

# ---- facilities: export terminals (shared, no FieldId) + a flowstation
# (and sometimes a gas plant) per field --------------------------------------
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

# ---- wells: WellsTotal per field, correlated to that field -----------------
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

# ---- wellbores: 1 or 2 per well ---------------------------------------------
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

# ---- completions: one active completion per wellbore ------------------------
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
# Explicit StructTypes for every table. NOT optional here: dimension rows all
# carry valid_to=None (every row is "current"), and letting Spark infer a
# schema from an all-null column raises "Some of types cannot be determined
# after inferring" - createDataFrame(rows) without an explicit schema fails
# outright for these tables. Matches the pattern nb_fetch_reports.ipynb (in
# northstar-formation/auth) already used for exactly this reason.

_AUDIT_FIELDS = [
    StructField("Sourcefile", StringType()),
    StructField("Manifest_package", StringType()),
    StructField("Manifest_file", StringType()),
    StructField("Load_date", DateType()),
    StructField("Load_timestamp", TimestampType()),
    StructField("Partitionkey", StringType()),
    StructField("ins_batchid", IntegerType()),
    StructField("upd_batchid", IntegerType()),
    StructField("Exportdate", TimestampType()),
]

_SCD_FIELDS = [
    StructField("valid_from", TimestampType()),
    StructField("valid_to", TimestampType(), nullable=True),
    StructField("is_current", BooleanType()),
]

SCHEMAS = {
    "partner": StructType([
        StructField("PartnerId", StringType()),
        StructField("PartnerName", StringType()),
        StructField("PartnerRole", StringType()),
        StructField("EquityPct", DecimalType(6, 3)),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "field": StructType([
        StructField("FieldId", StringType()),
        StructField("FieldName", StringType()),
        StructField("ExportPoint", StringType()),
        StructField("WellsTotal", IntegerType()),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "period": StructType([
        StructField("PeriodId", StringType()),
        StructField("Period", DateType()),
        StructField("Label", StringType()),
        StructField("Year", IntegerType()),
        StructField("Quarter", IntegerType()),
        StructField("MonthNumber", IntegerType()),
        StructField("MonthName", StringType()),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "downtime_cause": StructType([
        StructField("CauseId", StringType()),
        StructField("CauseName", StringType()),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "reconciliation": StructType([
        StructField("PeriodId", StringType()),
        StructField("FieldId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("AllocatedBbl", DecimalType(18, 2)),
        StructField("LiftedBbl", DecimalType(18, 2)),
        StructField("CashCallStatus", StringType()),
        StructField("CashCallUsd", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS),
    "production": StructType([
        StructField("PeriodId", StringType()),
        StructField("FieldId", StringType()),
        StructField("ActualBopd", DecimalType(18, 2)),
        StructField("ForecastBopd", DecimalType(18, 2)),
        StructField("WellsOnline", IntegerType()),
        StructField("UptimePct", DecimalType(9, 2)),
        StructField("OpsStatus", StringType()),
    ] + _AUDIT_FIELDS),
    "downtime": StructType([
        StructField("PeriodId", StringType()),
        StructField("CauseId", StringType()),
        StructField("Hours", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS),
    "hse_exposure": StructType([
        StructField("PeriodId", StringType()),
        StructField("HoursWorked", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS),
    "hse_incidents": StructType([
        StructField("IncidentId", StringType()),
        StructField("PeriodId", StringType()),
        StructField("IncidentDate", DateType()),
        StructField("FieldId", StringType()),
        StructField("Severity", StringType()),
        StructField("Recordable", BooleanType()),
        StructField("Description", StringType()),
    ] + _AUDIT_FIELDS),
    "cash_call_event": StructType([
        StructField("PeriodId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("FieldId", StringType()),
        StructField("Stage", StringType()),
        StructField("EventTimestamp", TimestampType()),
        StructField("Note", StringType()),
    ] + _AUDIT_FIELDS),
    "well": StructType([
        StructField("WellId", StringType()),
        StructField("WellName", StringType()),
        StructField("FieldId", StringType()),
        StructField("FacilityId", StringType()),
        StructField("PartnerId", StringType()),
        StructField("WellType", StringType()),
        StructField("Status", StringType()),
        StructField("SpudDate", DateType()),
        StructField("TotalDepthM", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "wellbore": StructType([
        StructField("WellboreId", StringType()),
        StructField("WellId", StringType()),
        StructField("WellboreName", StringType()),
        StructField("Trajectory", StringType()),
        StructField("IsSidetrack", BooleanType()),
        StructField("MeasuredDepthM", DecimalType(18, 2)),
        StructField("TrueVerticalDepthM", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "completion": StructType([
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
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "facility": StructType([
        StructField("FacilityId", StringType()),
        StructField("FacilityName", StringType()),
        StructField("FacilityType", StringType()),
        StructField("FieldId", StringType(), nullable=True),
        StructField("ExportPoint", StringType()),
        StructField("CapacityBopd", DecimalType(18, 2)),
    ] + _AUDIT_FIELDS + _SCD_FIELDS),
    "production_volume": StructType([
        StructField("PeriodId", StringType()),
        StructField("WellId", StringType()),
        StructField("FieldId", StringType()),
        StructField("FacilityId", StringType()),
        StructField("OilBbl", DecimalType(18, 2)),
        StructField("GasMscf", DecimalType(18, 2)),
        StructField("WaterBbl", DecimalType(18, 2)),
        StructField("OnstreamHours", DecimalType(9, 2)),
        StructField("WaterCutPct", DecimalType(9, 2)),
    ] + _AUDIT_FIELDS),
    "well_test": StructType([
        StructField("TestId", StringType()),
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
    ] + _AUDIT_FIELDS),
    "drilling_telemetry": StructType([
        StructField("ReportId", StringType()),
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
    ] + _AUDIT_FIELDS),
}


def _audit_cols(source_name: str):
    """Framework-required bronze columns, common to every table."""
    return {
        "Sourcefile": f"{source_name}_dummy.parquet",
        "Manifest_package": "DUMMY_DAILY",
        "Manifest_file": f"{source_name}_manifest.json",
        "Load_date": LOAD_TS.date(),
        "Load_timestamp": LOAD_TS,
        "Partitionkey": f"dummy|{LOAD_TS.date().isoformat()}",
        "ins_batchid": BATCH_ID,
        "upd_batchid": BATCH_ID,
        "Exportdate": LOAD_TS,
    }


def _scd_cols():
    """SCD-anchor columns, required on dims only."""
    return {"valid_from": LOAD_TS, "valid_to": None, "is_current": True}


def _write(table: str, rows: list) -> int:
    df = spark.createDataFrame(rows, schema=SCHEMAS[table])
    # overwriteSchema=true because this table may already exist from a prior
    # run with a slightly different schema (e.g. inferred vs. explicit) -
    # without it, Delta rejects the write with DELTA_FAILED_TO_MERGE_FIELDS
    # even when mode is "overwrite". Same pattern northstar-formation/auth/nb_fetch_reports
    # already uses for the same reason.
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"bronze.{table}")
    return len(rows)


# ---- dimensions -------------------------------------------------------------

def write_dim_partner():
    # partners' EquityPct stays a plain float in the source list (used in
    # arithmetic elsewhere) - only cast to Decimal here, to match bronze's
    # declared DECIMAL(6,3) column type.
    rows = [
        Row(**{**p, "EquityPct": Decimal(str(p["EquityPct"]))}, **_audit_cols("partner"), **_scd_cols())
        for p in partners
    ]
    return _write("partner", rows)


def write_dim_field():
    rows = [Row(**f, **_audit_cols("field"), **_scd_cols()) for f in fields]
    return _write("field", rows)


def write_dim_period():
    rows = [Row(**p, **_audit_cols("period"), **_scd_cols()) for p in periods]
    return _write("period", rows)


def write_dim_downtime_cause():
    rows = [Row(**c, **_audit_cols("downtime_cause"), **_scd_cols()) for c in downtime_causes]
    return _write("downtime_cause", rows)


def write_dim_facility():
    rows = [
        Row(
            FacilityId=fc["FacilityId"], FacilityName=fc["FacilityName"], FacilityType=fc["FacilityType"],
            FieldId=fc["FieldId"], ExportPoint=fc["ExportPoint"], CapacityBopd=Decimal(str(fc["CapacityBopd"])),
            **_audit_cols("facility"), **_scd_cols(),
        )
        for fc in facilities
    ]
    return _write("facility", rows)


def write_dim_well():
    rows = [
        Row(
            WellId=w["WellId"], WellName=w["WellName"], FieldId=w["FieldId"], FacilityId=w["FacilityId"],
            PartnerId=w["PartnerId"], WellType=w["WellType"], Status=w["Status"], SpudDate=w["SpudDate"],
            TotalDepthM=Decimal(str(w["TotalDepthM"])),
            **_audit_cols("well"), **_scd_cols(),
        )
        for w in wells
    ]
    return _write("well", rows)


def write_dim_wellbore():
    rows = [
        Row(
            WellboreId=wb["WellboreId"], WellId=wb["WellId"], WellboreName=wb["WellboreName"],
            Trajectory=wb["Trajectory"], IsSidetrack=wb["IsSidetrack"],
            MeasuredDepthM=Decimal(str(wb["MeasuredDepthM"])), TrueVerticalDepthM=Decimal(str(wb["TrueVerticalDepthM"])),
            **_audit_cols("wellbore"), **_scd_cols(),
        )
        for wb in wellbores
    ]
    return _write("wellbore", rows)


def write_dim_completion():
    rows = [
        Row(
            CompletionId=c["CompletionId"], WellboreId=c["WellboreId"], WellId=c["WellId"],
            CompletionType=c["CompletionType"], ReservoirUnit=c["ReservoirUnit"],
            PerforationTopM=Decimal(str(c["PerforationTopM"])), PerforationBaseM=Decimal(str(c["PerforationBaseM"])),
            ArtificialLift=c["ArtificialLift"], CompletionDate=c["CompletionDate"], IsActive=c["IsActive"],
            **_audit_cols("completion"), **_scd_cols(),
        )
        for c in completions
    ]
    return _write("completion", rows)


# ---- facts --------------------------------------------------------------

def write_fact_reconciliation():
    rows = []
    for p in periods:
        for f in fields:
            base_bopd = 30000 + fields.index(f) * 6000
            for partner in partners:
                share = base_bopd * (partner["EquityPct"] / 100.0) * 30  # monthly bbl for this partner's share
                seasonal = 1 + 0.05 * _stable_rand("season", p["PeriodId"], f["FieldId"], low=-1, high=1)
                allocated = round(share * seasonal, 2)
                drift = _stable_rand("drift", p["PeriodId"], f["FieldId"], partner["PartnerId"], low=-0.03, high=0.03)
                lifted = round(allocated * (1 + drift), 2)
                variance_pct = abs((lifted - allocated) / allocated * 100) if allocated else 0
                r = _stable_rand("status", p["PeriodId"], f["FieldId"], partner["PartnerId"])
                if variance_pct >= 3 and r > 0.4:
                    status = "disputed"
                elif p["PeriodId"] == periods[-1]["PeriodId"] and r > 0.55:
                    status = "pending"
                else:
                    status = "settled"
                cash_call_usd = round(allocated * 11.4, 2)
                rows.append(Row(
                    PeriodId=p["PeriodId"], FieldId=f["FieldId"], PartnerId=partner["PartnerId"],
                    AllocatedBbl=Decimal(str(allocated)), LiftedBbl=Decimal(str(lifted)),
                    CashCallStatus=status, CashCallUsd=Decimal(str(cash_call_usd)),
                    **_audit_cols("fct_reconciliation"),
                ))
    return _write("reconciliation", rows)


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
            status = "down" if uptime_pct < 88 else ("watch" if (uptime_pct < 94 or actual < forecast * 0.93) else "normal")
            rows.append(Row(
                PeriodId=p["PeriodId"], FieldId=f["FieldId"],
                ActualBopd=Decimal(str(actual)), ForecastBopd=Decimal(str(forecast)),
                WellsOnline=wells_online, UptimePct=Decimal(str(uptime_pct)), OpsStatus=status,
                **_audit_cols("fct_production"),
            ))
    return _write("production", rows)


def write_fact_downtime():
    rows = []
    for p in periods:
        for c in downtime_causes:
            base = 60 + downtime_causes.index(c) * 40
            hours = round(base + _stable_rand("downtime", p["PeriodId"], c["CauseId"], low=0, high=300), 2)
            rows.append(Row(
                PeriodId=p["PeriodId"], CauseId=c["CauseId"], Hours=Decimal(str(hours)),
                **_audit_cols("downtime"),
            ))
    return _write("downtime", rows)


def write_fact_hse_exposure():
    rows = []
    for p in periods:
        hours = round(410000 + _stable_rand("exposure", p["PeriodId"], low=0, high=90000), 2)
        rows.append(Row(PeriodId=p["PeriodId"], HoursWorked=Decimal(str(hours)), **_audit_cols("hse_exposure")))
    return _write("hse_exposure", rows)


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
                **_audit_cols("hse_incidents"),
            ))
    return _write("hse_incidents", rows)


def write_fact_cash_call_event():
    """One row per event in each reconciliation record's cash-call trail -
    submitted -> under-review -> settled/disputed, mirroring Project Spark's
    cashCallTrail() generator exactly (src/data/delta-basin.ts)."""
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
    recon_rows = spark.table("bronze.reconciliation").select(
        "PeriodId", "FieldId", "PartnerId", "CashCallStatus"
    ).collect()

    rows = []
    for r in recon_rows:
        # Cash calls are raised the month after the production period.
        y, m = int(r.PeriodId[:4]), int(r.PeriodId[5:7])
        m += 1
        if m > 12:
            m = 1
            y += 1
        submitted_day = 2 + int(_stable_rand("cc_submit", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=4))
        review_day = submitted_day + 1 + int(_stable_rand("cc_review_gap", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=4))
        close_day = review_day + 2 + int(_stable_rand("cc_close_gap", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=8))

        def _dt(day, hour):
            day = min(day, 28)
            return datetime(y, m, day, hour, 0, 0)

        events = [
            ("submitted", _dt(submitted_day, 9), f"Cash call raised for {r.PeriodId} on {r.FieldId}."),
            ("under-review", _dt(review_day, 11), review_notes[int(_stable_rand("cc_review_note", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=len(review_notes)))]),
        ]
        if r.CashCallStatus == "disputed":
            events.append(("disputed", _dt(close_day, 15), dispute_notes[int(_stable_rand("cc_dispute_note", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=len(dispute_notes)))]))
        elif r.CashCallStatus == "settled":
            events.append(("settled", _dt(close_day, 14), settle_notes[int(_stable_rand("cc_settle_note", r.PeriodId, r.FieldId, r.PartnerId, low=0, high=len(settle_notes)))]))
        # "pending" status -> only submitted + under-review, matching Spark's logic

        for stage, ts, note in events:
            rows.append(Row(
                PeriodId=r.PeriodId, PartnerId=r.PartnerId, FieldId=r.FieldId,
                Stage=stage, EventTimestamp=ts, Note=note,
                **_audit_cols("cash_call_event"),
            ))

    return _write("cash_call_event", rows)


def write_fact_production_volume():
    """Well-level monthly production volume - shares the field's production
    total (bronze.fact_production) across its producing/shut-in wells, then
    correlates onstream hours / water cut to well status. Different grain
    than field-level production, not a duplicate."""
    HOURS_PER_MONTH = 730
    prod_by_key = {}
    for row in spark.table("bronze.production").select("PeriodId", "FieldId", "ActualBopd").collect():
        prod_by_key[(row.PeriodId, row.FieldId)] = float(row.ActualBopd)

    rows = []
    for p in periods:
        for f in fields:
            actual_bopd = prod_by_key.get((p["PeriodId"], f["FieldId"]), 0.0)
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
                    **_audit_cols("production_volume"),
                ))
    return _write("production_volume", rows)


def write_fact_well_test():
    """One well test per well per quarter, correlated to that well's
    production_volume oil rate for the same period where available."""
    quarter_periods = [p for i, p in enumerate(periods) if i % 3 == 2]
    pv_by_key = {}
    for row in spark.table("bronze.production_volume").select("PeriodId", "WellId", "OilBbl", "WaterCutPct").collect():
        pv_by_key[(row.PeriodId, row.WellId)] = (float(row.OilBbl), float(row.WaterCutPct))

    rows = []
    for w in wells:
        completion = completion_by_well.get(w["WellId"])
        if completion is None:
            continue
        for p in quarter_periods:
            key = (w["WellId"], p["PeriodId"])
            oil_bbl, base_wc = pv_by_key.get((p["PeriodId"], w["WellId"]), (0.0, 20.0))
            base_rate = oil_bbl / 30
            oil_rate = round(base_rate * (0.92 + _stable_rand("wt_rate", *key, low=0, high=0.18)), 1)
            water_cut = round(max(0.0, base_wc + (_stable_rand("wt_wc", *key, low=0, high=1) - 0.5) * 6), 1)
            r_valid = _stable_rand("wt_valid", *key)
            validity = "Rejected" if r_valid > 0.93 else ("Suspect" if r_valid > 0.84 else "Valid")
            test_day = 6 + int(_stable_rand("wt_day", *key, low=0, high=18))
            month, day = p["MonthNumber"], min(test_day, 28)
            rows.append(Row(
                TestId=f"WT-{w['WellId']}-{p['PeriodId']}",
                TestDate=date(p["Year"], month, day),
                PeriodId=p["PeriodId"], WellId=w["WellId"], CompletionId=completion["CompletionId"],
                DurationHours=Decimal(str(6 + int(_stable_rand("wt_dur", *key, low=0, high=12)))),
                OilRateBopd=Decimal(str(oil_rate)),
                GasRateMscfd=Decimal(str(round(oil_rate * (0.6 + _stable_rand("wt_gas", *key, low=0, high=1.6)), 1))),
                WaterCutPct=Decimal(str(water_cut)),
                GorScf=Decimal(str(round(500 + _stable_rand("wt_gor", *key, low=0, high=1400), 1))),
                ChokeSize64ths=16 + int(_stable_rand("wt_choke", *key, low=0, high=40)),
                ThpPsi=Decimal(str(round(600 + _stable_rand("wt_thp", *key, low=0, high=1800), 1))),
                Validity=validity,
                **_audit_cols("well_test"),
            ))
    return _write("well_test", rows)


def write_fact_drilling_telemetry():
    """Daily drilling report telemetry for wells currently in Drilling
    status only - a 30-day trailing window ending at the current load date."""
    wellbore_by_well = {}
    for wb in wellbores:
        wellbore_by_well.setdefault(wb["WellId"], wb)

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
                ReportId=f"DRL-{w['WellId']}-{report_date.isoformat()}",
                WellId=w["WellId"], WellboreId=wb["WellboreId"], ReportDate=report_date,
                DepthM=Decimal(str(round(depth, 1))), RopMPerHr=Decimal(str(rop)),
                WobKlbs=Decimal(str(round(12 + _stable_rand("dt_wob", *key, low=0, high=28), 1))),
                Rpm=Decimal(str(round(60 + _stable_rand("dt_rpm", *key, low=0, high=100), 1))),
                MudWeightPpg=Decimal(str(round(9.2 + _stable_rand("dt_mud", *key, low=0, high=3), 1))),
                FlowRateGpm=Decimal(str(round(420 + _stable_rand("dt_flow", *key, low=0, high=380), 1))),
                Npt=npt,
                **_audit_cols("drilling_telemetry"),
            ))
    return _write("drilling_telemetry", rows)


# ---- run ------------------------------------------------------------------

print("=" * 70)
print("DUMMY BRONZE DATA GENERATOR - customer0")
print(f"Batch: {BATCH_ID}  |  Periods: {periods[0]['PeriodId']} .. {periods[-1]['PeriodId']}")
print("=" * 70)

spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")

counts = {}
counts["partner"] = write_dim_partner()
counts["field"] = write_dim_field()
counts["period"] = write_dim_period()
counts["downtime_cause"] = write_dim_downtime_cause()
counts["facility"] = write_dim_facility()
counts["well"] = write_dim_well()
counts["wellbore"] = write_dim_wellbore()
counts["completion"] = write_dim_completion()
counts["reconciliation"] = write_fact_reconciliation()
counts["production"] = write_fact_production()
counts["downtime"] = write_fact_downtime()
counts["hse_exposure"] = write_fact_hse_exposure()
counts["hse_incidents"] = write_fact_hse_incidents()
counts["cash_call_event"] = write_fact_cash_call_event()
counts["production_volume"] = write_fact_production_volume()
counts["well_test"] = write_fact_well_test()
counts["drilling_telemetry"] = write_fact_drilling_telemetry()

print("\nRows written:")
for table, n in counts.items():
    print(f"  bronze.{table:<20} {n:>8,}")
print(f"\nTotal: {sum(counts.values()):,} rows across {len(counts)} tables")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
