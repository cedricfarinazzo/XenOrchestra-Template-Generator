import time
import asyncio
from pathlib import Path
from rich.table import Table
from typing import Optional, Callable

from .tools import logger, MultiTaskProgress
from .image_providers import IMAGE_PROVIDERS, BaseImageProvider
from .xen_orchestra import XenOrchestraApi
from .models import TemplateConfig

class TemplateManager:
    def __init__(self, template_config: TemplateConfig, multi_task_progress: MultiTaskProgress):
        self.template_config = template_config
        self.build_id = self.__generate_build_id()

        self.multi_task_progress = multi_task_progress
        self.task_id = self.multi_task_progress.add_task(
            description=self.template_name,
            total=7
        )

    def plan(self, out_table: Table) -> None:
        """
        Plan the template creation.
        
        Args:
            out_table: Table to display the plan.
        """
        out_table.add_row(
            self.template_config.target.name,
            self.template_config.source.distribution,
            self.template_config.source.base_template,
            str(self.template_config.source.version),
            str(self.template_config.target.cpu),
            str(self.template_config.target.memory),
            self.template_config.target.network,
            self.template_config.target.sr
        )

    def __advance_task(self) -> None:
        """
        Advance the task progress.
        """
        self.multi_task_progress.advance_task(self.task_id)
    
    def __set_description(self, description: str) -> None:
        """
        Set the task description.
        
        Args:
            description: Description to set.
        """
        self.multi_task_progress.set_description(
            self.task_id,
            description=f"{self.template_name} {description}"
        )

    async def generate(self, xo_api: XenOrchestraApi) -> None:
        logger.info(f"[{self.template_name}] Step 1/7: Downloading and preparing image...")
        download_image_description = "⬇️ Downloading image"
        self.__set_description(download_image_description)
        def dl_image_progress_callback(progress: float) -> None:
            self.__set_description(f"{download_image_description} {int(progress * 100)}%")
        image_path = await self.__download(dl_image_progress_callback)
        self.__advance_task()

        logger.info(f"[{self.template_name}] Step 2/7: Getting XCP-ng resources...")
        self.__set_description("🔍 Gathering resources")
        # Gather resources in parallel
        sr_id, template_id, network_id = await asyncio.gather(
            self._get_storage_repository(xo_api),
            self._get_base_template(xo_api),
            self._get_network(xo_api)
        )
        self.__advance_task()

        # Step 3: Import disk
        logger.info(f"[{self.template_name}] Step 3/7: Importing disk...")
        import_disk_description = "📤 Importing disk"
        self.__set_description(import_disk_description)
        def disk_import_progress_callback(progress: float) -> None:
            self.__set_description(f"{import_disk_description} {int(progress * 100)}%")
        vdi_id = await self._import_disk(xo_api, image_path, sr_id, disk_import_progress_callback)
        self.__advance_task()

        # Step 4: Create and configure VM
        logger.info(f"[{self.template_name}] Step 4/7: Creating VM...")
        self.__set_description("🖥️ Creating VM")
        vm_id = await self._create_vm(xo_api, template_id, network_id)
        self.__advance_task()

        # Step 5: Attach disk and set boot order
        logger.info(f"[{self.template_name}] Step 5/7: Configuring VM...")
        self.__set_description("⚙️ Configuring VM")
        await self._configure_vm(xo_api, vm_id, vdi_id)
        self.__advance_task()

        # Step 6: Convert VM to template
        logger.info(f"[{self.template_name}] Step 6/7: Converting to template...")
        self.__set_description("🛠️ Converting to template")
        await self._convert_to_template(xo_api, vm_id)
        self.__advance_task()

        # Step 7: Delete old templates
        logger.info(f"[{self.template_name}] Step 7/7: Cleaning up old templates...")
        self.__set_description("🧹 Cleaning up old templates")
        await self._delete_old_templates(xo_api)
        self.__advance_task()

        self.__set_description("✅ Template created successfully")
        logger.info(f"[{self.template_name}] Template '{self.template_name}' created successfully with ID: {vm_id}")

    def __generate_build_id(self) -> int:
        """
        Generate a unique build ID.
        """
        return int(time.time())

    def __template_base_name(self) -> str:
        """
        Generate a unique template name.
        """
        return f"template.{self.template_config.target.name}"

    @property
    def template_name(self) -> str:
        """
        Generate a unique template name.
        """
        return f"{self.__template_base_name()}.{self.build_id}"

    def __template_description(self) -> str:
        """
        Generate a unique template description.
        """
        return f"{self.template_config.source.distribution.capitalize()} {self.template_config.source.version} {self.template_config.source.variant} {self.template_config.source.architecture} {self.build_id} template"

    def __template_tags(self) -> list[str]:
        """
        Generate a list of tags for the template.
        """
        return [
            f"template.{self.template_config.target.name}",
            f"build.{self.build_id}",
            f"arch.{self.template_config.source.architecture}",
            f"version.{self.template_config.source.version}",
        ]

    async def __download(self, progress_callback: Optional[Callable[[float], None]] = None) -> Path:
        """
        Download the image.
        """
        image_provider = IMAGE_PROVIDERS[self.template_config.source.distribution]
        
        image_provider_instance : BaseImageProvider = image_provider(
            version=self.template_config.source.version,
            arch=self.template_config.source.architecture,
            variant=self.template_config.source.variant
        )

        image_path = image_provider_instance.download_image(
            use_cache=True,
            progress_callback=progress_callback
        )

        return image_path

    async def _get_storage_repository(self, xo_api: XenOrchestraApi) -> str:
        """Get storage repository ID by name."""
        logger.debug(f"[{self.template_name}] Looking for storage repository: {self.template_config.target.sr}")
        sr_id = await xo_api.get_sr_by_name(self.template_config.target.sr)
        if not sr_id:
            raise ValueError(f"[{self.template_name}] Storage repository '{self.template_config.target.sr}' not found")
        logger.info(f"[{self.template_name}] Storage repository {self.template_config.target.sr} found with ID: {sr_id}")
        return sr_id

    async def _get_base_template(self, xo_api: XenOrchestraApi) -> str:
        """Get base template ID for the given distribution."""
        logger.debug(f"[{self.template_name}] Looking for base template: {self.template_config.source.base_template}")
        template_id = await xo_api.get_template_by_name(self.template_config.source.base_template)
        if not template_id:
            raise ValueError(f"[{self.template_name}] Template '{self.template_config.source.base_template}' not found")
        logger.info(f"[{self.template_name}] Base Template {self.template_config.source.base_template} found with ID: {template_id}")
        return template_id
        
    async def _get_network(self, xo_api: XenOrchestraApi) -> str:
        """Get network ID by name."""
        logger.debug(f"[{self.template_name}] Looking for network: {self.template_config.target.network}")
        network_id = await xo_api.get_network_by_name(self.template_config.target.network)
        if not network_id:
            raise ValueError(f"[{self.template_name}] Network '{self.template_config.target.network}' not found")
        logger.info(f"[{self.template_name}] Network {self.template_config.target.network} found with ID: {network_id}")
        return network_id

    async def _import_disk(
        self,
        xo_api: XenOrchestraApi,
        image_path: Path, sr_id: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """Import disk to Xen Orchestra."""
        
        file_format = image_path.suffix[1:]
        upload_file_name = f"{image_path.stem}.{self.build_id}.{file_format}"
        
        image_size = image_path.stat().st_size
        
        logger.info(f"[{self.template_name}] Importing disk {upload_file_name} (size: {image_size}) to Xen Orchestra...")
        
        vdi_id = xo_api.import_disk(
            sr_id=sr_id,
            file_path=image_path,
            upload_name=upload_file_name,
            progress_callback=progress_callback
        )
        logger.info(f"[{self.template_name}] Disk imported with ID: {vdi_id}")
        if not vdi_id:
            raise ValueError(f"[{self.template_name}] Failed to import disk '{upload_file_name}'")
        
        return vdi_id

    async def _create_vm(self, xo_api: XenOrchestraApi, template_id: str, network_id: str) -> str:
        """Create a VM for the template."""
        logger.debug(f"[{self.template_name}] Creating VM: {self.template_name}")
        
        vm_id = await xo_api.create_vm(
            name_label=self.template_name,
            name_description=self.__template_description(),
            template_id=template_id,
            network_id=network_id,
            cpus=self.template_config.target.cpu,
            memory=self.template_config.target.memory,
            tags=self.__template_tags(),
        )
        logger.info(f"[{self.template_name}] VM {self.template_name} created with ID: {vm_id}")
        return vm_id

    async def _configure_vm(self, xo_api: XenOrchestraApi, vm_id: str, vdi_id: str) -> bool:
        """Configure VM with disk and boot order."""
        logger.debug(f"[{self.template_name}] Attaching VDI to VM...")
        attach_result = await xo_api.attach_vdi_to_vm(
            vm_id=vm_id,
            vdi_id=vdi_id,
        )
        logger.info(f"[{self.template_name}] VDI {vdi_id} attached to VM {vm_id}: {attach_result}")
        
        logger.debug(f"[{self.template_name}] Setting boot order...")
        boot_result = await xo_api.set_boot_order(
            vm_id=vm_id,
            boot_order="cd",
        )
        logger.info(f"[{self.template_name}] Boot order set for VM {vm_id}: {boot_result}")

        return attach_result and boot_result

    async def _convert_to_template(self, xo_api: XenOrchestraApi, vm_id: str) -> bool:
        """Convert VM to template."""
        logger.debug(f"[{self.template_name}] Converting VM to template...")
        convert_result = await xo_api.convert_vm_to_template(vm_id=vm_id)
        logger.info(f"[{self.template_name}] VM {vm_id} converted to template: {convert_result}")

        return convert_result

    async def _delete_old_templates(self, xo_api: XenOrchestraApi) -> None:
        """Delete old templates with the same name but older build IDs.
        """
        template_base_name = self.__template_base_name()
        logger.debug(f"[{self.template_name}] Looking for old templates with base name: {template_base_name}")
        
        all_templates = await xo_api.list_templates()
        
        # Find templates with matching name pattern
        matching_templates = []
        for template_id, template_info in all_templates.items():
            template_label = template_info.get("name_label", "")
            if template_base_name in template_label:
                # Extract build ID from template name
                try:
                    build_id = int(template_label.split(".")[-1])
                    matching_templates.append({
                        "id": template_id,
                        "name": template_label,
                        "build_id": build_id
                    })
                except (ValueError, IndexError):
                    # Skip if build ID extraction fails
                    continue
                    
        # Sort templates by build ID (descending)
        matching_templates.sort(key=lambda x: x["build_id"], reverse=True)
        
        logger.debug(f"[{self.template_name}] Found {len(matching_templates)} matching templates")
        
        templates_to_delete = [
            template for template in matching_templates
            if template["id"] != self.template_name
        ]
        
        if not templates_to_delete:
            logger.debug(f"[{self.template_name}] No old templates to delete for '{template_base_name}'")
            return
            
        # Delete old templates
        for template in templates_to_delete:
            try:
                logger.debug(f"Deleting old template: {template['name']} (ID: {template['id']})")
                delete_result = await xo_api.delete_template(template["id"])
                logger.info(f"[{self.template_name}] Template '{template['name']}' with ID {template['id']} deleted: {delete_result}")
            except Exception as e:
                logger.warning(f"[{self.template_name}] Failed to delete template '{template['name']} (ID: {template['id']})': {e}")
                continue