# Part 1: Oracle Setup

## What You Are Working With

Oracle AI Database is not a separate AI product — it is the core Oracle Database engine with native support for `VECTOR` columns, HNSW indexes, and SQL `VECTOR_DISTANCE()`. The workshop's memory layer lives in a single queryable, ACID-compliant database — not a vector store bolted on the side.

The `oracleagentmemory` SDK creates its tables and HNSW index for you in Part 2. The workshop also creates two **hand-rolled** SQL tables (`CITY_ASSET` and `CITY_INSPECTION_FINDING`) alongside the SDK's tables — same connection, same engine. Your job in Part 1 is just to confirm Oracle is reachable.

## Two Environments — Same Notebook

The `connect_to_oracle` helper auto-detects the environment:

| Mode | Trigger | Used for |
|---|---|---|
| **Wallet / ADB** | `ORACLE_WALLET_LOCATION` is set in env | Local dev against Oracle Autonomous Database via mTLS |
| **Local / Codespaces** | `ORACLE_WALLET_LOCATION` is **not** set | Codespace default — Oracle Free Docker container at `localhost:1521/FREEPDB1` |

### Wallet Mode (Local Development)

Set these in your shell or in a project-root `.env` file:

```bash
ORACLE_WALLET_LOCATION=/path/to/unzipped/wallet
ORACLE_USER=ADMIN
ORACLE_PASSWORD=<your-db-password>
ORACLE_DSN=<full-TNS-descriptor-or-alias>
ORACLE_WALLET_PASSWORD=<your-wallet-password-or-empty-for-auto-login>
```

The notebook's first cell (`Load environment from .env`) reads them. Set them once, run the workshop unchanged.

### Local Mode (Codespaces — Default)

No env vars needed. The function falls back to:

```python
oracledb.connect(
    user="VECTOR",
    password="VectorPwd_2025",
    dsn="localhost:1521/FREEPDB1",
)
```

These match the credentials baked into `.devcontainer/docker-compose.yml`.

## Connecting

After running the helper + the `vector_conn = connect_to_oracle()` cell, you should see:

```
 Loaded env vars from /path/to/.env
  mode: ADB / wallet  (...)
Connection attempt 1/3 — ADB (...)...
 Connected as ANANT.
```

Or, in Codespaces:

```
ℹ No .env file found — assuming env vars are set externally
  mode: local (Codespaces / Oracle Free on localhost:1521)
Connection attempt 1/3 — local (localhost:1521/FREEPDB1)...
 Connected as VECTOR.
```

## Coexistence

If you have run other workshops against the same Oracle instance, their tables will still be present. This is fine — this workshop creates its own tables under prefix `CITY_*` and they will not collide. You can leave older tables in place or drop them at your discretion.

## Troubleshooting

**"ORA-12541: TNS:no listener"** — The listener is still starting. Wait 30s and retry.

**"ORA-01017: invalid username/password"** — Verify you're using the right credentials for the mode (`VECTOR` / `VectorPwd_2025` for local; your ADB user/password for wallet mode).

**"Could not reach Oracle after all retries"** in Codespaces — Rebuild the Codespace via VS Code command palette: `Codespaces: Rebuild Container`.

**Vector-related errors later** — See `troubleshooting.md`. The most common is `ORA-51962` (vector memory area not allocated); this workshop's `setup_runtime.sh` handles that automatically for Codespaces, but local-Oracle-Free setups need `ALTER SYSTEM SET vector_memory_size = 1G SCOPE=SPFILE;` followed by a restart.
