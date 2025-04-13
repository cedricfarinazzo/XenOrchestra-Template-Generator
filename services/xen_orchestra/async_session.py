from ..tools import logger
from .api import XenOrchestraApi

class AsyncAPISession:
    """Context manager for Xen Orchestra API session."""
    
    def __init__(self, api: XenOrchestraApi):
        self.api = api
        
    async def __aenter__(self):
        try:
            await self.api.connect()
            logger.debug("Connected to Xen Orchestra.")
            
            logger.debug("Logging in...")
            await self.api.login()
            logger.debug("Logged in.")
            
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
            logger.debug("Disconnected from Xen Orchestra.")
        except Exception as e:
            logger.error(f"Error disconnecting from API: {e}")