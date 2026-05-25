# CityOps Copilot — Agent Memory Workshop

This hands-on workshop shows how to implement agent memory as a first-class capability end to end on Oracle AI Database. Explore **episodic memory** (per-asset conversation threads and per-finding records), **semantic memory** (auto-extracted facts and preferences + a queryable asset registry), and **procedural memory** (auto-extracted operating guidelines from inspection narratives), all assembled into bounded **working memory** via on-demand context cards. With the `oracleagentmemory` SDK and a **minimal Python harness — no LangChain, no agent framework** — you will build a city-operations inspection copilot with persistent state, cross-inspector recall, and patterns that get sharper as the inspection history grows. Learn context engineering techniques such as running-summary compaction and bounded context cards, plus memory engineering for hybrid retrieval that mixes vector similarity with relational filters in a single `VECTOR_DISTANCE` SQL statement. See how memory fits into the agent loop from ingestion and recall to reasoning and action, with runnable Python code and production-ready patterns.

## Memory Types — Where Each Lives

| Classical type | What it means | How this workshop covers it |
|---|---|---|
| **Episodic** | Specific events: what happened, when, by whom | `CITY_MESSAGE` (raw inspection narratives) + `CITY_INSPECTION_FINDING` (one row per finding, with inspector + timestamp) |
| **Semantic** | General durable knowledge, declarative facts | SDK auto-extracted `fact` + `preference` records, `CITY_ASSET` registry, plus the `recommendation` field on each finding |
| **Procedural** | Reusable patterns, operating rules, "next time do X" lessons | SDK auto-extracted `guideline` records (e.g. *"on Harbor Bridge, check sensor 4B before declaring a jam"*) |
| **Working** | Bounded context the LLM sees this turn | The SDK's **context card** — assembled fresh per call from summary, topics, top-K relevant memories, and recent messages |

## Use Case

An inspector / city-operations copilot that remembers every asset's maintenance history across inspectors. Built on Oracle AI Database + the `oracleagentmemory` SDK. The key moment: a new inspector encounters a corrosion concern on Harbor Bridge, and the copilot already knows what the prior inspector observed, recommended, and graded — without anyone telling it.

## The Data

This workshop runs on a realistic seed dataset of city infrastructure events, committed in `data/`:

| File | Shape | What's inside |
|---|---|---|
| `data/maintenance_logs.json` | 308 entries × 26 assets | Maintenance event narratives (routine / warning / critical) — paragraph-long technical write-ups |
| `data/inspection_reports.json` | 60 reports × 20 assets, ~220 findings | Structured findings with category (corrosion, structural, drainage, mechanical, safety, electrical, coating), severity (low/medium/high/critical), description, recommendation, inspector name, overall grade |

The asset mix spans bridges, substations, pipelines, water treatment plants, sensors, comms towers, seawalls — realistic urban infrastructure, not synthetic CNC mills.

## Architecture — Two Storage Layers

The `oracleagentmemory` SDK ships with 4 native record types in its MEMORY table (`fact`, `memory`, `preference`, `guideline`) — covering conversational and tribal-knowledge memory. For structured domain objects (asset registries, inspection findings), you bring your own SQL tables alongside — same connection, same Oracle vector engine.

| Layer | What lives here | Implementation |
|---|---|---|
| Auto-extracted `fact` / `preference` / `guideline` (SDK) | Inspector-level tribal knowledge from maintenance narratives | `thread.add_messages` triggers SDK extractor LLM |
| `CITY_ASSET` (hand-rolled SQL) | The 26 assets, with asset class | Bulk-loaded in Part 3 |
| `CITY_INSPECTION_FINDING` (hand-rolled SQL with `VECTOR(384)`) | All ~220 structured findings, embedded on `description` | Bulk-loaded in Part 4 |
| Scoping (`user_id` = inspector, `agent_id="CITY"`, `thread_id` = per asset) | Inspector-personal vs city-wide knowledge | Demoed in Part 5 |
| Context cards (SDK) | Per-asset thread briefing the LLM sees | Used in Part 6's `call_copilot` |

>  See `docs/overview.md` for the one-pager, `docs/sdk-data-model.md` for the SDK schema breakdown.

## Workshop Structure

| Part | Topic | TODOs |
|---|---|---|
| 1 | Oracle setup (Codespaces / ADB wallet auto-detected) | — |
| 2 | Embedder + SDK init | TODO 1 |
| 3 | City asset registry + auto-extraction from maintenance logs | TODO 2, 3 |
| 4 | Inspection findings + similar-finding search (`VECTOR_DISTANCE`) | TODO 4, 5 |
| 5 | Scoping: inspector-personal vs city-wide | — (guided demo) |
| 6 | End-to-end CityOps copilot + cross-inspector handoff demo | TODO 6 |

## Demo

Inspector A logs a finding on Harbor Bridge ("corrosion on Pier 2 bearing assemblies, ~25% section loss"). Days later, Inspector B inspects Harbor Bridge for a different concern. They've never met A. The copilot's response references A's prior finding, A's recommendation (timeline + materials), and the most recent grade — pulling from both the SDK's auto-extracted memory and the `CITY_INSPECTION_FINDING` SQL table via `VECTOR_DISTANCE()`. Zero human handoff.

## Status

 Workshop scaffolding in place. Notebooks and docs to follow.
