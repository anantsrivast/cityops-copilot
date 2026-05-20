# Workshop TODO Checklist

6 hands-on tasks across Parts 2–6. Complete them in order — each builds on the last.

Part 1 (Oracle setup) is pre-built — just run the cells to connect.

---

### Part 2 — Embedder + SDK ([Guide](part-2-embedder-and-sdk.md))

1. Implement `LocalSentenceTransformerEmbedder(IEmbedder)` — bridge sentence-transformers to the SDK (TODO 1)

### Part 3 — City Assets + Auto-Extraction ([Guide](part-3-city-assets-and-extraction.md))

2. Implement `report_event(asset_id, inspector, narrative, thread_id)` — wraps `thread.add_messages` to trigger SDK auto-extraction on a maintenance narrative (TODO 2)
3. Pick ~8 narratives from `data/maintenance_logs.json` spanning different assets / severities, run them through `report_event`, and inspect the typed records the extractor produced (TODO 3)

### Part 4 — Inspection Findings + Similar-Finding Search ([Guide](part-4-findings-and-search.md))

4. Implement `log_finding(asset_id, inspector, category, severity, description, recommendation, overall_grade)` — INSERT a row into `CITY_INSPECTION_FINDING` with a `VECTOR(384)` embedding on the description (TODO 4)
5. Implement `find_similar_findings(description, asset_id=None, category=None, k=3)` — one SQL statement using `VECTOR_DISTANCE()` mixed with asset and category filters (TODO 5)

### Part 5 — Scoping Demo ([Guide](part-5-scoping.md))

*No TODO — runs as a guided demo with assertions.*

### Part 6 — End-to-End Copilot ([Guide](part-6-copilot-end-to-end.md))

6. Implement `call_copilot(narrative, inspector_id, thread_id, asset_id)` — assemble context card + `find_similar_findings` + LLM call + persist (TODO 6)

---

## After You Finish

Run the **cross-inspector handoff scenario** at the end of Part 6. Inspector Mercer logs a corrosion concern on Harbor Bridge and a recommendation. Days later, a different inspector — who has never met Mercer — encounters a related concern on the same asset. The copilot surfaces Mercer's prior finding (severity, recommendation, time-to-remediate), the relevant guidelines extracted from the maintenance narratives, and any tribal knowledge from the asset's thread. Compare against a stateless LLM response on the same narrative — the difference is the workshop's point.
