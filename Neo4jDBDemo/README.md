# Project SENTINEL – Supabase to Neo4j Graph ETL

This project loads transaction and reference data from Supabase into Neo4j for graph-based fraud analysis.

The ETL script creates:

- `Customer`, `Device`, and `Merchant` nodes
- `USED_DEVICE` relationships between customers and devices
- `PAID` relationships between customers and merchants
- Transaction-level relationship properties, including transaction ID, timestamp, amount, and fraud label

The loader uses Neo4j `MERGE` operations and uniqueness constraints so that rerunning the ETL does not create duplicate entities or transaction relationships, provided the same IDs are used.

---

## 1. Prerequisites

Install or have access to:

- Python 3.10 or later
- Docker Desktop
- Git
- A Supabase project with the required tables
- A Neo4j-compatible database (the instructions below use Neo4j in Docker)

The ETL expects these Supabase tables:

- `transactions`
- `labels`
- `customers`
- `devices`
- `merchants`

Make sure the table and column names in Supabase match the names expected by the Python script.

## 2. Project files

A typical project structure:

```text
Neo4jDBDemo/
├── load_sentinal_graph.py
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
└── README.md
```

If your Python script has a different filename, use that filename in the run command below.

## 3. Configure environment variables

The application reads credentials and connection details from environment variables. Do not hard-code secrets in Python files, Docker Compose files, or documentation.

Create a local `.env` file in the project root. Use `.env.example` as the template.

Example `.env.example`:

```dotenv
# Supabase
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_KEY=YOUR_SUPABASE_ANON_OR_SERVICE_ROLE_KEY

# Neo4j
# Use bolt://localhost:7687 when Python runs on your Windows host
# and Neo4j runs in Docker with port 7687 published.
NEO4J_URI=bolt://localhost:7687
NEO4JUSER=neo4j
NEO4JPASSWORD=CHANGE_ME

# Optional: number of transactions to load.
# Use 5000 to load 5,000 transactions.
# Use 0 to load all available transactions.
TRANSACTION_LIMIT=5000
```

Copy the example file to `.env`:

**PowerShell**

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholders with your actual Supabase and Neo4j credentials.

> **Security:** Never commit `.env`, API keys, database passwords, or service-role keys. Keep `.env.example` committed with placeholders only. A Supabase service-role key has elevated permissions; protect it and never expose it in frontend code or public repositories.

## 4. Configure Git to ignore secrets

Add the following entries to `.gitignore`:

```gitignore
# Secrets and local environment
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Local/editor files
.vscode/
.idea/

# Logs
*.log
```

If `.env` was already tracked by Git, adding it to `.gitignore` is not enough. Remove it from Git tracking (without deleting your local file):

```bash
git rm --cached .env
```

If a real key or password was committed previously, rotate/revoke it in the relevant service. Removing it from the latest commit does not make the exposed credential safe.

## 5. Start Neo4j with Docker Compose

The `docker-compose.yml` file can use the official Neo4j image:

```yaml
services:
  neo4j:
    image: neo4j:5
    container_name: neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/CHANGE_ME
    volumes:
      - neo4j-data:/data

volumes:
  neo4j-data:
```

Use the same Neo4j password in the Compose configuration and in `.env`. For a personal/local development setup, replace `CHANGE_ME` with a strong local password. Do not commit a real production password in the Compose file; for shared or production environments, inject it through a protected environment or secrets manager.

From the project root, start the container:

```bash
docker compose up -d
```

The Compose file uses the prebuilt official Neo4j image, so `docker compose build` is not required.

Check that the container is running:

```bash
docker ps
```

View Neo4j logs if needed:

```bash
docker compose logs -f neo4j
```

Open Neo4j Browser:

- URL: http://localhost:7474
- Username: `neo4j`
- Password: the password configured in `docker-compose.yml`

You can test the connection in Neo4j Browser:

```cypher
RETURN "Neo4j is running" AS status;
```

## 6. Install Python dependencies

It is recommended to use a virtual environment.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

Install the required packages:

```bash
python -m pip install --upgrade pip
pip install supabase neo4j python-dotenv
```

If the repository has a `requirements.txt`, install from it instead:

```bash
pip install -r requirements.txt
```

## 7. Run the ETL script

Make sure:

1. Docker Desktop is running.
2. The Neo4j container is running (`docker ps`).
3. `.env` exists and contains valid Supabase and Neo4j settings.
4. The Supabase tables are accessible using the configured key.

Run the script from the project root:

```bash
python load_sentinal_graph.py
```

The script should report its Supabase and Neo4j connections, number of records fetched, node and relationship counts, and a load summary.

If your script is named `load_sentinel_graph.py` (with the spelling `sentinel`), run:

```bash
python load_sentinel_graph.py
```

### Transaction limit

The optional `TRANSACTION_LIMIT` variable controls how many transactions are loaded:

```dotenv
TRANSACTION_LIMIT=5000
```

To load all available transactions, set:

```dotenv
TRANSACTION_LIMIT=0
```

Check the loader's implementation before using `0` on a large dataset, and ensure your Neo4j instance has sufficient resources.

## 8. Verify the graph in Neo4j

In Neo4j Browser, check node counts:

```cypher
MATCH (n)
RETURN labels(n) AS node_type, count(n) AS total
ORDER BY node_type;
```

Check relationship counts:

```cypher
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(r) AS total;
```

Inspect fraud-labelled payments:

```cypher
MATCH (c:Customer)-[p:PAID]->(m:Merchant)
WHERE p.fraud_label = 1
RETURN c, p, m
LIMIT 100;
```

## 9. Useful Docker commands

| Task | Command |
|---|---|
| Start Neo4j in the background | `docker compose up -d` |
| Check running containers | `docker ps` |
| Follow Neo4j logs | `docker compose logs -f neo4j` |
| Stop Neo4j | `docker compose stop` |
| Start a stopped container | `docker compose start` |
| Restart Neo4j | `docker compose restart neo4j` |
| Stop and remove the container/network | `docker compose down` |
| Stop and delete the named data volume too | `docker compose down -v` |

**Warning:** `docker compose down -v` deletes the `neo4j-data` volume and therefore removes the persisted Neo4j database. Do not use it unless you intentionally want to delete the graph data.

## 10. Troubleshooting

### Python cannot connect to Neo4j

When Python runs directly on Windows and Neo4j runs in Docker with port `7687` published, use:

```dotenv
NEO4J_URI=bolt://localhost:7687
```

Confirm that the container is running and that port `7687` is published:

```bash
docker ps
```

### Neo4j Browser is unavailable

Check the container and logs:

```bash
docker ps
docker compose logs --tail=100 neo4j
```

Then try http://localhost:7474 again.

### Authentication failed

Confirm that `NEO4JUSER` and `NEO4JPASSWORD` in `.env` match the credentials configured when the Neo4j database was first initialized. Changing `NEO4J_AUTH` on an existing container with a persisted `/data` volume does not necessarily reset the existing database password.

### Supabase authentication or table errors

Verify `SUPABASE_URL`, `SUPABASE_KEY`, table names, permissions, and the columns expected by the ETL script. Do not paste credentials into issue reports or commit them to the repository.

---

## Security checklist

- [ ] `.env` contains real credentials locally and is ignored by Git.
- [ ] `.env.example` contains placeholders only.
- [ ] `.gitignore` excludes `.env` and other local secret files.
- [ ] No Supabase keys or Neo4j passwords are hard-coded in source files.
- [ ] No credentials are included in screenshots, logs, or public issue reports.
- [ ] Any credential accidentally committed or shared has been rotated.

## Notes

- This setup is intended for local development and learning.
- The graph loader is designed to be rerun safely using `MERGE` and stable IDs. If source records are updated, confirm that the ETL updates the corresponding Neo4j properties as intended.
- Shared-device patterns are investigation signals, not proof of fraud. Interpret them alongside transaction labels and other evidence.
