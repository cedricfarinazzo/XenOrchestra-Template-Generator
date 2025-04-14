from pathlib import Path
from typing import Optional, Callable

import aiohttp
import requests
from jsonrpc_websocket import Server

from ..tools import BufferedReaderWithProgressCallback

from .models import VmCreateParams, DiskAttachParams, BootOrderParams


class XenOrchestraApi:
    def __init__(self, host: str, auth_token: str) -> None:
        self.host = host + "/api/"
        self.auth_token = auth_token

        self.http_host = host.replace("ws://", "http://")
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
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        supported_formats = ["iso", "raw"]
        if file_path.suffix[1:] not in supported_formats:
            raise ValueError(
                f"Unsupported file format. Supported formats are: {supported_formats}"
            )

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
                data=BufferedReaderWithProgressCallback(
                    file.raw, progress_callback=progress_callback
                ),
            )

        if response.status_code == 200:
            return response.text
        else:
            raise Exception(
                f"Failed to upload file: {response.status_code}, reason: {response.text}"
            )

    async def list_templates(self) -> dict:
        return await self.ws.xo.getAllObjects(filter={"type": "VM-template"})

    async def get_template_by_name(self, name: str) -> Optional[dict]:
        for template_id, template_info in (await self.list_templates()).items():
            if template_info["name_label"] == name:
                return template_id
        return None

    async def get_networks(self) -> dict:
        return await self.ws.xo.getAllObjects(filter={"type": "network"})

    async def get_network_by_name(self, name: str) -> Optional[dict]:
        for network_id, network_info in (await self.get_networks()).items():
            if network_info["name_label"] == name:
                return network_id
        return None

    async def create_vm(
        self,
        name_label: str,
        name_description: str,
        template_id: str,
        network_id: str,
        cpus: int = 1,
        memory: int = 1,
        bootAfterCreate: bool = False,
        tags: Optional[list] = [],
    ) -> dict:
        # Validate parameters with Pydantic
        params = VmCreateParams(
            name_label=name_label,
            name_description=name_description,
            template_id=template_id,
            network_id=network_id,
            cpus=cpus,
            memory=memory,
            bootAfterCreate=bootAfterCreate,
            tags=tags or [],
        )

        return await self.ws.vm.create(
            acls=[],
            clone=False,
            existingDisks={},
            installation={"method": "network", "repository": "pxe"},
            bootAfterCreate=params.bootAfterCreate,
            name_label=params.name_label,
            name_description=params.name_description,
            template=params.template_id,
            VDIs=[],
            VIFs=[
                {
                    "network": params.network_id,
                    "allowedIpv4Addresses": [],
                    "allowedIpv6Addresses": [],
                },
            ],
            CPUs=params.cpus,
            cpusMax=params.cpus,
            cpuWeight=None,
            cpuCap=None,
            memory=params.memory * 1024 * 1024 * 1024,
            copyHostBiosStrings=True,
            createVtpm=False,
            destroyCloudConfigVdiAfterBoot=False,
            secureBoot=False,
            shared=False,
            coreOs=False,
            tags=params.tags,
            hvmBootFirmware="uefi",
        )

    async def attach_vdi_to_vm(
        self,
        vm_id: str,
        vdi_id: str,
        mode: Optional[str] = "RW",
        bootable: Optional[bool] = True,
    ) -> bool:
        # Validate parameters with Pydantic
        params = DiskAttachParams(
            vm_id=vm_id,
            vdi_id=vdi_id,
            mode=mode,
            bootable=bootable,
        )

        return await self.ws.vm.attachDisk(
            vdi=params.vdi_id,
            vm=params.vm_id,
            mode=params.mode,
            bootable=params.bootable,
        )

    async def set_boot_order(
        self,
        vm_id: str,
        boot_order: str,
        # Boot order list:
        # - "c" = Hard Disk
        # - "d" = DVD-Drive
        # - "n" = Network
        # No letter means "do not boot from this device"
        # Example: "cdn"
        # means boot from Hard Disk, then DVD-Drive, then Network
        # Example: "dn"
        # means boot from DVD-Drive, then Network
    ) -> bool:
        # Validate parameters with Pydantic
        params = BootOrderParams(
            vm_id=vm_id,
            boot_order=boot_order,
        )

        return await self.ws.vm.setBootOrder(
            vm=params.vm_id,
            order=params.boot_order,
        )

    async def convert_vm_to_template(
        self,
        vm_id: str,
    ) -> bool:
        return await self.ws.vm.convertToTemplate(
            id=vm_id,
        )

    async def delete_template(
        self,
        template_id: str,
    ) -> bool:
        """Delete a template.

        Args:
            template_id: The ID of the template to delete

        Returns:
            bool: True if successful, raises an exception otherwise
        """
        return await self.ws.vm.delete(
            id=template_id,
        )
