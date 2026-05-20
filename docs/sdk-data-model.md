# `oracleagentmemory` SDK Data Model (v 26.4.0)

Reference doc covering the SDK's storage layout, the closed record-type taxonomy, the write paths, and the read paths. Everything below is verified directly against the SDK source and a live Oracle Autonomous Database.

This workshop uses the SDK with `table_name_prefix="CITY_"`, so every SDK-created table is `CITY_*` (alongside the workshop's hand-rolled `CITY_ASSET` and `CITY_INSPECTION_FINDING` tables that live outside the SDK).

---

## High-Level Diagram

```
                                          ┌──────────────────────┐
                                          │ CITY_ACTOR_PROFILE   │
                                          │ ─────────────────    │
                                          │  actor_id (PK)       │
                                          │  actor_type {user,   │
                                          │              agent}  │
                                          │  information (CLOB)  │
                                          └──────────────────────┘
                                                   (no FK in or out)

  ┌──────────────────────┐
  │ CITY_THREAD          │ ◄─────────────┐  ◄────────────────┐
  │ ─────────────────    │               │                   │
  │  record_id (PK)      │               │                   │
  │  user_id             │               │                   │
  │  agent_id            │               │                   │
  │  metadata    (JSON)  │               │                   │
  │  runtime_config(JSON)│               │                   │
  │  → cached running    │               │                   │
  │    summary lives here│               │                   │
  └──────────────────────┘               │                   │
                                         │                   │
                              ON DELETE CASCADE     ON DELETE CASCADE
                                         │                   │
                                         │                   │
  ┌──────────────────────┐    ┌─────────┴────────────┐  ┌──┴────────────────┐
  │ CITY_MESSAGE         │    │ CITY_MEMORY          │  │ CITY_RECORD_CHUNKS│
  │ ─────────────────    │    │ ─────────────────    │  │ ─────────────────  │
  │  record_id (PK)      │    │  record_id (PK)      │  │  chunk_id (PK)     │
  │  thread_id (FK)      │    │  thread_id (FK)      │  │  source_id         │
  │  order_seq (autoinc) │    │  order_seq (autoinc) │  │  source_record_type│
  │  message_role        │    │  memory_type *       │  │  source_emb_column │
  │  content (CLOB)      │    │  content (CLOB)      │  │  thread_id         │
  │  metadata (JSON)     │    │  metadata (JSON)     │  │  user_id           │
  │  user_id             │    │  user_id             │  │  agent_id          │
  │  agent_id            │    │  agent_id            │  │  embedding         │
  │  space_id            │    │  space_id            │  │  VECTOR(384) **    │
  └──────────────────────┘    └──────────────────────┘  └────────────────────┘
                                         * closed taxonomy:                                              ** shared HNSW
                                           {fact, memory,                                                 vector index
                                            preference,                                                   over all
                                            guideline}                                                    embeddings
```

All SDK tables get this workshop's `table_name_prefix` (`CITY_THREAD`, `CITY_MESSAGE`, etc.).

The two **hand-rolled** tables live alongside but **outside** the SDK schema:

```
  ┌──────────────────────┐
  │ CITY_ASSET           │
  │ ─────────────────    │
  │  asset_id (PK)       │ ← e.g. 'Harbor Bridge', 'Substation Gamma'
  │  asset_class         │ ← bridge / substation / pipeline / sensor / ...
  │  metadata (JSON)     │
  └──────────────────────┘
            ▲
            │ FK from
            │
  ┌──────────────────────┐
  │ CITY_INSPECTION_     │
  │     FINDING          │
  │ ─────────────────    │
  │  finding_id (PK)     │
  │  asset_id            │
  │  inspector           │
  │  overall_grade       │
  │  category            │ ← corrosion / structural / drainage / ...
  │  severity            │ ← low / medium / high / critical
  │  description (CLOB)  │
  │  recommendation(CLOB)│
  │  days_ago (NUMBER)   │
  │  embedding VECTOR(384)│ ← + its own HNSW index
  │  created_at          │
  └──────────────────────┘
```

---

## Table-by-Table DDL + Notes

### 1. `CITY_THREAD` — one row per per-asset inspection thread

```sql
CREATE TABLE CITY_THREAD (
  record_id       VARCHAR2(128) NOT NULL,    -- thread_id (e.g. 'asset_harbor_bridge')
  user_id         VARCHAR2(128),             -- inspector who created the thread
  agent_id        VARCHAR2(128),             -- 'CITY'
  space_id        VARCHAR2(128),             -- reserved for future multi-city partitioning
  metadata        JSON,                       -- application metadata
  runtime_config  JSON,                       -- SDK-managed: holds the cached running summary
  created_at      TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  PRIMARY KEY (record_id)
);
```

**What `runtime_config` carries** — JSON column where the SDK's extractor pipeline stashes per-thread state:

```json
{
  "context_summary": "Harbor Bridge had corrosion observed on Pier 2 bearings in March...",
  "last_summary_update_counter": 7,
  ...
}
```

This is the **cached running summary**. The SDK's extractor reads it as `{prior_summary}` and rewrites it every `context_summary_update_frequency` messages.

---

### 2. `CITY_MESSAGE` — every inspection narrative

```sql
CREATE TABLE CITY_MESSAGE (
  record_id       VARCHAR2(128) NOT NULL,
  order_seq       NUMBER GENERATED ALWAYS AS IDENTITY NOT NULL,
  thread_id       VARCHAR2(128),
  user_id         VARCHAR2(128),
  agent_id        VARCHAR2(128),
  space_id        VARCHAR2(128),
  message_role    VARCHAR2(30) NOT NULL,
  content         CLOB,
  timestamp       VARCHAR2(64),
  metadata        JSON,
  created_at      TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  PRIMARY KEY (record_id),
  CONSTRAINT message_thread_fk FOREIGN KEY (thread_id)
    REFERENCES CITY_THREAD(record_id) ON DELETE CASCADE
);
```

`order_seq` lets you query "the last N messages for this asset" with `ORDER BY order_seq DESC FETCH FIRST :n ROWS`. Used internally by `get_context_card()` for `<recent_messages>` and by the extractor's recent-message window.

---

### 3. `CITY_MEMORY` — durable typed memories (the polymorphic table)

```sql
CREATE TABLE CITY_MEMORY (
  record_id       VARCHAR2(128) NOT NULL,
  order_seq       NUMBER GENERATED ALWAYS AS IDENTITY NOT NULL,
  thread_id       VARCHAR2(128),
  user_id         VARCHAR2(128),
  agent_id        VARCHAR2(128),
  space_id        VARCHAR2(128),
  memory_type     VARCHAR2(128) NOT NULL,   -- * pinned to {fact, memory, preference, guideline}
  content         CLOB,
  timestamp       VARCHAR2(64),
  metadata        JSON,
  created_at      TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  PRIMARY KEY (record_id),
  CONSTRAINT memory_thread_fk FOREIGN KEY (thread_id)
    REFERENCES CITY_THREAD(record_id) ON DELETE CASCADE
);
```

* **The critical detail.** `memory_type` is `VARCHAR2(128)` at the schema level — so the *database* could store anything. But the SDK validates `memory_type` against a hard-coded `frozenset` before writing:

```python
# In oracleagentmemory/core/oracledbmemorystore.py
_SEARCHABLE_RECORD_TYPES = frozenset({
    'user_profile', 'agent_profile', 'fact', 'message',
    'memory', 'preference', 'guideline'
})

def _is_memory_table_record_type(record_type):
    return (record_type in _SEARCHABLE_RECORD_TYPES
            and record_type != 'message'
            and record_type not in {'user_profile', 'agent_profile'})
```

The MEMORY table accepts exactly four values for `memory_type`:

| `memory_type` | Purpose |
|---|---|
| `memory` | General durable record (default for `add_memory()`); fallback when LLM extraction can't classify |
| `fact` | Declarative statement about inspector / asset / environment |
| `preference` | Stable inspector preference |
| `guideline` | Operating instruction or "next time check X" lesson |

Any other string → `ValueError: Unsupported DB record_type.` raised at `_prepare_add_batch`. This is why **`CITY_ASSET` and `CITY_INSPECTION_FINDING` live outside the SDK** — they need their own structured shapes.

---

### 4. `CITY_RECORD_CHUNKS` — embeddings + the HNSW index for the SDK

```sql
CREATE TABLE CITY_RECORD_CHUNKS (
  chunk_id           NUMBER GENERATED ALWAYS AS IDENTITY NOT NULL,
  source_id          VARCHAR2(128) NOT NULL,
  source_record_type VARCHAR2(30) NOT NULL,
  source_emb_column  VARCHAR2(30) NOT NULL,
  thread_id          VARCHAR2(128),
  user_id            VARCHAR2(128),
  agent_id            VARCHAR2(128),
  space_id           VARCHAR2(128),
  embedding          VECTOR(384),
  PRIMARY KEY (chunk_id)
);

CREATE VECTOR INDEX CITY_RECORD_CHUNKS_EMBEDDING_VEC_I
  ON CITY_RECORD_CHUNKS (embedding)
  ORGANIZATION INMEMORY NEIGHBOR GRAPH
  DISTANCE COSINE
  WITH TARGET ACCURACY 95
  PARAMETERS (TYPE HNSW, M 16, EFCONSTRUCTION 200);
```

One **shared** HNSW index for messages AND memories. Scope columns are duplicated here from the parent so search can filter without joining.

---

### 5. `CITY_ACTOR_PROFILE` — inspectors + agents in one table

```sql
CREATE TABLE CITY_ACTOR_PROFILE (
  actor_id     VARCHAR2(128) NOT NULL,
  actor_type   VARCHAR2(30) NOT NULL,            -- 'user' or 'agent'
  space_id     VARCHAR2(128),
  order_seq    NUMBER GENERATED ALWAYS AS IDENTITY NOT NULL,
  information  CLOB NOT NULL,
  created_at   TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  PRIMARY KEY (actor_id),
  CHECK (actor_type IN ('user', 'agent'))
);
```

Inspectors and agents share one table, distinguished by `actor_type`. `actor_id` is the same identifier you pass as `user_id` or `agent_id` everywhere else.

---

### 6. `CITY_ORACLEAGENTMEMORY_SCHEMA_META` — bookkeeping

Internal — the SDK uses it to track schema version and avoid re-running DDL. Not interesting for the workshop.

---

## Hand-Rolled Tables (Outside The SDK)

### `CITY_ASSET`

```sql
CREATE TABLE CITY_ASSET (
  asset_id     VARCHAR2(128) PRIMARY KEY,
  asset_class  VARCHAR2(32),         -- bridge / substation / pipeline / water / sensor / comms / civil / energy
  metadata     JSON,                 -- whatever else you want
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Loaded from `data/maintenance_logs.json` + `data/inspection_reports.json` (union of `asset_name` fields). 26 rows. `asset_class` is derived from name heuristics.

### `CITY_INSPECTION_FINDING`

```sql
CREATE TABLE CITY_INSPECTION_FINDING (
  finding_id      VARCHAR2(64) PRIMARY KEY,
  asset_id        VARCHAR2(128) NOT NULL,
  inspector       VARCHAR2(128),
  overall_grade   VARCHAR2(2),              -- A/B/C/D/F
  category        VARCHAR2(32),             -- corrosion / structural / drainage / ...
  severity        VARCHAR2(16),             -- low / medium / high / critical
  description     CLOB NOT NULL,
  recommendation  CLOB,
  days_ago        NUMBER,
  embedding       VECTOR(384) NOT NULL,
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_finding_asset FOREIGN KEY (asset_id) REFERENCES CITY_ASSET(asset_id)
);

CREATE VECTOR INDEX city_finding_embedding_idx
  ON CITY_INSPECTION_FINDING (embedding)
  ORGANIZATION INMEMORY NEIGHBOR GRAPH
  DISTANCE COSINE
  WITH TARGET ACCURACY 95
  PARAMETERS (TYPE HNSW, M 16, EFCONSTRUCTION 200);
```

Loaded from `data/inspection_reports.json` — ~220 findings across 20 assets. The embedding is computed on the `description` field. The `category` / `severity` / `inspector` columns enable SQL `WHERE` filters mixed with `VECTOR_DISTANCE()` ranking in one statement.

---

## Why The Workshop Uses Both Layers

| What it stores | Why this layer |
|---|---|
| Conversational maintenance narratives + auto-extracted insights | **SDK** — extractor LLM + thread management + context cards are exactly what the SDK was built for |
| Static asset registry + structured inspection findings | **Hand-rolled SQL** — they have specific shapes (category enum, severity enum, recommendation text, grade letter) that don't fit the SDK's `(memory_type, content, metadata)` triple, and the SDK rejects custom record types |
| Cross-layer joins | Both layers live in the same Oracle schema on the same connection — `SELECT ... FROM CITY_INSPECTION_FINDING f, CITY_MEMORY m WHERE ...` works |

This is the Oracle converged-DB story made concrete: same database, same engine, both layers indexed with HNSW, queryable with `VECTOR_DISTANCE()` and standard SQL.

---

## Version Caveat

Everything above is verified against `oracleagentmemory==26.4.0`. Oracle may relax the `_SEARCHABLE_RECORD_TYPES` allowlist or add a public extension API in future versions. Recheck on upgrade.
