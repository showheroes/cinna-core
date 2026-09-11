# /// script
# requires-python = ">=3.10"
# dependencies = ["agent-client-protocol[http]==0.12.1"]
# ///
"""Official ACP SDK client example: CINNA_ACP_URL and CINNA_ACP_TOKEN required."""

import asyncio
import os
import sys

from acp import PROTOCOL_VERSION, connect_to_agent
from acp.schema import TextContentBlock
from acp.ws import create_websocket_stream
from stdio_bridge import validate_url


class Client:
    async def session_update(self, session_id, update, **kwargs):
        content = getattr(update, "content", None)
        if getattr(update, "session_update", None) == "agent_message_chunk" and content:
            sys.stdout.write(content.text)
            sys.stdout.flush()


async def main():
    url = os.environ["CINNA_ACP_URL"]
    validate_url(url)
    transport = await create_websocket_stream(
        url, headers={"Authorization": f"Bearer {os.environ['CINNA_ACP_TOKEN']}"}
    )
    connection = connect_to_agent(Client(), transport)
    try:
        await connection.initialize(protocol_version=PROTOCOL_VERSION)
        session = await connection.new_session(cwd="/app/workspace", mcp_servers=[])
        await connection.prompt(
            session_id=session.session_id,
            prompt=[TextContentBlock(type="text", text="Hello from ACP")],
        )
    finally:
        await connection.close()
        await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
