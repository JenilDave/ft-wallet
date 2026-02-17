import logging
from typing import Optional
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.primary_server import initialize_primary_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global primary service instance
primary_service = None

# Request/Response models
class TransactionRequest(BaseModel):
    account_id: str = Field(..., description="Account ID")
    amount: float = Field(..., gt=0, description="Amount to transfer")

class BalanceRequest(BaseModel):
    account_id: str = Field(..., description="Account ID")

class TransactionResponse(BaseModel):
    success: bool
    message: str
    new_balance: float

class BalanceResponse(BaseModel):
    success: bool
    balance: float
    message: str

# FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global primary_service
    logger.info("Starting FastAPI server...")
    primary_service = await initialize_primary_service(backup_host="localhost", backup_port=50052)
    logger.info("Primary service initialized")
    yield
    # Shutdown
    logger.info("Shutting down FastAPI server...")

# Create FastAPI app
app = FastAPI(
    title="FT-Wallet API",
    description="Fault-Tolerant Wallet with Primary and Backup Servers",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/withdraw", response_model=TransactionResponse)
async def withdraw(request: TransactionRequest):
    """Withdraw money from account"""
    try:
        if primary_service is None:
            raise HTTPException(status_code=500, detail="Service not initialized")
        
        success, message, new_balance = await primary_service.withdraw(
            request.account_id,
            request.amount
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return TransactionResponse(
            success=success,
            message=message,
            new_balance=new_balance
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Withdraw error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/deposit", response_model=TransactionResponse)
async def deposit(request: TransactionRequest):
    """Deposit money to account"""
    try:
        if primary_service is None:
            raise HTTPException(status_code=500, detail="Service not initialized")
        
        success, message, new_balance = await primary_service.deposit(
            request.account_id,
            request.amount
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return TransactionResponse(
            success=success,
            message=message,
            new_balance=new_balance
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deposit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/balance", response_model=BalanceResponse)
async def get_balance(request: BalanceRequest):
    """Get account balance"""
    try:
        if primary_service is None:
            raise HTTPException(status_code=500, detail="Service not initialized")
        
        success, balance, message = await primary_service.get_balance(request.account_id)
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return BalanceResponse(
            success=success,
            balance=balance,
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Balance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )