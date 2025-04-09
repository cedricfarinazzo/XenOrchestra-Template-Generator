from pathlib import Path
from typing import Optional

import aiohttp
import requests
from jsonrpc_websocket import Server

class XenOrchestraApi:
    def __init__(
        self,
        host: str,
        auth_token: str
    ) -> None:
        self.host = host + "/api/"
        self.auth_token = auth_token

        self.http_host = host.replace("wss://", "http://")
        self.http_cookies = {
            "authenticationToken": auth_token,
        }

    async def connect(self):
        self.session = aiohttp.ClientSession()
        self.ws = Server(self.host, session=self.session)
        await self.ws.ws_connect()

    async def login(self) -> dict:
        return await self.ws.session.signIn(token=self.auth_token)

    async def disconnect(self) -> None:
        await self.ws.close()
        await self.session.close()

    async def introspect(self) -> dict:
        return await self.ws.system.getMethodsInfo()

    async def list_pools(self) -> dict:
        return await self.ws.pool.listPoolsMatchingCriteria()

    async def get_default_pool(self) -> dict:
        return (await self.list_pools())[0]

    async def get_default_sr(self) -> str:
        return (await self.get_default_pool())["default_SR"]

    async def list_servers(self) -> dict:
        return await self.ws.server.getAll()

    async def list_srs(self) -> dict:
        return await self.ws.xo.getAllObjects(filter={"type": "SR"})

    async def get_sr_by_name(self, name: str) -> Optional[dict]:
        for sr_id, sr_info in (await self.list_srs()).items():
            if sr_info["name_label"] == name:
                return sr_id
        return None

    def import_disk(
        self,
        sr_id: str,
        file_path: Path,
        upload_name: str,
    ):
        upload_url = (
            self.http_host
            + f"/rest/v0/srs/{sr_id}/vdis"
            + f"?raw&name_label={upload_name}"
        )

        with file_path.open("rb") as file:
            response = requests.post(
                upload_url,
                cookies=self.http_cookies,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(file_path.stat().st_size),
                },
                data=file,
            )

        if response.status_code == 200:
            return response.text
        else:
            raise Exception(
                f"Failed to upload file: {response.status_code}, reason: {response.text}"
            )

