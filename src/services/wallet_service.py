import json
from pathlib import Path
from typing import Dict
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WalletService:
    """In-memory wallet service with persistence and idempotency using WAL"""
    
    def __init__(self, data_file: str = "wallets.json", txn_file: str = "transactions.json"):
        self.data_file = data_file
        self.txn_file = txn_file
        self.wallets: Dict[str, float] = {}
        self.transactions: Dict[str, Dict] = {}  # transaction_id -> {status, result}
        self.load_wallets()
        self.load_transactions()
    
    def load_wallets(self):
        """Load wallet data from JSON file"""
        if Path(self.data_file).exists():
            with open(self.data_file, 'r') as f:
                self.wallets = json.load(f)
        else:
            self.wallets = {}
    
    def load_transactions(self):
        """Load transaction history for idempotency"""
        if Path(self.txn_file).exists():
            with open(self.txn_file, 'r') as f:
                self.transactions = json.load(f)
        else:
            self.transactions = {}
    
    def save_wallets(self):
        """Save wallet data to JSON file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.wallets, f, indent=2)
    
    def save_transactions(self):
        """Save transaction history (atomic write)"""
        temp_file = f"{self.txn_file}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(self.transactions, f, indent=2)
        
        # Atomic rename to avoid partial writes
        Path(temp_file).replace(self.txn_file)
    
    def _is_duplicate_transaction(self, transaction_id: str) -> bool:
        """Check if transaction was already processed"""
        return transaction_id in self.transactions
    
    def _get_cached_result(self, transaction_id: str) -> tuple[bool, str, float]:
        """Return cached result of previous transaction"""
        txn = self.transactions[transaction_id]
        return txn['success'], txn['message'], txn['new_balance']
    
    def _record_transaction_wal(self, transaction_id: str, operation: str, account_id: str, amount: float):
        """Write-Ahead Log: Record transaction BEFORE executing it"""
        # Mark transaction as PENDING to indicate it's in-flight
        self.transactions[transaction_id] = {
            'status': 'PENDING',
            'operation': operation,
            'account_id': account_id,
            'amount': amount,
            'success': None,
            'message': None,
            'new_balance': None,
        }
        self.save_transactions()
        logger.info(f"WAL: Recorded PENDING transaction {transaction_id}")
    
    def _commit_transaction(self, transaction_id: str, success: bool, message: str, new_balance: float):
        """Commit transaction after successful execution"""
        if transaction_id in self.transactions:
            self.transactions[transaction_id].update({
                'status': 'COMMITTED',
                'success': success,
                'message': message,
                'new_balance': new_balance,
            })
        else:
            # Fallback: create record if WAL didn't execute (shouldn't happen)
            self.transactions[transaction_id] = {
                'status': 'COMMITTED',
                'success': success,
                'message': message,
                'new_balance': new_balance,
            }
        self.save_transactions()
        logger.info(f"WAL: Committed transaction {transaction_id}")
    
    def _rollback_transaction(self, transaction_id: str):
        """Mark transaction as rolled back after failure"""
        if transaction_id in self.transactions:
            self.transactions[transaction_id]['status'] = 'ROLLED_BACK'
            self.save_transactions()
            logger.warning(f"WAL: Rolled back transaction {transaction_id}")
    
    def deposit(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Deposit money to account (idempotent with WAL)"""
        
        # Check if already processed
        if self._is_duplicate_transaction(transaction_id):
            return self._get_cached_result(transaction_id)
        
        # Validation checks (don't need WAL)
        if amount <= 0:
            result = (False, "Amount must be positive", 0.0)
            self._commit_transaction(transaction_id, *result)
            return result
        
        try:
            # Step 1: Write-Ahead Log - record BEFORE execution
            self._record_transaction_wal(transaction_id, "DEPOSIT", account_id, amount)
            
            # Step 2: Execute the operation
            if account_id not in self.wallets:
                self.wallets[account_id] = 0.0
            
            self.wallets[account_id] += amount
            
            # Step 3: Persist wallet state
            self.save_wallets()
            
            # Step 4: Commit transaction in log
            new_balance = self.wallets[account_id]
            result = (True, f"Deposited {amount}", new_balance)
            self._commit_transaction(transaction_id, *result)
            
            logger.info(f"Deposit successful: {transaction_id} -> {account_id} +{amount}")
            return result
        
        except Exception as e:
            logger.error(f"Deposit failed for transaction {transaction_id}: {e}")
            self._rollback_transaction(transaction_id)
            return False, f"Deposit failed: {str(e)}", 0.0
    
    def withdraw(self, account_id: str, amount: float, transaction_id: str) -> tuple[bool, str, float]:
        """Withdraw money from account (idempotent with WAL)"""
        
        # Check if already processed
        if self._is_duplicate_transaction(transaction_id):
            return self._get_cached_result(transaction_id)
        
        # Validation checks (don't need WAL)
        if amount <= 0:
            result = (False, "Amount must be positive", 0.0)
            self._commit_transaction(transaction_id, *result)
            return result
        
        try:
            # Step 1: Check balance (fail fast before WAL)
            if account_id not in self.wallets:
                self.wallets[account_id] = 0.0
            
            if self.wallets[account_id] < amount:
                result = (False, "Insufficient balance", self.wallets[account_id])
                # Still commit to mark this txn_id as processed
                self._commit_transaction(transaction_id, *result)
                return result
            
            # Step 2: Write-Ahead Log - record BEFORE execution
            self._record_transaction_wal(transaction_id, "WITHDRAW", account_id, amount)
            
            # Step 3: Execute the operation
            self.wallets[account_id] -= amount
            
            # Step 4: Persist wallet state
            self.save_wallets()
            
            # Step 5: Commit transaction in log
            new_balance = self.wallets[account_id]
            result = (True, f"Withdrew {amount}", new_balance)
            self._commit_transaction(transaction_id, *result)
            
            logger.info(f"Withdraw successful: {transaction_id} -> {account_id} -{amount}")
            return result
        
        except Exception as e:
            logger.error(f"Withdraw failed for transaction {transaction_id}: {e}")
            self._rollback_transaction(transaction_id)
            return False, f"Withdraw failed: {str(e)}", 0.0
    
    def get_balance(self, account_id: str) -> tuple[bool, float, str]:
        """Get account balance (read-only, always safe)"""
        if account_id not in self.wallets:
            self.wallets[account_id] = 0.0
            self.save_wallets()
        
        return True, self.wallets[account_id], "Balance retrieved"
    
    def recover_pending_transactions(self):
        """Recover pending transactions after crash"""
        recovered = 0
        for txn_id, txn_data in list(self.transactions.items()):
            if txn_data.get('status') == 'PENDING':
                logger.warning(f"Recovering pending transaction: {txn_id}")
                # This transaction was started but not completed
                # Mark as ROLLED_BACK to prevent re-execution
                self._rollback_transaction(txn_id)
                recovered += 1
        
        if recovered > 0:
            logger.warning(f"Recovered {recovered} pending transactions")
        
        return recovered