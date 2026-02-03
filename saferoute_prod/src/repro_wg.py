from pyroute2 import WireGuard
from src.tunnel_manager import TunnelManager
from src.config_store import ConfigStore
import logging
import sys

# Configure logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

class MockConfigStore(ConfigStore):
    def get_profile(self, name):
        return {
            'interface_name': 'wg_vpn_mock',
            'table_id': 100,
            'config_path': '/app/data/configs/mock_vpn.conf'
        }
    
    def _parse_wg_config(self, path):
         # Validating that we are returning EXACTLY what we want to test
         # The 'Address' and 'PrivateKey' keys come from Interface section
         return {
             'Interface': {
                 'PrivateKey': 'aAXd+IeSkXCydp6YJAufGJ28dQMDLJdN5Pgcezn0F3k=',
                 'Address': '10.13.13.2/32' 
             },
             'Peer': {
                 'PublicKey': 'V+6CrzEaWKXZFM0D1lWgvt0NtirDQLB8vcoe4+EPdCY=',
                 'AllowedIPs': '0.0.0.0/0',
                 'Endpoint': '172.29.0.2:51820',
                 'PersistentKeepalive': '25'
             }
         }

print("Starting TunnelManager test...")
try:
    store = MockConfigStore()
    tm = TunnelManager(store)
    tm.setup_tunnel("vpn_mock")
    print("Success: TunnelManager setup completed")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
