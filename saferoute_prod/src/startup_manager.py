import yaml
import logging
import os
from pathlib import Path
from typing import Dict, List
from .config_store import ConfigStore, CONFIG_DIR
from .tunnel_manager import TunnelManager
from .route_manager import RouteManager

logger = logging.getLogger(__name__)

class StartupManager:
    """
    Manages automatic startup from a configuration file.
    Reads config.yaml to find WireGuard configs and device mappings.
    """
    
    def __init__(self, config_store: ConfigStore, tunnel_manager: TunnelManager, route_manager: RouteManager):
        self.config_store = config_store
        self.tunnel_manager = tunnel_manager
        self.route_manager = route_manager
    
    def startup(self, config_file: str):
        """
        Perform automatic startup from a configuration file.
        
        Args:
            config_file: Path to YAML config file specifying:
                - wireguard_configs: Directory containing .conf files
                - device_mappings: Path to devices.yaml file (default: devices.yaml)
        
        Process:
            1. Read config file
            2. Discover all .conf files in wireguard_configs directory
            3. Import each as a tunnel profile
            4. Read device_mappings file
            5. Setup all tunnels
            6. Map all devices to their assigned tunnels
        """
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise ValueError(f"Config file does not exist: {config_file}")
        
        logger.info(f"Starting automatic setup from {config_file}")
        
        # Read the config file
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to read config file: {e}")
        
        wireguard_dir = Path(config.get('wireguard_configs', ''))
        device_mappings_file = Path(config.get('device_mappings', 'devices.yaml'))
        
        if not wireguard_dir.exists():
            raise ValueError(f"WireGuard configs directory does not exist: {wireguard_dir}")
        
        logger.info(f"WireGuard configs directory: {wireguard_dir}")
        logger.info(f"Device mappings file: {device_mappings_file}")
        
        # Initialize tunnel names dictionary
        tunnel_names = {}
        
        # Step 1: Auto-discover WireGuard configs in the wireguard directory
        # This allows users to just copy .conf files and click "Apply All"
        wireguard_config_dir = Path(CONFIG_DIR) / 'wireguard'
        if wireguard_config_dir.exists():
            conf_files = list(wireguard_config_dir.glob("*.conf"))
            if conf_files:
                logger.info(f"Auto-discovering configs in {wireguard_config_dir}")
                logger.info(f"Found {len(conf_files)} WireGuard config files")
                
                for conf_file in conf_files:
                    tunnel_name = conf_file.stem
                    tunnel_names[tunnel_name] = str(conf_file)
                    
                    # Check if already imported
                    existing = self.config_store.get_profile(tunnel_name)
                    if existing:
                        logger.info(f"  Profile '{tunnel_name}' already imported, skipping")
                    else:
                        try:
                            logger.info(f"  Importing {conf_file.name} as '{tunnel_name}'")
                            self.config_store.import_config(str(conf_file), tunnel_name)
                            logger.info(f"  ✓ Imported '{tunnel_name}'")
                        except Exception as e:
                            logger.error(f"  ✗ Failed to import {conf_file.name}: {e}")
                            continue
        
        # Step 1b: Also check the legacy wireguard_configs path from config file
        if wireguard_dir.exists() and wireguard_dir != wireguard_config_dir:
            conf_files = list(wireguard_dir.glob("*.conf"))
            if conf_files:
                logger.info(f"Found {len(conf_files)} additional configs in {wireguard_dir}")
                
                for conf_file in conf_files:
                    tunnel_name = conf_file.stem
                    if tunnel_name in tunnel_names:
                        continue  # Already processed
                    
                    tunnel_names[tunnel_name] = str(conf_file)
                    
                    existing = self.config_store.get_profile(tunnel_name)
                    if existing:
                        logger.info(f"  Profile '{tunnel_name}' already exists, skipping import")
                    else:
                        try:
                            logger.info(f"  Importing {conf_file.name} as '{tunnel_name}'")
                            self.config_store.import_config(str(conf_file), tunnel_name)
                            logger.info(f"  ✓ Imported '{tunnel_name}'")
                        except Exception as e:
                            logger.error(f"  ✗ Failed to import {conf_file.name}: {e}")
                            continue
        
        if not tunnel_names:
            logger.warning("No WireGuard configs found to import")
            return
        
        # Step 2: Read device mappings
        if not device_mappings_file.exists():
            logger.warning(f"Device mappings file not found: {device_mappings_file}, skipping device mappings")
            devices = []
        else:
            try:
                with open(device_mappings_file, 'r') as f:
                    mappings_config = yaml.safe_load(f)
                    devices = mappings_config.get('devices', [])
                logger.info(f"Loaded {len(devices)} device mappings from {device_mappings_file.name}")
            except Exception as e:
                logger.error(f"Failed to read device mappings: {e}")
                devices = []
        
        # Step 3: Setup all tunnels
        logger.info("Cleaning up stale tunnels...")
        self.tunnel_manager.cleanup_stale_tunnels()

        logger.info("Setting up tunnels...")
        setup_tunnels = []
        for tunnel_name in tunnel_names.keys():
            try:
                logger.info(f"Setting up tunnel '{tunnel_name}'")
                self.tunnel_manager.setup_tunnel(tunnel_name)
                setup_tunnels.append(tunnel_name)
                logger.info(f"  ✓ Tunnel '{tunnel_name}' is up")
            except Exception as e:
                logger.error(f"  ✗ Failed to setup '{tunnel_name}': {e}")
                continue
        
        # Step 4: Clean up existing device routing rules
        logger.info("Cleaning up existing device routing rules...")
        self.route_manager.flush_all_device_rules()
        
        # Step 5: Map devices to tunnels
        if devices:
            logger.info("Mapping devices to tunnels...")
            for device in devices:
                device_ip = device.get('ip')
                tunnel_name = device.get('tunnel')
                active = device.get('active', True)  # Default to active if not specified
                
                if not device_ip or not tunnel_name:
                    logger.warning(f"Invalid device entry: {device}")
                    continue
                
                if not active:
                    logger.info(f"Skipping inactive mapping: {device_ip}")
                    continue
                
                if tunnel_name not in setup_tunnels:
                    logger.warning(f"  Tunnel '{tunnel_name}' not available for device {device_ip}, skipping")
                    continue
                
                try:
                    logger.info(f"Mapping {device_ip} → {tunnel_name}")
                    self.route_manager.add_mapping(device_ip, tunnel_name)
                    logger.info(f"  ✓ Mapped {device_ip} → {tunnel_name}")
                except Exception as e:
                    logger.error(f"  ✗ Failed to map {device_ip}: {e}")
                    continue
        
        # Step 6: Sync rules to ensure DNS cleanup for inactive mappings
        logger.info("Syncing routing and DNS rules...")
        try:
            self.route_manager.sync_rules()
            logger.info("  ✓ Rules synced successfully")
        except Exception as e:
            logger.error(f"  ✗ Failed to sync rules: {e}")
        
        logger.info("Startup complete!")
        logger.info(f"  Tunnels active: {len(setup_tunnels)}")
        logger.info(f"  Devices mapped: {len(devices)}")
