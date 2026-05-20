"""Generate notebook_complete.ipynb by replacing each TODO cell in
notebook_student.ipynb with its working solution.

Run after notebook_student.ipynb has been generated:
    python3 _build_complete_notebook.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDENT = HERE / "notebook_student.ipynb"
COMPLETE = HERE / "notebook_complete.ipynb"

with STUDENT.open() as f:
    nb = json.load(f)


def cell_source(cell) -> str:
    s = cell["source"]
    return s if isinstance(s, str) else "".join(s)


def replace_cell_source(idx: int, new_source: str):
    nb["cells"][idx]["source"] = new_source


MARKERS = {
    "TODO 1": "class LocalSentenceTransformerEmbedder(IEmbedder):",
    "TODO 2": "def report_event(asset_id: str, inspector: str, narrative: str, thread_id: str) -> list:",
    "TODO 3": "# TODO 3:",
    "TODO 4": "def log_finding(",
    "TODO 5": "def find_similar_findings(description: str, asset_id: str = None, category: str = None, k: int = 3) -> list:",
    "TODO 6": "def call_copilot(narrative: str, inspector_id: str, thread_id: str, asset_id: str) -> str:",
}

found = {}
for i, c in enumerate(nb["cells"]):
    if c["cell_type"] != "code":
        continue
    src = cell_source(c)
    for name, marker in MARKERS.items():
        if name in found:
            continue
        if marker in src:
            found[name] = i
            break

missing = set(MARKERS) - set(found)
if missing:
    raise SystemExit(f"Could not find cells for: {sorted(missing)}")

# ────────────────────────────────────────────────────────────────────────────
# TODO 1 — Embedder
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 1"], (
    "from oracleagentmemory.apis.embedders.embedder import IEmbedder\n"
    "from sentence_transformers import SentenceTransformer\n"
    "import numpy as np\n"
    "import asyncio\n"
    "\n"
    "\n"
    "class LocalSentenceTransformerEmbedder(IEmbedder):\n"
    "    \"\"\"Bridges sentence-transformers to the SDK's IEmbedder.\"\"\"\n"
    "\n"
    "    def __init__(self, model_name: str = \"sentence-transformers/all-MiniLM-L6-v2\"):\n"
    "        self.model = SentenceTransformer(model_name)\n"
    "\n"
    "    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:\n"
    "        arr = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)\n"
    "        return arr.astype(np.float32)\n"
    "\n"
    "    async def embed_async(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:\n"
    "        return await asyncio.to_thread(self.embed, texts, is_query=is_query)\n"
))

# ────────────────────────────────────────────────────────────────────────────
# TODO 2 — report_event
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 2"], (
    "def report_event(asset_id: str, inspector: str, narrative: str, thread_id: str) -> list:\n"
    "    \"\"\"Persist a maintenance event narrative and trigger SDK auto-extraction.\"\"\"\n"
    "    try:\n"
    "        t = memory.get_thread(thread_id)\n"
    "    except Exception:\n"
    "        t = None\n"
    "    if t is None:\n"
    "        t = memory.create_thread(\n"
    "            user_id=inspector,\n"
    "            thread_id=thread_id,\n"
    "            agent_id=\"CITY\",\n"
    "        )\n"
    "    content = f\"[Asset: {asset_id}] [Inspector: {inspector}] {narrative}\"\n"
    "    return t.add_messages([Message(role=\"user\", content=content)])\n"
))

# ────────────────────────────────────────────────────────────────────────────
# TODO 3 — submit 8 narratives and inspect
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 3"], (
    "for narr in narratives:\n"
    "    report_event(\n"
    "        asset_id=narr[\"asset_name\"],\n"
    "        inspector=\"inspector_demo\",\n"
    "        narrative=narr[\"narrative\"],\n"
    "        thread_id=\"inspect_demo\",\n"
    "    )\n"
    "\n"
    "# The SDK's high-level search requires a specific user_id (rejects\n"
    "# exact_user_match=False). The records inherit user_id from the thread,\n"
    "# which we created with inspector=\"inspector_demo\".\n"
    "results = memory.search(\n"
    "    query=\"recurring asset concerns and inspector practices\",\n"
    "    user_id=\"inspector_demo\",\n"
    "    agent_id=\"CITY\",\n"
    "    record_types=[\"fact\", \"preference\", \"guideline\", \"memory\"],\n"
    "    max_results=30,\n"
    ")\n"
    "for r in results:\n"
    "    print(f\"  [{r.record.record_type:11s}] {r.record.content}\")\n"
))

# ────────────────────────────────────────────────────────────────────────────
# TODO 4 — log_finding
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 4"], (
    "import array, uuid\n"
    "\n"
    "def log_finding(\n"
    "    asset_id: str,\n"
    "    inspector: str,\n"
    "    category: str,\n"
    "    severity: str,\n"
    "    description: str,\n"
    "    recommendation: str = \"\",\n"
    "    overall_grade: str = None,\n"
    "    days_ago: int = 0,\n"
    ") -> str:\n"
    "    \"\"\"Persist a new inspection finding into CITY_INSPECTION_FINDING.\"\"\"\n"
    "    finding_id = str(uuid.uuid4())[:12]\n"
    "    # array.array('f', ...) is what oracledb needs for VECTOR binds.\n"
    "    # A plain Python list would trigger ORA-01484.\n"
    "    vec = array.array('f', embedder.embed([description])[0].tolist())\n"
    "    with vector_conn.cursor() as cur:\n"
    "        cur.execute(\n"
    "            \"\"\"INSERT INTO CITY_INSPECTION_FINDING\n"
    "                 (finding_id, asset_id, inspector, overall_grade, category, severity,\n"
    "                  description, recommendation, days_ago, embedding)\n"
    "               VALUES (:finding_id, :asset_id, :inspector, :overall_grade, :category, :severity,\n"
    "                       :description, :recommendation, :days_ago, :embedding)\"\"\",\n"
    "            finding_id=finding_id, asset_id=asset_id, inspector=inspector,\n"
    "            overall_grade=overall_grade, category=category, severity=severity,\n"
    "            description=description, recommendation=recommendation,\n"
    "            days_ago=days_ago, embedding=vec,\n"
    "        )\n"
    "    vector_conn.commit()\n"
    "    return finding_id\n"
))

# ────────────────────────────────────────────────────────────────────────────
# TODO 5 — find_similar_findings
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 5"], (
    "def find_similar_findings(description: str, asset_id: str = None, category: str = None, k: int = 3) -> list:\n"
    "    \"\"\"Vector-search CITY_INSPECTION_FINDING, optionally narrowed to one asset and/or category.\n"
    "\n"
    "    Returns a list of dicts with all the structured fields + a `score` (cosine distance).\n"
    "    \"\"\"\n"
    "    import array\n"
    "    query_vec = array.array('f', embedder.embed([description])[0].tolist())\n"
    "    sql = \"\"\"\n"
    "        SELECT finding_id, asset_id, inspector, overall_grade, category, severity,\n"
    "               description, recommendation, days_ago,\n"
    "               VECTOR_DISTANCE(embedding, :q, COSINE) AS score\n"
    "          FROM CITY_INSPECTION_FINDING\n"
    "         WHERE (:asset_id IS NULL OR asset_id = :asset_id)\n"
    "           AND (:category IS NULL OR category = :category)\n"
    "         ORDER BY score\n"
    "         FETCH FIRST :k ROWS ONLY\n"
    "    \"\"\"\n"
    "    with vector_conn.cursor() as cur:\n"
    "        cur.execute(sql, q=query_vec, asset_id=asset_id, category=category, k=k)\n"
    "        cols = [d[0].lower() for d in cur.description]\n"
    "        rows = []\n"
    "        for r in cur.fetchall():\n"
    "            row = dict(zip(cols, r))\n"
    "            for key in (\"description\", \"recommendation\"):\n"
    "                v = row.get(key)\n"
    "                if v is not None and hasattr(v, \"read\"):\n"
    "                    row[key] = v.read()\n"
    "            rows.append(row)\n"
    "    return rows\n"
))

# ────────────────────────────────────────────────────────────────────────────
# TODO 6 — call_copilot
# ────────────────────────────────────────────────────────────────────────────

replace_cell_source(found["TODO 6"], (
    "def call_copilot(narrative: str, inspector_id: str, thread_id: str, asset_id: str) -> str:\n"
    "    \"\"\"End-to-end CityOps copilot turn: build context, query LLM, persist.\"\"\"\n"
    "    # 1. Resolve thread.\n"
    "    try:\n"
    "        t = memory.get_thread(thread_id)\n"
    "    except Exception:\n"
    "        t = None\n"
    "    if t is None:\n"
    "        t = memory.create_thread(\n"
    "            user_id=inspector_id,\n"
    "            thread_id=thread_id,\n"
    "            agent_id=\"CITY\",\n"
    "        )\n"
    "\n"
    "    # 2. Asset record — straight SQL lookup against CITY_ASSET.\n"
    "    asset = get_asset(asset_id)\n"
    "    asset_info = (\n"
    "        f\"Asset {asset['asset_id']} (class: {asset['asset_class']})\"\n"
    "        if asset else \"(no asset record found)\"\n"
    "    )\n"
    "\n"
    "    # 3. Context card (thread state + extracted facts/guidelines).\n"
    "    card = t.get_context_card(\n"
    "        fallback_message_count=100,\n"
    "        max_recent_messages=10,\n"
    "        max_relevant_results=8,\n"
    "    )\n"
    "\n"
    "    # 4. Similar past findings on this asset.\n"
    "    similar = find_similar_findings(narrative, asset_id=asset_id, k=3)\n"
    "    if similar:\n"
    "        similar_text = \"\\n\\n\".join(\n"
    "            f\"  (score={r['score']:.3f})  [{r['category']}/{r['severity']}]  \"\n"
    "            f\"inspector={r['inspector']}, grade={r['overall_grade']}, days_ago={r['days_ago']}\\n\"\n"
    "            f\"     description: {r['description']}\\n\"\n"
    "            f\"     recommendation: {r['recommendation']}\"\n"
    "            for r in similar\n"
    "        )\n"
    "    else:\n"
    "        similar_text = \"  (no prior findings for this asset)\"\n"
    "\n"
    "    # 5. Assemble the context string.\n"
    "    context = (\n"
    "        f\"# Current inspection narrative\\n\"\n"
    "        f\"Asset: {asset_id}\\n\"\n"
    "        f\"Inspector: {inspector_id}\\n\"\n"
    "        f\"Narrative: {narrative}\\n\\n\"\n"
    "        f\"# Asset record\\n{asset_info}\\n\\n\"\n"
    "        f\"# Thread context\\n{card.formatted_content}\\n\\n\"\n"
    "        f\"# Similar past findings (from CITY_INSPECTION_FINDING)\\n{similar_text}\"\n"
    "    )\n"
    "\n"
    "    # 6. LLM call.\n"
    "    messages = [\n"
    "        {\"role\": \"system\", \"content\": COPILOT_SYSTEM_PROMPT},\n"
    "        {\"role\": \"user\",   \"content\": context},\n"
    "    ]\n"
    "    resp = call_openai_chat(messages)\n"
    "    answer = resp.choices[0].message.content or \"\"\n"
    "\n"
    "    # 7. Persist — both messages trigger SDK auto-extraction.\n"
    "    t.add_messages([\n"
    "        Message(role=\"user\",      content=f\"[{inspector_id} @ {asset_id}] {narrative}\"),\n"
    "        Message(role=\"assistant\", content=answer),\n"
    "    ])\n"
    "    return answer\n"
))

# ────────────────────────────────────────────────────────────────────────────
# Emit
# ────────────────────────────────────────────────────────────────────────────

COMPLETE.write_text(json.dumps(nb, indent=1, ensure_ascii=False))
print(f"Wrote {COMPLETE} ({len(nb['cells'])} cells, {len(found)} TODOs filled in)")
