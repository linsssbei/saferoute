import yaml
import os
import logging
from pathlib import Path
from pyroute2 import IPRoute
from .config import DEVICE_PRIORITY_BASE
from .config_store import ConfigStore
from .dns_manager import DNSManager

logger = logging.getLogger(__name__)

# Use the same YAML file as the UI
CONFIG_DIR = os.environ.get('CONFIG_DIR', '/app/data/configs')
MAPPINGS_FILE = os.path.join(CONFIG_DIR, 'mappings', 'devices.yaml')

class RouteManager:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store
        self.dns_manager = DNSManager()
        self._ensure_mappings_file()

    def _ensure_mappings_file(self):
        mappings_path = Path(MAPPINGS_FILE)
        if not mappings_path.exists():
            mappings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(mappings_path, 'w') as f:
                yaml.dump({'devices': []}, f)

    def load_mappings(self):
        try:
            with open(MAPPINGS_FILE, 'r') as f:
                config = yaml.safe_load(f) or {}
                return config.get('devices', [])
        except Exception:
            return []

    def save_mappings(self, mappings):
        mappings_path = Path(MAPPINGS_FILE)
        mappings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mappings_path, 'w') as f:
            yaml.dump({'devices': mappings}, f, default_flow_style=False)

    def add_mapping(self, ip_addr, tunnel_name, active=True):
        mappings = self.load_mappings()
        
        # Find existing mapping for this IP to preserve fields like 'active', 'nickname'
        existing = next((m for m in mappings if m['ip'] == ip_addr), None)
        
        # Remove existing for this IP
        mappings = [m for m in mappings if m['ip'] != ip_addr]
        
        # Verify tunnel exists
        profile = self.config_store.get_profile(tunnel_name)
        if not profile:
            raise ValueError(f"Tunnel '{tunnel_name}' does not exist")
        
        # Create new mapping, preserving existing fields
        new_mapping = {'ip': ip_addr, 'tunnel': tunnel_name}
        if existing:
            # Preserve all existing fields except ip and tunnel
            for key, value in existing.items():
                if key not in ['ip', 'tunnel']:
                    new_mapping[key] = value
        else:
            # New mapping - set active based on parameter
            new_mapping['active'] = active
            
        mappings.append(new_mapping)
        self.save_mappings(mappings)
        logger.info(f"Mapped {ip_addr} -> {tunnel_name} (active={new_mapping.get('active', True)})")
        
        # Apply immediately only if active
        if new_mapping.get('active', True):
            self.apply_rule_for_ip(ip_addr, tunnel_name)

    def list_mappings(self):
        return self.load_mappings()

    def sync_rules(self):
        """
        Applies all ACTIVE rules from storage.
        Also cleans up DNS rules for INACTIVE mappings.
        """
        mappings = self.load_mappings()
        logger.info(f"Syncing rules for {len(mappings)} devices")
        
        # First, clean up ALL existing DNS rules to start fresh
        for m in mappings:
            try:
                self.dns_manager.cleanup_dns_for_client(m['ip'])
            except Exception as e:
                logger.debug(f"No DNS rules to clean for {m['ip']}: {e}")
        
        # Now apply rules only for ACTIVE mappings
        for m in mappings:
            is_active = m.get('active', True)  # Default to active if not specified
            
            if is_active:
                try:
                    self.apply_rule_for_ip(m['ip'], m['tunnel'])
                except Exception as e:
                    logger.error(f"Failed to apply rule for {m['ip']}: {e}")
            else:
                # Inactive mapping - ensure routing rule is also removed
                logger.info(f"Skipping inactive mapping: {m['ip']}")
                with IPRoute() as ip:
                    try:
                        ip.rule('del', src=m['ip'])
                    except Exception:
                        pass  # Already removed

    def apply_rule_for_ip(self, ip_addr, tunnel_name):
        profile = self.config_store.get_profile(tunnel_name)
        if not profile:
            logger.warning(f"Skipping rule for {ip_addr}: Tunnel {tunnel_name} missing")
            return

        table_id = profile['table_id']
        
        # Delete old rules for this IP (cleanup)
        # Using pyroute2 to delete any rule with this src
        with IPRoute() as ip:
            # We must be careful not to delete system rules.
            # But here we only target rules with source = ip_addr
            # pyroute2.rule('del', ...) is best effort
            try:
                ip.rule('del', src=ip_addr)
            except Exception:
                pass # Usually NetlinkError if not found
            
            # Add new rule
            # ip rule add from <IP> lookup <TABLE> pref <PRIO>
            logger.info(f"Adding rule: {ip_addr} -> Table {table_id}")
            try:
                ip.rule('add', src=ip_addr, table=table_id, priority=DEVICE_PRIORITY_BASE)
            except Exception as e:
                 # Check if it exists? pyroute2 often allows duplicates if not strict.
                 logger.error(f"Rule add failed: {e}")
        
        # Set up DNS routing for this client
        dns_servers = profile.get('dns_servers', [])
        if dns_servers:
            logger.info(f"Setting up DNS for {ip_addr}: {dns_servers}")
            try:
                self.dns_manager.setup_dns_for_client(ip_addr, dns_servers, table_id)
            except Exception as e:
                logger.error(f"Failed to setup DNS for {ip_addr}: {e}")
        else:
            logger.warning(f"No DNS servers found for tunnel {tunnel_name}")

    def flush_all_device_rules(self):
        """
        Remove all routing rules with our device priority.
        This cleans up before re-applying mappings.
        """
        with IPRoute() as ip:
            try:
                # Get all rules
                rules = ip.get_rules()
                deleted_count = 0
                
                for rule in rules:
                    # Check if this is one of our device rules (by priority)
                    attrs = dict(rule['attrs'])
                    priority = attrs.get('FRA_PRIORITY')
                    
                    if priority == DEVICE_PRIORITY_BASE:
                        # This is one of our rules, delete it
                        try:
                            src = attrs.get('FRA_SRC')
                            if src:
                                ip.rule('del', src=src, priority=priority)
                                deleted_count += 1
                                logger.debug(f"Deleted rule for {src}")
                        except Exception as e:
                            logger.warning(f"Failed to delete rule: {e}")
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} existing device rules")
            except Exception as e:
                logger.error(f"Error flushing device rules: {e}")
