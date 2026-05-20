# Part 6: The CityOps Copilot — End-to-End

Everything you've built so far comes together here. One function, `call_copilot`, ties together:

- Thread resolution (SDK)
- Asset lookup (`CITY_ASSET` SQL table via `get_asset()`)
- The context card (SDK — central read primitive for conversational + extracted memory)
- Similar-finding search (`CITY_INSPECTION_FINDING` SQL table via `VECTOR_DISTANCE()`)
- LLM call (your `call_openai_chat`)
- Persistence (`thread.add_messages` — triggers auto-extraction on both messages)

## The Architecture

```
                 ┌────────────────────────────────────────────┐
                 │  call_copilot(narrative, inspector_id,     │
                 │               thread_id, asset_id)         │
                 └────────────────────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 1. Resolve thread            │
                  │    get_thread OR create_thread│
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 2. Asset record (SQL)        │
                  │    get_asset(asset_id)       │
                  │    → CITY_ASSET              │
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 3. Context card (SDK)        │
                  │    thread.get_context_card(  │
                  │      fallback_message_count=100,
                  │      max_recent_messages=10, │
                  │      max_relevant_results=8) │
                  │    {L} → one LLM call        │
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 4. Similar findings (SQL)    │
                  │    find_similar_findings(    │
                  │      narrative,              │
                  │      asset_id=asset_id, k=3) │
                  │    VECTOR_DISTANCE() + WHERE │
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 5. Assemble context string   │
                  │    (4 labelled sections)     │
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 6. Agent LLM call            │
                  │    {A} → one LLM call        │
                  └──────────────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │ 7. Persist: thread.add_messages│
                  │    [user_msg, assistant_msg] │
                  │    {L} {L} → extractor runs  │
                  │              on each message │
                  └──────────────────────────────┘
                                  │
                                  ▼
                          Return assistant answer
```

**LLM-call accounting per copilot turn:** 1 (context-card summary) + 1 (agent LLM) + 2 (extractor on user msg + extractor on assistant msg) = **~4 LLM calls per inspection report**. If the extractor's summary-refresh cadence kicks in (`context_summary_update_frequency`), add 1–2 more.

---

## TODO 6: Implement `call_copilot`

**Complete solution:**

```python
def call_copilot(narrative: str, inspector_id: str, thread_id: str, asset_id: str) -> str:
    """End-to-end copilot turn: build context, query LLM, persist."""
    # 1. Resolve thread.
    try:
        t = memory.get_thread(thread_id)
    except Exception:
        t = None
    if t is None:
        t = memory.create_thread(
            user_id=inspector_id,
            thread_id=thread_id,
            agent_id="CITY",
        )

    # 2. Asset record — straight SQL lookup against CITY_ASSET.
    asset = get_asset(asset_id)
    asset_info = (
        f"Asset {asset['asset_id']} (class: {asset['asset_class']})"
        if asset else "(no asset record found)"
    )

    # 3. Context card (thread state + extracted facts/guidelines).
    card = t.get_context_card(
        fallback_message_count=100,
        max_recent_messages=10,
        max_relevant_results=8,
    )

    # 4. Similar past findings — VECTOR_DISTANCE() SQL on CITY_INSPECTION_FINDING.
    similar = find_similar_findings(narrative, asset_id=asset_id, k=3)
    if similar:
        similar_text = "\n\n".join(
            f"  (score={r['score']:.3f})  [{r['category']}/{r['severity']}] "
            f"inspector={r['inspector']}, grade={r['overall_grade']}, days_ago={r['days_ago']}\n"
            f"     description: {r['description']}\n"
            f"     recommendation: {r['recommendation']}"
            for r in similar
        )
    else:
        similar_text = "  (no prior findings for this asset)"

    # 5. Assemble the context string.
    context = (
        f"# Current inspection narrative\n"
        f"Asset: {asset_id}\n"
        f"Inspector: {inspector_id}\n"
        f"Narrative: {narrative}\n\n"
        f"# Asset record\n{asset_info}\n\n"
        f"# Thread context\n{card.formatted_content}\n\n"
        f"# Similar past findings (from CITY_INSPECTION_FINDING)\n{similar_text}"
    )

    # 6. LLM call.
    messages = [
        {"role": "system", "content": COPILOT_SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]
    resp = call_openai_chat(messages)
    answer = resp.choices[0].message.content or ""

    # 7. Persist — both messages trigger SDK auto-extraction.
    t.add_messages([
        Message(role="user",      content=f"[{inspector_id} @ {asset_id}] {narrative}"),
        Message(role="assistant", content=answer),
    ])
    return answer
```

### Why `fallback_message_count=100`?

The SDK's default is **5** — meaning the summary LLM only sees the last 5 messages from the thread when generating the `<summary>` block of the context card. On a multi-inspection asset thread, that's too few to capture history.

Passing 100 lets the LLM see up to 100 most recent messages (capped further by `memory_extraction_token_limit=100000`). The token cost rises; for very long-lived asset threads cap at 50 or 30 depending on your LLM's pricing.

### Why include the asset record separately?

The asset record lives in `CITY_ASSET`, a hand-rolled SQL table outside the SDK entirely. The SDK has no way to surface it. Fetching it via `get_asset(asset_id)` puts the asset class (bridge / substation / pipeline / sensor / ...) into the LLM's prompt with one primary-key lookup.

### Why include similar findings separately?

Same reason — `CITY_INSPECTION_FINDING` is outside the SDK. The context card surfaces only the SDK natives (`fact` / `memory` / `preference` / `guideline`). Findings have structured fields (`category`, `severity`, `recommendation`, `inspector`, `overall_grade`) that the SDK doesn't model, so they need their own SQL fetch.

---

## The Cross-Inspector Handoff Scenario

The final three cells of the notebook are the demo. Read them carefully — they're the whole point of the workshop.

**Day 1 — Inspector Mercer logs a Harbor Bridge corrosion finding.** Calls `call_copilot` with her observation, then calls `log_finding` to formally record it with category, severity, and recommendation.

**Day 1 (later) — Mercer follow-up note.** Same `thread_id`, same `asset_id`. The copilot's context card now includes Mercer's earlier turn. Auto-extracted guidelines about Pier 2 corrosion will surface in future calls.

**Day N — Inspector Vance arrives.** Never met Mercer. Same `thread_id` (per-asset). New narrative about Harbor Bridge. The copilot has:

- Mercer's earlier messages in the thread's `<recent_messages>` block (SDK)
- Auto-extracted facts/guidelines from Mercer's turns (SDK, surfaced via `<relevant_information>`)
- Mercer's finding in `CITY_INSPECTION_FINDING` surfacing as the top similar-failure hit (SQL, via `find_similar_findings`)

**The copilot's response to Vance is rich with Mercer's context, with zero human handoff.** This is the workshop's clincher.

---

## The Stateless Comparison

The last cell runs the same Vance narrative through a stateless OpenAI call — no thread, no context card, no `find_similar_findings`. Just `system + user_message → LLM`. Print the two responses side by side.

The stateless agent will give a generic answer ("check the bearings, look for visible rust, document with photos"). The memory-enabled copilot will reference Mercer's earlier 25%-section-loss finding, name the recommended primer-and-coat schedule, ask about progression of the corrosion measurement, and possibly cite the prior overall grade.

This is the workshop in one screenshot.

---

## Things The Production Version Adds

| What | Why |
|---|---|
| Push the finding back to your inspection-tracking system (Cityworks, ProjectMates, etc.) when the copilot helps confirm a diagnosis | Closes the loop with the system of record |
| `record_type="failure_pattern"` aggregated from findings (well, actually a `CITY_FAILURE_PATTERN` SQL table since the SDK rejects custom types) | Higher-confidence guidance than raw findings |
| Geospatial column on `CITY_ASSET` (`SDO_GEOMETRY` lat/lon) | Enable "findings within 500m of this asset" queries |
| `discover_tools(query)` meta-tool | When tool count grows past ~20, let the LLM discover them mid-loop |
| VPD policy on `CITY_MEMORY` | Hard row-level security for regulated environments |
| External cache on `get_context_card` keyed by `(thread_id, msg_count)` | Cut the per-turn LLM cost by avoiding redundant summary calls |

The workshop's harness is deliberately small. Each of the above is a clean extension on top.
