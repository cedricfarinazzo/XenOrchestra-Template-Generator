from pathlib import Path
import os
import time
import asyncio
import yaml
import logging
from typing import Dict, List, Optional, Any, Literal

from pydantic import BaseModel, Field, field_validator

from services.debian_cloud_image import DebianCloudImage
from services.xen_orchestra import XenOrchestraApi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('template_generator')


# Pydantic models for configuration validation
class SourceConfig(BaseModel):
    distribution: Literal["debian"] = Field(description="The Linux distribution")
    architecture: Literal["amd64", "arm64"] = Field(description="The CPU architecture")
    version: int = Field(description="The distribution version number")
    variant: str = Field(description="The image variant (e.g. genericcloud)")

    @field_validator('distribution')
    @classmethod
    def validate_distribution(cls, v):
        if v.lower() != 'debian':
            raise ValueError('Currently only Debian distribution is supported')
        return v.lower()
    
    @field_validator('architecture')
    @classmethod
    def validate_architecture(cls, v):
        return v.lower()


class TargetConfig(BaseModel):
    name: str = Field(description="The name of the target template")
    cpu: int = Field(description="Number of CPUs", ge=1)
    memory: int = Field(description="Memory in GB", ge=1)
    network: str = Field(description="Network name to connect the VM to")
    sr: str = Field(description="Storage repository name")


class TemplateConfig(BaseModel):
    @field_validator('template')
    @classmethod
    def validate_template(cls, v):
        if 'source' not in v or 'target' not in v:
            raise ValueError("Template must have both 'source' and 'target' sections")
        return v
    
    def get_source_config(self) -> SourceConfig:
        return SourceConfig(**self.template['source'])
    
    def get_target_config(self) -> TargetConfig:
        return TargetConfig(**self.template['target'])


class TemplateGenerator:
    """Class to handle template generation process."""
    
    def __init__(self, api: XenOrchestraApi):
        self.api = api
        self.dl_folder = Path("/tmp")
        self.dl_format = "vmdk"
        
    async def process_template(self, config: TemplateConfig) -> None:
        """Process a single template configuration."""
        source_config = config.get_source_config()
        target_config = config.get_target_config()
        
        try:
            logger.info(f"Processing template: {target_config.name}")
            
            # Step 1: Download and prepare image
            image_path = await self._prepare_image(source_config)
            
            # Step 2: Get required XCP-ng resources
            # Gather resources in parallel
            sr_id, template_id, network_id = await asyncio.gather(
                self._get_storage_repository(target_config.sr),
                self._get_base_template(source_config),
                self._get_network(target_config.network)
            )
            
            # Step 3: Import disk
            vdi_id = await self._import_disk(image_path, sr_id)
            
            # Step 4: Create and configure VM
            build_id = int(time.time())
            vm_id = await self._create_vm(source_config, target_config, template_id, network_id, build_id)
            
            # Step 5: Attach disk and set boot order
            await self._configure_vm(vm_id, vdi_id)
            
            # Step 6: Convert VM to template
            await self._convert_to_template(vm_id)
            
            logger.info(f"Template '{target_config.name}' created successfully!")

            # Step 7: Delete old templates
            await self._delete_old_templates(target_config.name, vm_id)
            
        except Exception as e:
            logger.error(f"Error processing template '{target_config.name}': {e}")
            raise
        
    async def _prepare_image(self, config: SourceConfig) -> Path:
        """Download and prepare the disk image."""
        debian_cloud_dl = DebianCloudImage(
            version=str(config.version),
            arch=config.architecture,
            variant=config.variant
        )
        
        image_filename = debian_cloud_dl.get_image_name().replace(".qcow2", f".{self.dl_format}")
        image_path = self.dl_folder / image_filename
        
        if image_path.exists():
            logger.info(f"Using existing image: {image_path}")
        else:
            logger.info(f"Downloading and converting image for {config.distribution} {config.version}...")
            image_path = debian_cloud_dl.download_and_convert_image_to_format(
                folder_out=self.dl_folder,
                format=self.dl_format
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
        
    async def _import_disk(self, image_path: Path, sr_id: str) -> str:
        """Import disk to Xen Orchestra."""
        file_format = image_path.suffix[1:]
        build_id = int(time.time())
        upload_file_name = f"{image_path.stem}.{build_id}.{file_format}"
        logger.info(f"Upload file name: {upload_file_name}")
        
        image_size = image_path.stat().st_size
        logger.info(f"Image size: {image_size} bytes")
        
        logger.info(f"Importing disk to Xen Orchestra...")
        vdi_id = await self.api.import_disk(
            sr_id=sr_id,
            file_path=image_path,
            upload_name=upload_file_name,
        )
        logger.info(f"VDI ID: {vdi_id}")
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

    async def _delete_old_templates(self, template_name: str, curent_template_id: str) -> None:
        """Delete old templates with the same name but older build IDs.
        
        Args:
            template_name: The base name of the template without build ID
            curent_template_id: The ID of the current template to keep
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
            if template["id"] != curent_template_id
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


def get_version_name(distribution, version):
    """Get the version name for a distribution version."""
    if distribution.lower() == 'debian':
        version_map = {
            12: "Bookworm",
            11: "Bullseye",
            10: "Buster",
            9: "Stretch",
            8: "Jessie",
            7: "Wheezy"
        }
        return version_map.get(int(version), "Unknown")
    return "Unknown"


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


async def main():
    """Main function to process all templates."""
    try:
        # Load configuration
        config_path = Path("config.yml")
        logger.info(f"Loading configuration from {config_path}")
        try:
            with open(config_path, 'r') as config_file:
                config_data = yaml.safe_load(config_file)
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return
            
        # Validate configuration with Pydantic
        try:
            templates_config = [TemplateConfig(**item) for item in config_data]
            logger.info(f"Configuration validated successfully. Found {len(templates_config)} template(s).")
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return

        # XenOrchestra API setup
        host = os.getenv("XOA_URL")
        if not host:
            logger.error("Error: XOA_URL environment variable not set")
            return
            
        auth_token = os.getenv("XOA_TOKEN")
        if not auth_token:
            logger.error("Error: XOA_TOKEN environment variable not set")
            return

        # Connect to Xen Orchestra API
        logger.info("Connecting to Xen Orchestra...")
        api = XenOrchestraApi(host=host, auth_token=auth_token)
        
        async with AsyncAPISession(api) as session_api:
            # Initialize template generator
            generator = TemplateGenerator(session_api)
            
            # Process templates concurrently with a semaphore to limit concurrency
            sem = asyncio.Semaphore(2)  # Process up to 2 templates at a time
            
            async def process_template_with_sem(template_config):
                async with sem:
                    try:
                        await generator.process_template(template_config)
                    except Exception as e:
                        logger.error(f"Error processing template: {e}")
            
            # Create tasks for all templates
            tasks = [
                process_template_with_sem(template_config)
                for template_config in templates_config
            ]
            
            # Wait for all tasks to complete
            if tasks:
                await asyncio.gather(*tasks)
            else:
                logger.info("No templates to process")
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())