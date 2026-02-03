import os
import json
import configparser
import logging
import shutil
from .config import CONFIG_DIR, PROFILES_FILE, TABLE_OFFSET

logger = logging.getLogger(__name__)

class ConfigStore:
    def __init__(self):
        self._ensure_dirs()
        self.profiles = self._load_profiles()

    def _ensure_dirs(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE, 'w') as f:
                json.dump({}, f)

    def _load_profiles(self):
        try:
            with open(PROFILES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load profiles: {e}")
            return {}

    def _save_profiles(self):
        with open(PROFILES_FILE, 'w') as f:
            json.dump(self.profiles, f, indent=2)

    def list_profiles(self):
        return self.profiles

    def get_profile(self, name):
        return self.profiles.get(name)

    def import_config(self, source_path, name):
        """
        Import a config file, validate it, and store it.
        """
        if name in self.profiles:
            raise ValueError(f"Profile '{name}' already exists.")

        # Validate config
        parsed = self._parse_wg_config(source_path)
        
        # Copy to storage
        dest_filename = f"{name}.conf"
        dest_path = os.path.join(CONFIG_DIR, dest_filename)
        shutil.copy(source_path, dest_path)

        # Allocate Table ID
        table_id = self._allocate_table_id()

        # Save metadata
        self.profiles[name] = {
            "config_path": dest_path,
            "table_id": table_id,
            "interface_name": f"sr_{name}"[:15], # Linux interface limit
            "endpoint": parsed['Peer'].get('Endpoint'),
            "allowed_ips": parsed['Peer'].get('AllowedIPs'),
            "address": parsed['Interface'].get('Address')
        }
        self._save_profiles()
        logger.info(f"Imported profile '{name}' (Table {table_id})")
        return self.profiles[name]

    def delete_profile(self, name):
        if name not in self.profiles:
            return
        
        cfg_path = self.profiles[name].get('config_path')
        if cfg_path and os.path.exists(cfg_path):
            os.remove(cfg_path)
        
        del self.profiles[name]
        self._save_profiles()
        logger.info(f"Deleted profile '{name}'")

    def _allocate_table_id(self):
        used_ids = {p['table_id'] for p in self.profiles.values()}
        next_id = TABLE_OFFSET
        while next_id in used_ids:
            next_id += 1
        return next_id

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
        
        return {
            'Interface': dict(config['Interface']),
            'Peer': dict(config[peers[0]])
        }
