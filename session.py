from services.xen_orchestra import XenOrchestraApi
from utils import logger

class AsyncAPISession:
    """Context manager for Xen Orchestra API session."""
    
    def __init__(self, api: XenOrchestraApi):
        self.api = api
        
    async def __aenter__(self):
        try:
            await self.api.connect()
            logger.info("Connected to Xen Orchestra.")
            
            logger.info("Logging in...")
            await self.api.login()
            logger.info("Logged in.")
            
            return self.api
        except Exception as e:
            logger.error(f"Failed to establish API session: {e}")
            # Make sure to disconnect if connect succeeded but login failed
            try:
                await self.api.disconnect()
            except:
                pass
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.api.disconnect()
            logger.info("Disconnected from Xen Orchestra.")
        except Exception as e:
            logger.error(f"Error disconnecting from API: {e}")