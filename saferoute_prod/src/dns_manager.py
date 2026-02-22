"""
DNS Manager - Prevents DNS leaks by managing iptables DNAT rules.

This module sets up iptables rules to redirect DNS queries (port 53)
from client IPs to use the VPN provider's DNS servers through the tunnel.
"""
import logging
import subprocess
import shutil

logger = logging.getLogger(__name__)

# Detect which iptables command to use (legacy vs nf_tables)
IPTABLES_CMD = 'iptables-legacy' if shutil.which('iptables-legacy') else 'iptables'


class DNSManager:
    """
    Manages DNS routing using iptables DNAT rules to prevent DNS leaks.
    
    Tracks active DNS rules per client IP for debugging and cleanup.
    """
    
    def __init__(self):
        """Initialize DNS manager with empty rule tracking."""
        # Track active DNS rules: {ip_addr: {dns_servers: [...], primary_dns: str}}
        self.active_rules = {}
    
    def setup_dns_for_client(self, client_ip: str, dns_servers: list, table_id: int):
        """
        Set up iptables DNAT rules to redirect DNS queries from client_ip 
        to use dns_servers through the VPN tunnel routing table.
        
        Args:
            client_ip: IP address of the client device (e.g., '192.168.1.100')
            dns_servers: List of DNS server IPs from WireGuard config
            table_id: Routing table ID for the VPN tunnel
        """
        if not dns_servers:
            logger.warning(f"No DNS servers provided for {client_ip}")
            return
        
        # Clean up any existing rules for this client first
        self.cleanup_dns_for_client(client_ip)
        
        logger.info(f"Setting up DNS DNAT for {client_ip} -> {dns_servers}")
        
        # Use first DNS server (most VPN configs list primary first)
        primary_dns = dns_servers[0]
        
        try:
            # Add UDP DNS redirect rule
            subprocess.run([
                IPTABLES_CMD, '-t', 'nat', '-I', 'PREROUTING',
                '-s', client_ip,
                '-p', 'udp', '--dport', '53',
                '-j', 'DNAT', '--to-destination', f'{primary_dns}:53'
            ], check=True, capture_output=True, text=True)
            logger.debug(f"Added UDP DNS rule: {client_ip}:53 -> {primary_dns}:53")
            
            # Add TCP DNS redirect rule (needed for large responses)
            subprocess.run([
                IPTABLES_CMD, '-t', 'nat', '-I', 'PREROUTING',
                '-s', client_ip,
                '-p', 'tcp', '--dport', '53',
                '-j', 'DNAT', '--to-destination', f'{primary_dns}:53'
            ], check=True, capture_output=True, text=True)
            logger.debug(f"Added TCP DNS rule: {client_ip}:53 -> {primary_dns}:53")
            
            # Track the rules for debugging and cleanup
            self.active_rules[client_ip] = {
                'dns_servers': dns_servers,
                'primary_dns': primary_dns,
                'table_id': table_id
            }
            
            logger.info(f"DNS leak prevention active for {client_ip}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to setup DNS rules for {client_ip}: {e.stderr}")
            # Attempt cleanup if partial setup
            self.cleanup_dns_for_client(client_ip)
            raise
    
    def cleanup_dns_for_client(self, client_ip: str):
        """
        Remove all DNS DNAT rules for a specific client IP.
        
        Args:
            client_ip: IP address of the client device
        """
        logger.info(f"Cleaning up DNS rules for {client_ip}")
        
        try:
            # Get current rules and find line numbers for this client
            result = subprocess.run([
                IPTABLES_CMD, '-t', 'nat', '-L', 'PREROUTING', '-n', '--line-numbers'
            ], capture_output=True, text=True, check=True)
            
            # Find all line numbers for DNS rules matching this client IP
            lines_to_delete = []
            for line in result.stdout.split('\n'):
                if client_ip in line and 'dpt:53' in line and 'DNAT' in line:
                    # Extract line number (first column)
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        lines_to_delete.append(int(parts[0]))
            
            # Delete rules in reverse order (so line numbers don't shift)
            for line_num in sorted(lines_to_delete, reverse=True):
                try:
                    subprocess.run([
                        IPTABLES_CMD, '-t', 'nat', '-D', 'PREROUTING', str(line_num)
                    ], capture_output=True, text=True, check=True)
                    logger.debug(f"Deleted DNS rule at line {line_num} for {client_ip}")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Failed to delete rule at line {line_num}: {e.stderr}")
            
            if lines_to_delete:
                logger.info(f"DNS cleanup complete for {client_ip} ({len(lines_to_delete)} rules removed)")
            else:
                logger.debug(f"No DNS rules found for {client_ip}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup DNS for {client_ip}: {e}")
        
        # Remove from tracking
        if client_ip in self.active_rules:
            del self.active_rules[client_ip]

    
    def get_dns_rules_for_client(self, client_ip: str):
        """
        Return DNS configuration for a specific client by parsing actual iptables rules.
        For debugging UI.
        
        Args:
            client_ip: IP address of the client device
            
        Returns:
            dict with DNS configuration or None if no rules exist
        """
        try:
            # Query actual iptables rules
            result = subprocess.run([
                IPTABLES_CMD, '-t', 'nat', '-L', 'PREROUTING', '-n', '-v'
            ], capture_output=True, text=True, check=True)
            
            # Parse output to find rules for this client
            dns_servers = []
            for line in result.stdout.split('\n'):
                if client_ip in line and 'dpt:53' in line and 'DNAT' in line:
                    # Extract destination DNS server from "to:IP:53"
                    parts = line.split('to:')
                    if len(parts) > 1:
                        dns_ip = parts[1].split(':')[0]
                        if dns_ip not in dns_servers:
                            dns_servers.append(dns_ip)
            
            if dns_servers:
                return {
                    'dns_servers': dns_servers,
                    'primary_dns': dns_servers[0],
                    'active': True
                }
            return None
            
        except Exception as e:
            logger.warning(f"Failed to query iptables for {client_ip}: {e}")
            return None
    
    def get_all_dns_rules(self):
        """
        Return all active DNS rules by parsing actual iptables output.
        For debugging UI.
        
        Returns:
            dict mapping client IPs to their DNS configurations
        """
        try:
            # Query actual iptables rules
            result = subprocess.run([
                IPTABLES_CMD, '-t', 'nat', '-L', 'PREROUTING', '-n', '-v'
            ], capture_output=True, text=True, check=True)
            
            # Parse output to find all DNS DNAT rules
            rules = {}
            for line in result.stdout.split('\n'):
                if 'DNAT' in line and 'dpt:53' in line:
                    # Extract source IP and destination DNS
                    parts = line.split()
                    if len(parts) >= 8:
                        # Find source IP (after protocol columns)
                        try:
                            source_idx = parts.index('--') + 3  # Skip prot opt in out
                            source_ip = parts[source_idx]
                            
                            # Extract destination DNS from "to:IP:53"
                            for part in parts:
                                if part.startswith('to:'):
                                    dns_ip = part.split(':')[1]
                                    
                                    if source_ip not in rules:
                                        rules[source_ip] = {
                                            'dns_servers': [],
                                            'primary_dns': dns_ip
                                        }
                                    if dns_ip not in rules[source_ip]['dns_servers']:
                                        rules[source_ip]['dns_servers'].append(dns_ip)
                                    break
                        except (ValueError, IndexError):
                            continue
            
            return rules
            
        except Exception as e:
            logger.warning(f"Failed to query iptables: {e}")
            return {}
