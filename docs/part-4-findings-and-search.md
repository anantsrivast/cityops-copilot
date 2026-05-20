# Part 4: Inspection Findings + Similar-Finding Search

## Why Findings Need Their Own SQL Table

An **inspection finding** isn't a `fact` or a `preference`. It's a structured domain object:
- Has fields with specific shapes (`asset_id`, `category`, `severity`, `recommendation`, `inspector`, `overall_grade`)
- Will be queried by exact value (`severity='critical'`, `category='corrosion'`, `asset_id='Harbor Bridge'`) **and** by similarity (find similar past findings)
- Has a clear write/read pattern (write once when a finding is logged, read often for diagnosis)

The `oracleagentmemory` SDK rejects custom `record_type` values — its MEMORY table only accepts `fact`, `memory`, `preference`, `guideline`. So findings need their own table.

But this isn't a limitation — it's an opportunity. Oracle's converged DB lets us put a `VECTOR(384)` column on a regular SQL table and query with `VECTOR_DISTANCE()` mixed with relational `WHERE` clauses in **one SQL statement**. No metadata-filter quirks. Full SQL expressiveness — filter by `category`, `severity`, asset class, time window, inspector, grade — all in one query.

---

## Pre-Built: The `CITY_INSPECTION_FINDING` Table

```sql
CREATE TABLE CITY_INSPECTION_FINDING (
    finding_id      VARCHAR2(64) PRIMARY KEY,
    asset_id        VARCHAR2(128) NOT NULL,
    inspector       VARCHAR2(128),
    overall_grade   VARCHAR2(2),                 -- A/B/C/D/F (from the parent report)
    category        VARCHAR2(32),                -- corrosion / structural / drainage / ...
    severity        VARCHAR2(16),                -- low / medium / high / critical
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

**Notes:**
- The `embedding` is computed at write time from the `description` field — that's what future searches will hit on.
- The HNSW index uses cosine distance, matching what the embedder produces (normalized vectors).
- The FK to `CITY_ASSET` enforces referential integrity — you can't log a finding against a nonexistent asset.

## Pre-Built: Bulk-Load Every Finding from `data/inspection_reports.json`

Unlike the maintenance logs (where we only feed ~8 through the extractor due to LLM cost), the **~220 inspection findings get bulk-loaded entirely into SQL**. They're already structured — no LLM extraction needed — so the cost is just embedding computation (local, free) + INSERT.

The pre-built cell:

```python
import json, uuid, array

with open("data/inspection_reports.json") as f:
    reports = json.load(f)

rows = []
for report in reports:
    asset_id = report["asset_name"]
    inspector = report["inspector"]
    grade = report["overall_grade"]
    days_ago = report["days_ago"]
    for finding in report["findings"]:
        vec = array.array('f', embedder.embed([finding["description"]])[0].tolist())
        rows.append({
            "finding_id":     str(uuid.uuid4())[:12],
            "asset_id":       asset_id,
            "inspector":      inspector,
            "overall_grade":  grade,
            "category":       finding["category"],
            "severity":       finding["severity"],
            "description":    finding["description"],
            "recommendation": finding["recommendation"],
            "days_ago":       days_ago,
            "embedding":      vec,
        })

with vector_conn.cursor() as cur:
    cur.executemany("""
        INSERT INTO CITY_INSPECTION_FINDING
          (finding_id, asset_id, inspector, overall_grade, category, severity,
           description, recommendation, days_ago, embedding)
        VALUES (:finding_id, :asset_id, :inspector, :overall_grade, :category, :severity,
                :description, :recommendation, :days_ago, :embedding)
    """, rows)
vector_conn.commit()
print(f" Inserted {len(rows)} findings.")
```

~220 findings × one local embedding each. Takes 10–30 seconds on a Mac.

---

## TODO 4: `log_finding`

Add a new inspection finding interactively (the helper you'd call from the copilot in Part 6).

**Complete solution:**

```python
import array, uuid

def log_finding(
    asset_id: str,
    inspector: str,
    category: str,
    severity: str,
    description: str,
    recommendation: str = "",
    overall_grade: str = None,
    days_ago: int = 0,
) -> str:
    """Persist a new inspection finding into CITY_INSPECTION_FINDING and return its finding_id."""
    finding_id = str(uuid.uuid4())[:12]
    # array.array('f', ...) is what oracledb needs for VECTOR binds.
    # A plain Python list would trigger ORA-01484.
    vec = array.array('f', embedder.embed([description])[0].tolist())
    with vector_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO CITY_INSPECTION_FINDING
              (finding_id, asset_id, inspector, overall_grade, category, severity,
               description, recommendation, days_ago, embedding)
            VALUES (:finding_id, :asset_id, :inspector, :overall_grade, :category, :severity,
                    :description, :recommendation, :days_ago, :embedding)
        """,
            finding_id=finding_id, asset_id=asset_id, inspector=inspector,
            overall_grade=overall_grade, category=category, severity=severity,
            description=description, recommendation=recommendation,
            days_ago=days_ago, embedding=vec,
        )
    vector_conn.commit()
    return finding_id
```

**Gotcha — `array.array('f', ...)` vs Python list:** passing a plain Python list to `oracledb` for a `VECTOR` column raises `ORA-01484: arrays can only be bound to PL/SQL statements`. The driver interprets a list as "batch values for one bind variable" instead of "one vector value." Wrap in `array.array('f', ...)` with the float32 typecode to force the right interpretation.

---

## TODO 5: `find_similar_findings` — The Converged-DB Money Shot

This is where Oracle's converged DB earns its keep. One SQL statement mixes vector similarity with relational filters on **category**, **asset**, and (extensibly) **severity** / **inspector** / **time window**:

```sql
SELECT finding_id, asset_id, inspector, overall_grade, category, severity,
       description, recommendation, days_ago,
       VECTOR_DISTANCE(embedding, :q, COSINE) AS score
  FROM CITY_INSPECTION_FINDING
 WHERE (:asset_id IS NULL OR asset_id = :asset_id)
   AND (:category IS NULL OR category = :category)
 ORDER BY score
 FETCH FIRST :k ROWS ONLY
```

No metadata_filter, no JSON-path quirks. Pure SQL.

**Complete solution:**

```python
def find_similar_findings(description: str, asset_id: str = None, category: str = None, k: int = 3) -> list:
    """Vector-search CITY_INSPECTION_FINDING, optionally narrowed to one asset and/or category.

    Returns a list of dicts with all the structured fields + a `score` (cosine distance).
    """
    import array
    query_vec = array.array('f', embedder.embed([description])[0].tolist())
    sql = """
        SELECT finding_id, asset_id, inspector, overall_grade, category, severity,
               description, recommendation, days_ago,
               VECTOR_DISTANCE(embedding, :q, COSINE) AS score
          FROM CITY_INSPECTION_FINDING
         WHERE (:asset_id IS NULL OR asset_id = :asset_id)
           AND (:category IS NULL OR category = :category)
         ORDER BY score
         FETCH FIRST :k ROWS ONLY
    """
    with vector_conn.cursor() as cur:
        cur.execute(sql, q=query_vec, asset_id=asset_id, category=category, k=k)
        cols = [d[0].lower() for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            # CLOBs need .read()
            for key in ("description", "recommendation"):
                v = row.get(key)
                if v is not None and hasattr(v, "read"):
                    row[key] = v.read()
            rows.append(row)
    return rows
```

**Things to notice:**

1. **`VECTOR_DISTANCE(embedding, :q, COSINE)`** — third arg is the distance metric. Options: `COSINE`, `DOT`, `EUCLIDEAN`, `EUCLIDEAN_SQUARED`, `MANHATTAN`, `HAMMING`.
2. **Optional filter pattern** — `WHERE (:bind IS NULL OR col = :bind)` lets one bind handle both "give me all" and "narrow to one value". Add more for severity / inspector / time window as needed.
3. **`ORDER BY score`** — lower distance = higher similarity. The HNSW index makes this cheap.
4. **CLOBs need `.read()`** — `cur.description` returns LOB objects for CLOB columns; materialise to string.

---

## What This Pattern Unlocks

Once you have a vector column on a normal SQL table, you can:

- **Severity-filtered semantic search:** `find_similar_findings(..., severity='critical')`
- **Time-window queries:** `WHERE days_ago < 90 AND VECTOR_DISTANCE(...) < 0.3`
- **Joins across vector tables:** `SELECT f.*, a.asset_class FROM CITY_INSPECTION_FINDING f JOIN CITY_ASSET a USING (asset_id) WHERE a.asset_class='bridge' ORDER BY VECTOR_DISTANCE(f.embedding, :q, COSINE)`
- **Aggregates:** `SELECT category, COUNT(*) FROM CITY_INSPECTION_FINDING WHERE VECTOR_DISTANCE(...) < 0.3 GROUP BY category`
- **Hybrid keyword + vector**: add Oracle Text indexes and combine `CONTAINS()` with `VECTOR_DISTANCE()` in one query

None of this is possible with the SDK's `metadata_filter` on its private `_store` — that's exact-equality only on top-level JSON keys. Going to SQL is *more* expressive, not less.

## Production Note

In a real city-ops deployment you'd add:
- A **`finding_id` link back to your inspection-tracking system** (Cityworks, Esri, ProjectMates, etc.) so the copilot can cite a real ticket.
- A **`closed_at` timestamp** for remediation-status queries.
- **Aggregated cluster summaries** — periodic rollup rows that summarise N findings of the same category on the same asset class. Becomes higher-confidence guidance for the copilot than raw findings alone.
- **Geospatial coordinates** — if your assets have lat/lon, an additional `SDO_GEOMETRY` column lets you query "findings within 500m of this location."

All of these extensions are clean SQL on the same table.
