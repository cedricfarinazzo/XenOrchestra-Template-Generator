#!/usr/bin/env python3
"""
XCP-NG Template Generator
Generate VM templates for XCP-NG using Xen Orchestra API
"""
import os
import asyncio
import sys
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.logging import RichHandler
from rich.live import Live

from pydantic_yaml import parse_yaml_file_as

from services.models import TemplateList
from services.template import TemplateManager
from services.xen_orchestra import XenOrchestraApi, AsyncAPISession
from services.tools import logger, MultiTaskProgress

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
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Increase logging verbosity (use -v for INFO, -vv for DEBUG)",
)
@click.pass_context
def cli(ctx, verbose):
    """
    # XCP-NG Template Generator

    Generate VM templates for XCP-NG using Xen Orchestra API.

    This tool creates VM templates based on configurations defined in a YAML file.
    It downloads cloud images and configures them for use with XCP-NG.
    """
    # Set logging level based on verbosity count
    if verbose == 0:
        logger.setLevel("WARNING")  # Default level
    elif verbose == 1:
        logger.setLevel("INFO")
        console.log("[green]Verbose mode enabled (INFO)[/green]")
    elif verbose >= 2:
        logger.setLevel("DEBUG")
        console.log("[bold green]Debug mode enabled (DEBUG)[/bold green]")

    # Store verbose setting in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, file_okay=True, readable=True),
    default="config.yml",
    help="Path to the YAML configuration file",
    show_default=True,
)
@click.option(
    "--xoa-url", "-u", envvar="XOA_URL", help="Xen Orchestra API URL [env var: XOA_URL]"
)
@click.option(
    "--xoa-token",
    "-t",
    envvar="XOA_TOKEN",
    help="Xen Orchestra API token [env var: XOA_TOKEN]",
)
@click.pass_context
def generate(ctx, config: str, xoa_url: str, xoa_token: str):
    """
    Generate VM templates from configuration file.

    Reads template specifications from the YAML configuration file and creates
    VM templates according to these specifications using Xen Orchestra API.
    """
    # Run the async function in the event loop
    return asyncio.run(_generate(config, xoa_url, xoa_token))


async def _generate(config: str, xoa_url: str, xoa_token: str):
    """Async implementation of generate command."""
    try:
        # XenOrchestra API setup
        host = xoa_url or os.getenv("XOA_URL")
        auth_token = xoa_token or os.getenv("XOA_TOKEN")

        if not host or not auth_token:
            console.print(
                Panel(
                    "[bold red]Error:[/bold red] XOA_URL and XOA_TOKEN must be provided either as command-line options or environment variables",
                    title="Missing Credentials",
                    border_style="red",
                )
            )
            return 1

        multi_task_progress = MultiTaskProgress()

        # Load the configuration file
        templates = parse_yaml_file_as(TemplateList, Path(config))
        templates_managers = [
            TemplateManager(template, multi_task_progress)
            for template in templates.templates.values()
        ]

        # Display template information
        table = Table(title="Templates to be Generated")
        table.add_column("Name", style="cyan")
        table.add_column("Distribution", style="green")
        table.add_column("Base Template", style="blue")
        table.add_column("Version", justify="right")
        table.add_column("CPUs", justify="right")
        table.add_column("Memory (GB)", justify="right")
        table.add_column("Network", style="blue")
        table.add_column("SR", style="blue")

        for manager in templates_managers:
            manager.plan(table)

        console.print(table)

        if click.confirm(
            "Do you want to continue with template generation?", default=True
        ):
            api = XenOrchestraApi(host=host, auth_token=auth_token)
            async with AsyncAPISession(api) as session_api:
                with Live(
                    multi_task_progress.render(), refresh_per_second=10, console=console
                ) as live:
                    for manager in templates_managers:
                        await manager.generate(session_api)

                console.print(
                    "[bold green]All templates processed successfully![/bold green]"
                )
        else:
            console.print("[yellow]Template generation cancelled.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        console.print_exception()
        return 1

    return 0


@cli.command()
@click.option(
    "--xoa-url", "-u", envvar="XOA_URL", help="Xen Orchestra API URL [env var: XOA_URL]"
)
@click.option(
    "--xoa-token",
    "-t",
    envvar="XOA_TOKEN",
    help="Xen Orchestra API token [env var: XOA_TOKEN]",
)
@click.pass_context
def list_templates(ctx, xoa_url: str, xoa_token: str):
    """
    List available templates on XCP-NG server.

    Connects to Xen Orchestra and displays a table of all VM templates.
    """
    # Run the async function in the event loop
    return asyncio.run(_list_templates(xoa_url, xoa_token))


async def _list_templates(xoa_url: str, xoa_token: str):
    """Async implementation of list_templates command."""
    try:
        # XenOrchestra API setup
        host = xoa_url or os.getenv("XOA_URL")
        auth_token = xoa_token or os.getenv("XOA_TOKEN")

        if not host or not auth_token:
            console.print(
                Panel(
                    "[bold red]Error:[/bold red] XOA_URL and XOA_TOKEN must be provided either as command-line options or environment variables",
                    title="Missing Credentials",
                    border_style="red",
                )
            )
            return 1

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
                memory_gb = round(
                    template_info.get("memory", {}).get("size", 0) / (1024**3), 1
                )
                table.add_row(
                    template_info.get("name_label", "Unknown"),
                    template_info.get("uuid", "Unknown"),
                    str(template_info.get("CPUs", {}).get("number", "N/A")),
                    str(memory_gb),
                )

            console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        console.print_exception()
        return 1

    return 0


def main():
    """Entry point for the CLI."""
    return cli()


if __name__ == "__main__":
    sys.exit(main())
