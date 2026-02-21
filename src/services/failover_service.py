import logging
import grpc
import asyncio
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FailoverManager:
    """Manages primary-to-backup failover"""
    
    def __init__(self, backup_host: str = "localhost", backup_port: int = 50052):
        self.backup_host = backup_host
        self.backup_port = backup_port
        self.is_primary_alive = True
        self.failover_mode = False
    
    async def check_primary_health(self, primary_grpc_port: int = 50051, timeout: int = 5):
        """Periodically check if primary gRPC server is alive"""
        while True:
            try:
                channel = grpc.aio.insecure_channel(f"localhost:{primary_grpc_port}")
                await asyncio.wait_for(channel.channel_ready(), timeout=timeout)
                await channel.close()
                self.is_primary_alive = True
                self.failover_mode = False
                logger.info("Primary server is healthy")
            except Exception as e:
                logger.warning(f"Primary server health check failed: {e}")
                self.is_primary_alive = False
                if not self.failover_mode:
                    logger.critical("PRIMARY SERVER DOWN - ACTIVATING BACKUP FAILOVER MODE")
                    self.failover_mode = True
            
            # Check every 5 seconds
            await asyncio.sleep(5)