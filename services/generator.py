from pathlib import Path
import time
import asyncio
from typing import Callable, Optional
from services.debian_cloud_image import DebianCloudImage
from services.xen_orchestra import XenOrchestraApi
from services.models import SourceConfig, TargetConfig, TemplateConfig
from services.utils import logger, get_version_name

class TemplateGenerator:
    """Class to handle template generation process."""
    
    def __init__(self, api: XenOrchestraApi):
        self.api = api
        self.dl_folder = Path("/tmp")
        self.dl_format = "vmdk"
        
    async def process_template(self, config: TemplateConfig, progress_callback: Optional[Callable[[float], None]] = None) -> None:
        """Process a single template configuration.
        
        Args:
            config: The template configuration
            progress_callback: Optional callback function to report progress (0.0 to 1.0)
        """
        source_config = config.get_source_config()
        target_config = config.get_target_config()
        
        # Default no-op progress callback
        if progress_callback is None:
            progress_callback = lambda _: None
            
        # Define step weights (percentage of total progress)
        steps = {
            "prepare_image": 0.25,       # Image download/preparation (25%)
            "get_resources": 0.05,       # Getting XCP-ng resources (5%)
            "import_disk": 0.40,         # Disk import (40%) 
            "create_vm": 0.10,           # VM creation (10%)
            "configure_vm": 0.10,        # VM configuration (10%)
            "convert_template": 0.05,    # Convert to template (5%)
            "cleanup": 0.05,             # Cleanup (5%)
        }
        
        # Track progress
        current_progress = 0.0
        
        def update_progress(step_name: str, step_progress: float = 1.0):
            """Update progress for a step."""
            nonlocal current_progress
            # Calculate the contribution of this step to overall progress
            step_contribution = steps[step_name] * step_progress
            current_progress += step_contribution
            # Ensure we don't exceed 100%
            current_progress = min(current_progress, 1.0)
            # Call the progress callback
            progress_callback(current_progress)
        
        try:
            logger.info(f"Processing template: {target_config.name}")
            progress_callback(0.0)  # Start at 0%
            
            # Step 1: Download and prepare image
            logger.info("Step 1/7: Downloading and preparing image...")
            image_path = await self._prepare_image(source_config, 
                                                  lambda p: update_progress("prepare_image", p))
            
            # Step 2: Get required XCP-ng resources
            logger.info("Step 2/7: Getting XCP-ng resources...")
            # Gather resources in parallel
            sr_id, template_id, network_id = await asyncio.gather(
                self._get_storage_repository(target_config.sr),
                self._get_base_template(source_config),
                self._get_network(target_config.network)
            )
            update_progress("get_resources")
            
            # Step 3: Import disk
            logger.info("Step 3/7: Importing disk...")
            vdi_id = await self._import_disk(image_path, sr_id, 
                                           lambda p: update_progress("import_disk", p))
            
            # Step 4: Create and configure VM
            logger.info("Step 4/7: Creating VM...")
            build_id = int(time.time())
            vm_id = await self._create_vm(source_config, target_config, template_id, network_id, build_id)
            update_progress("create_vm")
            
            # Step 5: Attach disk and set boot order
            logger.info("Step 5/7: Configuring VM...")
            await self._configure_vm(vm_id, vdi_id)
            update_progress("configure_vm")
            
            # Step 6: Convert VM to template
            logger.info("Step 6/7: Converting to template...")
            await self._convert_to_template(vm_id)
            update_progress("convert_template")
            
            # Step 7: Delete old templates
            logger.info("Step 7/7: Cleaning up old templates...")
            await self._delete_old_templates(target_config.name, vm_id)
            update_progress("cleanup")
            
            logger.info(f"Template '{target_config.name}' created successfully!")
            progress_callback(1.0)  # Ensure we end at 100%

        except Exception as e:
            logger.error(f"Error processing template '{target_config.name}': {e}")
            raise
        
    async def _prepare_image(self, config: SourceConfig, 
                           progress_callback: Optional[Callable[[float], None]] = None) -> Path:
        """Download and prepare the disk image."""
        if progress_callback is None:
            progress_callback = lambda _: None
            
        debian_cloud_dl = DebianCloudImage(
            version=str(config.version),
            arch=config.architecture,
            variant=config.variant
        )
        
        image_filename = debian_cloud_dl.get_image_name().replace(".qcow2", f".{self.dl_format}")
        image_path = self.dl_folder / image_filename
        
        if image_path.exists():
            logger.info(f"Using existing image: {image_path}")
            progress_callback(1.0)  # Skip directly to 100% if file exists
        else:
            logger.info(f"Downloading and converting image for {config.distribution} {config.version}...")
            image_path = debian_cloud_dl.download_and_convert_image_to_format(
                folder_out=self.dl_folder,
                format=self.dl_format,
                progress_callback=progress_callback
            )
            logger.info(f"Image downloaded and converted: {image_path}")
            
        return image_path
        
    async def _get_storage_repository(self, sr_name: str) -> str:
        """Get storage repository ID by name."""
        logger.info(f"Looking for storage repository: {sr_name}")
        sr_id = await self.api.get_sr_by_name(sr_name)
        if not sr_id:
            raise ValueError(f"Storage repository '{sr_name}' not found")
        logger.info(f"Found SR ID: {sr_id}")
        return sr_id
        
    async def _get_base_template(self, config: SourceConfig) -> str:
        """Get base template ID for the distribution/version."""
        template_name = f"{config.distribution.capitalize()} {get_version_name(config.distribution, config.version)} {config.version}"
        logger.info(f"Looking for base template: {template_name}")
        template_id = await self.api.get_template_by_name(template_name)
        if not template_id:
            raise ValueError(f"Template '{template_name}' not found")
        logger.info(f"Found template ID: {template_id}")
        return template_id
        
    async def _get_network(self, network_name: str) -> str:
        """Get network ID by name."""
        logger.info(f"Looking for network: {network_name}")
        network_id = await self.api.get_network_by_name(network_name)
        if not network_id:
            raise ValueError(f"Network '{network_name}' not found")
        logger.info(f"Found network ID: {network_id}")
        return network_id
        
    async def _import_disk(self, image_path: Path, sr_id: str, 
                        progress_callback: Optional[Callable[[float], None]] = None) -> str:
        """Import disk to Xen Orchestra."""
        if progress_callback is None:
            progress_callback = lambda _: None
            
        # Start progress
        progress_callback(0.0)
        
        file_format = image_path.suffix[1:]
        build_id = int(time.time())
        upload_file_name = f"{image_path.stem}.{build_id}.{file_format}"
        logger.info(f"Upload file name: {upload_file_name}")
        
        image_size = image_path.stat().st_size
        logger.info(f"Image size: {image_size} bytes")
        
        logger.info(f"Importing disk to Xen Orchestra...")
        # Report 50% progress as we start the import process
        progress_callback(0.5)
        
        vdi_id = self.api.import_disk(
            sr_id=sr_id,
            file_path=image_path,
            upload_name=upload_file_name,
        )
        logger.info(f"VDI ID: {vdi_id}")
        
        # Complete progress
        progress_callback(1.0)
        
        return vdi_id
        
    async def _create_vm(self, source_config: SourceConfig, target_config: TargetConfig, 
                        template_id: str, network_id: str, build_id: int) -> str:
        """Create a VM for the template."""
        vm_name = f"template.{target_config.name}.{build_id}"
        vm_description = f"{source_config.distribution.capitalize()} {source_config.version} {source_config.variant} {source_config.architecture} {build_id} template"
        logger.info(f"Creating VM: {vm_name}")
        
        vm_id = await self.api.create_vm(
            name_label=vm_name,
            name_description=vm_description,
            template_id=template_id,
            network_id=network_id,
            cpus=target_config.cpu,
            memory=target_config.memory,
            tags=[f"template.{target_config.name}"]
        )
        logger.info(f"VM ID: {vm_id}")
        return vm_id
        
    async def _configure_vm(self, vm_id: str, vdi_id: str) -> None:
        """Configure VM with disk and boot order."""
        logger.info("Attaching VDI to VM...")
        attach_result = await self.api.attach_vdi_to_vm(
            vm_id=vm_id,
            vdi_id=vdi_id,
        )
        logger.info(f"VDI attached to VM: {attach_result}")
        
        logger.info("Setting boot order...")
        boot_result = await self.api.set_boot_order(
            vm_id=vm_id,
            boot_order="cd",
        )
        logger.info(f"Boot order set: {boot_result}")
        
    async def _convert_to_template(self, vm_id: str) -> None:
        """Convert VM to template."""
        logger.info("Converting VM to template...")
        convert_result = await self.api.convert_vm_to_template(vm_id=vm_id)
        logger.info(f"VM converted to template: {convert_result}")

    async def _delete_old_templates(self, template_name: str, current_template_id: str) -> None:
        """Delete old templates with the same name but older build IDs.
        
        Args:
            template_name: The base name of the template without build ID
            current_template_id: The ID of the current template to keep
        """
        logger.info(f"Looking for old templates with base name: {template_name}")
        
        all_templates = await self.api.list_templates()
        template_pattern = f"template.{template_name}."
        
        # Find templates with matching name pattern
        matching_templates = []
        for template_id, template_info in all_templates.items():
            template_label = template_info.get("name_label", "")
            if template_pattern in template_label:
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
        
        logger.info(f"Found {len(matching_templates)} matching templates")
        
        templates_to_delete = [
            template for template in matching_templates
            if template["id"] != current_template_id
        ]
        
        if not templates_to_delete:
            logger.info(f"No old templates to delete for '{template_name}'")
            return
            
        # Delete old templates
        for template in templates_to_delete:
            try:
                logger.info(f"Deleting old template: {template['name']} (ID: {template['id']})")
                delete_result = await self.api.delete_template(template["id"])
                logger.info(f"Template deleted: {delete_result}")
            except Exception as e:
                logger.warning(f"Failed to delete template '{template['name']}': {e}")
                continue