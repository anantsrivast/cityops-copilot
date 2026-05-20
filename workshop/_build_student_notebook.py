"""Generator for notebook_student.ipynb (CityOps Copilot workshop).

Run from this directory:
    python3 _build_student_notebook.py

Produces a Jupyter notebook with 6 TODOs across Parts 2–6.
"""

import json
from pathlib import Path

CELLS = []


def md(src: str):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": src})


def code(src: str):
    CELLS.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": src,
    })


# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────

md("# CityOps Copilot — Agent Memory Workshop")

md(
    "An inspector / city-operations copilot that remembers every asset's "
    "history across inspectors. By the end, a new inspector will encounter a "
    "corrosion concern on Harbor Bridge and the copilot will already know what "
    "the prior inspector observed, recommended, and graded — without anyone "
    "telling it.\n\n"
    "Built on Oracle AI Database + the `oracleagentmemory` SDK, seeded with a "
    "realistic dataset of 308 maintenance logs and ~220 inspection findings "
    "across 26 urban infrastructure assets (bridges, substations, pipelines, "
    "water treatment, sensors, comms towers, seawalls).\n\n"
    ">  Open `docs/overview.md` for the one-pager."
)

md(
    "## What You'll Build\n\n"
    "An agent that uses **four memory layers** simultaneously:\n\n"
    "| Layer | What it stores | How it's populated |\n"
    "|---|---|---|\n"
    "| Auto-extracted `fact` / `preference` / `guideline` (SDK) | Inspector tribal knowledge from maintenance narratives | SDK's extractor runs on every event report |\n"
    "| `CITY_ASSET` (hand-rolled SQL) | The plant's asset registry — 26 assets from real data | Bulk-loaded from `data/maintenance_logs.json` + `data/inspection_reports.json` |\n"
    "| `CITY_INSPECTION_FINDING` (hand-rolled SQL with `VECTOR(384)`) | Structured findings — category, severity, description, recommendation, grade | ~220 findings bulk-loaded from `data/inspection_reports.json` |\n"
    "| Conversational messages (SDK) | Per-asset inspection threads, naturally scoped to the asset | `thread.add_messages` |\n\n"
    ">  **Two storage layers?** The SDK only allows 4 native record types "
    "(`fact`, `memory`, `preference`, `guideline`). Domain objects need their "
    "own SQL tables. Oracle's converged engine makes this clean — same "
    "connection, vector search via `VECTOR_DISTANCE()` available everywhere. "
    "See `docs/sdk-data-model.md`."
)

md(
    "## Select Your Kernel\n\n"
    "**Step 1.** Click **Select Kernel** in the top-right.\n\n"
    "**Step 2.** Choose **CityOps Copilot** (or Python 3.11).\n\n"
    "If you don't see the kernel, wait for the Codespace setup to complete."
)

code(
    "# Dependencies are pre-installed in this Codespace via .devcontainer/setup.sh\n"
    "# If you are running locally, uncomment the next line:\n"
    "# ! pip install -qU oracleagentmemory sentence-transformers oracledb openai matplotlib"
)

# ────────────────────────────────────────────────────────────────────────────
# Part 1 — Oracle Setup
# ────────────────────────────────────────────────────────────────────────────

md("# Part 1: Oracle Setup")

md(
    "Oracle AI Database is reachable in one of two ways:\n\n"
    "- **Codespaces (default):** Oracle Free runs as a Docker service alongside "
    "the dev container — `localhost:1521`, service `FREEPDB1`, user `VECTOR`.\n"
    "- **Local dev against ADB:** drop a `.env` file in the project root with "
    "your wallet path and ADB credentials; the next cell loads it.\n\n"
    "Either way, the SDK creates its tables under prefix `CITY_` in Part 2."
)

code(
    "# Load environment from a project-root .env (no-op if missing — Codespaces path).\n"
    "# Keeps the notebook portable across local-dev (ADB+wallet), Codespaces (local Oracle\n"
    "# Free), and headless nbconvert runs without depending on the VS Code Python extension.\n"
    "import os\n"
    "from pathlib import Path\n"
    "\n"
    "_env_file = next((p for p in (Path(\".env\"), Path(\"../.env\")) if p.exists()), None)\n"
    "if _env_file is not None:\n"
    "    for _line in _env_file.read_text().splitlines():\n"
    "        _line = _line.strip()\n"
    "        if not _line or _line.startswith(\"#\") or \"=\" not in _line:\n"
    "            continue\n"
    "        _k, _v = _line.split(\"=\", 1)\n"
    "        # .setdefault — env vars already set externally (Codespaces secrets) win.\n"
    "        os.environ.setdefault(_k.strip(), _v.strip().strip('\"').strip(\"'\"))\n"
    "    print(f\" Loaded env vars from {_env_file.resolve()}\")\n"
    "else:\n"
    "    print(\"ℹ No .env file found — assuming env vars are set externally\")\n"
    "\n"
    "if os.environ.get(\"ORACLE_WALLET_LOCATION\"):\n"
    "    print(f\"  mode: ADB / wallet  ({os.environ.get('ORACLE_DSN','<DSN missing>')[:60]}...)\")\n"
    "else:\n"
    "    print(\"  mode: local (Codespaces / Oracle Free on localhost:1521)\")"
)

code(
    "import oracledb, os, time\n"
    "\n"
    "def connect_to_oracle(max_retries=3, retry_delay=5,\n"
    "                     program=\"cityops_copilot\"):\n"
    "    \"\"\"Connect to Oracle (ADB+wallet if ORACLE_WALLET_LOCATION set, else local).\"\"\"\n"
    "    wallet_dir = os.environ.get(\"ORACLE_WALLET_LOCATION\")\n"
    "    if wallet_dir:\n"
    "        kwargs = dict(\n"
    "            user=os.environ[\"ORACLE_USER\"],\n"
    "            password=os.environ[\"ORACLE_PASSWORD\"],\n"
    "            dsn=os.environ[\"ORACLE_DSN\"],\n"
    "            config_dir=wallet_dir,\n"
    "            wallet_location=wallet_dir,\n"
    "            wallet_password=os.environ.get(\"ORACLE_WALLET_PASSWORD\", \"\"),\n"
    "            program=program,\n"
    "        )\n"
    "        mode = f\"ADB ({os.environ['ORACLE_DSN'][:50]}...)\"\n"
    "    else:\n"
    "        kwargs = dict(\n"
    "            user=os.environ.get(\"ORACLE_USER\", \"VECTOR\"),\n"
    "            password=os.environ.get(\"ORACLE_PASSWORD\", \"VectorPwd_2025\"),\n"
    "            dsn=os.environ.get(\"ORACLE_DSN\", \"localhost:1521/FREEPDB1\"),\n"
    "            program=program,\n"
    "        )\n"
    "        mode = f\"local ({kwargs['dsn']})\"\n"
    "\n"
    "    for attempt in range(1, max_retries + 1):\n"
    "        try:\n"
    "            print(f\"Connection attempt {attempt}/{max_retries} — {mode}...\")\n"
    "            conn = oracledb.connect(**kwargs)\n"
    "            print(f\" Connected as {kwargs['user']}.\")\n"
    "            return conn\n"
    "        except oracledb.OperationalError as e:\n"
    "            print(f\" {e}\")\n"
    "            if attempt < max_retries:\n"
    "                time.sleep(retry_delay)\n"
    "            else:\n"
    "                raise\n"
    "    raise ConnectionError(\"Could not connect.\")"
)

code(
    "vector_conn = connect_to_oracle()\n"
    "print(\"Using user:\", vector_conn.username)"
)

md(
    " Connected. Next: wire up the SDK's embedder + create the schema.\n\n"
    ">  **Key insight — Part 1:** Oracle AI Database is a converged engine. "
    "The SDK's tables, our hand-rolled `CITY_ASSET` / `CITY_INSPECTION_FINDING` "
    "tables, and any other SQL all live on this same connection. Vector search "
    "via `VECTOR_DISTANCE()` works across all of them."
)

# ────────────────────────────────────────────────────────────────────────────
# Optional Reset (between Part 1 and Part 2)
# ────────────────────────────────────────────────────────────────────────────

md(
    "###  Optional: Reset The Workspace\n\n"
    "If you've run this workshop before (or are sharing an Oracle instance with "
    "someone who has), the SDK's tables (`CITY_THREAD`, `CITY_MESSAGE`, "
    "`CITY_MEMORY`, `CITY_RECORD_CHUNKS`, `CITY_ACTOR_PROFILE`) and the "
    "workshop's custom tables (`CITY_ASSET`, `CITY_INSPECTION_FINDING`) may "
    "still hold state from prior runs.\n\n"
    "Why this matters: when you call `report_event(\"smoke_thread\", ...)` in "
    "TODO 2, the SDK does `get_thread(\"smoke_thread\")` first — and will pick "
    "up an existing thread from a previous run, **appending** the new message "
    "to whatever's already there instead of starting fresh.\n\n"
    "**Run the cell below to wipe everything CITY_*, then re-run from Part 2.** "
    "If you've already initialised the SDK (`memory = OracleAgentMemory(...)`) "
    "in Part 2, you'll need to **restart the kernel** after this reset — the "
    "in-memory `memory` and `thread` objects still reference the dropped tables.\n\n"
    "Skip this cell on the first-ever run."
)

code(
    "# Optional: wipe all CITY_* tables for a clean slate.\n"
    "# Safe to run multiple times; safe to skip.\n"
    "_to_drop = (\n"
    "    # Drop the hand-rolled tables first (they have FKs into CITY_ASSET).\n"
    "    \"CITY_INSPECTION_FINDING\", \"CITY_ASSET\",\n"
    "    # Then the SDK's tables (FK-cascaded in this order).\n"
    "    \"CITY_MEMORY\", \"CITY_MESSAGE\", \"CITY_RECORD_CHUNKS\",\n"
    "    \"CITY_THREAD\", \"CITY_ACTOR_PROFILE\",\n"
    "    \"CITY_ORACLEAGENTMEMORY_SCHEMA_META\",\n"
    ")\n"
    "with vector_conn.cursor() as cur:\n"
    "    for t in _to_drop:\n"
    "        try:\n"
    "            cur.execute(f'DROP TABLE \"{t}\" CASCADE CONSTRAINTS')\n"
    "            print(f\"  dropped {t}\")\n"
    "        except Exception:\n"
    "            pass  # table didn't exist — fine\n"
    "vector_conn.commit()\n"
    "print(\"\\n Workspace clean. RESTART THE KERNEL before re-running Part 2 if you've already done it.\")"
)

# ────────────────────────────────────────────────────────────────────────────
# Part 2 — Embedder + SDK Init
# ────────────────────────────────────────────────────────────────────────────

md("# Part 2: The Embedder and SDK")

md(
    "The SDK handles vectorisation and search — but needs an embedder plug-in. "
    "You'll provide a local `sentence-transformers` model (384-dim, no API key, "
    "no per-call cost).\n\n"
    "**TODO 1: Implement `LocalSentenceTransformerEmbedder`.**\n\n"
    "1. Subclass `IEmbedder`.\n"
    "2. Hold a `SentenceTransformer` instance from `\"sentence-transformers/all-MiniLM-L6-v2\"`.\n"
    "3. `embed` returns `model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)`.\n"
    "4. `embed_async` runs `embed` on a thread via `asyncio.to_thread`."
)

code(
    "from oracleagentmemory.apis.embedders.embedder import IEmbedder\n"
    "from sentence_transformers import SentenceTransformer\n"
    "import numpy as np\n"
    "import asyncio\n"
    "\n"
    "\n"
    "class LocalSentenceTransformerEmbedder(IEmbedder):\n"
    "    \"\"\"Bridges sentence-transformers to the SDK's IEmbedder.\"\"\"\n"
    "\n"
    "    def __init__(self, model_name: str = \"sentence-transformers/all-MiniLM-L6-v2\"):\n"
    "        # TODO 1: load the model into self.model\n"
    "        # YOUR CODE HERE\n"
    "        pass\n"
    "\n"
    "    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:\n"
    "        # TODO 1: encode with normalize_embeddings=True; return float32\n"
    "        # YOUR CODE HERE\n"
    "        pass\n"
    "\n"
    "    async def embed_async(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:\n"
    "        # TODO 1: run self.embed on a thread via asyncio.to_thread\n"
    "        # YOUR CODE HERE\n"
    "        pass\n"
)

code(
    "# PASS: Checkpoint: TODO 1\n"
    "embedder = LocalSentenceTransformerEmbedder()\n"
    "_v = embedder.embed([\"corrosion on bearing assembly\"])\n"
    "assert _v.shape == (1, 384), f\"Expected (1, 384), got {_v.shape}\"\n"
    "assert _v.dtype == np.float32, f\"Expected float32, got {_v.dtype}\"\n"
    "print(\"PASS: TODO 1 passed — embedder returns float32 (n, 384) arrays\")"
)

md(
    "### SDK Initialization (Pre-Built)\n\n"
    "Wires up `OracleAgentMemory` and the SDK's internal LLM. No changes needed.\n\n"
    "- `extract_memories=True` turns on automatic LLM extraction of `fact` / "
    "`preference` / `guideline` / `memory` on every `add_messages` call.\n"
    "- `table_name_prefix=\"CITY_\"` namespaces the SDK's tables."
)

code(
    "import os\n"
    "from openai import OpenAI\n"
    "from oracleagentmemory.core import OracleAgentMemory, SchemaPolicy\n"
    "from oracleagentmemory.core.llms.llm import Llm\n"
    "from oracleagentmemory.apis.thread import Message\n"
    "\n"
    "OCI_GENAI_ENDPOINT = os.environ.get(\n"
    "    \"OCI_GENAI_ENDPOINT\",\n"
    "    \"https://inference.generativeai.us-phoenix-1.oci.oraclecloud.com/openai/v1\",\n"
    ")\n"
    "OCI_GENAI_API_KEY = os.environ[\"OCI_GENAI_API_KEY\"]\n"
    "\n"
    "client = OpenAI(base_url=OCI_GENAI_ENDPOINT, api_key=OCI_GENAI_API_KEY)\n"
    "sdk_llm = Llm(\n"
    "    model=\"openai/xai.grok-3-fast\",\n"
    "    api_base=OCI_GENAI_ENDPOINT,\n"
    "    api_key=OCI_GENAI_API_KEY,\n"
    ")\n"
    "\n"
    "memory = OracleAgentMemory(\n"
    "    connection=vector_conn,\n"
    "    embedder=embedder,\n"
    "    llm=sdk_llm,\n"
    "    extract_memories=True,\n"
    "    schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,\n"
    "    table_name_prefix=\"CITY_\",\n"
    ")\n"
    "print(\" OracleAgentMemory ready. Tables under prefix CITY_*\")"
)

# ────────────────────────────────────────────────────────────────────────────
# Part 3 — Asset Registry (from real data) + Auto-Extraction
# ────────────────────────────────────────────────────────────────────────────

md("# Part 3: City Asset Registry + Auto-Extraction")

md(
    "Two pieces in this part:\n\n"
    "1. The **`CITY_ASSET` registry** — 26 real urban infrastructure assets, "
    "loaded from `data/maintenance_logs.json` + `data/inspection_reports.json`. "
    "Hand-rolled SQL table outside the SDK.\n"
    "2. **Auto-extraction from real maintenance narratives** — the SDK's "
    "extractor turns paragraph-long inspection write-ups into typed `fact` / "
    "`preference` / `guideline` records inside `CITY_MEMORY`.\n\n"
    "Both pre-built cells run automatically; the TODOs are the auto-extraction logic."
)

code(
    "# Pre-built: load the real asset registry from the committed JSON files.\n"
    "# The 26 assets are the union of asset_name fields across both datasets.\n"
    "import json\n"
    "from pathlib import Path\n"
    "\n"
    "_data_dir = Path(\"data\") if Path(\"data\").exists() else Path(\"../data\")\n"
    "with open(_data_dir / \"maintenance_logs.json\") as f:\n"
    "    _logs = json.load(f)\n"
    "with open(_data_dir / \"inspection_reports.json\") as f:\n"
    "    _reports = json.load(f)\n"
    "\n"
    "_asset_names = sorted(set(x[\"asset_name\"] for x in _logs) | set(x[\"asset_name\"] for x in _reports))\n"
    "print(f\"Loaded {len(_logs)} maintenance logs, {len(_reports)} inspection reports.\")\n"
    "print(f\"Discovered {len(_asset_names)} unique assets.\")"
)

code(
    "# Pre-built: classify each asset by name heuristics into one of 8 asset classes.\n"
    "def classify_asset(name: str) -> str:\n"
    "    n = name.lower()\n"
    "    if \"bridge\" in n or \"overpass\" in n: return \"bridge\"\n"
    "    if \"substation\" in n:                  return \"substation\"\n"
    "    if \"pipeline\" in n:                    return \"pipeline\"\n"
    "    if \"water\" in n or \"outfall\" in n or \"treatment\" in n: return \"water\"\n"
    "    if \"solar\" in n or \"gas distribution\" in n:           return \"energy\"\n"
    "    if \"sensor\" in n or \"array\" in n or \"monitor\" in n or \"gauge\" in n: return \"sensor\"\n"
    "    if \"tower\" in n or \"relay\" in n:      return \"comms\"\n"
    "    if \"seawall\" in n or \"retaining\" in n or \"booster\" in n: return \"civil\"\n"
    "    return \"other\"\n"
    "\n"
    "equipment = [{\"asset_id\": name, \"asset_class\": classify_asset(name)} for name in _asset_names]\n"
    "from collections import Counter\n"
    "print(\"Asset class distribution:\", dict(Counter(e['asset_class'] for e in equipment)))\n"
    "print(\"\\nFirst 5 assets:\")\n"
    "for e in equipment[:5]:\n"
    "    print(f\"  {e['asset_id']:40} -> {e['asset_class']}\")"
)

code(
    "# Pre-built: create PLANT_ASSET... wait, no — CITY_ASSET — and bulk-INSERT all 26.\n"
    "with vector_conn.cursor() as cur:\n"
    "    try:\n"
    "        cur.execute(\"DROP TABLE CITY_INSPECTION_FINDING CASCADE CONSTRAINTS\")\n"
    "    except Exception:\n"
    "        pass\n"
    "    try:\n"
    "        cur.execute(\"DROP TABLE CITY_ASSET CASCADE CONSTRAINTS\")\n"
    "    except Exception:\n"
    "        pass\n"
    "    cur.execute(\"\"\"\n"
    "        CREATE TABLE CITY_ASSET (\n"
    "            asset_id     VARCHAR2(128) PRIMARY KEY,\n"
    "            asset_class  VARCHAR2(32) NOT NULL,\n"
    "            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
    "        )\n"
    "    \"\"\")\n"
    "    cur.executemany(\n"
    "        \"INSERT INTO CITY_ASSET (asset_id, asset_class) VALUES (:1, :2)\",\n"
    "        [(e[\"asset_id\"], e[\"asset_class\"]) for e in equipment],\n"
    "    )\n"
    "vector_conn.commit()\n"
    "print(f\" Inserted {len(equipment)} rows into CITY_ASSET.\")"
)

code(
    "# Helper: look up one asset row as a dict.\n"
    "def get_asset(asset_id: str) -> dict | None:\n"
    "    with vector_conn.cursor() as cur:\n"
    "        cur.execute(\n"
    "            \"SELECT asset_id, asset_class FROM CITY_ASSET WHERE asset_id = :id\",\n"
    "            id=asset_id,\n"
    "        )\n"
    "        row = cur.fetchone()\n"
    "    if not row:\n"
    "        return None\n"
    "    return {\"asset_id\": row[0], \"asset_class\": row[1]}\n"
    "\n"
    "print(get_asset(\"Harbor Bridge\"))"
)

md(
    "### Auto-Extraction\n\n"
    "When you call `thread.add_messages(...)` with `extract_memories=True`, the "
    "SDK runs its extractor LLM internally. It reads the new message + cached "
    "running summary + past memories, and outputs typed records "
    "(`fact` / `preference` / `guideline` / `memory`) into `CITY_MEMORY`.\n\n"
    "**You don't write the extraction prompt.** The SDK does."
)

md(
    "**TODO 2: Implement `report_event(asset_id, inspector, narrative, thread_id)`.**\n\n"
    "1. **Get-or-create the thread** for this asset:\n"
    "   - Try `memory.get_thread(thread_id)`.\n"
    "   - If it raises or returns None, call `memory.create_thread(user_id=inspector, thread_id=thread_id, agent_id=\"CITY\")`.\n"
    "2. **Build a content string** that includes both asset and inspector — e.g. `f\"[Asset: {asset_id}] [Inspector: {inspector}] {narrative}\"`.\n"
    "3. **Call `thread.add_messages([Message(role=\"user\", content=content)])`** and return the list of message IDs."
)

code(
    "def report_event(asset_id: str, inspector: str, narrative: str, thread_id: str) -> list:\n"
    "    \"\"\"Persist a maintenance event narrative and trigger SDK auto-extraction.\"\"\"\n"
    "    # TODO 2: get-or-create the thread, build the content string,\n"
    "    # add_messages, and return the IDs.\n"
    "    # YOUR CODE HERE\n"
    "    pass\n"
)

code(
    "# PASS: Checkpoint: TODO 2 — smoke test with one real narrative from the dataset\n"
    "_seed = _logs[0]  # First maintenance log — likely Harbor Bridge routine inspection\n"
    "ids = report_event(\n"
    "    asset_id=_seed[\"asset_name\"],\n"
    "    inspector=\"smoke_inspector\",\n"
    "    narrative=_seed[\"narrative\"],\n"
    "    thread_id=\"smoke_thread\",\n"
    ")\n"
    "assert ids and len(ids) >= 1, \"TODO 2 incomplete — add_messages should return at least one ID\"\n"
    "print(f\"PASS: TODO 2 passed — added message(s): {ids}\")"
)

md(
    "### See What Got Persisted\n\n"
    "When `report_event` ran, two things happened inside the SDK:\n\n"
    "1. **One row INSERTed into `CITY_MESSAGE`** — the raw narrative\n"
    "2. **The extractor LLM ran** and INSERTed 0+ typed records into "
    "`CITY_MEMORY`\n\n"
    "The helper below shows both tables. Run it now to see the smoke-test state, "
    "then again after TODO 3."
)

code(
    "def peek_sdk_tables(thread_id: str = None) -> None:\n"
    "    \"\"\"Print rows from CITY_MESSAGE and CITY_MEMORY (optionally scoped to one thread).\"\"\"\n"
    "    where = \"WHERE thread_id = :tid\" if thread_id else \"\"\n"
    "    bind = {\"tid\": thread_id} if thread_id else {}\n"
    "    with vector_conn.cursor() as cur:\n"
    "        cur.execute(f\"\"\"\n"
    "            SELECT message_role, SUBSTR(content, 1, 100) AS preview, user_id, agent_id\n"
    "              FROM CITY_MESSAGE {where}\n"
    "             ORDER BY order_seq\n"
    "        \"\"\", bind)\n"
    "        msgs = cur.fetchall()\n"
    "        print(f\" CITY_MESSAGE — {len(msgs)} row(s)\" + (f\" for thread={thread_id}\" if thread_id else \"\"))\n"
    "        for role, preview, uid, aid in msgs:\n"
    "            text = preview.read() if hasattr(preview, 'read') else preview\n"
    "            print(f\"   [{role:9}] user={uid or '-':18} agent={aid or '-':6} | {text}\")\n"
    "\n"
    "        cur.execute(f\"\"\"\n"
    "            SELECT memory_type, SUBSTR(content, 1, 100) AS preview, user_id, agent_id\n"
    "              FROM CITY_MEMORY {where}\n"
    "             ORDER BY order_seq\n"
    "        \"\"\", bind)\n"
    "        mems = cur.fetchall()\n"
    "        print(f\"\\n CITY_MEMORY — {len(mems)} row(s)\" + (f\" for thread={thread_id}\" if thread_id else \"\"))\n"
    "        for mtype, preview, uid, aid in mems:\n"
    "            text = preview.read() if hasattr(preview, 'read') else preview\n"
    "            print(f\"   [{mtype:10}] user={uid or '-':18} agent={aid or '-':6} | {text}\")\n"
    "\n"
    "peek_sdk_tables(thread_id=\"smoke_thread\")"
)

md(
    "**TODO 3: Run 8 narratives through `report_event` and inspect what got extracted.**\n\n"
    "1. The cell below samples 8 narratives from `data/maintenance_logs.json` "
    "spanning different assets and severities.\n"
    "2. Loop over them and call `report_event(...)` with `thread_id=\"inspect_demo\"`.\n"
    "3. Query `memory.search` filtered to the four native record types. **You must "
    "specify the same `user_id` you wrote with** (`\"inspector_demo\"`) — the SDK's "
    "high-level search rejects `exact_user_match=False`, and the records have "
    "`user_id=\"inspector_demo\"` inherited from the thread, so passing `user_id=None` "
    "would return zero. Print each extracted record's `record_type` and `content`.\n\n"
    "Expect at least 10+ extracted memories across the 8 narratives — the real "
    "maintenance logs are dense and the extractor finds plenty of structure."
)

code(
    "# Pre-built helper: stratified sample of 8 narratives.\n"
    "def sample_narratives(n: int = 8) -> list:\n"
    "    \"\"\"Stratified sample: mix of severities, multiple assets.\"\"\"\n"
    "    import random\n"
    "    random.seed(42)  # Reproducible across re-runs\n"
    "    buckets = {\"routine\": [], \"warning\": [], \"critical\": []}\n"
    "    for log in _logs:\n"
    "        buckets.get(log[\"severity\"], []).append(log)\n"
    "    # Take roughly proportional sample\n"
    "    n_routine, n_warning, n_critical = max(1, n // 2), max(1, n // 3), max(1, n - n // 2 - n // 3)\n"
    "    picks = (random.sample(buckets[\"routine\"], min(n_routine, len(buckets[\"routine\"]))) +\n"
    "             random.sample(buckets[\"warning\"], min(n_warning, len(buckets[\"warning\"]))) +\n"
    "             random.sample(buckets[\"critical\"], min(n_critical, len(buckets[\"critical\"]))))\n"
    "    return picks[:n]\n"
    "\n"
    "narratives = sample_narratives(8)\n"
    "print(\"Sampled narratives (asset, severity):\")\n"
    "for n in narratives:\n"
    "    print(f\"  {n['asset_name']:40} [{n['severity']}]\")"
)

code(
    "# TODO 3:\n"
    "# 1. Loop over `narratives` and call report_event(...) with thread_id=\"inspect_demo\".\n"
    "#    Use any plausible inspector_id (e.g. \"inspector_demo\" — same for all 8).\n"
    "# 2. Call memory.search across the four native record types, scoped to\n"
    "#    agent_id=\"CITY\", user_id=None, max_results=30, and print the results.\n"
    "# YOUR CODE HERE\n"
)

code(
    "# PASS: Checkpoint: TODO 3\n"
    "# The SDK's high-level search REQUIRES a specific user_id (it rejects\n"
    "# exact_user_match=False). We wrote the records with inspector=\"inspector_demo\",\n"
    "# so we search for the same.\n"
    "_results = memory.search(\n"
    "    query=\"recurring asset concerns and inspector practices\",\n"
    "    user_id=\"inspector_demo\",\n"
    "    agent_id=\"CITY\",\n"
    "    record_types=[\"fact\", \"preference\", \"guideline\", \"memory\"],\n"
    "    max_results=50,\n"
    ")\n"
    "assert len(_results) >= 5, (\n"
    "    f\"TODO 3 — expected at least 5 extracted records from 8 narratives, got {len(_results)}.\\n\"\n"
    "    \"Check OCI_GENAI_API_KEY and that you called report_event for all 8 narratives.\"\n"
    ")\n"
    "print(f\"PASS: TODO 3 passed — {len(_results)} memories extracted from 8 narratives\")"
)

md(
    "### Peek At The Tables Again — After 8 Narratives\n\n"
    "Same helper, this time scoped to the `inspect_demo` thread. You should see "
    "8 user-role messages in `CITY_MESSAGE` and dozens of typed records in "
    "`CITY_MEMORY`. Notice that none of the records are custom types — the SDK "
    "rejects them. All extracted records are one of the four natives."
)

code(
    "peek_sdk_tables(thread_id=\"inspect_demo\")"
)

# ────────────────────────────────────────────────────────────────────────────
# Part 4 — Inspection Findings + Similar-Finding Search
# ────────────────────────────────────────────────────────────────────────────

md("# Part 4: Inspection Findings + Similar-Finding Search")

md(
    "An **inspection finding** isn't a `fact` or a `preference` — it's a "
    "structured domain object with `category`, `severity`, `description`, "
    "`recommendation`, `inspector`, and `overall_grade`. The SDK rejects custom "
    "`record_type` values, so findings live in their own hand-rolled "
    "`CITY_INSPECTION_FINDING` SQL table with a `VECTOR(384)` column + HNSW "
    "index.\n\n"
    "Oracle's converged DB lets us mix vector similarity with relational filters "
    "(asset, category, severity, time window) in **one SQL statement** — no "
    "metadata-filter quirks, full SQL expressiveness.\n\n"
    ">  Open `docs/part-4-findings-and-search.md` for the full walk-through."
)

code(
    "# Pre-built: create CITY_INSPECTION_FINDING with VECTOR(384) + HNSW index.\n"
    "with vector_conn.cursor() as cur:\n"
    "    cur.execute(\"\"\"\n"
    "        CREATE TABLE CITY_INSPECTION_FINDING (\n"
    "            finding_id      VARCHAR2(64) PRIMARY KEY,\n"
    "            asset_id        VARCHAR2(128) NOT NULL,\n"
    "            inspector       VARCHAR2(128),\n"
    "            overall_grade   VARCHAR2(2),\n"
    "            category        VARCHAR2(32),\n"
    "            severity        VARCHAR2(16),\n"
    "            description     CLOB NOT NULL,\n"
    "            recommendation  CLOB,\n"
    "            days_ago        NUMBER,\n"
    "            embedding       VECTOR(384) NOT NULL,\n"
    "            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
    "            CONSTRAINT fk_finding_asset FOREIGN KEY (asset_id) REFERENCES CITY_ASSET(asset_id)\n"
    "        )\n"
    "    \"\"\")\n"
    "    try:\n"
    "        cur.execute(\"\"\"\n"
    "            CREATE VECTOR INDEX city_finding_embedding_idx\n"
    "            ON CITY_INSPECTION_FINDING (embedding)\n"
    "            ORGANIZATION INMEMORY NEIGHBOR GRAPH\n"
    "            DISTANCE COSINE\n"
    "            WITH TARGET ACCURACY 95\n"
    "            PARAMETERS (TYPE HNSW, M 16, EFCONSTRUCTION 200)\n"
    "        \"\"\")\n"
    "    except Exception as e:\n"
    "        print(f\"  (skipped HNSW index: {e})\")\n"
    "vector_conn.commit()\n"
    "print(\" CITY_INSPECTION_FINDING created with VECTOR(384) embedding column.\")"
)

code(
    "# Pre-built: bulk-load all ~220 findings from the inspection reports.\n"
    "# No LLM extraction needed — findings are already structured. Just embed + INSERT.\n"
    "import array, uuid\n"
    "\n"
    "rows = []\n"
    "for report in _reports:\n"
    "    asset_id = report[\"asset_name\"]\n"
    "    inspector = report[\"inspector\"]\n"
    "    grade = report[\"overall_grade\"]\n"
    "    days_ago = report[\"days_ago\"]\n"
    "    for finding in report[\"findings\"]:\n"
    "        vec = array.array('f', embedder.embed([finding[\"description\"]])[0].tolist())\n"
    "        rows.append({\n"
    "            \"finding_id\":     str(uuid.uuid4())[:12],\n"
    "            \"asset_id\":       asset_id,\n"
    "            \"inspector\":      inspector,\n"
    "            \"overall_grade\":  grade,\n"
    "            \"category\":       finding[\"category\"],\n"
    "            \"severity\":       finding[\"severity\"],\n"
    "            \"description\":    finding[\"description\"],\n"
    "            \"recommendation\": finding[\"recommendation\"],\n"
    "            \"days_ago\":       days_ago,\n"
    "            \"embedding\":      vec,\n"
    "        })\n"
    "\n"
    "with vector_conn.cursor() as cur:\n"
    "    cur.executemany(\"\"\"\n"
    "        INSERT INTO CITY_INSPECTION_FINDING\n"
    "          (finding_id, asset_id, inspector, overall_grade, category, severity,\n"
    "           description, recommendation, days_ago, embedding)\n"
    "        VALUES (:finding_id, :asset_id, :inspector, :overall_grade, :category, :severity,\n"
    "                :description, :recommendation, :days_ago, :embedding)\n"
    "    \"\"\", rows)\n"
    "vector_conn.commit()\n"
    "print(f\" Inserted {len(rows)} findings into CITY_INSPECTION_FINDING.\")"
)

md(
    "**TODO 4: Implement `log_finding(...)`.**\n\n"
    "Signature:\n"
    "```python\n"
    "def log_finding(\n"
    "    asset_id: str,\n"
    "    inspector: str,\n"
    "    category: str,\n"
    "    severity: str,\n"
    "    description: str,\n"
    "    recommendation: str = \"\",\n"
    "    overall_grade: str = None,\n"
    "    days_ago: int = 0,\n"
    ") -> str:\n"
    "```\n\n"
    "Steps:\n\n"
    "1. **Generate `finding_id`** — `str(uuid.uuid4())[:12]`.\n"
    "2. **Compute the embedding** from `description` via "
    "`embedder.embed([description])[0].tolist()`. Wrap in `array.array('f', ...)` "
    "so `oracledb` binds it as a `VECTOR` (a plain list triggers `ORA-01484`).\n"
    "3. **INSERT** into `CITY_INSPECTION_FINDING` using named binds.\n"
    "4. **Commit** and return `finding_id`."
)

code(
    "import array, uuid\n"
    "\n"
    "def log_finding(\n"
    "    asset_id: str,\n"
    "    inspector: str,\n"
    "    category: str,\n"
    "    severity: str,\n"
    "    description: str,\n"
    "    recommendation: str = \"\",\n"
    "    overall_grade: str = None,\n"
    "    days_ago: int = 0,\n"
    ") -> str:\n"
    "    \"\"\"Persist a new inspection finding into CITY_INSPECTION_FINDING.\"\"\"\n"
    "    # TODO 4: generate finding_id, compute embedding, INSERT, commit, return finding_id.\n"
    "    # YOUR CODE HERE\n"
    "    pass\n"
)

code(
    "# PASS: Checkpoint: TODO 4\n"
    "_fid = log_finding(\n"
    "    asset_id=\"Harbor Bridge\",\n"
    "    inspector=\"checkpoint_test\",\n"
    "    category=\"corrosion\",\n"
    "    severity=\"medium\",\n"
    "    description=\"Surface corrosion on pier 2 bearing assemblies; ~25% section loss observed.\",\n"
    "    recommendation=\"Remove corrosion, apply primer + finish coat within 60 days.\",\n"
    "    overall_grade=\"C\",\n"
    "    days_ago=0,\n"
    ")\n"
    "assert _fid and isinstance(_fid, str), \"TODO 4 — should return a finding_id string\"\n"
    "\n"
    "with vector_conn.cursor() as cur:\n"
    "    cur.execute(\n"
    "        \"SELECT COUNT(*) FROM CITY_INSPECTION_FINDING WHERE inspector = :i\",\n"
    "        i=\"checkpoint_test\",\n"
    "    )\n"
    "    n = cur.fetchone()[0]\n"
    "assert n == 1, \"TODO 4 — checkpoint test finding not retrievable\"\n"
    "print(f\"PASS: TODO 4 passed — finding_id={_fid}\")"
)

md(
    "**TODO 5: Implement `find_similar_findings(description, asset_id=None, category=None, k=3)`.**\n\n"
    "One SQL statement mixes vector similarity with optional asset + category filters:\n\n"
    "```sql\n"
    "SELECT finding_id, asset_id, inspector, overall_grade, category, severity,\n"
    "       description, recommendation, days_ago,\n"
    "       VECTOR_DISTANCE(embedding, :q, COSINE) AS score\n"
    "  FROM CITY_INSPECTION_FINDING\n"
    " WHERE (:asset_id IS NULL OR asset_id = :asset_id)\n"
    "   AND (:category IS NULL OR category = :category)\n"
    " ORDER BY score\n"
    " FETCH FIRST :k ROWS ONLY\n"
    "```\n\n"
    "Steps:\n\n"
    "1. **Embed the query description** wrapped in `array.array('f', ...)`.\n"
    "2. **Execute the SQL** with binds `q=query_vec`, `asset_id=asset_id`, `category=category`, `k=k`.\n"
    "3. Return a list of dicts. For `description` and `recommendation` CLOB columns, call `.read()` to materialise them."
)

code(
    "def find_similar_findings(description: str, asset_id: str = None, category: str = None, k: int = 3) -> list:\n"
    "    \"\"\"Vector-search CITY_INSPECTION_FINDING, optionally narrowed to one asset and/or category.\n"
    "\n"
    "    Returns a list of dicts:\n"
    "        {finding_id, asset_id, inspector, overall_grade, category, severity,\n"
    "         description, recommendation, days_ago, score}\n"
    "    \"\"\"\n"
    "    # TODO 5: embed the query, run the SQL with VECTOR_DISTANCE, return list of dicts.\n"
    "    # YOUR CODE HERE\n"
    "    pass\n"
)

code(
    "# PASS: Checkpoint: TODO 5\n"
    "_broad = find_similar_findings(\"bearing corrosion at piers\", k=5)\n"
    "_bridge = find_similar_findings(\"bearing corrosion at piers\", asset_id=\"Harbor Bridge\", k=5)\n"
    "_corrosion_only = find_similar_findings(\"bearing corrosion at piers\", category=\"corrosion\", k=5)\n"
    "\n"
    "assert _broad and len(_broad) >= 3, f\"TODO 5 — broad search returned {len(_broad) if _broad else 0} hits\"\n"
    "assert _bridge and all(r[\"asset_id\"] == \"Harbor Bridge\" for r in _bridge), \\\n"
    "    \"TODO 5 — asset_id filter should restrict results to Harbor Bridge\"\n"
    "assert _corrosion_only and all(r[\"category\"] == \"corrosion\" for r in _corrosion_only), \\\n"
    "    \"TODO 5 — category filter should restrict results to corrosion only\"\n"
    "print(f\"PASS: TODO 5 passed — broad={len(_broad)}, asset-filtered={len(_bridge)}, category-filtered={len(_corrosion_only)}\")\n"
    "for r in _bridge[:3]:\n"
    "    print(f\"  score={r['score']:.3f}  [{r['category']}/{r['severity']}]  {str(r['description'])[:90]}\")"
)

# ────────────────────────────────────────────────────────────────────────────
# Part 5 — Scoping Demo (no TODO)
# ────────────────────────────────────────────────────────────────────────────

md("# Part 5: Scoping — Inspector vs City")

md(
    "Three scope dimensions: `user_id` (inspector), `agent_id` (`CITY`), "
    "`thread_id` (per asset). Enforced as SQL `WHERE` predicates — cross-user "
    "leakage is impossible at the DB layer.\n\n"
    "**No TODO** — just run the demo cells to see scoping in action."
)

code(
    "# Inspector Mercer writes a personal note (user-scoped, invisible to others)\n"
    "memory.add_memory(\n"
    "    content=\"Remember to swap shifts with Jordan next Tuesday.\",\n"
    "    user_id=\"Evelyn_H_Mercer\",\n"
    ")\n"
    "\n"
    "# Mercer also writes a city-wide tribal-knowledge guideline (agent-scoped)\n"
    "memory.add_memory(\n"
    "    content=\"On Harbor Bridge, inspect Pier 2 bearings annually — corrosion-prone since 2024.\",\n"
    "    agent_id=\"CITY\",\n"
    ")\n"
    "print(\" Mercer wrote one personal memory and one city-wide memory.\")"
)

code(
    "# Inspector Vance searches at user scope — should NOT see Mercer's personal note\n"
    "vance_personal = memory.search(\n"
    "    query=\"shift swap notes\",\n"
    "    user_id=\"Jordan_Vance\",\n"
    "    record_types=[\"memory\"],\n"
    "    max_results=10,\n"
    ")\n"
    "\n"
    "# Vance searches at city scope — SHOULD see the Pier 2 guideline\n"
    "vance_city = memory.search(\n"
    "    query=\"Harbor Bridge Pier 2 bearings\",\n"
    "    user_id=None,           # explicitly leave user dimension unconstrained\n"
    "    agent_id=\"CITY\",\n"
    "    record_types=[\"memory\"],\n"
    "    max_results=10,\n"
    ")\n"
    "\n"
    "print(f\"  Vance's personal-scope hits for 'shift swap': {len(vance_personal)}  (should be 0)\")\n"
    "print(f\"  Vance's city-scope hits for 'Pier 2 bearings': {len(vance_city)}  (should be ≥ 1)\")"
)

code(
    "# Assertions — multi-tenancy is enforced at the SQL layer\n"
    "assert all(\"shift swap\" not in r.record.content.lower() for r in vance_personal), \\\n"
    "    \"Cross-inspector leak: Mercer's personal note showed up in Vance's user-scoped search\"\n"
    "assert any(\"Pier 2\" in r.record.content for r in vance_city), \\\n"
    "    \"Pier 2 guideline not retrievable at agent scope — check agent_id wiring\"\n"
    "print(\" Multi-tenancy verified: Vance sees city-wide guidelines but NOT Mercer's personal notes.\")"
)

md(
    ">  **Key insight — Part 5:** scoping is enforced as a SQL `WHERE` clause "
    "on `user_id` / `agent_id` / `thread_id` columns — not as a soft filter in "
    "Python. A bug in your harness can't leak Mercer's note to Vance; only a "
    "SQL injection could. For regulated infrastructure, add VPD policies on top "
    "(see `docs/part-5-scoping.md`)."
)

# ────────────────────────────────────────────────────────────────────────────
# Part 6 — End-to-End Copilot
# ────────────────────────────────────────────────────────────────────────────

md("# Part 6: The CityOps Copilot — End-to-End")

md(
    "One function, `call_copilot`, ties together: thread resolution (SDK), "
    "asset lookup (`CITY_ASSET` SQL), the context card (SDK), similar-finding "
    "search (`CITY_INSPECTION_FINDING` SQL via `VECTOR_DISTANCE()`), agent LLM "
    "call, and persistence (which triggers auto-extraction).\n\n"
    ">  Open `docs/part-6-copilot-end-to-end.md` for the architecture diagram."
)

code(
    "# Pre-built: system prompt + LLM call helper.\n"
    "COPILOT_SYSTEM_PROMPT = \"\"\"You are a CityOps inspection copilot.\n"
    "\n"
    "Each turn you are given:\n"
    "- The current inspection narrative\n"
    "- The asset record (class)\n"
    "- A thread context card (recent inspector messages + extracted facts/guidelines)\n"
    "- Up to 3 similar past findings on the same asset (with category, severity,\n"
    "  recommendation, prior inspector, prior overall grade)\n"
    "\n"
    "Your job: suggest a likely diagnosis or characterisation; cite prior findings\n"
    "with their inspector + grade + recommendation timeline; surface relevant\n"
    "guidelines from the thread context. Keep responses ≤ 8 sentences.\n"
    "When safety- or maintenance-critical guidelines apply, name them.\"\"\"\n"
    "\n"
    "def call_openai_chat(messages: list, model: str = \"xai.grok-3-fast\"):\n"
    "    return client.chat.completions.create(model=model, messages=messages)"
)

md(
    "### What Does `get_context_card` Actually Return?\n\n"
    "Before you wire it into `call_copilot` (TODO 6), see what the SDK gives "
    "you. The cell below grabs the `inspect_demo` thread (8 narratives from "
    "Part 3) and prints `card.formatted_content` verbatim.\n\n"
    "The card is **XML, not Markdown**. Four blocks: `<summary>`, `<topics>`, "
    "`<relevant_information>`, `<recent_messages>`."
)

code(
    "_demo_thread = memory.get_thread(\"inspect_demo\")\n"
    "_demo_card = _demo_thread.get_context_card(\n"
    "    fallback_message_count=100,\n"
    "    max_recent_messages=5,\n"
    "    max_relevant_results=5,\n"
    ")\n"
    "print(\"=\" * 70)\n"
    "print(\"Raw context-card output — this is the XML the agent LLM will see:\")\n"
    "print(\"=\" * 70)\n"
    "print(_demo_card.formatted_content)"
)

md(
    "**TODO 6: Implement `call_copilot(narrative, inspector_id, thread_id, asset_id)`.**\n\n"
    "Step by step:\n\n"
    "1. **Resolve thread.** `memory.get_thread(thread_id)`; on failure call `memory.create_thread(user_id=inspector_id, thread_id=thread_id, agent_id=\"CITY\")`.\n\n"
    "2. **Asset record.** `get_asset(asset_id)` → dict or None. Format as a short string for the prompt.\n\n"
    "3. **Context card.** `thread.get_context_card(fallback_message_count=100, max_recent_messages=10, max_relevant_results=8)`. Use `.formatted_content`.\n\n"
    "4. **Similar findings.** `find_similar_findings(narrative, asset_id=asset_id, k=3)`. Format as a string — each row has `score`, `category`, `severity`, `description`, `recommendation`, `inspector`, `overall_grade`, `days_ago`.\n\n"
    "5. **Build the context string** with sections `# Current inspection narrative`, `# Asset record`, `# Thread context`, `# Similar past findings`.\n\n"
    "6. **Call `call_openai_chat`** with the system prompt + context.\n\n"
    "7. **Persist** with `thread.add_messages([Message(role=\"user\", content=...), Message(role=\"assistant\", content=answer)])`.\n\n"
    "8. **Return** the assistant's answer."
)

code(
    "def call_copilot(narrative: str, inspector_id: str, thread_id: str, asset_id: str) -> str:\n"
    "    \"\"\"End-to-end CityOps copilot turn: build context, query LLM, persist.\"\"\"\n"
    "    # TODO 6:\n"
    "    # 1. Resolve thread (get_thread or create_thread)\n"
    "    # 2. Lookup asset via get_asset()\n"
    "    # 3. Build context card via thread.get_context_card\n"
    "    # 4. Find similar findings via find_similar_findings(asset_id=...)\n"
    "    # 5. Assemble context string\n"
    "    # 6. call_openai_chat\n"
    "    # 7. thread.add_messages with user + assistant\n"
    "    # 8. Return answer\n"
    "    # YOUR CODE HERE\n"
    "    pass\n"
)

code(
    "# PASS: Checkpoint: TODO 6 — smoke test\n"
    "_smoke = call_copilot(\n"
    "    narrative=\"Smoke test — please ignore. One-line check on Harbor Bridge.\",\n"
    "    inspector_id=\"smoke_inspector\",\n"
    "    thread_id=\"copilot_smoke\",\n"
    "    asset_id=\"Harbor Bridge\",\n"
    ")\n"
    "assert _smoke and len(_smoke) > 10, \"TODO 6 — copilot returned empty/short answer\"\n"
    "print(\"PASS: TODO 6 passed — copilot ran end-to-end\")\n"
    "print(f\"\\nSample response (first 300 chars):\\n  {_smoke[:300]}\")"
)

md(
    "## The Cross-Inspector Handoff Scenario\n\n"
    "Inspector Mercer reviews Harbor Bridge, logs a corrosion finding. Days "
    "later, Inspector Vance — who has never met Mercer — encounters a related "
    "concern on the same asset. Watch what the copilot tells Vance."
)

code(
    "# Day 1, 10:00 — Inspector Mercer reviews Harbor Bridge and logs corrosion\n"
    "print(\"=\" * 70)\n"
    "print(\"DAY 1: Inspector Mercer on Harbor Bridge\")\n"
    "print(\"=\" * 70)\n"
    "MERCER_NOTES = call_copilot(\n"
    "    narrative=(\n"
    "        \"Quarterly inspection of Harbor Bridge. Surface corrosion observed on Pier 2 \"\n"
    "        \"bearing assemblies (south side), estimated section loss ~25% on bearing plate \"\n"
    "        \"edges with local rust bleeding onto the concrete pedestal. Corrosion extends \"\n"
    "        \"roughly 1.5 m longitudinally along the bearing line.\"\n"
    "    ),\n"
    "    inspector_id=\"Evelyn_H_Mercer\",\n"
    "    thread_id=\"asset_harbor_bridge\",\n"
    "    asset_id=\"Harbor Bridge\",\n"
    ")\n"
    "# Mercer logs the formal finding\n"
    "log_finding(\n"
    "    asset_id=\"Harbor Bridge\",\n"
    "    inspector=\"Evelyn_H_Mercer\",\n"
    "    category=\"corrosion\",\n"
    "    severity=\"medium\",\n"
    "    description=\"Surface corrosion + pitting on steel bearing assemblies at Pier 2 south, ~25% section loss; rust bleed onto concrete pedestal; ~1.5m longitudinal extent.\",\n"
    "    recommendation=\"Remove loose corrosion products, apply corrosion-inhibiting primer + finish coat to affected bearing assemblies within 60 days; re-inspect annually with caliper section-loss measurements.\",\n"
    "    overall_grade=\"C\",\n"
    "    days_ago=0,\n"
    ")\n"
    "print(f\"\\n Mercer's copilot response:\\n{MERCER_NOTES}\")"
)

code(
    "# Day 1, 14:00 — Mercer adds a follow-up observation\n"
    "print(\"\\n\" + \"=\" * 70)\n"
    "print(\"DAY 1 (afternoon): Mercer follow-up note\")\n"
    "print(\"=\" * 70)\n"
    "MERCER_FOLLOWUP = call_copilot(\n"
    "    narrative=(\n"
    "        \"Coordinated with maintenance — recommend scheduling the bearing remediation \"\n"
    "        \"to coincide with the deck wearing-surface resurfacing in Q3 to share access \"\n"
    "        \"and traffic management.\"\n"
    "    ),\n"
    "    inspector_id=\"Evelyn_H_Mercer\",\n"
    "    thread_id=\"asset_harbor_bridge\",\n"
    "    asset_id=\"Harbor Bridge\",\n"
    ")\n"
    "print(f\"\\n Mercer's followup response:\\n{MERCER_FOLLOWUP}\")"
)

code(
    "# Day N (later) — Inspector Vance arrives. Different inspector, same asset.\n"
    "print(\"\\n\" + \"=\" * 70)\n"
    "print(\"DAY N: Inspector Vance on Harbor Bridge (never met Mercer)\")\n"
    "print(\"=\" * 70)\n"
    "VANCE_DIAGNOSIS = call_copilot(\n"
    "    narrative=(\n"
    "        \"Reviewing Harbor Bridge as part of routine cycle. Noticing rust bleed near \"\n"
    "        \"a pier on the south side and what looks like spalling on the concrete \"\n"
    "        \"pedestal below.\"\n"
    "    ),\n"
    "    inspector_id=\"Jordan_Vance\",\n"
    "    thread_id=\"asset_harbor_bridge\",\n"
    "    asset_id=\"Harbor Bridge\",\n"
    ")\n"
    "print(f\"\\n Vance's copilot response (built from Mercer's work, NO human handoff):\\n{VANCE_DIAGNOSIS}\")"
)

md(
    "## Compare: Vance With And Without Memory\n\n"
    "Below: same Vance narrative, but stripped of all memory layers — no thread, "
    "no context card, no `find_similar_findings`. Just the LLM and the narrative. "
    "The contrast is the workshop's point."
)

code(
    "stateless_messages = [\n"
    "    {\"role\": \"system\", \"content\": COPILOT_SYSTEM_PROMPT},\n"
    "    {\"role\": \"user\",   \"content\": (\n"
    "        \"Reviewing Harbor Bridge as part of routine cycle. Noticing rust bleed near \"\n"
    "        \"a pier on the south side and what looks like spalling on the concrete \"\n"
    "        \"pedestal below.\"\n"
    "    )},\n"
    "]\n"
    "STATELESS_VANCE = call_openai_chat(stateless_messages).choices[0].message.content\n"
    "\n"
    "print(\"=\" * 70)\n"
    "print(\"WITHOUT MEMORY (stateless LLM):\")\n"
    "print(\"=\" * 70)\n"
    "print(STATELESS_VANCE)\n"
    "print(\"\\n\" + \"=\" * 70)\n"
    "print(\"WITH MEMORY (the copilot you built):\")\n"
    "print(\"=\" * 70)\n"
    "print(VANCE_DIAGNOSIS)"
)

# ────────────────────────────────────────────────────────────────────────────
# Wrap-up
# ────────────────────────────────────────────────────────────────────────────

md(
    "## Key Takeaways\n\n"
    "| Layer | Earned its keep by… |\n"
    "|---|---|\n"
    "| Auto-extracted `fact` / `preference` / `guideline` (SDK) | Surfacing tribal knowledge from real maintenance narratives without explicit code |\n"
    "| `CITY_ASSET` SQL table | Letting the copilot look up structured asset facts at the start of every turn |\n"
    "| `CITY_INSPECTION_FINDING` SQL with `VECTOR(384)` | Vector-searchable history via Oracle's native `VECTOR_DISTANCE()` — mixed with relational filters in one SQL |\n"
    "| Context card (SDK) | Compressing the per-asset thread into ~200 tokens that travel with every turn |\n"
    "| Scoping (`user_id` / `agent_id` / `thread_id`) | Multi-tenant-safety at the SQL layer |"
)

md(
    "## Production Hardening Checklist\n\n"
    "- Real asset registry wired to your CMMS (IBM Maximo, Esri, ProjectMates)\n"
    "- Asset hierarchy via self-FK on `CITY_ASSET.parent_asset_id`\n"
    "- Oracle VPD policies on `CITY_MEMORY` for hard row-level security\n"
    "- Audit log of LLM-generated diagnoses\n"
    "- Push findings back to inspection-tracking system on confirmation\n"
    "- Geospatial column (`SDO_GEOMETRY`) for proximity queries\n"
    "- Periodic re-extraction when domain vocabulary evolves"
)

md(
    "## Where to Next?\n\n"
    "- **[Oracle AI Agent Memory documentation](https://docs.oracle.com/en/database/oracle/agent-memory/)**\n"
    "- **[Oracle AI Developer Hub](https://github.com/oracle-devrel/oracle-ai-developer-hub)**\n"
    "- **[Agent Memory short course (DeepLearning.AI)](https://www.deeplearning.ai/short-courses/agent-memory-building-memory-aware-agents/)**"
)

# ────────────────────────────────────────────────────────────────────────────
# Emit
# ────────────────────────────────────────────────────────────────────────────

NOTEBOOK = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "CityOps Copilot",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).resolve().parent / "notebook_student.ipynb"
out.write_text(json.dumps(NOTEBOOK, indent=1, ensure_ascii=False))
print(f"Wrote {out} with {len(CELLS)} cells")
