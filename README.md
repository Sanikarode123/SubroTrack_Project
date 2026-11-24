# SubroTrack – AI-Driven Insurance Subrogation Management System

## Overview

SubroTrack is a web-based application developed to manage and track insurance subrogation recovery cases after a claim has been identified for recovery. It provides a centralized platform for case management, employee coordination, document handling, third-party insurer tracking and recovery analytics.

The system also integrates a locally hosted AI model and a Retrieval-Augmented Generation (RAG) pipeline to assist users in retrieving information from insurance documents and case records. Apache Spark is used to process recovery-related data and generate analytical insights.

## Features

- **Case Management:** Register, import, assign and manage insurance recovery cases.
- **Role-Based Access:** Separate dashboards and permissions for Managers, Employees and Clients.
- **AI Assistant:** Get AI-powered assistance using Qwen3 1.7B through Ollama.
- **Document Intelligence:** Extract text, generate summaries and identify key information from uploaded documents.
- **RAG-Based Evidence Search:** Retrieve relevant information from case documents and records to answer user queries.
- **Follow-up Management:** Track follow-ups, identify delayed cases and generate AI-assisted reports.
- **Third-Party Tracking:** Maintain insurer responses, claimed amounts and recovered amounts.
- **Recovery Analytics:** Analyze recovery trends, employee performance, case status and insurer-wise performance using Apache Spark.
- **Client Portal:** Allow clients to track recovery progress, view missing documents, upload files and ask questions about their cases.

## User Roles

| Role | Permissions and Responsibilities |
|---|---|
| Manager | Full system access. Can register and import cases, assign employees, link clients, close cases, create user logins and monitor team performance. |
| Employee | Accesses assigned cases, updates statuses and follow-ups, records third-party responses and payments, reviews documents and uses AI assistance. |
| Client | Views their own recovery cases, tracks progress and financial details, checks missing documents, uploads documents and asks questions about their claims. |

Client-uploaded documents are automatically processed. The system extracts text, generates summaries, identifies important details and performs content checks. The processed information becomes available to Managers and Employees through the case Documents tab and dashboard. The case AI assistant can also use these extracted details when answering staff queries.

## Main Modules

1. **Case Registration and Import:** Register cases individually or import them through CSV/XLSX files. Only claims marked `subrogation_potential = Yes` are added.
2. **Case Status Workflow:** Manage case statuses and maintain a history of status changes.
3. **Follow-up Management:** Generate rule-based reminders and detect delayed cases, with an AI-generated report to support follow-up activities.
4. **Document Management:** Maintain document checklists and analyze PDF documents using PyMuPDF and Qwen3.
5. **Third-Party Tracking:** Record insurer responses for each case and maintain insurer-wise claimed versus recovered amounts.
6. **AI Case Assistant:** Provide case summaries and question-answering functionality for staff and clients.
7. **Dashboard and Analytics:** Display recovery amounts, case information and employee-wise performance.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React.js, Tailwind CSS |
| Backend | Python, Django, Django REST Framework |
| Database | SQLite, PostgreSQL |
| AI Runtime | Ollama |
| Language Model | Qwen3 1.7B |
| RAG Framework | Sentence Transformers, ChromaDB |
| Document Processing | PyMuPDF |
| Big Data Processing | Apache Spark, PySpark |
| Data Output | Parquet, JSON |
| Communication | REST APIs |

## AI and Document Intelligence

### 1. Ollama and Qwen3 1.7B

Ollama is used to run the Qwen3 1.7B language model locally. The Django backend communicates with Ollama to send prompts and receive generated responses.

The model supports:
- AI-powered case assistance.
- Case summaries and contextual responses.
- Document analysis and extraction of important details.
- Question answering using retrieved case information.

Running the model locally reduces dependency on paid external LLM APIs.

### 2. Retrieval-Augmented Generation (RAG)

SubroTrack uses RAG to answer questions using information from individual insurance cases rather than relying only on the language model's general knowledge.

The RAG pipeline uses Sentence Transformers, ChromaDB and Qwen3 1.7B.

**How it works:**

```text
User Question
     |
     v
Sentence Transformers
(Generate Query Embeddings)
     |
     v
ChromaDB
(Similarity Search)
     |
     v
Retrieve Relevant Passages
     |
     v
Qwen3 1.7B through Ollama
     |
     v
Context-Aware Answer
with Source References
```

The system indexes the following information for each case:
- Extracted document text and AI-generated summaries.
- Evidence checklist.
- Case details and important facts.
- Activity and follow-up history.
- Third-party insurer updates and payment information.

The index is automatically updated when relevant case information changes, such as a new document upload, activity entry or payment.

**RAG functionality:**
- The Evidence Search page allows Managers and Employees to search across cases.
- Users can mention a case ID, such as `SUB-1003`, to focus their search on a particular case.
- The Case AI Assistant uses document retrieval by default and displays relevant source references.
- Users can switch back to standard AI responses when required.
- If RAG dependencies are unavailable, the assistant falls back to standard responses. The existing client assistant remains available.

### 3. Apache Spark and PySpark Analytics

Apache Spark is used to process insurance recovery-related data and generate analytical results for the Manager's Data Analytics dashboard.

PySpark is used to implement the analytics jobs in Python.

**Analytics generated:**
- Employee-wise recovery performance.
- Monthly recovery trends.
- Case status analysis.
- Recovery performance by claim size and insurer.
- Delayed-case analytics.

**Analytics execution workflow:**

```text
Manager Opens Data Analytics
           |
           v
      Django Backend
           |
           v
   Analytics Runner
   (runner.py)
           |
           v
   PySpark Analytics Job
   (spark_jobs.py)
           |
           v
  Process and Analyze Data
           |
           v
    Parquet + results.json
           |
           v
       Django API
           |
           v
    React Dashboard
```

**How Spark runs:**

- Spark jobs start when a Manager opens the Data Analytics page and analytics need to be generated.
- Previous results are displayed immediately when available.
- Analytics are recalculated only when relevant case data changes.
- The page periodically checks for data changes while it remains open.
- A Refresh Now option forces a new analytics run, while Stop cancels a running job.
- Spark results are saved and reused instead of recalculating them on every page request.

### Spark Data Sources

| Database | Processing Method |
|---|---|
| SQLite | Django exports database tables into JSON files, which Spark reads for processing. |
| PostgreSQL / RDS | Spark reads database tables through JDBC. |

The analytics output is stored in:

```text
backend/analytics_data/output/
```

This directory contains Parquet output folders and `results.json`.

### Spark Performance and Configuration

- A Spark worker process starts when required and stays active for five minutes of inactivity by default.
- Subsequent jobs reuse the running worker to reduce startup overhead.
- Analytics results are cached to avoid unnecessary duplicate calculations.
- Spark is configured for single-machine processing using `local[*]` by default.
- `SPARK_WORKER=0` disables the persistent worker and runs one process per job.
- `SPARK_WRITE_PARQUET=0` disables Parquet output.
- `SPARK_WORKER_IDLE_MIN` controls the worker's idle timeout.
- `SPARK_STARTUP_TIMEOUT_S` controls the Spark startup timeout.
- `SPARK_JOB_TIMEOUT_S` controls the maximum job execution time.
- `SPARK_MASTER` configures the Spark master.
- `SPARK_SOURCE` controls the data source (`auto`, `export` or `jdbc`).

Parquet output uses PyArrow, so Hadoop winutils is not required for the configured Windows setup.

## Project Structure

```text
SubroTrack/
│
├── backend/
│   ├── analytics/
│   │   ├── runner.py
│   │   ├── spark_jobs.py
│   │   ├── spark_worker.py
│   │   └── store.py
│   │
│   ├── cases/
│   │   ├── management/
│   │   ├── migrations/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── rag/
│   │   ├── engine.py
│   │   └── views.py
│   │
│   ├── subrotrack/
│   ├── requirements.txt
│   ├── requirements-rag.txt
│   ├── requirements-spark.txt
│   └── manage.py
│
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.js
│
├── sample_accident_report.txt
├── sample_claims_mixed.csv
├── sample_import.csv
├── README.md
└── .gitignore
```

## Installation and Setup

### Prerequisites

Install the following before running the project:

- Python and pip.
- Node.js and npm.
- Git.
- Ollama.
- Java Development Kit (JDK 17) for Spark analytics.
- PostgreSQL (only if using PostgreSQL instead of SQLite).

### 1. Clone the Repository

```bash
git clone https://github.com/Sanikarode123/SubroTrack_Project.git

cd SubroTrack_Project
```

### 2. Install and Start Ollama

Install Ollama from https://ollama.com/download.

Pull the Qwen3 model:

```bash
ollama pull qwen3:1.7b
```

Start the Ollama service if it is not already running:

```bash
ollama serve
```

Ollama normally runs locally at:

```text
http://localhost:11434
```

### 3. Backend Setup

Open a terminal in the project root:

```bash
cd backend
```

Create a Python virtual environment:

```bash
python -m venv venv
```

Activate the environment on Windows:

```powershell
venv\Scripts\activate
```

For Mac/Linux:

```bash
source venv/bin/activate
```

Install the core backend dependencies:

```bash
pip install -r requirements.txt
```

Install RAG dependencies:

```bash
pip install -r requirements-rag.txt
```

Install Spark dependencies:

```bash
pip install -r requirements-spark.txt
```

Run database migrations:

```bash
python manage.py migrate
```

Load sample data:

```bash
python manage.py seed
```

Start the Django development server:

```bash
python manage.py runserver
```

The backend will be available at:

```text
http://127.0.0.1:8000/
```

**Note:** The project already contains migration files. Do not delete the migrations folder when performing a normal installation or upgrade. Deleting the local database is only appropriate when intentionally resetting local development data.

### 4. Frontend Setup

Open another terminal in the project root:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the frontend:

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

Open the URL in your browser and select the appropriate role.

### 5. Spark Configuration

Spark analytics requires JDK 17.

Verify the Java installation:

```bash
java -version
```

Make sure `JAVA_HOME` points to your JDK 17 installation.

To check Spark compatibility and run a small test:

```bash
cd backend

python manage.py check_spark
```

Optionally, load historical sample cases:

```bash
python manage.py seed_history
```

Run analytics manually:

```bash
python manage.py run_spark_analytics
```

Normally, Spark analytics starts automatically when a Manager opens the Data Analytics page and a recalculation is required.

For PostgreSQL mode, configure the PostgreSQL JDBC driver using `SPARK_JDBC_JAR` if necessary. The driver can otherwise be downloaded automatically.

### 6. RAG Configuration

Install the RAG dependencies from the backend directory:

```bash
pip install -r requirements-rag.txt
```

Optionally, build the complete document index in advance:

```bash
python manage.py rag_index
```

On the first run, Sentence Transformers downloads the embedding model (approximately 90 MB). For offline environments, configure `RAG_EMBED_MODEL` with a local model folder.

The RAG index is stored in:

```text
backend/rag_store/
```

Additional configuration:

- `RAG_EMBED_MODEL`: Embedding model name or local model directory.
- `RAG_TOP_K`: Number of relevant passages retrieved per query (default: 6).

## Configuration

The application supports environment variables for application settings, AI integration and database configuration.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Django debug mode |
| `ALLOWED_HOSTS` | Allowed application hosts |
| `DELAY_THRESHOLD_DAYS` | Number of days used for delayed-case detection (default: 14) |
| `OLLAMA_URL` | Ollama service URL |
| `OLLAMA_MODEL` | Language model name (default: `qwen3:1.7b`) |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL username |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host |
| `RAG_EMBED_MODEL` | RAG embedding model |
| `RAG_TOP_K` | Number of retrieved passages |
| `SPARK_MASTER` | Spark master configuration |
| `SPARK_SOURCE` | Spark data source selection |
| `SPARK_JDBC_JAR` | PostgreSQL JDBC driver path |

For PostgreSQL support, install:

```bash
pip install psycopg2-binary
```

Use your own environment-specific values. Never commit real passwords, API keys or production secrets to GitHub.

## Demo Login Credentials

The following accounts are created by the database seed command for local development and demonstration.

**For local development and demonstration only. Do not use these credentials in production.**

| Username | Demo Password | Role |
|---|---|---|
| manager | manager123 | Manager |
| priya, amit | pass1234 | Employee |
| rahul, sneha, vikram | pass1234 | Client |

## Troubleshooting

**Ollama is not responding**

- Check whether Ollama is installed and running.
- Run `ollama list` to verify that `qwen3:1.7b` is available.
- Check the configured `OLLAMA_URL`.

**RAG is not working**

- Verify that the RAG dependencies are installed.
- Run `python manage.py rag_index` to build the index.
- Check that the embedding model is available.
- Verify the `backend/rag_store/` directory.

**Spark fails to start**

- Verify that JDK 17 is installed.
- Check `JAVA_HOME` and `java -version`.
- Run `python manage.py check_spark` to identify compatibility issues.
- For PostgreSQL, verify the JDBC driver configuration.
- Check Spark startup and job timeout settings.

**Analytics are not updating**

- Check whether case data has changed.
- Use Refresh Now on the Data Analytics page.
- Check the Spark worker and analytics job status.

## Future Enhancements

- Improved recovery prediction and prioritization.
- Advanced AI-powered document analysis.
- Additional recovery performance metrics.
- Automated workflow optimization.
- Enhanced reporting and analytics.

## Author

**Sanika Rode**

GitHub: https://github.com/Sanikarode123
