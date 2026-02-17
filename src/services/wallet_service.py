import json
from pathlib import Path
from typing import Dict

class WalletService:
    """In-memory wallet service with persistence"""
    
    def __init__(self, data_file: str = "wallets.json"):
        self.data_file = data_file
        self.wallets: Dict[str, float] = {}
        self.load_wallets()
    
    def load_wallets(self):
        """Load wallet data from JSON file"""
        if Path(self.data_file).exists():
            with open(self.data_file, 'r') as f:
                self.wallets = json.load(f)
        else:
            self.wallets = {}
    
    def save_wallets(self):
        """Save wallet data to JSON file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.wallets, f)
    
    def deposit(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Deposit money to account"""
        if amount <= 0:
            return False, "Amount must be positive", 0.0
        
        if account_id not in self.wallets:
            self.wallets[account_id] = 0.0
        
        self.wallets[account_id] += amount
        self.save_wallets()
        return True, f"Deposited {amount}", self.wallets[account_id]
    
    def withdraw(self, account_id: str, amount: float) -> tuple[bool, str, float]:
        """Withdraw money from account"""
        if amount <= 0:
            return False, "Amount must be positive", 0.0
        
        if account_id not in self.wallets:
            self.wallets[account_id] = 0.0
        
        if self.wallets[account_id] < amount:
            return False, "Insufficient balance", self.wallets[account_id]
        
        self.wallets[account_id] -= amount
        self.save_wallets()
        return True, f"Withdrew {amount}", self.wallets[account_id]
    
    def get_balance(self, account_id: str) -> tuple[bool, float, str]:
        """Get account balance"""
        if account_id not in self.wallets:
            self.wallets[account_id] = 0.0
            self.save_wallets()
        
        return True, self.wallets[account_id], "Balance retrieved"
