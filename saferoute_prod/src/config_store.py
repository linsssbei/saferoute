import os
import json
import shutil
import configparser
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Config paths
CONFIG_DIR = os.environ.get('CONFIG_DIR', '/app/data/configs')
WIREGUARD_DIR = os.path.join(CONFIG_DIR, 'wireguard')
PROFILES_FILE = os.path.join(CONFIG_DIR, 'profiles.json')

class ConfigStore:
    def __init__(self):
        self.profiles = {}
        self._ensure_dirs()
        self._load_profiles()
    
    def _ensure_dirs(self):
        os.makedirs(WIREGUARD_DIR, exist_ok=True)
    
    def _load_profiles(self):
        if os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE, 'r') as f:
                self.profiles = json.load(f)
    
    def _save_profiles(self):
        with open(PROFILES_FILE, 'w') as f:
            json.dump(self.profiles, f, indent=2)
    
    def _allocate_table_id(self):
        existing_ids = [p['table_id'] for p in self.profiles.values()]
        return max(existing_ids, default=99) + 1
    
    def import_config(self, source_path, name):
        """Import a WireGuard config file."""
        # Validate and parse
        parsed = self._parse_wg_config(source_path)
        
        # Check if name already exists
        if name in self.profiles:
            raise ValueError(f"Profile '{name}' already exists")
        
        # Determine destination path
        dest_path = os.path.join(WIREGUARD_DIR, f"{name}.conf")
        
        # Only copy if source and destination are different
        source_abs = os.path.abspath(source_path)
        dest_abs = os.path.abspath(dest_path)
        
        if source_abs != dest_abs:
            shutil.copy(source_path, dest_path)
            logger.info(f"Copied config from {source_path} to {dest_path}")
        else:
            logger.info(f"Config already in correct location: {dest_path}")
        
        # Allocate routing table ID
        table_id = self._allocate_table_id()

        # Save metadata
        self.profiles[name] = {
            "config_path": dest_path,
            "table_id": table_id,
            "interface_name": f"sr_{name}"[:15], # Linux interface limit
            "endpoint": parsed['Peer'].get('Endpoint'),
            "allowed_ips": parsed['Peer'].get('AllowedIPs'),
            "address": parsed['Interface'].get('Address'),
            "dns_servers": parsed.get('dns_servers', [])
        }
        self._save_profiles()
        logger.info(f"Imported profile '{name}' (Table {table_id})")
        return self.profiles[name]

    def delete_profile(self, name):
        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' not found")
        
        # Delete config file
        config_path = self.profiles[name]['config_path']
        if os.path.exists(config_path):
            os.remove(config_path)
        
        # Remove from profiles
        del self.profiles[name]
        self._save_profiles()
        logger.info(f"Deleted profile '{name}'")

    def get_profile(self, name):
        return self.profiles.get(name)
    
    def list_profiles(self):
        return self.profiles

    def _parse_wg_config(self, path):
        config = configparser.ConfigParser()
        config.optionxform = str # Preserve case for WireGuard keys
        try:
            config.read(path)
        except Exception as e:
            raise ValueError(f"Invalid config file: {e}")

        if 'Interface' not in config:
            raise ValueError("Missing [Interface] section")
        
        # Taking first available peer
        peers = [s for s in config.sections() if s == 'Peer']
        if not peers:
             raise ValueError("Missing [Peer] section")
        
        # Parse DNS servers from Interface section
        interface_dict = dict(config['Interface'])
        dns_str = interface_dict.get('DNS', '')
        dns_servers = [s.strip() for s in dns_str.split(',') if s.strip()]
        
        return {
            'Interface': interface_dict,
            'Peer': dict(config[peers[0]]),
            'dns_servers': dns_servers
        }
