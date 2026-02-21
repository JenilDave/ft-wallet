## FT Wallet

**FT-Wallet** (Fault-Tolerant Wallet) is a distributed banking system that manages user accounts with automatic failover protection. It ensures that no money is ever lost, even if servers crash mid-transaction.

**Think of it like this:**
- A primary cashier handles all transactions (HTTP server)
- A backup cashier watches and copies every transaction (gRPC server)
- If the primary cashier disappears, the backup is always in sync and ready

### Why You Need This

Imagine you're withdrawing $100 from an ATM:
- ❌ **Without Fault Tolerance**: Server crashes mid-transaction → Money vanishes or gets doubled
- ✅ **With FT-Wallet**: Both primary and backup have identical records → You always get your money

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────┐
│         Client (External)           │
│   (Your App / Mobile / Web)         │
└────────────────┬────────────────────┘
                 │ 
                 │ HTTP REST API
                 │ (Port 8000)
                 ↓
┌─────────────────────────────────────────────────────────────┐
│         Primary Server (FastAPI)                            │
│  - Handles all client requests                              │
│  - Exposes REST API endpoints                               │
│  - Syncs with backup before executing transactions          │
│  - Maintains wallet state in memory + persists to JSON      │
│  - Listens on HTTP port 8000                                │
│  - Listens on gRPC port 50051 (for failover)                │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ gRPC (Sync First Protocol)
                 │ (Port 50052)
                 ↓
┌─────────────────────────────────────────────────────────────┐
│         Backup Server (gRPC)                                │
│  - Mirrors all transactions from primary                    │
│  - Maintains identical wallet state                         │
│  - Can take over if primary fails                           │
│  - Listens on gRPC port 50052                               │
└─────────────────────────────────────────────────────────────┘
```

### Transaction Flow

```
Client Request (with transaction_id)
        ↓
    [Primary HTTP Server]
        ↓
Step 1: Send to Backup (gRPC) ← MUST SUCCEED FIRST
        ↓
Step 2: Execute on Primary (if backup succeeds)
        ↓
Step 3: Persist both servers
        ↓
    Response to Client
```

**Key Principle:** Backup executes FIRST, then primary. This ensures backup always has the latest state.

---

## Components

### 1. **Primary Server** (`src/server/primary_server.py`)

The main HTTP server that clients interact with.

**Responsibilities:**
- Listen for HTTP requests from clients
- Communicate with backup server before executing transactions
- Maintain primary wallet state
- Implement failover detection

**Key Classes:**

| Class | Purpose |
|-------|---------|
| `PrimaryWalletClient` | gRPC client to communicate with backup |
| `PrimaryWalletService` | Main service orchestrating transactions |
| `PrimaryWalletServicer` | gRPC service for failover |

### 2. **Backup Server** (`src/server/backup_server.py`)

The passive gRPC server that shadows all primary operations.

**Responsibilities:**
- Listen for gRPC requests from primary
- Execute transactions and persist state
- Maintain exact copy of primary's wallet data

**Key Classes:**

| Class | Purpose |
|-------|---------|
| `WalletBackupServicer` | gRPC service handling backup operations |

### 3. **Wallet Service** (`src/services/wallet_service.py`)

Core business logic for wallet operations.

**Responsibilities:**
- Handle deposit/withdraw operations
- Implement idempotency using transaction IDs
- Write-Ahead Logging (WAL) for crash recovery
- Persist data to JSON files

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `deposit()` | Add money to account (idempotent) |
| `withdraw()` | Remove money from account (idempotent) |
| `get_balance()` | Check account balance |
| `_record_transaction_wal()` | Write transaction BEFORE executing |
| `_commit_transaction()` | Mark transaction as completed |
| `recover_pending_transactions()` | Recover from crashes |

### 4. **Failover Service** (`src/services/failover_service.py`)

Monitors system health and triggers failover if needed.

**Responsibilities:**
- Periodically check if backup is alive
- Set failover mode if backup becomes unreachable
- Resume normal sync when backup recovers

**Key Classes:**

| Class | Purpose |
|-------|---------|
| `FailoverManager` | Health monitoring and failover detection |

### 5. **HTTP Server** (`src/server/http_server.py`)

FastAPI application that exposes REST endpoints.

**Responsibilities:**
- Define REST API endpoints
- Handle request validation
- Manage server startup/shutdown
- Route requests to primary service

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- `uv` package manager (install from https://docs.astral.sh/uv/getting-started/)

### Step 1: Install `uv` (if not already installed)

**On macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**On Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Step 2: Create Virtual Environment and Install Dependencies

```bash
uv sync
```

This creates a `.venv` directory with an isolated Python environment with all dependencies installed.


### Step 3: Generate gRPC Code

The proto files define the gRPC service interface. Generate Python code from it:

```bash
python -m grpc_tools.protoc -I./protos \
  --python_out=./src/services \
  --grpc_python_out=./src/services \
  ./protos/wallet.proto
```

This creates:
- `src/services/wallet_pb2.py` - Data structures
- `src/services/wallet_pb2_grpc.py` - Service interface

### Step 4: Verify Structure

```
ft-wallet/
├── protos/
│   └── wallet.proto
├── src/
│   ├── __init__.py
│   ├── services/
│   │   ├── wallet_service.py
│   │   ├── failover_service.py
│   │   ├── wallet_pb2.py
│   │   └── wallet_pb2_grpc.py
│   └── server/
│       ├── primary_server.py
│       ├── backup_server.py
│       └── http_server.py
├── example_client.py
├── requirements.txt
├── pyproject.toml
└── wallets.json (created at runtime)
```

## Running the System

### Terminal 1: Start Backup Server

```bash
python -m src.server.backup_server
```

**Expected Output:**
```
INFO:services.wallet_service:WAL: Recorded PENDING transaction xxx
INFO:src.server.backup_server:Backup server listening on [::]:50052
```

The backup listens on `localhost:50052` for gRPC requests from primary.

### Terminal 2: Start Primary Server

```bash
python -m src.server.http_server
```

**Expected Output:**
```
INFO:src.server.primary_server:Primary gRPC server listening on [::]:50051
INFO:src.server.primary_server:Connected to backup server at localhost:50052
INFO:src.server.http_server:Primary service initialized with failover support
Uvicorn running on http://0.0.0.0:8000
```

The primary listens on:
- HTTP: `localhost:8000` (for client requests)
- gRPC: `localhost:50051` (for failover detection)
- Connects to Backup: `localhost:50052` (for sync)

### Terminal 3: Run Client Tests

```bash
python example_client.py
```

---

## API Reference

### 1. Deposit Money

**Endpoint:** `POST /deposit`

**Request Body:**
```json
{
  "account_id": "user123",
  "amount": 1000.50,
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Deposited 1000.5",
  "new_balance": 1000.5,
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Failure):**
```json
{
  "detail": "Amount must be positive"
}
```

### 2. Withdraw Money

**Endpoint:** `POST /withdraw`

**Request Body:**
```json
{
  "account_id": "user123",
  "amount": 250.50,
  "transaction_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Withdrew 250.5",
  "new_balance": 750.0,
  "transaction_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Failure - Insufficient Funds):**
```json
{
  "detail": "Insufficient balance"
}
```

### 3. Check Balance

**Endpoint:** `POST /balance`

**Request Body:**
```json
{
  "account_id": "user123"
}
```

**Response:**
```json
{
  "success": true,
  "balance": 750.0,
  "message": "Balance retrieved"
}
```

### 4. Health Check

**Endpoint:** `GET /health`

**Response (Healthy):**
```json
{
  "status": "healthy"
}
```

**Response (Initializing):**
```json
{
  "status": "initializing"
}
```

---

## Client Usage

### Using the Example Client

```python
from example_client import deposit_with_retry, withdraw_with_retry, get_balance_with_retry

# Deposit $1000
deposit_with_retry("user123", 1000.00)

# Check balance
get_balance_with_retry("user123")

# Withdraw $250
withdraw_with_retry("user123", 250.50)

# Check balance again
get_balance_with_retry("user123")
```

### Manual Client (Using requests)

```python
import uuid
import requests

# Client generates unique transaction ID
txn_id = str(uuid.uuid4())

# Deposit money
response = requests.post(
    "http://localhost:8000/deposit",
    json={
        "account_id": "user123",
        "amount": 500.00,
        "transaction_id": txn_id
    },
    timeout=5
)

print(response.json())
```

### Using cURL

```bash
# Deposit
curl -X POST http://localhost:8000/deposit \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "user123",
    "amount": 1000.00,
    "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
  }'

# Check balance
curl -X POST http://localhost:8000/balance \
  -H "Content-Type: application/json" \
  -d '{"account_id": "user123"}'
```

---

## Key Features

### 1. **Idempotency**

Every request includes a unique `transaction_id`. If you retry with the same ID, you get the same result without double-spending.

**Example:**
```python
txn_id = "550e8400-e29b-41d4-a716-446655440000"

# First request: Deposits $100
requests.post(..., json={"account_id": "user123", "amount": 100, "transaction_id": txn_id})

# Second request with SAME txn_id: Returns same result, no double deposit
requests.post(..., json={"account_id": "user123", "amount": 100, "transaction_id": txn_id})
```

**How it works:**
- Server tracks all completed transactions
- If same `transaction_id` is seen again, cached result is returned
- Money is transferred only once ✅

### 2. **Write-Ahead Logging (WAL)**

Transactions are logged BEFORE execution. If server crashes mid-transaction, it can recover without data loss.

**Transaction States:**

```
1. PENDING → Transaction recorded to disk
2. EXECUTE → Money transferred
3. COMMITTED → Transaction marked complete
```

If crash happens at step 2, recovery logic detects PENDING transaction and rolls it back safely.

### 3. **Automatic Retries**

Client automatically retries on:
- Network timeouts
- Connection errors  
- Server errors (5xx)

```python
for attempt in range(1, max_retries + 1):
    try:
        response = requests.post(...)
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.Timeout:
        time.sleep(1)
        continue  # Retry
```

### 4. **Failover Detection**

`FailoverManager` monitors backup server health every 5 seconds:

```
✓ Backup responding → Normal mode
✗ Backup not responding → Failover mode
  - Primary continues operating independently
  - Skips backup sync
  - All changes stored locally
✓ Backup recovers → Resume sync automatically
```

### 5. **Persistence**

Both servers save wallet data to JSON files:

```
primary_wallets.json
├── "user123": 1000.5
├── "user456": 500.0
└── ...

primary_transactions.json
├── "txn_id_1": {status: COMMITTED, success: true, ...}
├── "txn_id_2": {status: ROLLED_BACK, ...}
└── ...
```

---

## Common `uv` Commands

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Install dependencies
uv pip install -r requirements.txt

# Add a new package
uv pip install <package-name>

# Remove a package
uv pip uninstall <package-name>

# List installed packages
uv pip list

# Run Python script
python script.py

# Deactivate virtual environment
deactivate
```

---

## Performance Notes

- **Synchronous transfers:** Primary waits for backup response (consistency guaranteed)
- **Timeout:** 5 seconds per request
- **Health checks:** Every 5 seconds (adjustable in `failover_service.py`)
- **Persistence:** Atomic file writes to prevent corruption
- **Scalability:** Current implementation handles ~100 requests/second per instance

---

Happy banking! 🏦💰