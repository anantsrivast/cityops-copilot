# CityOps Copilot — Workshop One-Pager

This hands-on workshop shows how to implement agent memory as a first-class capability end to end on Oracle AI Database. Explore **episodic memory** (per-asset conversation threads and per-finding records), **semantic memory** (auto-extracted facts and preferences + a queryable asset registry), and **procedural memory** (auto-extracted operating guidelines from inspection narratives), all assembled into bounded **working memory** via on-demand context cards. With the `oracleagentmemory` SDK and a **minimal Python harness — no LangChain, no agent framework** — you will build a city-operations inspection copilot with persistent state, cross-inspector recall, and patterns that get sharper as the inspection history grows. Learn context engineering techniques such as running-summary compaction and bounded context cards, plus memory engineering for hybrid retrieval that mixes vector similarity with relational filters in a single `VECTOR_DISTANCE` SQL statement. See how memory fits into the agent loop from ingestion and recall to reasoning and action, with runnable Python code and production-ready patterns.

## Memory Types — Where Each Lives

| Classical type | What it means | How this workshop covers it |
|---|---|---|
| **Episodic** | Specific events: what happened, when, by whom | `CITY_MESSAGE` (raw inspection narratives) + `CITY_INSPECTION_FINDING` (one row per finding, with inspector + timestamp) |
| **Semantic** | General durable knowledge, declarative facts | SDK auto-extracted `fact` + `preference` records, `CITY_ASSET` registry, plus the `recommendation` field on each finding |
| **Procedural** | Reusable patterns, operating rules, "next time do X" lessons | SDK auto-extracted `guideline` records (e.g. *"on Harbor Bridge, check sensor 4B before declaring a jam"*) |
| **Working** | Bounded context the LLM sees this turn | The SDK's **context card** — assembled fresh per call from summary, topics, top-K relevant memories, and recent messages |

The wow moment is a **cross-inspector handoff**: Inspector B walks up to Harbor Bridge with a corrosion concern weeks after Inspector A inspected it, and the copilot surfaces A's findings, severity grades, recommendations, and tribal observations with zero human briefing — pulling from both the SDK's auto-extracted memory and the `CITY_INSPECTION_FINDING` SQL table via `VECTOR_DISTANCE()`.

---

## Two-Layer Storage Architecture

The `oracleagentmemory` SDK only allows **4 record types** in its memory table (`fact`, `memory`, `preference`, `guideline`). Domain objects can't live there. The workshop uses two storage layers on **one Oracle connection**:

| Layer | What lives here | Examples |
|---|---|---|
| **SDK** (managed by `oracleagentmemory`) | Conversational maintenance narratives + auto-extracted semantic memory | Field notes, tribal-knowledge guidelines (*"east scupper at Pier 2 needs annual clearing"*), inspector preferences |
| **Hand-rolled SQL** (raw tables alongside the SDK) | Structured domain objects + their embeddings | `CITY_ASSET` (26-asset registry), `CITY_INSPECTION_FINDING` (~220 findings with `VECTOR(384)` column + HNSW index) |

>  The full schema breakdown is in `sdk-data-model.md`. The data model is the *why* — start there if the design feels surprising.

---

## The Scope Model — Thread Per Asset

Three first-class scope dimensions on every SDK row (`user_id`, `agent_id`, `thread_id`):

| Dimension | Used for | This workshop's value |
|---|---|---|
| `user_id` | The inspector | Real inspector names from the dataset (e.g. `Evelyn_H_Mercer`) |
| `agent_id` | The city ops agent | `CITY` — shared across all inspectors |
| `thread_id` | One conversation thread | **`asset_harbor_bridge` — one thread per asset, not per inspector** |

**Why "thread per asset"?** Inspections are collaborative across time. Inspector A inspects Harbor Bridge in March; Inspector B does the routine semi-annual in September — they should see each other's work for free. Calling `memory.get_thread("asset_harbor_bridge")` returns the existing thread; new findings append; cross-inspector handoff is automatic.

The alternative (thread per inspector) would give cleaner per-inspector privacy at the cost of cross-inspector continuity — wrong for infrastructure inspection, right for, say, a wealth advisor whose clients shouldn't see each other.

---

## Workshop Flow (6 Parts, 6 TODOs)

| Part | Topic | TODOs | What you learn |
|---|---|---|---|
| 1 | Oracle setup | — | Connect to ADB (wallet) or Codespaces (local Oracle Free) — same notebook, env-driven |
| 2 | Embedder + SDK init | **TODO 1** | `IEmbedder` adapter; SDK creates its 5 tables under `CITY_*` |
| 3 | Asset registry + auto-extraction | **TODO 2, 3** | `CITY_ASSET` from `data/`; `thread.add_messages` triggers SDK extractor → typed records from real maintenance narratives |
| 4 | Inspection findings + similarity search | **TODO 4, 5** | `CITY_INSPECTION_FINDING` with `VECTOR(384)` (all ~220 findings pre-loaded); `VECTOR_DISTANCE()` SQL mixed with category/severity filters |
| 5 | Scoping demo | — (guided) | `user_id` (inspector) vs `agent_id="CITY"` enforcement via SQL `WHERE`, not Python guards |
| 6 | End-to-end copilot + cross-inspector demo | **TODO 6** | `call_copilot()` ties it all together; killer cross-inspector handoff demo runs |

---

## One Copilot Turn — What Actually Happens

```
call_copilot(narrative, inspector_id, thread_id, asset_id)
│
├─ 1. get_or_create thread (SDK)
│
├─ 2. SQL lookup:  get_asset(asset_id) → CITY_ASSET
│       returns: asset class (bridge / substation / pipeline / ...), grade-history hints
│
├─ 3. Context card (SDK):  thread.get_context_card(
│            fallback_message_count=100,
│            max_recent_messages=10,
│            max_relevant_results=8)
│      │
│      └─ {L} summary LLM call → XML with:
│           <summary>      LLM-distilled thread state across prior inspections
│           <topics>       1-8 retrieval keywords
│           <relevant_information>  top-8 fact/preference/guideline records
│           <recent_messages>       last 10 messages verbatim
│
├─ 4. SQL search:  find_similar_findings(narrative, asset_id=..., category=..., k=3)
│       VECTOR_DISTANCE(embedding, :q, COSINE) + relational WHERE in one SQL
│       returns: top-3 prior findings (with severity, recommendation, inspector, grade)
│
├─ 5. {A} agent LLM call:  system_prompt + context_card + sql_extras
│
└─ 6. thread.add_messages([user_msg, assistant_msg]) (SDK)
        └─ side effect: extractor LLM runs on both → 0+ new typed records
```

**LLM-call accounting per turn:** 1 (context-card summary) + 1 (agent reasoning) + 2 (extractor on user + extractor on assistant) = **~4 LLM calls per copilot turn.** Plus an occasional running-summary refresh every N messages.

---

## The Cross-Inspector Demo — Why It Works

Three calls in the workshop, same `thread_id="asset_harbor_bridge"`:

```
March — Inspector Mercer
  ├─ Reviews Harbor Bridge, logs a maintenance event narrative
  └─ Submits a CITY_INSPECTION_FINDING:
       category=corrosion, severity=medium,
       description="surface corrosion on Pier 2 bearings, ~25% section loss",
       recommendation="apply primer + finish coat within 60 days; annual re-inspection"

March (later) — Mercer follow-up
  └─ Notes the bearing inspection should be coordinated with the next coating cycle

September — Inspector Vance (never met Mercer)
  └─ call_copilot("Reviewing Harbor Bridge — noticing rust bleed near pier")
       │
       ├─ get_asset("Harbor Bridge")          → asset class (bridge), prior grade (SQL)
       ├─ thread.get_context_card(...)        → Mercer's notes + extracted guidelines (SDK)
       └─ find_similar_findings(...)          → Mercer's corrosion finding at the top (SQL)
       
       Vance's prompt now contains Mercer's prior corrosion work.
       The copilot responds with a diagnosis that references the 25% section
       loss number, the recommended primer-and-coat timeline, and asks Vance
       to verify the section-loss measurement has progressed.
       Zero human handoff.
```

The handoff works because:
1. **SDK side** — Vance inherits Mercer's thread (same `thread_id`), so the context card surfaces Mercer's notes and extracted guidelines.
2. **SQL side** — Mercer's finding is in `CITY_INSPECTION_FINDING`, vector-similar to Vance's narrative, surfaced by `find_similar_findings`.

Both layers contribute. Neither alone is sufficient.

---

## Run Anywhere — One Notebook, Two Environments

The notebook detects which environment it's in via env vars and switches connection mode automatically:

| Env var | Effect |
|---|---|
| `ORACLE_WALLET_LOCATION` set | **ADB / wallet mode** — local dev. Uses your wallet for mTLS to Oracle Autonomous Database. |
| `ORACLE_WALLET_LOCATION` not set | **Local mode** — Codespaces default. Connects to the Docker Oracle Free container at `localhost:1521/FREEPDB1`. |

Local-dev workflow: drop a `.env` file in the project root with your wallet + OCI credentials. The notebook's first cell loads it. Same notebook runs in Codespaces unchanged — env vars come from `devcontainer.json`'s `remoteEnv` instead.

---

## Reference Documents

| Doc | Read when |
|---|---|
| `sdk-data-model.md` | You want to understand what the SDK actually stores and why custom record types fail |
| `part-1-oracle-setup.md` → `part-6-copilot-end-to-end.md` | Step-by-step walkthroughs for each TODO with complete solutions |
| `TODO-checklist.md` | At-a-glance progress tracker |
| `troubleshooting.md` | When something breaks — covers ORA-51962, ORA-01484, SDK rate limits, scoping pitfalls |
