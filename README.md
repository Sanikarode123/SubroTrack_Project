# SubroTrack

A web system for tracking insurance subrogation recovery cases after a claim has been identified for recovery.
Stack: React + Tailwind CSS, Django + Django REST Framework, SQL database (SQLite locally, PostgreSQL/RDS on AWS), Qwen3 1.7B through Ollama.

## Roles
| Role | Theme | Can do |
|---|---|---|
| Manager | violet | Everything: import/register cases, assign employees, link clients, close cases, create logins, see team performance |
| Employee | green | Works only on cases assigned to them: update status and follow-ups, record third-party responses and payments, review documents, use the AI agent |
| Client | navy | Sees only their own recovery cases: progress, money position, missing documents (can upload them), insurer updates, ask the AI about their claim |

Client uploads are analysed automatically (text extraction, summary, key details, content check) and appear for the manager/employee
on the case's Documents tab and on the dashboard. The case AI assistant uses those extracted details when answering staff questions.

## Main modules
1. Case registration and CSV/XLSX import (only claims flagged `subrogation_potential = Yes` are added)
2. Status workflow with history
3. Follow-up reminders and delayed-case detection (rule based) with an AI agent report on top
4. Document checklist with PDF analysis (PyMuPDF + Qwen3)
5. Third-party tracking: every insurer response per case, plus an insurer-wise page of claimed vs recovered amounts
6. AI case summary and Q&A (staff and client versions)
7. Dashboard with recovery amounts and employee-wise performance

## Setup
Ollama:

    ollama pull qwen3:1.7b
    ollama serve

Backend (first time, or after upgrading: delete backend/db.sqlite3 and backend/cases/migrations):

    cd backend
    python -m venv venv
    venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
    pip install -r requirements.txt
    python manage.py makemigrations cases
    python manage.py migrate
    python manage.py seed
    python manage.py runserver

Frontend:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173 and pick the tab for your role.

## Demo Login Credentials

> **For local development and demonstration only.**
> These are sample accounts created by the database seed command.
> Do not use these credentials in production.

| Username | Demo Password | Role |
|---|---|---|
| manager | manager123 | Manager |
| priya, amit | pass1234 | Employee |
| rahul, sneha, vikram | pass1234 | Client |

## Configuration (environment variables)
DELAY_THRESHOLD_DAYS (14), OLLAMA_URL, OLLAMA_MODEL (qwen3:1.7b), SECRET_KEY, DEBUG, ALLOWED_HOSTS,
DB_NAME / DB_USER / DB_PASSWORD / DB_HOST for PostgreSQL (also `pip install psycopg2-binary`).

## Deploying on AWS
One EC2 instance (8 GB RAM) running gunicorn + nginx, Ollama on the same machine, optional RDS PostgreSQL and S3 for uploaded files.
Build the frontend with `npm run build` and serve `frontend/dist` from nginx, proxying `/api/` and `/media/` to gunicorn.

## Data Analytics (Apache Spark)
Managers get a **Data Analytics** page. Opening the page starts the PySpark job in the background when needed; the page polls its status and then
shows charts and tables. Page views only read saved results, so no Spark session is started per request.

Jobs: employee-wise recovery, monthly recovery trend, case status analysis, recovery performance (by claim size and insurer), delayed-case analytics.

    Run analytics -> Django (analytics/runner.py) -> PySpark job (analytics/spark_jobs.py) -> Parquet + results.json -> Django API -> React

Setup:

    # JDK 17 must be installed and JAVA_HOME set (java -version). Newer Java (23+) does not work with Spark.
    cd backend
    pip install -r requirements-spark.txt
    python manage.py seed_history          # optional: ~150 historical cases so there is 12 months of data
    python manage.py run_spark_analytics   # optional: run the job manually instead of from the page

Data source:
- SQLite (local): Django exports the tables to JSON files and Spark reads them.
- PostgreSQL / RDS (when DB_NAME is set): Spark reads the tables over JDBC. The PostgreSQL JDBC driver is downloaded automatically,
  or set SPARK_JDBC_JAR to a local driver file when the server has no internet access.
- Output is written to `backend/analytics_data/output/` (Parquet folders plus results.json).
- Other settings: SPARK_MASTER (default local[*]), SPARK_SOURCE (auto, export or jdbc).
- On Windows, writing Parquet needs Hadoop winutils; if it is missing the charts still work and the page notes that Parquet was not saved.
  Running on Linux, WSL or EC2 avoids this.

## Spark speed
The first run starts a Spark worker process (20-60 s for the JVM). The worker then stays warm for 5 minutes of inactivity (SPARK_WORKER_IDLE_MIN), so later runs
only do the calculations. Each result is also cached so it is computed once instead of twice, and Spark is configured for single-machine use
(few partitions, no web UI, loopback address). Set SPARK_WORKER=0 to run one process per job, SPARK_WRITE_PARQUET=0 to skip Parquet output.

## RAG: evidence search (Sentence Transformers + ChromaDB + Qwen3)
Staff questions are answered from the case's own documents and records instead of a fixed prompt.

    question -> embed (Sentence Transformers) -> ChromaDB similarity search -> top passages -> Qwen3 answers with [1][2] references

Indexed per case: document text and AI summaries, the evidence checklist, case facts, activity log, third-party insurer updates and payments.
A case is re-indexed automatically when something about it changes (new upload, activity, payment).

    cd backend
    pip install -r requirements-rag.txt
    python manage.py rag_index        # optional: build the whole index up front (first run downloads the embedding model, ~90 MB)

- **Evidence search** page (manager and employee): ask across cases; mention an ID like SUB-1003 to focus on one case.
- Case **AI assistant** tab: answers use retrieval by default (checkbox to switch back) and list their sources.
- If the RAG packages are not installed, the assistant falls back to the standard answer. Clients keep the existing client assistant.
- Settings: RAG_EMBED_MODEL (model name or local folder, for offline servers), RAG_TOP_K (default 6). The index lives in `backend/rag_store/`.

## When Spark runs (Data Analytics)
- Spark runs **only when a manager opens the Data Analytics page**. Nothing runs in the background otherwise, and the warm worker shuts itself down after 5 idle minutes.
- On opening, the previous results show immediately. Spark re-runs only if the case data changed since the last run (status, assignment, amounts,
  third party, payments or activity); otherwise it does nothing.
- While the page stays open it checks for data changes every few seconds, so editing or reassigning a case elsewhere refreshes the analytics automatically.
- **Refresh now** forces a re-run and **Stop** cancels a running job. A job that dies or runs longer than 10 minutes (SPARK_JOB_TIMEOUT_S) is marked failed
  with the reason instead of staying on "running".

## Spark: speed and troubleshooting
- Use **JDK 17**. Java 23+ breaks Spark, and PySpark 4.x needs Java 17+. The page checks Java, PySpark and Python versions first and tells you what to fix.
- `python manage.py check_spark` prints the versions and runs a tiny Spark job with timings. Run it first if the page reports a failure.
- Start-up of the Spark engine is the slow part (about 10-30 s, once). It then stays warm for 5 idle minutes, so repeat runs take a few seconds.
  The Spark settings are tuned for small data (2 partitions, no web UI, no code generation or adaptive planning, ANSI mode off, loopback address, light JVM flags).
- Parquet is written with pyarrow, so no Hadoop/winutils is needed on Windows. Set SPARK_WRITE_PARQUET=0 to skip it.
- If Spark does not start within 150 s (SPARK_STARTUP_TIMEOUT_S) or a job exceeds 10 min (SPARK_JOB_TIMEOUT_S), it is stopped and the reason is shown.
- PostgreSQL mode: set SPARK_JDBC_JAR to a downloaded postgresql driver `.jar` so Spark does not need internet access at start-up.
