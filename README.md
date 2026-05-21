# CityOps Copilot — Agent Memory Workshop
 A hands-on workshop on the fundamentals of agent memory — the architectural patterns that let AI agents remember across sessions, across
  users, and within the hard ceiling of the LLM's context window. You'll learn the distinct memory types that matter (typed semantic facts vs
   structured domain objects vs ephemeral conversation), how the context-window token budget shapes every retrieval decision, how to compress
   long history with running summaries and on-demand context cards, and how to mix vector similarity with relational filters for precise
  recall. The concepts land through a realistic use case — a city-infrastructure inspection copilot seeded with 308 real maintenance
  narratives and ~220 structured findings across 26 urban assets — so you spend the time understanding the patterns, not faking data. The wow
   moment is a cross-inspector handoff: Inspector B walks up to a bridge that Inspector A inspected last quarter, and the copilot surfaces
  A's findings, recommendations, and tribal observations with zero human briefing. Implemented on Oracle AI Database with the
  oracleagentmemory SDK, but the architectural patterns transfer to any agent-memory stack — you walk away with a mental model that maps onto
   whatever you build next.

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

The `oracleagentmemory` SDK  allows 4 record types in its MEMORY table (`fact`, `memory`, `preference`, `guideline`). Domain objects need their own SQL tables on the same connection.

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
