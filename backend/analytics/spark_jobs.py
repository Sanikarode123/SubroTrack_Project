"""PySpark jobs behind the Data Analytics page.

Run by analytics.spark_worker (warm session) or, for one-shot runs:
    python -m analytics.spark_jobs --mode export|jdbc --input DIR --output DIR
Results are collected into results.json (served to the UI) and saved as Parquet.
"""
import argparse, os, time
from datetime import datetime, timezone
from analytics import store
from pyspark.sql import SparkSession, Window, functions as F

STATUSES = ["New Case", "Under Investigation", "Recovery Initiated", "Awaiting Response",
            "Negotiation / Follow-up", "Recovered / Partially Recovered", "Closed"]
DONE = ["Recovered / Partially Recovered", "Closed"]
SCHEMAS = {
    "cases": "id long, recovery_id string, third_party string, amount_paid double, expected_recovery double, status string, assigned_to_id long, created_at string",
    "payments": "case_id long, amount double, date string",
    "activities": "case_id long, type string, created_at string",
    "users": "id long, username string",
}


def clean(v):
    if isinstance(v, float):
        return None if v != v else round(v, 2)
    return v if v is None or isinstance(v, (int, str, bool)) else str(v)


def rows(df):
    return [{k: clean(v) for k, v in r.asDict().items()} for r in df.collect()]


def build_session(mode):
    """Settings for small/medium data on one machine: tiny partition counts, no codegen/AQE planning overhead, no web UI,
    ANSI mode off (same null-on-error behaviour in Spark 3.5 and 4.x) and a fixed loopback address (no slow hostname lookups)."""
    b = (SparkSession.builder.appName("SubroTrackAnalytics").master(os.environ.get("SPARK_MASTER", "local[2]"))
         .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "1g"))
         .config("spark.sql.shuffle.partitions", "2").config("spark.default.parallelism", "2")
         .config("spark.sql.adaptive.enabled", "false").config("spark.sql.codegen.wholeStage", "false")
         .config("spark.sql.ansi.enabled", "false").config("spark.sql.session.timeZone", "UTC")
         .config("spark.ui.enabled", "false").config("spark.driver.bindAddress", "127.0.0.1").config("spark.driver.host", "127.0.0.1"))
    if mode == "jdbc":
        jar = os.environ.get("SPARK_JDBC_JAR")
        b = b.config("spark.jars", jar) if jar else b.config("spark.jars.packages", "org.postgresql:postgresql:42.7.3")
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def read_inputs(spark, mode, inp):
    if mode == "jdbc":  # PostgreSQL / AWS RDS
        opts = dict(url=f"jdbc:postgresql://{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}",
                    user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], driver="org.postgresql.Driver")
        rd = lambda t: spark.read.format("jdbc").options(dbtable=t, **opts).load()
        cases, pays, acts, users = rd("cases_recoverycase"), rd("cases_payment"), rd("cases_activity"), rd("auth_user")
    else:  # SQLite (local development): Django exported the tables as JSON lines
        rd = lambda n: spark.read.schema(SCHEMAS[n]).json(os.path.join(inp, n + ".jsonl"))
        cases, pays, acts, users = rd("cases"), rd("payments"), rd("activities"), rd("users")
    cases = cases.select("id", "recovery_id", "third_party", F.col("amount_paid").cast("double").alias("amount_paid"),
                         F.col("expected_recovery").cast("double").alias("expected_recovery"), "status", "assigned_to_id",
                         F.to_timestamp("created_at").alias("created_at"))
    pays = pays.select("case_id", F.col("amount").cast("double").alias("amount"), F.to_date("date").alias("date"))
    acts = acts.select("case_id", F.to_timestamp("created_at").alias("created_at"))
    users = users.select(F.col("id").alias("assigned_to_id"), F.col("username").alias("employee"))
    return cases, pays, acts, users


def build_base(cases, pays, users):
    # joins use shared column names so there is never an ambiguous reference
    per_case = (pays.groupBy("case_id").agg(F.sum("amount").alias("recovered"), F.min("date").alias("first_pay"), F.max("date").alias("last_pay"))
                .withColumnRenamed("case_id", "id"))
    base = (cases.join(per_case, "id", "left").join(users, "assigned_to_id", "left")
            .fillna({"recovered": 0.0, "employee": "Unassigned"})
            .withColumn("third_party", F.coalesce(F.nullif(F.col("third_party"), F.lit("")), F.lit("Unknown")))
            .withColumn("created_date", F.to_date("created_at"))
            .withColumn("amount_band", F.when(F.col("amount_paid") < 100000, "Small (below 1L)")
                        .when(F.col("amount_paid") < 250000, "Medium (1L - 2.5L)").otherwise("Large (above 2.5L)"))
            .withColumn("days_first", F.datediff("first_pay", "created_date"))
            .withColumn("days_full", F.when(F.col("recovered") >= F.col("expected_recovery"), F.datediff("last_pay", "created_date"))))
    return base.cache()


# 1. employee-wise recovery
def employee_job(base):
    return (base.groupBy("employee").agg(F.count("*").alias("cases_handled"), F.sum(F.col("status").isin(DONE).cast("int")).alias("closed_cases"),
            F.sum("expected_recovery").alias("expected_total"), F.sum("recovered").alias("recovered_total"), F.avg("amount_paid").alias("avg_case_amount"))
            .withColumn("recovery_rate", F.round(F.col("recovered_total") / F.col("expected_total") * 100, 1)).orderBy(F.desc("recovered_total")))


# 2. monthly recovery trend
def monthly_job(pays):
    m = pays.withColumn("month", F.date_format("date", "yyyy-MM")).groupBy("month").agg(F.sum("amount").alias("recovered"), F.count("*").alias("payments"))
    w = Window.orderBy("month")
    return (m.withColumn("prev", F.lag("recovered").over(w))
            .withColumn("mom_change", F.round((F.col("recovered") - F.col("prev")) / F.col("prev") * 100, 1))
            .withColumn("moving_avg", F.round(F.avg("recovered").over(w.rowsBetween(-2, 0)), 2)).drop("prev").orderBy("month"))


# 3. case status analysis
def status_job(base, total):
    return (base.groupBy("status").agg(F.count("*").alias("cases"), F.sum("expected_recovery").alias("expected"), F.sum("recovered").alias("recovered"))
            .withColumn("share", F.round(F.col("cases") / F.lit(max(total, 1)) * 100, 1)))


# 4. recovery performance by case type (amount band and insurer)
def performance_job(base, col):
    return (base.groupBy(F.col(col).alias("segment")).agg(F.count("*").alias("cases"), F.avg(F.when(F.col("recovered") > 0, F.col("recovered"))).alias("avg_recovered"),
            F.sum("recovered").alias("recovered_total"), F.sum("expected_recovery").alias("expected_total"),
            F.avg("days_first").alias("avg_days_first"), F.avg("days_full").alias("avg_days_full"))
            .withColumn("recovery_rate", F.round(F.col("recovered_total") / F.col("expected_total") * 100, 1)).drop("expected_total").orderBy("segment"))


# 5. delayed-case analytics from the activity history
def delay_base(base, acts, delay_days):
    w = Window.partitionBy("case_id").orderBy("created_at")
    gaps = (acts.withColumn("prev", F.lag("created_at").over(w))
            .withColumn("gap", (F.unix_timestamp("created_at") - F.unix_timestamp("prev")) / 86400)
            .groupBy("case_id").agg(F.max("gap").alias("max_gap"), F.max("created_at").alias("last_activity"))
            .withColumnRenamed("case_id", "id"))
    d = base.join(gaps, "id", "left")
    idle = F.when(~F.col("status").isin(DONE), (F.unix_timestamp(F.current_timestamp()) - F.unix_timestamp("last_activity")) / 86400)
    return (d.withColumn("worst_gap", F.greatest(F.coalesce(F.col("max_gap"), F.lit(0.0)), F.coalesce(idle, F.lit(0.0))))
            .withColumn("delayed", F.col("worst_gap") >= delay_days))


def delay_segment(d, col):
    return (d.groupBy(F.col(col).alias("segment")).agg(F.count("*").alias("cases"), F.sum(F.col("delayed").cast("int")).alias("delayed_cases"),
            F.avg("worst_gap").alias("avg_longest_gap"), F.avg("days_full").alias("avg_days_full"))
            .withColumn("delayed_pct", F.round(F.col("delayed_cases") / F.col("cases") * 100, 1)).orderBy(F.desc("delayed_pct")))


def insights(r):
    out = []
    if r["employee"]:
        top = r["employee"][0]
        out.append(f"{top['employee']} has recovered the most: Rs {top['recovered_total']:,.0f} across {top['cases_handled']} cases.")
    m = r["monthly"]
    if len(m) >= 2:
        out.append(f"Monthly recovery trend is {r['monthly_trend'].lower()}; the latest month recovered Rs {m[-1]['recovered']:,.0f}.")
    slow = [x for x in r["delays"]["by_third_party"] if x["cases"] >= 2]
    if slow:
        out.append(f"{slow[0]['segment']} has the highest share of delayed cases ({slow[0]['delayed_pct']}% of {slow[0]['cases']}).")
    perf = [x for x in r["performance"]["third_party"] if x["avg_days_first"] is not None]
    if perf:
        s = max(perf, key=lambda x: x["avg_days_first"])
        out.append(f"{s['segment']} takes the longest to make a first payment (about {s['avg_days_first']:.0f} days).")
    return out


def trend_label(m):
    if len(m) < 4:
        return "Not enough data"
    last, prev = sum(x["recovered"] for x in m[-3:]) / 3, sum(x["recovered"] for x in m[-6:-3]) / max(len(m[-6:-3]), 1)
    return "Rising" if last > prev * 1.05 else "Falling" if last < prev * 0.95 else "Stable"


def save_parquet(out, name, data, df):
    """Results are a few rows, so they are written with pyarrow: no Hadoop/winutils needed (that is what breaks Spark's own writer on Windows)."""
    path = os.path.join(out, "parquet", name)
    if not data:
        return True
    try:
        import pyarrow as pa, pyarrow.parquet as pq
        os.makedirs(path, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(data), os.path.join(path, "part-0.parquet"))
        return True
    except ImportError:
        pass
    except Exception:
        return False
    if os.name == "nt" and not os.environ.get("HADOOP_HOME"):
        return False
    try:
        df.coalesce(1).write.mode("overwrite").parquet(path)
        return True
    except Exception:
        return False


def run_analytics(spark, mode, inp, out, delay_days, stage=lambda s: None):
    """One full run on an existing session. Inputs are cached, each analysis is a single Spark job."""
    t0 = time.time()
    spark.catalog.clearCache()
    stage("Reading data")
    cases, pays, acts, users = read_inputs(spark, mode, inp)
    pays, acts = pays.cache(), acts.cache()
    base = build_base(cases, pays, users)
    n_cases, n_pays, n_acts = base.count(), pays.count(), acts.count()  # fills the caches once
    delay = delay_base(base, acts, delay_days).cache()

    stage("Running analyses")
    frames = {"employee": employee_job(base), "monthly": monthly_job(pays), "status": status_job(base, n_cases),
              "performance_amount_band": performance_job(base, "amount_band"), "performance_third_party": performance_job(base, "third_party"),
              "delay_amount_band": delay_segment(delay, "amount_band"), "delay_third_party": delay_segment(delay, "third_party"),
              "delay_status": delay.filter("delayed").groupBy("status").agg(F.count("*").alias("delayed_cases")).orderBy(F.desc("delayed_cases"))}
    data = {k: rows(v) for k, v in frames.items()}

    seen = {r["status"]: r for r in data["status"]}
    status = [seen.get(s, {"status": s, "cases": 0, "expected": 0, "recovered": 0, "share": 0}) for s in STATUSES]
    res = {"employee": data["employee"], "monthly": data["monthly"], "monthly_trend": trend_label(data["monthly"]), "status": status,
           "performance": {"amount_band": data["performance_amount_band"], "third_party": data["performance_third_party"]},
           "delays": {"by_amount_band": data["delay_amount_band"], "by_third_party": data["delay_third_party"], "by_status": data["delay_status"],
                      "threshold_days": delay_days}}
    res["insights"] = insights(res)
    res["meta"] = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": mode, "spark_version": spark.version,
                   "cases": n_cases, "payments": n_pays, "activities": n_acts, "parquet_ok": None, "duration_s": round(time.time() - t0, 1)}
    os.makedirs(out, exist_ok=True)
    store.write_json(os.path.join(out, "results.json"), res)  # the page can show results before Parquet is saved

    if os.environ.get("SPARK_WRITE_PARQUET", "1") == "1":
        stage("Saving Parquet")
        res["meta"]["parquet_ok"] = all([save_parquet(out, k, data[k], frames[k]) for k in frames])
        res["meta"]["duration_s"] = round(time.time() - t0, 1)
        store.write_json(os.path.join(out, "results.json"), res)


def main():  # one-shot run (management command / SPARK_WORKER=0)
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="export"); ap.add_argument("--input", default="."); ap.add_argument("--output", required=True)
    ap.add_argument("--delay-days", type=int, default=14)
    a = ap.parse_args()
    spark = build_session(a.mode)
    run_analytics(spark, a.mode, a.input, a.output, a.delay_days)
    spark.stop()


if __name__ == "__main__":
    main()
