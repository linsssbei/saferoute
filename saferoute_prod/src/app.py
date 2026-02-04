import click
import sys
import logging
import time
from .utils import setup_logging, enable_ipv4_forwarding, enable_masquerade, enable_src_valid_mark, enable_forwarding_allow
from .config_store import ConfigStore
from .tunnel_manager import TunnelManager
from .route_manager import RouteManager
from .startup_manager import StartupManager

setup_logging()
logger = logging.getLogger('app')


@click.group()
def cli():
    """Saferoute - WireGuard tunnel and routing manager"""
    pass


@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
def startup(config_file):
    """
    Auto-setup from config file.
    
    Reads config.yaml to discover WireGuard configs and device mappings,
    then automatically imports, sets up tunnels, and applies mappings.
    """
    # Enable system settings first
    enable_ipv4_forwarding()
    enable_src_valid_mark()
    enable_masquerade()
    enable_forwarding_allow()  # CRITICAL: Allow unmapped traffic to pass through
    
    # Initialize components
    store = ConfigStore()
    tm = TunnelManager(store)
    rm = RouteManager(store)
    sm = StartupManager(store, tm, rm)
    
    try:
        sm.startup(config_file)
        click.echo(click.style("✓ Startup complete!", fg='green', bold=True))
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        click.echo(click.style(f"✗ Startup failed: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command(name='import')
@click.argument('file', type=click.Path(exists=True))
@click.argument('name')
def import_config(file, name):
    """Import a WireGuard config file."""
    store = ConfigStore()
    try:
        store.import_config(file, name)
        click.echo(click.style(f"✓ Imported {name}", fg='green'))
    except Exception as e:
        logger.error(f"Import failed: {e}")
        click.echo(click.style(f"✗ Import failed: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('name')
def setup(name):
    """Setup a WireGuard tunnel."""
    store = ConfigStore()
    tm = TunnelManager(store)
    
    try:
        tm.setup_tunnel(name)
        click.echo(click.style(f"✓ Tunnel '{name}' is up", fg='green'))
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        click.echo(click.style(f"✗ Setup failed: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
@click.argument('ip')
@click.argument('tunnel')
def map(ip, tunnel):
    """Map a device IP to a tunnel."""
    store = ConfigStore()
    rm = RouteManager(store)
    
    try:
        rm.add_mapping(ip, tunnel)
        click.echo(click.style(f"✓ Mapped {ip} → {tunnel}", fg='green'))
    except Exception as e:
        logger.error(f"Mapping failed: {e}")
        click.echo(click.style(f"✗ Mapping failed: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command()
def list():
    """List all profiles and device mappings."""
    store = ConfigStore()
    rm = RouteManager(store)
    
    click.echo(click.style("Profiles:", fg='cyan', bold=True))
    profiles = store.list_profiles()
    if profiles:
        for name, p in profiles.items():
            click.echo(f"  • {name}: Table {p['table_id']}, Interface {p['interface_name']}")
    else:
        click.echo("  (none)")
    
    click.echo()
    click.echo(click.style("Device Mappings:", fg='cyan', bold=True))
    mappings = rm.list_mappings()
    if mappings:
        for m in mappings:
            click.echo(f"  • {m['ip']} → {m['tunnel']}")
    else:
        click.echo("  (none)")


@cli.command()
def start():
    """
    Start daemon mode (setup all tunnels and apply rules).
    
    This is the default command when running as a container.
    """
    logger.info("Starting Saferoute in daemon mode...")
    
    # 1. Enable Forwarding/NAT
    enable_ipv4_forwarding()
    enable_src_valid_mark()
    enable_masquerade()
    enable_forwarding_allow()

    # 2. Setup All Tunnels
    store = ConfigStore()
    tm = TunnelManager(store)
    rm = RouteManager(store)
    
    profiles = store.list_profiles()
    for name in profiles:
        try:
            tm.setup_tunnel(name)
        except Exception as e:
            logger.error(f"Failed to setup tunnel {name}: {e}")

    # 3. Apply Rules
    rm.sync_rules()

    logger.info("Startup complete. Entering wait loop.")
    click.echo(click.style("✓ Saferoute is running", fg='green', bold=True))
    
    # Keep alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        sys.exit(0)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
