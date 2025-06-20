import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional, List
from .config import Config
from .api import LambdaLabsAPI
from .scheduler import LambdaLabsScheduler


console = Console()


@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)
    config = Config()
    ctx.obj['config'] = config
    
    # Only check API key for non-config commands
    if ctx.invoked_subcommand != 'config' and not config.api_key:
        console.print("[red]No API key configured. Run 'lambdalabs config set-api-key <key>' first.[/red]")
        ctx.exit(1)
    
    if config.api_key:
        ctx.obj['api'] = LambdaLabsAPI(config)
    
    ctx.obj['scheduler'] = LambdaLabsScheduler(config)


@cli.group()
def instances():
    pass


@instances.command("list")
@click.pass_context
def list_instances(ctx):
    api = ctx.obj['api']
    try:
        instances = api.list_instances()
        
        if not instances:
            console.print("[yellow]No instances found.[/yellow]")
            return
        
        table = Table(title="Lambda Labs Instances")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Instance Type", style="green")
        table.add_column("Region", style="blue")
        table.add_column("Status", style="yellow")
        table.add_column("IP Address", style="white")
        
        for instance in instances:
            table.add_row(
                instance.get("id", ""),
                instance.get("name", ""),
                instance.get("instance_type", {}).get("name", ""),
                instance.get("region", {}).get("name", ""),
                instance.get("status", ""),
                instance.get("ip", "")
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing instances: {e}[/red]")


@instances.command("create")
@click.option("--type", "-t", required=True, help="Instance type")
@click.option("--region", "-r", required=True, help="Region")
@click.option("--name", "-n", help="Instance name")
@click.option("--filesystem", "-f", help="Filesystem to attach")
@click.pass_context
def create_instance(ctx, type: str, region: str, name: Optional[str], filesystem: Optional[str]):
    api = ctx.obj['api']
    config = ctx.obj['config']
    
    try:
        ssh_keys = api.list_ssh_keys()
        if not ssh_keys:
            console.print("[yellow]No SSH keys found. Setting up SSH key...[/yellow]")
            public_key = config.get_ssh_public_key()
            if not public_key:
                console.print("[red]No SSH public key found in {config.ssh_dir}[/red]")
                return
            
            api.add_ssh_key("default", public_key)
            ssh_key_names = ["default"]
        else:
            ssh_key_names = [key["name"] for key in ssh_keys]
        
        filesystem_names = []
        if filesystem:
            filesystem_names = [filesystem]
        elif config.default_filesystem:
            filesystems = api.list_filesystems()
            available_fs = [fs["name"] for fs in filesystems if fs["name"] == config.default_filesystem]
            if available_fs:
                filesystem_names = [config.default_filesystem]
                console.print(f"[green]Using default filesystem: {config.default_filesystem}[/green]")
        
        result = api.launch_instance(
            instance_type=type,
            region=region,
            ssh_key_names=ssh_key_names,
            filesystem_names=filesystem_names if filesystem_names else None,
            name=name
        )
        
        console.print(f"[green]Instance launch initiated: {result.get('instance_ids', [])}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error creating instance: {e}[/red]")


@instances.command("terminate")
@click.argument("instance_id")
@click.pass_context
def terminate_instance(ctx, instance_id: str):
    api = ctx.obj['api']
    
    try:
        result = api.terminate_instance(instance_id)
        console.print(f"[green]Instance {instance_id} termination initiated[/green]")
        
    except Exception as e:
        console.print(f"[red]Error terminating instance: {e}[/red]")


@instances.command("terminate-by-name")
@click.argument("instance_name")
@click.pass_context
def terminate_instance_by_name(ctx, instance_name: str):
    """Terminate instance by name instead of ID."""
    api = ctx.obj['api']
    
    try:
        # Find instance by name
        instances = api.list_instances()
        matching = [inst for inst in instances if inst.get("name") == instance_name]
        
        if not matching:
            console.print(f"[yellow]No instance found with name '{instance_name}'[/yellow]")
            return
        
        if len(matching) > 1:
            console.print(f"[red]Multiple instances found with name '{instance_name}'. Use terminate with ID instead.[/red]")
            for inst in matching:
                console.print(f"  ID: {inst.get('id', 'unknown')}")
            return
        
        instance_id = matching[0].get("id")
        result = api.terminate_instance(instance_id)
        console.print(f"[green]Instance '{instance_name}' (ID: {instance_id}) termination initiated[/green]")
        
    except Exception as e:
        console.print(f"[red]Error terminating instance by name: {e}[/red]")


@instances.command("terminate-all")
@click.confirmation_option(prompt="Are you sure you want to terminate ALL instances?")
@click.pass_context
def terminate_all_instances(ctx):
    api = ctx.obj['api']
    
    try:
        result = api.terminate_all_instances()
        terminated = result.get("terminated_instances", [])
        if terminated:
            console.print(f"[green]Terminated {len(terminated)} instances[/green]")
        else:
            console.print("[yellow]No instances to terminate[/yellow]")
        
    except Exception as e:
        console.print(f"[red]Error terminating instances: {e}[/red]")


@instances.command("ensure")
@click.option("--type", "-t", required=True, help="Instance type")
@click.option("--region", "-r", required=True, help="Region")
@click.option("--name", "-n", required=True, help="Instance name (required for ensure)")
@click.option("--filesystem", "-f", help="Filesystem to attach")
@click.pass_context
def ensure_instance(ctx, type: str, region: str, name: str, filesystem: Optional[str]):
    """Create instance if it doesn't exist, otherwise do nothing."""
    api = ctx.obj['api']
    config = ctx.obj['config']
    
    try:
        # Check if instance with this name already exists
        instances = api.list_instances()
        existing = [inst for inst in instances if inst.get("name") == name]
        
        if existing:
            instance = existing[0]
            console.print(f"[green]Instance '{name}' already exists (ID: {instance.get('id', 'unknown')})[/green]")
            return
        
        # Instance doesn't exist, create it
        console.print(f"[yellow]Instance '{name}' not found, creating...[/yellow]")
        
        ssh_keys = api.list_ssh_keys()
        if not ssh_keys:
            console.print("[yellow]No SSH keys found. Setting up SSH key...[/yellow]")
            public_key = config.get_ssh_public_key()
            if not public_key:
                console.print("[red]No SSH public key found in {config.ssh_dir}[/red]")
                return
            
            api.add_ssh_key("default", public_key)
            ssh_key_names = ["default"]
        else:
            ssh_key_names = [key["name"] for key in ssh_keys]
        
        filesystem_names = []
        if filesystem:
            filesystem_names = [filesystem]
        elif config.default_filesystem:
            filesystems = api.list_filesystems()
            available_fs = [fs["name"] for fs in filesystems if fs["name"] == config.default_filesystem]
            if available_fs:
                filesystem_names = [config.default_filesystem]
                console.print(f"[green]Using default filesystem: {config.default_filesystem}[/green]")
        
        result = api.launch_instance(
            instance_type=type,
            region=region,
            ssh_key_names=ssh_key_names,
            filesystem_names=filesystem_names if filesystem_names else None,
            name=name
        )
        
        console.print(f"[green]Instance '{name}' created: {result.get('instance_ids', [])}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error ensuring instance: {e}[/red]")


@cli.group()
def filesystems():
    pass


@filesystems.command("list")
@click.pass_context
def list_filesystems(ctx):
    api = ctx.obj['api']
    config = ctx.obj['config']
    
    try:
        filesystems = api.list_filesystems()
        
        if not filesystems:
            console.print("[yellow]No filesystems found.[/yellow]")
            return
        
        table = Table(title="Lambda Labs Filesystems")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Region", style="blue")
        table.add_column("Size (GB)", style="green")
        table.add_column("Default", style="yellow")
        
        for fs in filesystems:
            is_default = "✓" if fs.get("name") == config.default_filesystem else ""
            table.add_row(
                fs.get("id", ""),
                fs.get("name", ""),
                fs.get("region", {}).get("name", ""),
                str(fs.get("size", "")),
                is_default
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing filesystems: {e}[/red]")


@filesystems.command("set-default")
@click.argument("filesystem_name")
@click.pass_context
def set_default_filesystem(ctx, filesystem_name: str):
    config = ctx.obj['config']
    api = ctx.obj['api']
    
    try:
        filesystems = api.list_filesystems()
        fs_names = [fs["name"] for fs in filesystems]
        
        if filesystem_name not in fs_names:
            console.print(f"[red]Filesystem '{filesystem_name}' not found[/red]")
            return
        
        config.default_filesystem = filesystem_name
        console.print(f"[green]Default filesystem set to: {filesystem_name}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error setting default filesystem: {e}[/red]")


@filesystems.command("create")
@click.argument("name")
@click.option("--region", "-r", required=True, help="Region")
@click.pass_context
def create_filesystem(ctx, name: str, region: str):
    api = ctx.obj['api']
    
    try:
        result = api.create_filesystem(name, region)
        console.print(f"[green]Filesystem '{name}' created in {region}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error creating filesystem: {e}[/red]")


@filesystems.command("delete")
@click.argument("filesystem_id")
@click.confirmation_option(prompt="Are you sure you want to delete this filesystem?")
@click.pass_context
def delete_filesystem(ctx, filesystem_id: str):
    api = ctx.obj['api']
    
    try:
        api.delete_filesystem(filesystem_id)
        console.print(f"[green]Filesystem {filesystem_id} deleted[/green]")
        
    except Exception as e:
        console.print(f"[red]Error deleting filesystem: {e}[/red]")


@cli.group()
def config():
    pass


@config.command("set-api-key")
@click.argument("api_key")
@click.pass_context
def set_api_key(ctx, api_key: str):
    config = ctx.obj['config']
    config.api_key = api_key
    console.print("[green]API key updated successfully[/green]")


@config.command("set-ssh-dir")
@click.argument("ssh_dir")
@click.pass_context
def set_ssh_dir(ctx, ssh_dir: str):
    config = ctx.obj['config']
    config.ssh_dir = ssh_dir
    console.print(f"[green]SSH directory set to: {ssh_dir}[/green]")


@config.command("show")
@click.option("--full", is_flag=True, help="Show full API key (unredacted)")
@click.pass_context
def show_config(ctx, full: bool):
    config = ctx.obj['config']
    
    if config.api_key:
        if full:
            api_key_display = config.api_key
        else:
            # Show first 8 and last 8 characters
            if len(config.api_key) > 16:
                api_key_display = f"{config.api_key[:8]}...{config.api_key[-8:]}"
            else:
                api_key_display = config.api_key  # Show full if too short
    else:
        api_key_display = '[red]Not set[/red]'
    
    panel_content = f"""[cyan]API Key:[/cyan] {api_key_display}
[cyan]SSH Directory:[/cyan] {config.ssh_dir}
[cyan]Default Filesystem:[/cyan] {config.default_filesystem or '[yellow]None[/yellow]'}"""
    
    console.print(Panel(panel_content, title="Lambda Labs Configuration"))


@config.command("get-api-key")
@click.pass_context
def get_api_key(ctx):
    config = ctx.obj['config']
    if config.api_key:
        console.print(config.api_key)
    else:
        console.print("[red]No API key configured[/red]", err=True)
        ctx.exit(1)


@config.command("rotate")
@click.pass_context
def rotate_api_key(ctx):
    api = ctx.obj['api']
    config = ctx.obj['config']
    
    try:
        result = api.rotate_api_key()
        new_key = result.get("api_key")
        if new_key:
            config.api_key = new_key
            console.print("[green]API key rotated successfully[/green]")
        else:
            console.print("[red]Failed to rotate API key[/red]")
        
    except Exception as e:
        console.print(f"[red]Error rotating API key: {e}[/red]")


@cli.group()
def schedule():
    pass


@schedule.command("list")
@click.pass_context
def list_scheduled_jobs(ctx):
    scheduler = ctx.obj['scheduler']
    
    try:
        jobs = scheduler.list_jobs()
        
        if not jobs:
            console.print("[yellow]No scheduled jobs found.[/yellow]")
            return
        
        table = Table(title="Scheduled Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Schedule", style="green")
        table.add_column("Action", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Description", style="white")
        
        for job in jobs:
            status = "Enabled" if job["enabled"] else "Disabled"
            description = job["comment"].replace("lambdalabs-cli: ", "")
            table.add_row(
                job["id"][:8],  # Show first 8 chars of ID
                job["schedule"],
                job["command"].split()[-2:][0] if len(job["command"].split()) > 1 else "unknown",
                status,
                description
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing scheduled jobs: {e}[/red]")


@schedule.command("add-termination")
@click.option("--instance-id", "-i", help="Instance ID to terminate (leave empty for all instances)")
@click.option("--in", "-t", "duration_minutes", type=int, help="Terminate in X minutes")
@click.option("--at", "-a", "end_time", help="Terminate at specific time (HH:MM)")
@click.option("--description", "-d", help="Description for the scheduled job")
@click.pass_context
def add_termination_schedule(ctx, instance_id: Optional[str], duration_minutes: Optional[int], 
                           end_time: Optional[str], description: Optional[str]):
    scheduler = ctx.obj['scheduler']
    
    if not duration_minutes and not end_time:
        console.print("[red]Must specify either --in (minutes) or --at (HH:MM)[/red]")
        return
    
    try:
        job = scheduler.add_time_based_termination(
            instance_id=instance_id,
            duration_minutes=duration_minutes,
            end_time=end_time,
            description=description or ""
        )
        
        target_desc = f"in {duration_minutes} minutes" if duration_minutes else f"at {end_time}"
        instance_desc = f"instance {instance_id}" if instance_id else "all instances"
        console.print(f"[green]Scheduled termination of {instance_desc} {target_desc}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error scheduling termination: {e}[/red]")


@schedule.command("add-startup")
@click.option("--type", "-t", required=True, help="Instance type")
@click.option("--region", "-r", required=True, help="Region")
@click.option("--name", "-n", required=True, help="Instance name (required for idempotent scheduling)")
@click.option("--filesystem", "-f", help="Filesystem to attach")
@click.option("--cron", "-c", required=True, help="Cron schedule (e.g., '0 9 * * 1-5' for 9 AM weekdays)")
@click.option("--description", "-d", help="Description for the scheduled job")
@click.pass_context
def add_startup_schedule(ctx, type: str, region: str, name: str, 
                        filesystem: Optional[str], cron: str, description: Optional[str]):
    scheduler = ctx.obj['scheduler']
    
    try:
        job = scheduler.add_recurring_schedule(
            action="create_instance",
            cron_schedule=cron,
            description=description or f"Ensure {name} ({type}) in {region}",
            instance_type=type,
            region=region,
            name=name,
            filesystem=filesystem
        )
        
        console.print(f"[green]Scheduled idempotent instance startup: {cron}[/green]")
        console.print(f"[cyan]Instance '{name}' will be created if it doesn't exist[/cyan]")
        
    except Exception as e:
        console.print(f"[red]Error scheduling startup: {e}[/red]")


@schedule.command("add-recurring-termination")
@click.option("--instance-id", "-i", help="Instance ID to terminate")
@click.option("--instance-name", "-n", help="Instance name to terminate")
@click.option("--all", "terminate_all", is_flag=True, help="Terminate all instances")
@click.option("--cron", "-c", required=True, help="Cron schedule (e.g., '0 18 * * 1-5' for 6 PM weekdays)")
@click.option("--description", "-d", help="Description for the scheduled job")
@click.pass_context
def add_recurring_termination(ctx, instance_id: Optional[str], instance_name: Optional[str], 
                             terminate_all: bool, cron: str, description: Optional[str]):
    scheduler = ctx.obj['scheduler']
    
    # Validate that exactly one option is provided
    options_count = sum([bool(instance_id), bool(instance_name), bool(terminate_all)])
    if options_count != 1:
        console.print("[red]Must specify exactly one of: --instance-id, --instance-name, or --all[/red]")
        return
    
    try:
        if terminate_all:
            action = "terminate_all"
            kwargs = {}
            instance_desc = "all instances"
        elif instance_id:
            action = "terminate_instance"
            kwargs = {"instance_id": instance_id}
            instance_desc = f"instance {instance_id}"
        else:  # instance_name
            action = "terminate_instance_by_name"
            kwargs = {"instance_name": instance_name}
            instance_desc = f"instance '{instance_name}'"
        
        job = scheduler.add_recurring_schedule(
            action=action,
            cron_schedule=cron,
            description=description or f"Terminate {instance_desc}: {cron}",
            **kwargs
        )
        
        console.print(f"[green]Scheduled recurring termination of {instance_desc}: {cron}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error scheduling recurring termination: {e}[/red]")


@schedule.command("remove")
@click.argument("job_id")
@click.pass_context
def remove_scheduled_job(ctx, job_id: str):
    scheduler = ctx.obj['scheduler']
    
    try:
        if scheduler.remove_job(job_id):
            console.print(f"[green]Removed scheduled job {job_id}[/green]")
        else:
            console.print(f"[red]Job {job_id} not found[/red]")
        
    except Exception as e:
        console.print(f"[red]Error removing job: {e}[/red]")


@schedule.command("enable")
@click.argument("job_id")
@click.pass_context
def enable_scheduled_job(ctx, job_id: str):
    scheduler = ctx.obj['scheduler']
    
    try:
        if scheduler.enable_job(job_id):
            console.print(f"[green]Enabled scheduled job {job_id}[/green]")
        else:
            console.print(f"[red]Job {job_id} not found[/red]")
        
    except Exception as e:
        console.print(f"[red]Error enabling job: {e}[/red]")


@schedule.command("disable")
@click.argument("job_id")
@click.pass_context
def disable_scheduled_job(ctx, job_id: str):
    scheduler = ctx.obj['scheduler']
    
    try:
        if scheduler.disable_job(job_id):
            console.print(f"[green]Disabled scheduled job {job_id}[/green]")
        else:
            console.print(f"[red]Job {job_id} not found[/red]")
        
    except Exception as e:
        console.print(f"[red]Error disabling job: {e}[/red]")


@schedule.command("clear")
@click.confirmation_option(prompt="Are you sure you want to remove all scheduled jobs?")
@click.pass_context
def clear_all_jobs(ctx):
    scheduler = ctx.obj['scheduler']
    
    try:
        count = scheduler.clear_all_jobs()
        console.print(f"[green]Removed {count} scheduled jobs[/green]")
        
    except Exception as e:
        console.print(f"[red]Error clearing jobs: {e}[/red]")


@cli.command("info")
@click.pass_context
def info(ctx):
    api = ctx.obj['api']
    
    try:
        instance_types = api.list_instance_types()
        regions = api.list_regions()
        
        console.print("[bold]Available Instance Types:[/bold]")
        for instance_type in instance_types[:10]:  # Show first 10
            console.print(f"  • {instance_type.get('name', '')} - {instance_type.get('description', '')}")
        
        console.print(f"[dim]...and {len(instance_types) - 10} more[/dim]" if len(instance_types) > 10 else "")
        
        console.print("\n[bold]Available Regions:[/bold]")
        for region in regions:
            console.print(f"  • {region.get('name', '')} - {region.get('description', '')}")
        
    except Exception as e:
        console.print(f"[red]Error fetching info: {e}[/red]")


if __name__ == "__main__":
    cli()