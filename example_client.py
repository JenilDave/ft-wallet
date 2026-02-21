import uuid
import requests
import time

def deposit_with_retry(account_id: str, amount: float, txn_id: str = None, max_retries: int = 3):
    """Deposit with automatic retry on timeout or failure"""
    if txn_id is None:
        txn_id = str(uuid.uuid4())
    
    payload = {
        "account_id": account_id,
        "amount": amount,
        "transaction_id": txn_id
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries}: Depositing {amount} to {account_id} (txn_id={txn_id})")
            response = requests.post(
                "http://localhost:8000/deposit",
                json=payload,
                timeout=5
            )
            
            # Success
            if response.status_code == 200:
                print(f"✓ Success: {response.json()}")
                return response.json()
            
            # Bad request (validation error)
            elif response.status_code == 400:
                print(f"✗ Bad Request: {response.json()['detail']}")
                return None
            
            # Server error - retry
            elif response.status_code >= 500:
                print(f"✗ Server error ({response.status_code}). Retrying...")
                time.sleep(1)  # Wait before retry
                continue
        
        except requests.exceptions.Timeout:
            print(f"✗ Request timeout on attempt {attempt}. Retrying...")
            time.sleep(1)
            continue
        
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection failed on attempt {attempt}. Retrying...")
            time.sleep(1)
            continue
        
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return None
    
    print(f"✗ Failed after {max_retries} attempts")
    return None

def withdraw_with_retry(account_id: str, amount: float, txn_id: str = None, max_retries: int = 3):
    """Withdraw with automatic retry on timeout or failure"""
    if txn_id is None:
        txn_id = str(uuid.uuid4())
    
    payload = {
        "account_id": account_id,
        "amount": amount,
        "transaction_id": txn_id
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries}: Withdrawing {amount} from {account_id} (txn_id={txn_id})")
            response = requests.post(
                "http://localhost:8000/withdraw",
                json=payload,
                timeout=5
            )
            
            # Success
            if response.status_code == 200:
                print(f"✓ Success: {response.json()}")
                return response.json()
            
            # Bad request (validation error)
            elif response.status_code == 400:
                print(f"✗ Bad Request: {response.json()['detail']}")
                return None
            
            # Server error - retry
            elif response.status_code >= 500:
                print(f"✗ Server error ({response.status_code}). Retrying...")
                time.sleep(1)
                continue
        
        except requests.exceptions.Timeout:
            print(f"✗ Request timeout on attempt {attempt}. Retrying...")
            time.sleep(1)
            continue
        
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection failed on attempt {attempt}. Retrying...")
            time.sleep(1)
            continue
        
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return None
    
    print(f"✗ Failed after {max_retries} attempts")
    return None

def get_balance_with_retry(account_id: str, max_retries: int = 3):
    """Get balance with automatic retry"""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries}: Getting balance for {account_id}")
            response = requests.post(
                "http://localhost:8000/balance",
                json={"account_id": account_id},
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✓ Success: {response.json()}")
                return response.json()
            
            elif response.status_code >= 500:
                print(f"✗ Server error ({response.status_code}). Retrying...")
                time.sleep(1)
                continue
        
        except requests.exceptions.Timeout:
            print(f"✗ Request timeout. Retrying...")
            time.sleep(1)
            continue
        
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection failed. Retrying...")
            time.sleep(1)
            continue
    
    print(f"✗ Failed after {max_retries} attempts")
    return None

# Example usage
if __name__ == "__main__":
    account = "user123"
    
    print("=== Test 1: Deposit ===")
    deposit_with_retry(account, 1000.00)
    
    print("\n=== Test 2: Check Balance ===")
    get_balance_with_retry(account)
    
    print("\n=== Test 3: Withdraw ===")
    withdraw_with_retry(account, 250.50)
    
    print("\n=== Test 4: Check Balance Again ===")
    get_balance_with_retry(account)
    
    print("\n=== Test 5: Multiple Deposits with Same Transaction ID (Idempotency) ===")
    txn_id = str(uuid.uuid4())
    print("First request:")
    deposit_with_retry(account, 500.00, txn_id=txn_id)
    print("\nSecond request with SAME txn_id (should return same result):")
    deposit_with_retry(account, 500.00, txn_id=txn_id)