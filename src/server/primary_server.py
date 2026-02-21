import logging
import grpc
import asyncio
from concurrent import futures
from typing import Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.wallet_service import WalletService
from services import wallet_pb2, wallet_pb2_grpc
from services.failover_service import FailoverManager

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
            self.channel = grpc.aio.insecure_channel(
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
    
    async def withdraw(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Call backup server to withdraw"""
        try:
            request = wallet_pb2.WithdrawRequest(
                account_id=account_id, 
                amount=amount,
                transaction_id=transaction_id
            )
            response = await self.stub.withdraw(request, timeout=5.0)
            return response.success, response.message, response.new_balance
        except Exception as e:
            logger.error(f"Backup withdraw failed: {e}")
            raise

    async def deposit(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Call backup server to deposit"""
        try:
            request = wallet_pb2.DepositRequest(
                account_id=account_id, 
                amount=amount,
                transaction_id=transaction_id
            )
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

class PrimaryWalletServicer(wallet_pb2_grpc.WalletBackupServicer):
    """Primary server also implements WalletBackup service for failover"""
    
    def __init__(self, wallet_service: WalletService):
        self.wallet_service = wallet_service
    
    def withdraw(self, request, context):
        """Handle withdraw requests"""
        success, message, new_balance = self.wallet_service.withdraw(
            request.account_id, 
            request.amount,
            request.transaction_id
        )
        logger.info(f"Primary gRPC: Withdrew {request.amount} from {request.account_id}")
        return wallet_pb2.TransactionResponse(
            success=success,
            message=message,
            new_balance=new_balance,
            transaction_id=request.transaction_id
        )
    
    def deposit(self, request, context):
        """Handle deposit requests"""
        success, message, new_balance = self.wallet_service.deposit(
            request.account_id, 
            request.amount,
            request.transaction_id
        )
        logger.info(f"Primary gRPC: Deposited {request.amount} to {request.account_id}")
        return wallet_pb2.TransactionResponse(
            success=success,
            message=message,
            new_balance=new_balance,
            transaction_id=request.transaction_id
        )
    
    def getBalance(self, request, context):
        """Handle balance check requests"""
        success, balance, message = self.wallet_service.get_balance(request.account_id)
        logger.info(f"Primary gRPC: Balance check for {request.account_id} - {balance}")
        return wallet_pb2.GetBalanceResponse(
            success=success,
            balance=balance,
            message=message
        )

class PrimaryWalletService:
    """Primary wallet service that syncs with backup"""
    
    def __init__(self, backup_client: PrimaryWalletClient, failover_manager: FailoverManager):
        self.wallet_service = WalletService("primary_wallets.json", "primary_transactions.json")
        self.backup_client = backup_client
        self.failover_manager = failover_manager
    
    async def withdraw(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Withdraw: sync with backup first, then execute on primary"""
        try:
            # Step 1: Update backup first (if primary is alive)
            if not self.failover_manager.failover_mode:
                backup_success, backup_msg, backup_balance = await self.backup_client.withdraw(
                    account_id, 
                    amount,
                    transaction_id
                )
                
                if not backup_success:
                    logger.warning(f"Backup withdrawal failed: {backup_msg}")
                    return False, f"Backup error: {backup_msg}", 0.0
            else:
                logger.warning("Primary in failover mode - backup may be unavailable")
            
            # Step 2: Execute on primary
            primary_success, primary_msg, primary_balance = self.wallet_service.withdraw(
                account_id, 
                amount,
                transaction_id
            )
            
            logger.info(f"Primary: Withdrew {amount} from {account_id} (txn_id={transaction_id})")
            return primary_success, primary_msg, primary_balance
        
        except Exception as e:
            logger.error(f"Withdraw transaction failed: {e}")
            return False, f"Transaction failed: {str(e)}", 0.0

    async def deposit(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Deposit: sync with backup first, then execute on primary"""
        try:
            # Step 1: Update backup first (if primary is alive)
            if not self.failover_manager.failover_mode:
                backup_success, backup_msg, backup_balance = await self.backup_client.deposit(
                    account_id, 
                    amount,
                    transaction_id
                )
                
                if not backup_success:
                    logger.warning(f"Backup deposit failed: {backup_msg}")
                    return False, f"Backup error: {backup_msg}", 0.0
            else:
                logger.warning("Primary in failover mode - backup may be unavailable")
            
            # Step 2: Execute on primary
            primary_success, primary_msg, primary_balance = self.wallet_service.deposit(
                account_id, 
                amount,
                transaction_id
            )
            
            logger.info(f"Primary: Deposited {amount} to {account_id} (txn_id={transaction_id})")
            return primary_success, primary_msg, primary_balance
        
        except Exception as e:
            logger.error(f"Deposit transaction failed: {e}")
            return False, f"Transaction failed: {str(e)}", 0.0

    async def get_balance(self, account_id: str) -> tuple[bool, float, str]:
        """Get balance from primary"""
        try:
            success, balance, message = self.wallet_service.get_balance(account_id)
            logger.info(f"Primary: Balance check for {account_id} - {balance}")
            return success, balance, message
        except Exception as e:
            logger.error(f"Get balance failed: {e}")
            return False, 0.0, str(e)

# Global instances
primary_service: Optional[PrimaryWalletService] = None
grpc_server: Optional[grpc.aio.Server] = None

async def start_grpc_server():
    """Start primary gRPC server for backup to use in failover"""
    global grpc_server
    wallet_service = WalletService("primary_wallets.json", "primary_transactions.json")
    wallet_service.recover_pending_transactions()
    grpc_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    wallet_pb2_grpc.add_WalletBackupServicer_to_server(
        PrimaryWalletServicer(wallet_service),
        grpc_server
    )
    grpc_server.add_insecure_port('[::]:50051')
    logger.info("Primary gRPC server listening on [::]:50051")
    await grpc_server.start()

async def stop_grpc_server():
    """Stop primary gRPC server"""
    global grpc_server
    if grpc_server:
        await grpc_server.stop(grace=5)

async def initialize_primary_service(backup_host: str = "localhost", backup_port: int = 50052):
    """Initialize primary service with backup connection and failover"""
    global primary_service
    
    backup_client = PrimaryWalletClient(backup_host, backup_port)
    await backup_client.connect()
    
    failover_manager = FailoverManager(backup_host, backup_port)
    # Start health check in background
    asyncio.create_task(failover_manager.check_primary_health())
    
    primary_service = PrimaryWalletService(backup_client, failover_manager)
    return primary_service