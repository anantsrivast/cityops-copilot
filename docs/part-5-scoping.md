# Part 5: Scoping — Inspector vs City

This part has no TODO. It's a guided demonstration of the SDK's multi-tenancy model, with assertions that verify isolation.

## The Three Scoping Dimensions

Every memory row in `CITY_MEMORY` (and every message in `CITY_MESSAGE`) carries three nullable columns:

| Column | What it identifies | This workshop's usage |
|---|---|---|
| `user_id` | The end-user (inspector) | `Evelyn_H_Mercer`, `Jordan_Vance`, etc. — real inspector names from the dataset |
| `agent_id` | The agent or environment | `CITY` — shared across all inspectors |
| `thread_id` | The conversation thread | One per asset: `asset_harbor_bridge`, etc. |

At search time, you pass any combination of these plus per-dimension `exact_*_match` flags. The SDK compiles them into a SQL `WHERE` clause:

```sql
WHERE user_id   = :user_id      -- enforced when exact_user_match = True
  AND agent_id  = :agent_id     -- enforced when exact_agent_match = True
  AND thread_id = :thread_id    -- enforced when exact_thread_match = True
  AND memory_type IN (...)
```

Default for the higher-level `OracleAgentMemory.search()` API is **exact-match on every dimension you supply** — strict. Cross-inspector leakage is impossible at the database layer; it would require a SQL injection bug.

## What This Workshop Scopes Where

| Memory kind | Storage | Scope | Why |
|---|---|---|---|
| Asset registry (`CITY_ASSET` SQL table) | Hand-rolled | Plant-wide, no scope columns | Every inspector can see every asset |
| Inspection findings (`CITY_INSPECTION_FINDING` SQL table) | Hand-rolled | City-wide, no scope columns | Cross-inspector handoff is the point |
| Auto-extracted operational facts/guidelines (SDK) | `CITY_MEMORY` | Inherited from the thread (inspector as `user_id`, `CITY` as `agent_id`) | Tribal knowledge stays city-wide via `agent_id`; per-inspector preferences stay user-scoped |
| Personal notes via `memory.add_memory(user_id=...)` | `CITY_MEMORY` | User-scoped | An inspector's private notes are theirs alone |

## The Demo Cells

The notebook walks through three steps:

**Step 1 — Inspector A writes two memories, one personal, one city-wide:**

```python
# Personal: scoped to user_id only — invisible to other inspectors
memory.add_memory(
    content="Remember to swap shifts with Jordan next Tuesday.",
    user_id="Evelyn_H_Mercer",
)

# City-wide: scoped to agent_id only — visible to all inspectors
memory.add_memory(
    content="On Harbor Bridge, always inspect Pier 2 bearings annually — corrosion-prone.",
    agent_id="CITY",
)
```

**Step 2 — Inspector B searches at two different scopes:**

```python
# Bob's personal scope — should NOT see Alice's personal note
bob_personal = memory.search(
    query="shift swap notes",
    user_id="Jordan_Vance",
    record_types=["memory"],
    max_results=10,
)

# Bob's city scope — SHOULD see the Pier 2 guideline
bob_city = memory.search(
    query="Harbor Bridge bearings",
    user_id=None,                # required: explicitly leave user dimension unconstrained
    agent_id="CITY",
    record_types=["memory"],
    max_results=10,
)
```

**Step 3 — Assertions verify isolation:**

The notebook asserts both expectations. If either fails, you know something is wrong with your scope wiring.

## Why This Matters Operationally

City-asset inspection is fundamentally a **shared-knowledge** problem with **per-person nuance**. The same asset (Harbor Bridge) is inspected by many inspectors over years; their collective experience is the asset, not any one inspector's memory. But individual inspectors also have private observations they don't want broadcast.

The SDK's `user_id` / `agent_id` split maps onto this cleanly:

- **`agent_id="CITY"`** is where you put anything any inspector should benefit from — Pier 2 corrosion-proneness, "always check sensor X before declaring Y", recurring failure patterns.
- **`user_id="Evelyn_H_Mercer"`** is where her individual preferences and personal notes live, isolated from peers.

For multi-city deployment, `agent_id` could be `"CITY_AUSTIN"` vs `"CITY_AARHUS"` — naturally partitioning cities while still sharing within each.

## Production Hardening — Adding VPD

For regulated infrastructure (utilities, defense, transit) you may want hard row-level security beyond the SDK's WHERE-clause approach. Apply Oracle's **Virtual Private Database (VPD)** policy to `CITY_MEMORY`:

```sql
BEGIN
  DBMS_RLS.ADD_POLICY(
    object_schema   => 'VECTOR',
    object_name     => 'CITY_MEMORY',
    policy_name     => 'inspector_scope',
    function_schema => 'VECTOR',
    policy_function => 'inspector_scope_fn',
    statement_types => 'SELECT, UPDATE, DELETE'
  );
END;
/
```

Where `inspector_scope_fn` returns a predicate like `'user_id = SYS_CONTEXT(''CTX'', ''CURRENT_INSPECTOR'')'`. VPD enforces the predicate at the database engine — even direct SQL bypassing the SDK can't escape it.

This is what makes the SDK genuinely deployable in regulated multi-tenant settings — the SDK's WHERE clauses are belt-and-braces convenience; VPD is the actual seatbelt.
