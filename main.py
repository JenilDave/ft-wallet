import sys
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_backup_server():
    """Run backup server in subprocess"""
    import subprocess
    logger.info("Starting backup server...")
    subprocess.Popen(
        [sys.executable, "-m", "src.server.backup_server"],
        cwd=Path(__file__).parent
    )

def run_primary_server():
    """Run primary HTTP server"""
    logger.info("Starting primary HTTP server...")
    from src.server.http_server import app
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start backup server first
    run_backup_server()
    
    # Give backup server time to start
    import time
    time.sleep(2)
    
    # Start primary server
    run_primary_server()