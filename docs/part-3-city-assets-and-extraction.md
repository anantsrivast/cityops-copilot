# Part 3: City Asset Registry + Auto-Extraction

This part teaches the **two-store split** that runs throughout the workshop:

1. **Domain objects** (the asset registry, inspection findings) live in **hand-rolled SQL tables** alongside the SDK. The `oracleagentmemory` SDK accepts only its four native record types (`fact`, `memory`, `preference`, `guideline`) in its MEMORY table — custom types like "asset" or "finding" are rejected. See [`sdk-data-model.md`](sdk-data-model.md) for the proof.
2. **Auto-extracted semantic memory** from inspection narratives is the SDK's sweet spot — managed entirely inside its MEMORY table via `thread.add_messages(...)` + the auto-extractor.

The split is natural: SQL for SQL-shaped data, vectors + LLM extraction for fuzzy semantic recall. Oracle's converged engine makes both work on the same connection.

---

## Pre-Built: The Asset Registry from Real Data

`data/maintenance_logs.json` and `data/inspection_reports.json` together reference 26 distinct assets — bridges, substations, pipelines, water treatment plants, sensors, comms towers, seawalls. The Part 3 setup cells:

1. **Read both JSON files**, take the union of `asset_name` fields, classify each by name heuristics.
2. **Create `CITY_ASSET`** SQL table:
   ```sql
   CREATE TABLE CITY_ASSET (
       asset_id     VARCHAR2(128) PRIMARY KEY,
       asset_class  VARCHAR2(32),    -- bridge / substation / pipeline / water / sensor / comms / civil / energy
       metadata     JSON,
       created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```
3. **Bulk-INSERT** all 26 rows.

A helper for lookups:

```python
def get_asset(asset_id: str) -> dict | None:
    with vector_conn.cursor() as cur:
        cur.execute(
            "SELECT asset_id, asset_class, metadata FROM CITY_ASSET WHERE asset_id = :id",
            id=asset_id,
        )
        row = cur.fetchone()
    if not row: return None
    return {"asset_id": row[0], "asset_class": row[1], "metadata": row[2]}
```

In production, this would be a sync from your asset-management system (IBM Maximo, Esri, SAP PM, OCI Asset Manager).

---

## Auto-Extraction — The SDK's Headline Feature

When you call `thread.add_messages(...)` with `extract_memories=True` on the `OracleAgentMemory` instance, the SDK fires an **extractor LLM call** internally. It feeds the extractor:

- The new message(s)
- The cached running thread summary (from `CITY_THREAD.runtime_config`)
- The most recent existing memories (for deduplication)

And asks it to produce 0–8 typed records of `fact` / `preference` / `guideline` / `memory`. The records are inserted into `CITY_MEMORY` automatically.

**You don't write the extraction prompt.** You don't parse the LLM's JSON. You don't dedupe against existing records. The SDK does all of it.

What the SDK's extractor prompt asks (full quote from `_oneshotextractor.pyc`):

> *"You are a memory extraction module for an LLM agent. Extract a small set of HIGH-VALUE, ATOMIC memory records from the thread that will be stored verbatim and later retrieved with FLAT semantic search. Each extracted item must be assigned to the concrete storage `record_type` used by the system: `preference`, `fact`, `guideline`, or `memory`."*

---

## TODO 2: `report_event`

A thin wrapper around `thread.add_messages`. Its job:

1. **Get-or-create the thread** for this asset
2. **Format the content** so the extractor sees the asset and inspector along with the narrative
3. **Call `add_messages`** — extractor runs as a side effect

**Complete solution:**

```python
def report_event(asset_id: str, inspector: str, narrative: str, thread_id: str) -> list:
    """Persist a maintenance event narrative and trigger SDK auto-extraction."""
    try:
        t = memory.get_thread(thread_id)
    except Exception:
        t = None
    if t is None:
        t = memory.create_thread(
            user_id=inspector,
            thread_id=thread_id,
            agent_id="CITY",
        )

    # Include both asset and inspector in content — the extractor only reads the text.
    content = f"[Asset: {asset_id}] [Inspector: {inspector}] {narrative}"
    return t.add_messages([Message(role="user", content=content)])
```

**Why include asset and inspector in the content?** Because the extractor LLM sees only the message content — not the surrounding metadata. If you want it to extract "Harbor Bridge has pier corrosion" rather than just "the bridge has pier corrosion", the asset must be in the text.

**Why scope the thread to `agent_id="CITY"`?** All facts/preferences/guidelines extracted from this thread inherit that `agent_id`. City-wide knowledge (operational SOPs, asset gotchas) stays available to any inspector searching at the city scope; per-inspector preferences stay scoped to the inspector's `user_id`.

---

## TODO 3: Inspect the Extracted Memories

The workshop provides a helper to pick representative narratives from `data/maintenance_logs.json`:

```python
def sample_narratives(n: int = 8) -> list:
    """Return n narratives spanning different assets and severities."""
    with open("data/maintenance_logs.json") as f:
        logs = json.load(f)
    # Stratified sample: mix of routine / warning / critical, multiple assets
    # ... (workshop provides the implementation)
    return sampled
```

After running ~8 narratives through `report_event`, query the SDK:

```python
results = memory.search(
    query="recurring asset concerns and inspector practices",
    user_id="inspector_demo",      # * must match the user_id used at write time
    agent_id="CITY",
    record_types=["fact", "preference", "guideline", "memory"],
    max_results=20,
)
for r in results:
    print(f"  [{r.record.record_type:11s}] {r.record.content}")
```

> WARNING: **You can't search the SDK "across all users."** The public `memory.search()` API enforces exact user scoping — passing `exact_user_match=False` raises:
> ```
> ValueError: OracleAgentMemory client searches require exact user scoping.
> ```
> The SDK is opinionated here for security: every search must specify whose memory you're looking at. Practical consequence: either (a) search by a specific `user_id`, (b) drop to the private `memory._store.search()` for unrestricted access, or (c) query `CITY_MEMORY` directly via SQL.
>
> Since our 8 narratives were written under `inspector="inspector_demo"`, the records all inherited `user_id="inspector_demo"` from the thread — that's what we search for.

**Expected output** (exact wording varies):

```
  [fact       ] Harbor Bridge experienced surface corrosion on Pier 2 bearing assemblies during scheduled inspection.
  [fact       ] Ultrasonic thickness readings at Harbor Bridge stations 24+00 and 24+50 averaged 14.8 mm.
  [guideline  ] Inspect scuppers and verify deck drainage during routine bridge inspections.
  [fact       ] Substation Gamma transformer showed elevated oil temperature on the south bank.
  [preference ] Use ultrasonic readings before deciding section-loss measurements on steel components.
  ...
```

The split between types is the LLM's call. The diversity of the source narratives (bridges, substations, pipelines, sensors) gives a rich cross-section in `CITY_MEMORY`.

---

## Why Auto-Extraction Earns Its Keep On Real Data

The 308 maintenance logs are long, technical, and full of details — measurement readings, asset IDs, dates, weather, follow-up actions, equipment IDs. Manually parsing them into typed memories would take weeks of prompt engineering and validation. The SDK's auto-extractor turns each into 0–8 records in one LLM call — and as you process more narratives, the running summary in `CITY_THREAD.runtime_config` keeps the extractor's context up to date.

For production: you'd batch-ingest the rest of the 308 logs the same way. ~308 LLM calls at extractor pricing. The workshop only does ~8 to keep cost and time bounded.

## Troubleshooting

**Empty extraction results after `add_messages`:**
1. `OCI_GENAI_API_KEY` is unset or invalid (the extractor LLM fails silently)
2. Narrative was too short or had no extractable content
3. Rate limits — xAI Grok occasionally returns 429s. Wait a minute and retry.

**Records appearing under unexpected types:** the LLM's classification is non-deterministic at default temperature. Lower it on the SDK's `Llm` constructor (`temperature=0`) for more reproducible classifications.

**`memory.search` returns nothing despite records being there:** check the scope. Default is `exact_user_match=True`, so passing the wrong `user_id` returns zero. Pass `user_id=None` to leave that dimension unconstrained.

**Duplicates in extracted facts:** the SDK's dedup is LLM-judged, not fingerprinted. Near-duplicate phrasings can slip through. Common when you re-run the cell. Restart the kernel between runs for clean comparisons.
