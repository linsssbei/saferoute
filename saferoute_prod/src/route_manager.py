import json
import os
import logging
from pyroute2 import IPRoute
from .config import DEVICES_FILE, DEVICE_PRIORITY_BASE
from .config_store import ConfigStore

logger = logging.getLogger(__name__)

class RouteManager:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store
        self._ensure_devices_file()

    def _ensure_devices_file(self):
        if not os.path.exists(DEVICES_FILE):
            with open(DEVICES_FILE, 'w') as f:
                json.dump([], f)

    def load_mappings(self):
        try:
            with open(DEVICES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def save_mappings(self, mappings):
        with open(DEVICES_FILE, 'w') as f:
            json.dump(mappings, f, indent=2)

    def add_mapping(self, ip_addr, tunnel_name):
        mappings = self.load_mappings()
        # Remove existing for this IP
        mappings = [m for m in mappings if m['ip'] != ip_addr]
        
        # Verify tunnel exists
        profile = self.config_store.get_profile(tunnel_name)
        if not profile:
            raise ValueError(f"Tunnel '{tunnel_name}' does not exist")
        
        mappings.append({'ip': ip_addr, 'tunnel': tunnel_name})
        self.save_mappings(mappings)
        logger.info(f"Mapped {ip_addr} -> {tunnel_name}")
        
        # Apply immediately
        self.apply_rule_for_ip(ip_addr, tunnel_name)

    def list_mappings(self):
        return self.load_mappings()

    def sync_rules(self):
        """
        Applies all rules from storage.
        """
        mappings = self.load_mappings()
        logger.info(f"Syncing rules for {len(mappings)} devices")
        for m in mappings:
            try:
                self.apply_rule_for_ip(m['ip'], m['tunnel'])
            except Exception as e:
                logger.error(f"Failed to apply rule for {m['ip']}: {e}")

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
