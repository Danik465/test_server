import asyncio
import websockets
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ConnectionTest")

async def test_connection(uri):
    try:
        logger.info(f"Testing connection to {uri}")
        async with websockets.connect(
            uri,
            ping_interval=20,
            ping_timeout=10
        ) as websocket:
            logger.info("✅ Connection successful!")
            return True
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_connection.py <ws_or_wss_uri>")
        sys.exit(1)
    
    uri = sys.argv[1]
    asyncio.run(test_connection(uri))