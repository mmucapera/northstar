# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_unit_conversion
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: build_unit_conversion_sql
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Unit Conversion
# Generates dynamic SQL to convert measure columns between units of measure using dimension lookup tables.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


# def build_unit_conversion_sql(
#     base_measures,
#     domain,
#     main_tbl=None,
#     rptmeasure_filter=None,
#     id_col=None,
#     join_tbl=None,
#     join_tbl_key=None,
#     unit_tbl=None,
#     puc_tbl=None,
#     guc_tbl=None,
#     filter=None,
#     unit_combos_tbl=None,
# ):

#     debug_vars = {
#         "base_measures": base_measures,
#         "domain": domain,
#         "main_tbl": main_tbl,
#         "rptmeasure_filter": rptmeasure_filter,
#         "id_col": id_col,
#         "join_tbl": join_tbl,
#         "join_tbl_key": join_tbl_key,
#         "unit_tbl": unit_tbl,
#         "puc_tbl": puc_tbl,
#         "guc_tbl": guc_tbl,
#         "filter": filter,
#         "unit_combos_tbl": unit_combos_tbl,
#     }

#     for name, value in debug_vars.items():
#         logger.info(f"{name}: {value}")


#     # Evaluate counts once (avoid double scans)
#     counts = {
#         join_tbl: spark.table(join_tbl).count(),
#         unit_tbl: spark.table(unit_tbl).count(),
#         puc_tbl:  spark.table(puc_tbl).count(),
#         guc_tbl:  spark.table(guc_tbl).count(),
#     }

#     # Identify empty tables
#     empty = [tbl for tbl, c in counts.items() if c == 0]

#     if empty:
#         msg = (
#             f"No source data for {main_tbl}.\n"
#             f"Empty tables: {', '.join(empty)}"
#         )
#         stop_notebook(msg)



#     """
#     Unified builder for unit conversion SQL for both OPR and FCT domains.
#     - id_col: the join key column (e.g., 'Productlocationid' for OPR, 'forecastitemid' for FCT)
#     - join_tbl: the table to join for product/forecastitem (e.g., productlocation or forecastitem)
#     - join_tbl_key: the key in join_tbl to join on (e.g., 'Productlocationid' or 'forecastitemid')
#     - unit_combos_tbl: the table for unit combinations (e.g., 'silver.opr_unit_combinations' or 'silver.fct_unit_combinations')
#     """
#     if main_tbl is None:
#         raise ValueError("main_tbl must be provided.")
#     if id_col is None or join_tbl is None or join_tbl_key is None or unit_combos_tbl is None:
#         raise ValueError("id_col, join_tbl, join_tbl_key, and unit_combos_tbl must be provided.")

#     # Load unit combos
#     unit_combos_df = spark.table(unit_combos_tbl)

#     if rptmeasure_filter:
#         unit_combos_df = unit_combos_df.filter(f"'{rptmeasure_filter}'")

#     if filter:
#         unit_combos_df = unit_combos_df.filter(filter)

#     unit_combos_df = (
#         unit_combos_df
#         .filter("RptMeasure IS NOT NULL AND DefaultUnit IS NOT NULL")
#         .withColumn("RptMeasure", F.trim(F.upper(F.col("RptMeasure"))))
#         .withColumn("DefaultUnit", F.trim(F.col("DefaultUnit")))
#         .dropDuplicates(["RptMeasure", "DefaultUnit"])
#     )

#     unit_combos = unit_combos_df.collect()

#     fact_table = f"silver.{domain}_{main_tbl}"
#     join_table = join_tbl or f"silver.{domain}_{join_tbl}"
#     unit_table = unit_tbl or f"silver.{domain}_unit"
#     puc_table = puc_tbl or f"silver.{domain}_productunitconversion"
#     guc_table = guc_tbl or f"silver.{domain}_generalunitconversion"

#     # Detect existing columns in SOURCE table
#     source_cols_ordered = spark.table(fact_table).columns
#     source_cols_lower = set([c.lower() for c in source_cols_ordered])

#     generated_cols = []
#     cte_blocks = []
#     dynamic_cols = []
#     join_clauses = []

#     for row in unit_combos:
#         rpt = row["RptMeasure"]
#         tgt_unit = row["DefaultUnit"]

#         # Resolve actual Measure from fct_unit for the target unit
#         actual_measure_row = spark.sql(
#             f"SELECT Measure FROM {unit_table} WHERE Unitid = '{tgt_unit}'"
#         ).collect()
#         actual_measure = actual_measure_row[0][0].strip().upper() if actual_measure_row and actual_measure_row[0][0] else rpt

#         safe_tgt = tgt_unit.replace("/", "_").replace(" ", "_").replace(".", "_")
#         suffix = f"{rpt}_{safe_tgt}".lower()

#         puc_dedup_cte = f"puc_dedup_{suffix}"
#         puc_interm_sel_cte = f"puc_interm_sel_{suffix}"
#         puc_interm_final_cte = f"puc_interm_final_{suffix}"
#         puc_src_fb_cte = f"puc_src_fallback_{suffix}"
#         puc_src_fb_final_cte = f"puc_src_fallback_final_{suffix}"
#         cte_raw = f"cte_{suffix}_raw"
#         cte_final = f"cte_{suffix}"

#         alias = f"b_{suffix}"

#         # CTE SQL
#         cte_sql = f"""
# {puc_dedup_cte} AS (
#     SELECT Productid, Unitid, MAX(Factor) AS Factor
#     FROM {puc_table}
#     GROUP BY Productid, Unitid
# ),

# {puc_interm_sel_cte} AS (
#     SELECT
#         p.Productid,
#         p.Unitid,
#         p.Factor,
#         ROW_NUMBER() OVER (
#             PARTITION BY p.Productid
#             ORDER BY 
#                 CASE WHEN p.Factor IS NOT NULL THEN 1 ELSE 2 END,
#                 p.Unitid
#         ) AS rn
#     FROM {puc_dedup_cte} p
#     JOIN {unit_table} u 
#         ON u.Unitid = p.Unitid
#     JOIN {unit_table} utgt 
#         ON utgt.Unitid = '{tgt_unit}'
#     WHERE u.Measure = utgt.Measure
#       AND EXISTS (
#             SELECT 1
#             FROM {guc_table} g
#             WHERE g.Unitid = p.Unitid
#       )
#       AND p.Unitid <> '{tgt_unit}'
# ),

# {puc_interm_final_cte} AS (
#     SELECT Productid, Unitid AS IntermUnit, Factor AS puc_factor_interm
#     FROM {puc_interm_sel_cte}
#     WHERE rn = 1
# ),

# {puc_src_fb_cte} AS (
#     SELECT
#         p.Productid,
#         u_src.Unitid AS SourceUnit,
#         p.Unitid AS FallbackUnit,
#         p.Factor AS puc_factor_fallback,
#         ROW_NUMBER() OVER (
#             PARTITION BY p.Productid, u_src.Unitid
#             ORDER BY 
#                 CASE WHEN p.Factor IS NOT NULL THEN 1 ELSE 2 END,
#                 p.Unitid
#         ) AS rn
#     FROM {puc_dedup_cte} p
#     JOIN {unit_table} u_fb
#         ON u_fb.Unitid = p.Unitid
#     JOIN {unit_table} u_src
#         ON u_src.Measure = u_fb.Measure
#        AND u_src.Unitid <> p.Unitid
#     WHERE EXISTS (
#         SELECT 1 FROM {guc_table} g WHERE g.Unitid = p.Unitid
#     )
#     AND EXISTS (
#         SELECT 1 FROM {guc_table} g WHERE g.Unitid = u_src.Unitid
#     )
# ),

# {puc_src_fb_final_cte} AS (
#     SELECT Productid, SourceUnit, FallbackUnit, puc_factor_fallback
#     FROM {puc_src_fb_cte}
#     WHERE rn = 1
# ),

# {cte_raw} AS (
#     SELECT
#         f.{id_col},
#         f.Unitid AS SourceUnit,
#         pl.Productid,
#         us.Measure AS SourceMeasure,

#         puc_src.Factor AS puc_factor_src,
#         puc_tgt.Factor AS puc_factor_tgt,
#         puc_interm_final.puc_factor_interm AS puc_factor_interm,

#         guc_src.Factor AS guc_factor_src,
#         guc_interm.Factor AS guc_factor_interm,
#         guc_tgt.Factor AS guc_factor_tgt,

#         fb.puc_factor_fallback AS puc_factor_fallback,
#         guc_fb.Factor AS guc_factor_fb

#     FROM {fact_table} f
#     JOIN {join_table} pl
#         ON pl.{join_tbl_key} = f.{id_col}

#     LEFT JOIN {unit_table} us
#         ON us.Unitid = f.Unitid

#     LEFT JOIN {puc_dedup_cte} puc_src
#         ON puc_src.Productid = pl.Productid
#        AND puc_src.Unitid = f.Unitid

#     LEFT JOIN {puc_dedup_cte} puc_tgt
#         ON puc_tgt.Productid = pl.Productid
#        AND puc_tgt.Unitid = '{tgt_unit}'

#     LEFT JOIN {puc_interm_final_cte} puc_interm_final
#         ON puc_interm_final.Productid = pl.Productid

#     LEFT JOIN {guc_table} guc_src
#         ON guc_src.Unitid = f.Unitid

#     LEFT JOIN {guc_table} guc_interm
#         ON guc_interm.Unitid = puc_interm_final.IntermUnit

#     LEFT JOIN {guc_table} guc_tgt
#         ON guc_tgt.Unitid = '{tgt_unit}'

#     LEFT JOIN {puc_src_fb_final_cte} fb
#         ON fb.Productid = pl.Productid
#        AND fb.SourceUnit = f.Unitid

#     LEFT JOIN {guc_table} guc_fb
#         ON guc_fb.Unitid = fb.FallbackUnit
# ),

# {cte_final} AS (
#     SELECT *
#     FROM (
#         SELECT *,
#             ROW_NUMBER() OVER (
#                 PARTITION BY {id_col}, SourceUnit
#                 ORDER BY
#                     CASE
#                         WHEN puc_factor_tgt IS NOT NULL THEN 1
#                         WHEN puc_factor_interm IS NOT NULL THEN 2
#                         WHEN guc_factor_src IS NOT NULL AND guc_factor_tgt IS NOT NULL THEN 3
#                         WHEN puc_factor_fallback IS NOT NULL AND guc_factor_fb IS NOT NULL AND puc_factor_tgt IS NOT NULL THEN 4
#                         WHEN puc_factor_fallback IS NOT NULL AND guc_factor_fb IS NOT NULL AND puc_factor_interm IS NOT NULL THEN 5
#                         ELSE 6
#                     END,
#                     Productid
#             ) AS rn
#         FROM {cte_raw}
#     ) t
#     WHERE rn = 1
# )
# """
#         cte_blocks.append(cte_sql)

#         # Dynamic SELECT
#         for base in base_measures:
#             col_alias = f"{base}_{suffix}".lower()
#             generated_cols.append(col_alias)

#             expr = f"""
# (
#     CASE
#         WHEN {alias}.SourceMeasure = '{actual_measure}' THEN
#             CASE
#                 WHEN {alias}.guc_factor_src IS NOT NULL
#                  AND {alias}.guc_factor_tgt IS NOT NULL
#                     THEN T.{base} * {alias}.guc_factor_tgt / {alias}.guc_factor_src
#                 ELSE NULL
#             END
#         ELSE
#             CASE
#                 WHEN {alias}.puc_factor_src IS NOT NULL THEN
#                     CASE
#                         WHEN {alias}.puc_factor_tgt IS NOT NULL THEN
#                             T.{base} * {alias}.puc_factor_tgt / {alias}.puc_factor_src
#                         WHEN {alias}.puc_factor_interm IS NOT NULL
#                          AND {alias}.guc_factor_interm IS NOT NULL
#                          AND {alias}.guc_factor_tgt IS NOT NULL THEN
#                             T.{base}
#                             * {alias}.puc_factor_interm / {alias}.puc_factor_src
#                             * {alias}.guc_factor_tgt / {alias}.guc_factor_interm
#                         ELSE NULL
#                     END
#                 WHEN {alias}.puc_factor_fallback IS NOT NULL
#                  AND {alias}.guc_factor_src IS NOT NULL
#                  AND {alias}.guc_factor_fb IS NOT NULL THEN
#                     CASE
#                         WHEN {alias}.puc_factor_tgt IS NOT NULL THEN
#                             T.{base}
#                             * {alias}.guc_factor_fb / {alias}.guc_factor_src
#                             * {alias}.puc_factor_tgt / {alias}.puc_factor_fallback
#                         WHEN {alias}.puc_factor_interm IS NOT NULL
#                          AND {alias}.guc_factor_interm IS NOT NULL
#                          AND {alias}.guc_factor_tgt IS NOT NULL THEN
#                             T.{base}
#                             * {alias}.guc_factor_fb / {alias}.guc_factor_src
#                             * {alias}.puc_factor_interm / {alias}.puc_factor_fallback
#                             * {alias}.guc_factor_tgt / {alias}.guc_factor_interm
#                         ELSE NULL
#                     END
#                 ELSE NULL
#             END
#     END
# ) AS {col_alias}
# """
#             dynamic_cols.append(expr)

#         join_clauses.append(
#             f"LEFT JOIN {cte_final} {alias}\n"
#             f"    ON T.{id_col} = {alias}.{id_col}\n"
#             f"   AND T.Unitid = {alias}.SourceUnit\n"
#         )

#     # Build explicit base column list (no EXCEPT)
#     generated_set = set(generated_cols)
#     base_cols = [
#         c for c in source_cols_ordered
#         if c.lower() not in generated_set
#     ]

#     with_clause = "WITH\n" + ",\n".join(cte_blocks)
#     base_select = ",\n    ".join([f"T.{c}" for c in base_cols])
#     dynamic_select_sql = ",\n    ".join(dynamic_cols)
#     join_sql = "\n".join(join_clauses)
#     final_select = f"{base_select},\n    {dynamic_select_sql}"
#     return with_clause, final_select, join_sql

def build_unit_conversion_sql(
    base_measures,
    domain,
    main_tbl=None,
    rptmeasure_filter=None,
    id_col=None,
    join_tbl=None,
    join_tbl_key=None,
    unit_tbl=None,
    puc_tbl=None,
    guc_tbl=None,
    filter=None,
    unit_combos_tbl=None,
):
    """
    Optimized unit conversion SQL builder.
    Pre-materializes distinct fact keys and conversion factors as cached temp views,
    then returns simple SQL that joins the fact table to pre-computed factors in a single pass.
    """

    debug_vars = {
        "base_measures": base_measures,
        "domain": domain,
        "main_tbl": main_tbl,
        "rptmeasure_filter": rptmeasure_filter,
        "id_col": id_col,
        "join_tbl": join_tbl,
        "join_tbl_key": join_tbl_key,
        "unit_tbl": unit_tbl,
        "puc_tbl": puc_tbl,
        "guc_tbl": guc_tbl,
        "filter": filter,
        "unit_combos_tbl": unit_combos_tbl,
    }

    for name, value in debug_vars.items():
        logger.info(f"{name}: {value}")


    # Evaluate counts once (avoid double scans)
    counts = {
        join_tbl: spark.table(join_tbl).count(),
        unit_tbl: spark.table(unit_tbl).count(),
        puc_tbl:  spark.table(puc_tbl).count(),
        guc_tbl:  spark.table(guc_tbl).count(),
    }

    # Identify empty tables
    empty = [tbl for tbl, c in counts.items() if c == 0]

    if empty:
        msg = (
            f"No source data for {main_tbl}.\n"
            f"Empty tables: {', '.join(empty)}"
        )
        stop_notebook(msg)

    if main_tbl is None:
        raise ValueError("main_tbl must be provided.")
    if id_col is None or join_tbl is None or join_tbl_key is None or unit_combos_tbl is None:
        raise ValueError("id_col, join_tbl, join_tbl_key, and unit_combos_tbl must be provided.")

    # Load unit combos
    unit_combos_df = spark.table(unit_combos_tbl)

    if rptmeasure_filter:
        unit_combos_df = unit_combos_df.filter(f"'{rptmeasure_filter}'")

    if filter:
        unit_combos_df = unit_combos_df.filter(filter)

    unit_combos_df = (
        unit_combos_df
        .filter("RptMeasure IS NOT NULL AND DefaultUnit IS NOT NULL")
        .withColumn("RptMeasure", F.trim(F.upper(F.col("RptMeasure"))))
        .withColumn("DefaultUnit", F.trim(F.col("DefaultUnit")))
        .dropDuplicates(["RptMeasure", "DefaultUnit"])
    )

    unit_combos = unit_combos_df.collect()

    fact_table = f"silver.{domain}_{main_tbl}"
    join_table = join_tbl or f"silver.{domain}_{join_tbl}"
    unit_table = unit_tbl or f"silver.{domain}_unit"
    puc_table = puc_tbl or f"silver.{domain}_productunitconversion"
    guc_table = guc_tbl or f"silver.{domain}_generalunitconversion"

    # Detect existing columns in SOURCE table
    source_cols_ordered = spark.table(fact_table).columns
    source_cols_lower = set([c.lower() for c in source_cols_ordered])

    # =========================================================================
    # Generate unique temp view names to avoid conflicts with concurrent notebooks
    # =========================================================================
    _vn_fact_keys = _safe_view(f"uc_fact_keys_{domain}_{main_tbl}")
    _vn_puc_dedup = _safe_view(f"uc_puc_dedup_{domain}_{main_tbl}")
    _vn_all_factors = _safe_view(f"uc_all_factors_{domain}_{main_tbl}")

    # =========================================================================
    # OPTIMIZATION: Pre-materialize distinct fact keys (single fact table scan)
    # This avoids re-scanning the large fact table once per unit combo.
    # =========================================================================
    logger.info("Materializing distinct fact keys for unit conversion...")
    _uc_keys_df = spark.sql(f"""
        SELECT DISTINCT f.{id_col}, f.Unitid, pl.Productid
        FROM {fact_table} f
        JOIN {join_table} pl ON pl.{join_tbl_key} = f.{id_col}
    """).cache()
    _uc_keys_df.createOrReplaceTempView(_vn_fact_keys)
    _key_count = _uc_keys_df.count()  # force materialization
    logger.info(f"Distinct fact keys materialized: {_key_count:,} rows (view: {_vn_fact_keys})")

    # =========================================================================
    # OPTIMIZATION: Shared puc_dedup (computed once, not per combo)
    # =========================================================================
    spark.sql(f"""
        SELECT Productid, Unitid, MAX(Factor) AS Factor
        FROM {puc_table}
        GROUP BY Productid, Unitid
    """).cache().createOrReplaceTempView(_vn_puc_dedup)
    spark.table(_vn_puc_dedup).count()  # force cache

    # =========================================================================
    # FIX 1: Pre-fetch all actual_measure values in one Spark job
    # Avoids 2×N per-combo driver-side lookups (was a key 30-min bottleneck).
    # =========================================================================
    _tgt_units = list({row["DefaultUnit"] for row in unit_combos})
    _tgt_units_sql = ", ".join(f"'{u}'" for u in _tgt_units)
    _unit_measure_map = {
        r["Unitid"]: (r["Measure"].strip().upper() if r["Measure"] else None)
        for r in spark.sql(
            f"SELECT Unitid, Measure FROM {unit_table} WHERE Unitid IN ({_tgt_units_sql})"
        ).collect()
    } if _tgt_units else {}
    logger.info(f"Pre-fetched measure map for {len(_unit_measure_map)} target units: {list(_unit_measure_map.keys())}")

    # =========================================================================
    # FIX 2: Materialize each combo individually (avoids one massive N-branch union job).
    # For each unit combo, compute conversion factors on the SMALL keys set.
    # =========================================================================
    factor_views = []

    for _combo_idx, row in enumerate(unit_combos):
        rpt = row["RptMeasure"]
        tgt_unit = row["DefaultUnit"]

        # Use pre-fetched measure map — no per-combo Spark job
        actual_measure = _unit_measure_map.get(tgt_unit) or rpt

        safe_tgt = tgt_unit.replace("/", "_").replace(" ", "_").replace(".", "_")
        suffix = f"{rpt}_{safe_tgt}".lower()

        # Build conversion factors using the small fact keys + dimension tables
        factor_sql = f"""
        WITH
        puc_interm_sel AS (
            SELECT
                p.Productid,
                p.Unitid,
                p.Factor,
                ROW_NUMBER() OVER (
                    PARTITION BY p.Productid
                    ORDER BY 
                        CASE WHEN p.Factor IS NOT NULL THEN 1 ELSE 2 END,
                        p.Unitid
                ) AS rn
            FROM {_vn_puc_dedup} p
            JOIN {unit_table} u ON u.Unitid = p.Unitid
            JOIN {unit_table} utgt ON utgt.Unitid = '{tgt_unit}'
            WHERE u.Measure = utgt.Measure
              AND EXISTS (SELECT 1 FROM {guc_table} g WHERE g.Unitid = p.Unitid)
              AND p.Unitid <> '{tgt_unit}'
        ),
        puc_interm_final AS (
            SELECT Productid, Unitid AS IntermUnit, Factor AS puc_factor_interm
            FROM puc_interm_sel
            WHERE rn = 1
        ),
        puc_src_fb AS (
            SELECT
                p.Productid,
                u_src.Unitid AS SourceUnit,
                p.Unitid AS FallbackUnit,
                p.Factor AS puc_factor_fallback,
                ROW_NUMBER() OVER (
                    PARTITION BY p.Productid, u_src.Unitid
                    ORDER BY 
                        CASE WHEN p.Factor IS NOT NULL THEN 1 ELSE 2 END,
                        p.Unitid
                ) AS rn
            FROM {_vn_puc_dedup} p
            JOIN {unit_table} u_fb ON u_fb.Unitid = p.Unitid
            JOIN {unit_table} u_src
                ON u_src.Measure = u_fb.Measure
               AND u_src.Unitid <> p.Unitid
            WHERE EXISTS (SELECT 1 FROM {guc_table} g WHERE g.Unitid = p.Unitid)
              AND EXISTS (SELECT 1 FROM {guc_table} g WHERE g.Unitid = u_src.Unitid)
        ),
        puc_src_fb_final AS (
            SELECT Productid, SourceUnit, FallbackUnit, puc_factor_fallback
            FROM puc_src_fb
            WHERE rn = 1
        ),
        cte_raw AS (
            SELECT
                fk.{id_col},
                fk.Unitid AS SourceUnit,
                fk.Productid,
                us.Measure AS SourceMeasure,

                puc_src.Factor AS puc_factor_src,
                puc_tgt.Factor AS puc_factor_tgt,
                puc_interm_final.puc_factor_interm AS puc_factor_interm,

                guc_src.Factor AS guc_factor_src,
                guc_interm.Factor AS guc_factor_interm,
                guc_tgt.Factor AS guc_factor_tgt,

                fb.puc_factor_fallback AS puc_factor_fallback,
                guc_fb.Factor AS guc_factor_fb

            FROM {_vn_fact_keys} fk

            LEFT JOIN {unit_table} us
                ON us.Unitid = fk.Unitid

            LEFT JOIN {_vn_puc_dedup} puc_src
                ON puc_src.Productid = fk.Productid
               AND puc_src.Unitid = fk.Unitid

            LEFT JOIN {_vn_puc_dedup} puc_tgt
                ON puc_tgt.Productid = fk.Productid
               AND puc_tgt.Unitid = '{tgt_unit}'

            LEFT JOIN puc_interm_final
                ON puc_interm_final.Productid = fk.Productid

            LEFT JOIN {guc_table} guc_src
                ON guc_src.Unitid = fk.Unitid

            LEFT JOIN {guc_table} guc_interm
                ON guc_interm.Unitid = puc_interm_final.IntermUnit

            LEFT JOIN {guc_table} guc_tgt
                ON guc_tgt.Unitid = '{tgt_unit}'

            LEFT JOIN puc_src_fb_final fb
                ON fb.Productid = fk.Productid
               AND fb.SourceUnit = fk.Unitid

            LEFT JOIN {guc_table} guc_fb
                ON guc_fb.Unitid = fb.FallbackUnit
        ),
        cte_final AS (
            SELECT *
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY {id_col}, SourceUnit
                        ORDER BY
                            CASE
                                WHEN puc_factor_tgt IS NOT NULL THEN 1
                                WHEN puc_factor_interm IS NOT NULL THEN 2
                                WHEN guc_factor_src IS NOT NULL AND guc_factor_tgt IS NOT NULL THEN 3
                                WHEN puc_factor_fallback IS NOT NULL AND guc_factor_fb IS NOT NULL AND puc_factor_tgt IS NOT NULL THEN 4
                                WHEN puc_factor_fallback IS NOT NULL AND guc_factor_fb IS NOT NULL AND puc_factor_interm IS NOT NULL THEN 5
                                ELSE 6
                            END,
                            Productid
                ) AS rn
                FROM cte_raw
            ) t
            WHERE rn = 1
        )
        SELECT
            {id_col},
            SourceUnit,
            SourceMeasure,
            puc_factor_src,
            puc_factor_tgt,
            puc_factor_interm,
            guc_factor_src,
            guc_factor_interm,
            guc_factor_tgt,
            puc_factor_fallback,
            guc_factor_fb,
            '{suffix}' AS _uc_combo
        FROM cte_final
        """

        # Materialize this combo individually — small plan, predictable job time
        _combo_view = _safe_view(f"uc_factors_{domain}_{main_tbl}_{_combo_idx}")
        spark.sql(factor_sql).cache().createOrReplaceTempView(_combo_view)
        spark.table(_combo_view).count()
        factor_views.append(_combo_view)
        logger.info(f"Combo {_combo_idx + 1}/{len(unit_combos)} materialized: {suffix} ({_combo_view})")

    # Union already-materialized views — each is cached, so this is a trivial fan-out job
    _union_sql = " UNION ALL ".join(f"SELECT * FROM {v}" for v in factor_views)
    spark.sql(_union_sql).cache().createOrReplaceTempView(_vn_all_factors)
    _factor_count = spark.table(_vn_all_factors).count()
    logger.info(f"Conversion factors materialized: {_factor_count:,} rows across {len(unit_combos)} unit combos (view: {_vn_all_factors})")

    # =========================================================================
    # Build final SQL that joins fact table to pre-computed factors (single scan)
    # =========================================================================
    generated_cols = []
    dynamic_cols = []
    join_clauses = []

    for row in unit_combos:
        rpt = row["RptMeasure"]
        tgt_unit = row["DefaultUnit"]

        # Use pre-fetched measure map — no per-combo Spark job
        actual_measure = _unit_measure_map.get(tgt_unit) or rpt

        safe_tgt = tgt_unit.replace("/", "_").replace(" ", "_").replace(".", "_")
        suffix = f"{rpt}_{safe_tgt}".lower()
        alias = f"b_{suffix}"

        for base in base_measures:
            col_alias = f"{base}_{suffix}".lower()
            generated_cols.append(col_alias)

            expr = f"""
(
    CASE
        WHEN {alias}.SourceMeasure = '{actual_measure}' THEN
            CASE
                WHEN {alias}.guc_factor_src IS NOT NULL
                 AND {alias}.guc_factor_tgt IS NOT NULL
                    THEN T.{base} * {alias}.guc_factor_tgt / {alias}.guc_factor_src
                ELSE NULL
            END
        ELSE
            CASE
                WHEN {alias}.puc_factor_src IS NOT NULL THEN
                    CASE
                        WHEN {alias}.puc_factor_tgt IS NOT NULL THEN
                            T.{base} * {alias}.puc_factor_tgt / {alias}.puc_factor_src
                        WHEN {alias}.puc_factor_interm IS NOT NULL
                         AND {alias}.guc_factor_interm IS NOT NULL
                         AND {alias}.guc_factor_tgt IS NOT NULL THEN
                            T.{base}
                            * {alias}.puc_factor_interm / {alias}.puc_factor_src
                            * {alias}.guc_factor_tgt / {alias}.guc_factor_interm
                        ELSE NULL
                    END
                WHEN {alias}.puc_factor_fallback IS NOT NULL
                 AND {alias}.guc_factor_src IS NOT NULL
                 AND {alias}.guc_factor_fb IS NOT NULL THEN
                    CASE
                        WHEN {alias}.puc_factor_tgt IS NOT NULL THEN
                            T.{base}
                            * {alias}.guc_factor_fb / {alias}.guc_factor_src
                            * {alias}.puc_factor_tgt / {alias}.puc_factor_fallback
                        WHEN {alias}.puc_factor_interm IS NOT NULL
                         AND {alias}.guc_factor_interm IS NOT NULL
                         AND {alias}.guc_factor_tgt IS NOT NULL THEN
                            T.{base}
                            * {alias}.guc_factor_fb / {alias}.guc_factor_src
                            * {alias}.puc_factor_interm / {alias}.puc_factor_fallback
                            * {alias}.guc_factor_tgt / {alias}.guc_factor_interm
                        ELSE NULL
                    END
                ELSE NULL
            END
    END
) AS {col_alias}
"""
            dynamic_cols.append(expr)

        join_clauses.append(
            f"LEFT JOIN {_vn_all_factors} {alias}\n"
            f"    ON T.{id_col} = {alias}.{id_col}\n"
            f"   AND T.Unitid = {alias}.SourceUnit\n"
            f"   AND {alias}._uc_combo = '{suffix}'\n"
        )

    # Build explicit base column list (no EXCEPT)
    generated_set = set(generated_cols)
    base_cols = [
        c for c in source_cols_ordered
        if c.lower() not in generated_set
    ]

    with_clause = ""
    base_select = ",\n    ".join([f"T.{c}" for c in base_cols])
    dynamic_select_sql = ",\n    ".join(dynamic_cols)
    join_sql = "\n".join(join_clauses)
    final_select = f"{base_select},\n    {dynamic_select_sql}"
    return with_clause, final_select, join_sql

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_unit_conversion")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
