import click
import logging
import subprocess
import time
import sys
from .wg import setup_tunnel

logging.basicConfig(level=logging.INFO)

@click.group()
def main():
    """Saferoute: WireGuard Routing in Isolated Namespaces"""
    pass

@main.command()
@click.option('--config', '-c', required=True, type=click.Path(exists=True), help='Path to WireGuard config file (e.g., wg0.conf)')
@click.option('--ns', default='saferoute_ns', help='Name of the Network Namespace to create')
def connect(config, ns):
    """Establish the WireGuard tunnel"""
    click.echo(f"Connecting using config: {config} in namespace: {ns}")
    
    try:
        setup_tunnel(config, ns_name=ns)
        click.echo(click.style("Tunnel established successfully!", fg='green'))
        
        while True:
            click.echo("\nOptions: [v]erify IP, [s]hell, [q]uit")
            char = click.getchar()
            if char in ('q', 'Q'):
                break
            elif char in ('v', 'V'):
                # Run verify logic
                click.echo("\n--- WireGuard Status ---")
                try:
                    subprocess.run(["ip", "netns", "exec", ns, "wg", "show"], timeout=5)
                except Exception:
                    pass
                
                click.echo("\n--- IP Verification ---")
                cmd = ["ip", "netns", "exec", ns, "curl", "-s", "https://ipinfo.io/json"]
                click.echo(f"Running verification...")
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    click.echo(res.stdout)
                    if res.stderr:
                        click.echo(click.style(res.stderr, fg='red'))
                except Exception as e:
                    click.echo(f"Error: {e}")
            elif char in ('s', 'S'):
                # Launch shell
                click.echo(f"Launching shell in {ns}. Type 'exit' to return.")
                subprocess.run(["ip", "netns", "exec", ns, "bash"])
            
    except Exception as e:
        click.echo(click.style(f"Connection failed: {e}", fg='red'))
        sys.exit(1)

@main.command()
@click.option('--ns', default='saferoute_ns', help='Network Namespace to use')
def verify(ns):
    """Check current IP address inside the tunnel"""
    cmd = ["ip", "netns", "exec", ns, "curl", "-s", "https://ipinfo.io/json"]
    click.echo(f"Running verification in namespace {ns}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo(click.style(f"Failed to verify: {result.stderr}", fg='red'))
    except Exception as e:
        click.echo(f"Error running verification: {e}")

@main.command()
@click.option('--ns', default='saferoute_ns', help='Network Namespace to use')
def shell(ns):
    """Launch a shell inside the tunnel namespace"""
    click.echo(f"Launching shell in {ns}. Type 'exit' to leave.")
    # We use 'ip netns exec' to verify getting a shell
    subprocess.run(["ip", "netns", "exec", ns, "bash"])

if __name__ == '__main__':
    main()
