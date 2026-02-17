import logging
import grpc
import asyncio
from typing import Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.wallet_service import WalletService
from services import wallet_pb2, wallet_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PrimaryWalletClient:
    """gRPC client to communicate with backup server"""
    
    def __init__(self, backup_host: str = "localhost", backup_port: int = 50052):
        self.backup_host = backup_host
        self.backup_port = backup_port
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[wallet_pb2_grpc.WalletBackupStub] = None
    
    async def connect(self):
        """Connect to backup server"""
        try:
            self.channel = grpc.aio.secure_channel(
                f"{self.backup_host}:{self.backup_port}",
                grpc.ssl_channel_credentials()
            ) if False else grpc.aio.insecure_channel(
                f"{self.backup_host}:{self.backup_port}"
            )
            self.stub = wallet_pb2_grpc.WalletBackupStub(self.channel)
            logger.info(f"Connected to backup server at {self.backup_host}:{self.backup_port}")
        except Exception as e:
            logger.error(f"Failed to connect to backup server: {e}")
    
    async def close(self):
        """Close connection to backup server"""
        if self.channel:
            await self.channel.close()
    
    async def withdraw(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Call backup server to withdraw"""
        try:
            request = wallet_pb2.WithdrawRequest(account_id=account_id, amount=amount)
            response = await self.stub.withdraw(request, timeout=5.0)
            return response.success, response.message, response.new_balance
        except Exception as e:
            logger.error(f"Backup withdraw failed: {e}")
            raise
    
    async def deposit(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Call backup server to deposit"""
        try:
            request = wallet_pb2.DepositRequest(account_id=account_id, amount=amount)
            response = await self.stub.deposit(request, timeout=5.0)
            return response.success, response.message, response.new_balance
        except Exception as e:
            logger.error(f"Backup deposit failed: {e}")
            raise
    
    async def get_balance(self, account_id: str) -> tuple[bool, float, str]:
        """Call backup server to get balance"""
        try:
            request = wallet_pb2.GetBalanceRequest(account_id=account_id)
            response = await self.stub.getBalance(request, timeout=5.0)
            return response.success, response.balance, response.message
        except Exception as e:
            logger.error(f"Backup get_balance failed: {e}")
            raise

class PrimaryWalletService:
    """Primary wallet service that syncs with backup"""
    
    def __init__(self, backup_client: PrimaryWalletClient):
        self.wallet_service = WalletService("primary_wallets.json")
        self.backup_client = backup_client
    
    async def withdraw(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Withdraw: sync with backup first, then execute on primary"""
        try:
            # Step 1: Update backup first
            backup_success, backup_msg, backup_balance = await self.backup_client.withdraw(
                account_id, 
                amount
            )
            
            if not backup_success:
                logger.warning(f"Backup withdrawal failed: {backup_msg}")
                return False, f"Backup error: {backup_msg}", 0.0
            
            # Step 2: Execute on primary
            primary_success, primary_msg, primary_balance = self.wallet_service.withdraw(
                account_id, 
                amount
            )
            
            logger.info(f"Primary: Withdrew {amount} from {account_id}")
            return primary_success, primary_msg, primary_balance
        
        except Exception as e:
            logger.error(f"Withdraw transaction failed: {e}")
            return False, f"Transaction failed: {str(e)}", 0.0
    
    async def deposit(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Deposit: sync with backup first, then execute on primary"""
        try:
            # Step 1: Update backup first
            backup_success, backup_msg, backup_balance = await self.backup_client.deposit(
                account_id, 
                amount
            )
            
            if not backup_success:
                logger.warning(f"Backup deposit failed: {backup_msg}")
                return False, f"Backup error: {backup_msg}", 0.0
            
            # Step 2: Execute on primary
            primary_success, primary_msg, primary_balance = self.wallet_service.deposit(
                account_id, 
                amount
            )
            
            logger.info(f"Primary: Deposited {amount} to {account_id}")
            return primary_success, primary_msg, primary_balance
        
        except Exception as e:
            logger.error(f"Deposit transaction failed: {e}")
            return False, f"Transaction failed: {str(e)}", 0.0
    
    async def get_balance(self, account_id: str) -> tuple[bool, float, str]:
        """Get balance from primary (no sync needed for read-only operation)"""
        try:
            success, balance, message = self.wallet_service.get_balance(account_id)
            logger.info(f"Primary: Balance check for {account_id} - {balance}")
            return success, balance, message
        except Exception as e:
            logger.error(f"Get balance failed: {e}")
            return False, 0.0, str(e)

# Global primary service instance
primary_service: Optional[PrimaryWalletService] = None

async def initialize_primary_service(backup_host: str = "localhost", backup_port: int = 50052):
    """Initialize primary service with backup connection"""
    global primary_service
    backup_client = PrimaryWalletClient(backup_host, backup_port)
    await backup_client.connect()
    primary_service = PrimaryWalletService(backup_client)
    return primary_service
