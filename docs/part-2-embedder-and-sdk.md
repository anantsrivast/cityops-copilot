# Part 2: The Embedder and the SDK

## What This Part Sets Up

The `oracleagentmemory` SDK handles vectorisation, similarity search, schema creation, and auto-extraction — but it doesn't ship with an embedding model. It expects you to plug in an `IEmbedder` of your choice. For this workshop you will use `sentence-transformers/all-MiniLM-L6-v2` locally:

- No API key needed (runs on CPU)
- No per-call cost
- 384 dimensions — matches the SDK's default `vector_dim` AND will match the embedding column we add to `CITY_INSPECTION_FINDING` in Part 4

## The `IEmbedder` Interface

The SDK accepts any object implementing:

```python
class IEmbedder(ABC):
    def embed(self, texts: list[str], *, is_query: bool = False) -> numpy.ndarray: ...
    async def embed_async(self, texts: list[str], *, is_query: bool = False) -> numpy.ndarray: ...
```

Both methods return a 2D `float32` array of shape `(len(texts), dim)`. The `is_query` flag is a hint some embedders use to apply different prompt prefixes for queries vs documents; `all-MiniLM-L6-v2` doesn't care.

---

## TODO 1: Implement `LocalSentenceTransformerEmbedder`

**Complete solution:**

```python
from oracleagentmemory.apis.embedders.embedder import IEmbedder
from sentence_transformers import SentenceTransformer
import numpy as np
import asyncio


class LocalSentenceTransformerEmbedder(IEmbedder):
    """Bridges sentence-transformers to the SDK's IEmbedder."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        arr = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return arr.astype(np.float32)

    async def embed_async(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        return await asyncio.to_thread(self.embed, texts, is_query=is_query)
```

**Why `normalize_embeddings=True`?** Cosine similarity over unit vectors becomes a simple dot product.

**Why `.astype(np.float32)`?** Oracle's `VECTOR(384)` column expects 32-bit floats. `sentence-transformers` already returns `float32`, but the cast guards against model swaps later.

>  First `SentenceTransformer(...)` call downloads ~90MB. Subsequent runs use the cached model.

---

## The SDK Initialization (Pre-Built — No TODO)

```python
sdk_llm = Llm(
    model="openai/xai.grok-3-fast",
    api_base=OCI_GENAI_ENDPOINT,
    api_key=OCI_GENAI_API_KEY,
)

memory = OracleAgentMemory(
    connection=vector_conn,
    embedder=embedder,
    llm=sdk_llm,
    extract_memories=True,
    schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,
    table_name_prefix="CITY_",
)
```

**Why `extract_memories=True`?** Turns on automatic LLM-driven extraction of `fact` / `preference` / `guideline` / `memory` from every message you write via `thread.add_messages`. Without it, the SDK is just a storage layer.

**Why `schema_policy=CREATE_IF_NECESSARY`?** Creates whatever tables are missing, leaves existing ones alone. Idempotent across re-runs.

**Why `table_name_prefix="CITY_"`?** Namespaces the SDK's tables (`CITY_THREAD`, `CITY_MESSAGE`, etc.). Prevents collisions with other workshops or applications.

**Why a separate `sdk_llm`?** The SDK uses this LLM internally for memory extraction and summary updates. Your agent's own LLM calls (Part 6) use the OpenAI `client` — different instance, same endpoint.

## What Gets Created When You Run This Cell

The SDK creates 5 tables under the `CITY_*` prefix:

| Table | What it holds |
|---|---|
| `CITY_THREAD` | One row per per-asset thread (with `runtime_config` JSON for the cached running summary) |
| `CITY_ACTOR_PROFILE` | Inspectors + agents in one table |
| `CITY_MESSAGE` | All inspection narratives |
| `CITY_MEMORY` | Auto-extracted `fact` / `preference` / `guideline` / `memory` records |
| `CITY_RECORD_CHUNKS` | One shared `VECTOR(384)` column + HNSW index over all SDK embeddings |

In Part 3 we add `CITY_ASSET`. In Part 4 we add `CITY_INSPECTION_FINDING` with its **own** `VECTOR(384)` column + HNSW index — independent from the SDK's index but sharing the same dimensionality and metric.

## Troubleshooting

**`ImportError: oracleagentmemory.apis.embedders.embedder`** — Confirm `pip show oracleagentmemory` reports 26.4.0+.

**Schema bootstrap fails with `ORA-51962`** — Oracle's vector memory area isn't allocated. The Codespace's `setup_runtime.sh` fixes this; for local Oracle Free run `ALTER SYSTEM SET vector_memory_size = 1G SCOPE=SPFILE;` as SYS then restart.

**`embed()` returns a 1D array** — Wrapper is calling `encode` on a single string. The interface requires a list input even for one text.

**`dtype` is `float64`** — `.astype(np.float32)` cast missing. SDK fails at insertion if dtype doesn't match.
