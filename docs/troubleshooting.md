# Troubleshooting

## Oracle / Connection

### `ORA-12541: TNS:no listener`
The listener is still starting after Docker came up. Wait 30 seconds and retry. If it persists for 2 minutes, `docker logs oracle-free | tail -50` and look for "DATABASE IS READY TO USE!" — if absent, the container is still bootstrapping.

### `ORA-01017: invalid username/password`
Local mode: `setup_runtime.sh` should normalize the `VECTOR` password — re-run it. Wallet mode: verify your ADB credentials in `.env`.

---

## Vector / Schema

### `ORA-51962: vector memory area not allocated`
The most common Oracle Free vector error. Run as SYS:

```sql
ALTER SYSTEM SET vector_memory_size = 1G SCOPE=SPFILE;
```

Then restart the container. The workshop's `setup_runtime.sh` does this automatically.

### `ORA-01484: arrays can only be bound to PL/SQL statements`
You're binding a Python list to a `VECTOR` column. The driver interprets a list as "batch values" rather than "one vector value."

**Fix:** wrap in `array.array('f', ...)`:

```python
import array
vec = array.array('f', embedder.embed([text])[0].tolist())
cur.execute("INSERT ... VALUES (..., :embedding)", embedding=vec)
```

Numpy `float32` arrays also work.

### Vector dim mismatch at insert
The embedder returned vectors of the wrong dimension. The SDK + workshop both use 384 dims (`sentence-transformers/all-MiniLM-L6-v2`). If you swap models (e.g. to a 768-dim variant), you need to recreate the schema with `vector_dim=768` and drop+recreate `CITY_INSPECTION_FINDING`'s `VECTOR(384)` column to `VECTOR(768)`.

---

## SDK Behavior

### `ValueError: Unsupported DB record_type`
The SDK rejects any `memory_type` outside its four-value frozenset (`fact`, `memory`, `preference`, `guideline`). Custom types like `"finding"` or `"asset"` raise this.

Workshop's approach: domain objects live in the hand-rolled `CITY_ASSET` and `CITY_INSPECTION_FINDING` SQL tables, not in the SDK's MEMORY table. See `sdk-data-model.md` for the proof.

### Extraction returns nothing after `add_messages`

Three usual causes:
1. **`OCI_GENAI_API_KEY` unset or invalid** — extractor LLM fails silently. Verify `os.environ.get("OCI_GENAI_API_KEY")`.
2. **Narrative too short** — "Looks OK" produces nothing. The seed maintenance logs are paragraph-length for a reason.
3. **Rate limits** — xAI Grok occasionally returns 429s. Wait a minute and retry just that cell.

### `memory.search` returns nothing for records I know are there
Two distinct traps:

**Trap 1: `user_id=None` does NOT mean "any user."** The SDK's default `exact_user_match=True` interprets `user_id=None` as "match records where `user_id IS NULL` exactly" — not "leave user dim unconstrained." If the records you want have a populated `user_id` (e.g. set by `thread.add_messages` from the thread's `user_id`), `user_id=None` returns zero.

**Trap 2: You can't search "across all users."** Passing `exact_user_match=False` raises:
```
ValueError: OracleAgentMemory client searches require exact user scoping.
Do not set exact_user_match=False.
```
The public API forces exact user scoping for security.

**To search records with a populated user_id**, you MUST pass that exact user_id:
```python
memory.search(
    query=...,
    user_id="inspector_demo",  # must match the user_id at write time
    agent_id="CITY",
    record_types=["fact", "preference", "guideline"],
)
```

**To search records you wrote with no user_id** (e.g. `memory.add_memory(content=..., agent_id="CITY")` — global guidelines):
```python
memory.search(..., user_id=None, agent_id="CITY", record_types=["memory"])
```

**To genuinely search across users** (not allowed in the high-level API), either:
- Drop to the private store: `memory._store.search(query, k, user_id=None, exact_user_match=False, ...)`
- Or query `CITY_MEMORY` directly with SQL (`SELECT ... WHERE memory_type IN (...)`)

Same kind of trap for `agent_id` and `thread_id`, though those don't have the `exact_*_match=False` rejection.

### Duplicate or near-duplicate extracted facts
The SDK's dedup is LLM-judged, not fingerprinted. Near-duplicates can slip through, especially when you re-run a cell (re-extraction on the same input produces paraphrased versions).

**Fix:**
1. Restart the kernel + drop the CITY_* tables before re-running cleanly.
2. For production, post-process: cosine similarity > 0.95 → drop one.
3. Lower the extractor LLM temperature: `Llm(..., temperature=0)` gives more reproducible classifications.

---

## Jupyter / Kernel

### Jupyter kernel "CityOps Copilot Workshop" missing
The setup script's kernel registration didn't run. Re-register:

```bash
python -m ipykernel install --user --name workshop --display-name "CityOps Copilot"
```

Then refresh the kernel picker in VS Code.

### `ImportError: oracleagentmemory.apis.embedders.embedder`
The SDK isn't installed in the kernel's Python. `pip show oracleagentmemory` should report 26.4.0+. If missing:

```bash
pip install -r requirements.txt
```

---

## Codespace / Container

### Out of disk in the Codespace
CPU-only PyTorch keeps the footprint under 2GB. If something else has eaten disk:
```bash
du -sh ~/.cache/* | sort -h
docker system df
```
`docker system prune -af` reclaims unused images. **Don't** prune volumes — that wipes Oracle state.

### Codespace doesn't pick up `.env`
VS Code's `python.envFile` setting doesn't always reach Jupyter kernels. The workshop's first cell loads `.env` explicitly, so this is a no-op now — but if you see `mode: local (Codespaces / Oracle Free on localhost:1521)` when you expected ADB mode, check:
1. Does `.env` exist in the project root?
2. Did you restart the kernel after creating/editing `.env`?
