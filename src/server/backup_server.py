import logging
import asyncio
from concurrent import futures
import grpc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.wallet_service import WalletService
from services import wallet_pb2, wallet_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WalletBackupServicer(wallet_pb2_grpc.WalletBackupServicer):
    """Backup server that maintains wallet state"""
    
    def __init__(self):
        self.wallet_service = WalletService("backup_wallets.json", "backup_transactions.json")
    
    def withdraw(self, request, context):
        """Handle withdraw requests"""
        success, message, new_balance = self.wallet_service.withdraw(
            request.account_id, 
            request.amount,
            request.transaction_id
        )
        logger.info(f"Backup: Withdraw txn_id={request.transaction_id} - {message}")
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
        logger.info(f"Backup: Deposit txn_id={request.transaction_id} - {message}")
        return wallet_pb2.TransactionResponse(
            success=success,
            message=message,
            new_balance=new_balance,
            transaction_id=request.transaction_id
        )
    
    def getBalance(self, request, context):
        """Handle balance check requests"""
        success, balance, message = self.wallet_service.get_balance(request.account_id)
        logger.info(f"Backup: Balance check for {request.account_id} - {balance}")
        return wallet_pb2.GetBalanceResponse(
            success=success,
            balance=balance,
            message=message
        )

async def serve():
    """Start backup gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    wallet_pb2_grpc.add_WalletBackupServicer_to_server(
        WalletBackupServicer(), 
        server
    )
    server.add_insecure_port('[::]:50052')
    logger.info("Backup server listening on [::]:50052")
    
    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve())
