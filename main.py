#!/usr/bin/env python3
"""
XCP-NG Template Generator
Generate VM templates for XCP-NG using Xen Orchestra API
"""
import os
import asyncio
import yaml
from pathlib import Path

from models import TemplateConfig
from generator import TemplateGenerator
from session import AsyncAPISession
from services.xen_orchestra import XenOrchestraApi
from utils import logger

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
        auth_token = os.getenv("XOA_TOKEN")
        
        if not host or not auth_token:
            logger.error("Error: XOA_URL and XOA_TOKEN environment variables must be set")
            return

        # Connect to Xen Orchestra API and process templates
        api = XenOrchestraApi(host=host, auth_token=auth_token)
        
        async with AsyncAPISession(api) as session_api:
            # Process templates with concurrency control
            await process_templates(session_api, templates_config)
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def process_templates(api, templates_config):
    """Process multiple templates concurrently."""
    # Initialize template generator
    generator = TemplateGenerator(api)
    
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


if __name__ == "__main__":
    asyncio.run(main())