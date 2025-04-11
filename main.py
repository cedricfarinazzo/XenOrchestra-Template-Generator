#!/usr/bin/env python3
"""
XCP-NG Template Generator
Generate VM templates for XCP-NG using Xen Orchestra API
"""
import os
import asyncio
import yaml
from pathlib import Path
import sys

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich.logging import RichHandler

from models import TemplateConfig
from generator import TemplateGenerator
from session import AsyncAPISession
from services.xen_orchestra import XenOrchestraApi
from utils import logger

# Configure rich-click
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.USE_MARKDOWN = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
click.rich_click.STYLE_ERRORS_SUGGESTION = "magenta italic"
click.rich_click.STYLE_OPTION = "green"
click.rich_click.STYLE_ARGUMENT = "yellow"
click.rich_click.STYLE_COMMAND = "blue"
click.rich_click.MAX_WIDTH = 100

# Create a console for rich output
console = Console()

# Configure RichHandler for logging - ensure there's only one handler
if logger.handlers:
    # Clear any existing handlers
    logger.handlers = []
# Add the RichHandler
logger.addHandler(RichHandler(rich_tracebacks=True, console=console, show_time=False))


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    # XCP-NG Template Generator

    Generate VM templates for XCP-NG using Xen Orchestra API.
    
    This tool creates VM templates based on configurations defined in a YAML file.
    It downloads cloud images and configures them for use with XCP-NG.
    """
    pass


@cli.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, file_okay=True, readable=True),
    default="config.yml",
    help="Path to the YAML configuration file",
    show_default=True
)
@click.option(
    "--xoa-url", "-u",
    envvar="XOA_URL",
    help="Xen Orchestra API URL [env var: XOA_URL]"
)
@click.option(
    "--xoa-token", "-t",
    envvar="XOA_TOKEN",
    help="Xen Orchestra API token [env var: XOA_TOKEN]"
)
@click.option(
    "--concurrent", "-j",
    type=int, 
    default=2,
    help="Number of templates to process concurrently",
    show_default=True
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    help="Enable debug logging"
)
def generate(config, xoa_url, xoa_token, concurrent, debug):
    """
    Generate VM templates from configuration file.
    
    Reads template specifications from the YAML configuration file and creates
    VM templates according to these specifications using Xen Orchestra API.
    """
    # Run the async function in the event loop
    return asyncio.run(_generate(config, xoa_url, xoa_token, concurrent, debug))

async def _generate(config, xoa_url, xoa_token, concurrent, debug):
    """Async implementation of generate command."""
    try:
        # Load configuration
        config_path = Path(config)
        console.print(f"Loading configuration from [cyan]{config_path}[/cyan]")
        
        try:
            with open(config_path, 'r') as config_file:
                config_data = yaml.safe_load(config_file)
        except Exception as e:
            console.print(Panel(f"[bold red]Error loading configuration:[/bold red] {str(e)}", 
                           title="Configuration Error", border_style="red"))
            return 1
            
        # Validate configuration with Pydantic
        try:
            templates_config = [TemplateConfig(**item) for item in config_data]
            console.print(f"Configuration validated successfully. Found [green]{len(templates_config)}[/green] template(s).")
        except Exception as e:
            console.print(Panel(f"[bold red]Configuration validation failed:[/bold red] {str(e)}", 
                           title="Validation Error", border_style="red"))
            return 1

        # XenOrchestra API setup
        host = xoa_url or os.getenv("XOA_URL")
        auth_token = xoa_token or os.getenv("XOA_TOKEN")
        
        if not host or not auth_token:
            console.print(Panel(
                "[bold red]Error:[/bold red] XOA_URL and XOA_TOKEN must be provided either as command-line options or environment variables",
                title="Missing Credentials", 
                border_style="red"
            ))
            return 1

        console.print(f"Connecting to Xen Orchestra API at [blue]{host}[/blue]")
        api = XenOrchestraApi(host=host, auth_token=auth_token)
        
        # Display template information
        table = Table(title="Templates to be Generated")
        table.add_column("Name", style="cyan")
        table.add_column("Distribution", style="green")
        table.add_column("Version", justify="right")
        table.add_column("CPUs", justify="right")
        table.add_column("Memory (GB)", justify="right")
        table.add_column("Network", style="blue")
        table.add_column("SR", style="blue")
        
        for template_config in templates_config:
            source = template_config.get_source_config()
            target = template_config.get_target_config()
            table.add_row(
                target.name,
                source.distribution,
                str(source.version),
                str(target.cpu),
                str(target.memory),
                target.network,
                target.sr
            )
        
        console.print(table)
        
        if click.confirm("Do you want to continue with template generation?", default=True):
            async with AsyncAPISession(api) as session_api:
                # Process templates with concurrency control
                await process_templates(session_api, templates_config, concurrent)
                console.print("[bold green]All templates processed successfully![/bold green]")
        else:
            console.print("[yellow]Template generation cancelled.[/yellow]")
            
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {str(e)}")
        if debug:
            console.print_exception()
        return 1
    
    return 0


@cli.command()
@click.option(
    "--xoa-url", "-u",
    envvar="XOA_URL",
    help="Xen Orchestra API URL [env var: XOA_URL]"
)
@click.option(
    "--xoa-token", "-t",
    envvar="XOA_TOKEN",
    help="Xen Orchestra API token [env var: XOA_TOKEN]"
)
def list_templates(xoa_url, xoa_token):
    """
    List available templates on XCP-NG server.
    
    Connects to Xen Orchestra and displays a table of all VM templates.
    """
    # Run the async function in the event loop
    return asyncio.run(_list_templates(xoa_url, xoa_token))

async def _list_templates(xoa_url, xoa_token):
    """Async implementation of list_templates command."""
    try:
        # XenOrchestra API setup
        host = xoa_url or os.getenv("XOA_URL")
        auth_token = xoa_token or os.getenv("XOA_TOKEN")
        
        if not host or not auth_token:
            console.print(Panel(
                "[bold red]Error:[/bold red] XOA_URL and XOA_TOKEN must be provided either as command-line options or environment variables",
                title="Missing Credentials", 
                border_style="red"
            ))
            return 1

        console.print(f"Connecting to Xen Orchestra API at [blue]{host}[/blue]")
        api = XenOrchestraApi(host=host, auth_token=auth_token)
        
        async with AsyncAPISession(api) as session_api:
            with console.status("[green]Fetching templates...[/green]"):
                templates_dict = await session_api.list_templates()
            
            if not templates_dict:
                console.print("[yellow]No templates found.[/yellow]")
                return 0
                
            table = Table(title="Available VM Templates")
            table.add_column("Name", style="cyan")
            table.add_column("ID", style="dim")
            table.add_column("CPUs", justify="right")
            table.add_column("Memory (GB)", justify="right")
            
            for template_id, template_info in templates_dict.items():
                memory_gb = round(template_info.get("memory", {}).get("size", 0) / (1024**3), 1)
                table.add_row(
                    template_info.get("name_label", "Unknown"),
                    template_info.get("uuid", "Unknown"),
                    str(template_info.get("CPUs", {}).get("number", "N/A")),
                    str(memory_gb)
                )
            
            console.print(table)
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        console.print_exception()
        return 1
    
    return 0


async def process_templates(api, templates_config, concurrency=2):
    """Process multiple templates concurrently."""
    # Initialize template generator
    generator = TemplateGenerator(api)
    
    # Process templates concurrently with a semaphore to limit concurrency
    sem = asyncio.Semaphore(concurrency)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=50),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TextColumn("[{task.completed}/{task.total}]"),
        console=console,
        expand=True
    ) as progress:
        # Add an overall progress bar
        overall_task = progress.add_task(
            "[bold blue]Overall Progress[/bold blue]", 
            total=len(templates_config),
            completed=0
        )
        
        # Create tasks for all templates
        tasks = []
        task_ids = {}
        
        for template_config in templates_config:
            target_config = template_config.get_target_config()
            source_config = template_config.get_source_config()
            
            # Create a task for this template
            template_name = f"{target_config.name} ({source_config.distribution} {source_config.version})"
            task_id = progress.add_task(
                f"[cyan]{template_name}[/cyan]", 
                total=100, 
                start=False,
                visible=True
            )
            task_ids[task_id] = template_name
            
            # Create a callback to update progress
            def make_progress_callback(task_id):
                def callback(percent):
                    # Update this template's progress
                    progress.update(task_id, completed=percent * 100)
                    
                    # Update overall progress
                    completed_templates = sum(1 for tid in task_ids if progress.tasks[tid].completed >= 100)
                    progress.update(overall_task, completed=completed_templates)
                    
                    # Add a nice status description
                    if percent < 0.25:
                        status = "⬇️ Downloading image"
                    elif percent < 0.30:
                        status = "🔍 Getting resources"
                    elif percent < 0.70:
                        status = "📤 Importing disk"
                    elif percent < 0.80:
                        status = "🖥️ Creating VM" 
                    elif percent < 0.90:
                        status = "⚙️ Configuring VM"
                    elif percent < 0.95:
                        status = "🔄 Converting to template"
                    else:
                        status = "🧹 Cleaning up"
                    
                    progress.update(task_id, description=f"[cyan]{template_name}[/cyan] {status}")
                    
                return callback
            
            # Process template with semaphore
            async def process_with_sem(config, task_id):
                async with sem:
                    progress.start_task(task_id)
                    try:
                        await generator.process_template(
                            config,
                            progress_callback=make_progress_callback(task_id)
                        )
                        progress.update(task_id, 
                                      completed=100, 
                                      description=f"[green]{task_ids[task_id]}[/green] ✅ Complete")
                    except Exception as e:
                        error_msg = str(e)
                        if len(error_msg) > 30:  # Truncate long error messages
                            error_msg = error_msg[:30] + "..."
                        progress.update(task_id, 
                                      description=f"[red]{task_ids[task_id]}[/red] ❌ Error: {error_msg}")
                        console.print(f"[bold red]Error processing {task_ids[task_id]}:[/bold red] {str(e)}")
                        raise
            
            tasks.append(process_with_sem(template_config, task_id))
        
        # Wait for all tasks to complete
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failures = [r for r in results if isinstance(r, Exception)]
            
            if failures:
                console.print(f"[bold red]{len(failures)}/{len(tasks)} templates failed to process[/bold red]")
                for failure in failures:
                    console.print(f"[red]Error: {str(failure)}[/red]")
            else:
                console.print("[bold green]All templates processed successfully![/bold green]")
        else:
            console.print("[yellow]No templates to process[/yellow]")


def main():
    """Entry point for the CLI."""
    return cli()


if __name__ == "__main__":
    sys.exit(main())