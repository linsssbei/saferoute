import logging
import os
import socket
from pyroute2 import IPRoute, WireGuard
from .config_store import ConfigStore

logger = logging.getLogger(__name__)

class TunnelManager:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store

    def setup_tunnel(self, name):
        profile = self.config_store.get_profile(name)
        if not profile:
            raise ValueError(f"Profile {name} not found")

        ifname = profile['interface_name']
        table_id = profile['table_id']
        config_path = profile['config_path']

        logger.info(f"Setting up tunnel {name} on {ifname} (Table {table_id})")

        # 1. Cleanup existing
        self.teardown_tunnel(name)

        # 2. Parse Config
        parsed = self.config_store._parse_wg_config(config_path)

        priv_key = parsed['Interface'].get('PrivateKey').strip()
        address_cidr = parsed['Interface'].get('Address').strip()
        peer_pub = parsed['Peer'].get('PublicKey').strip()
        endpoint = parsed['Peer'].get('Endpoint').strip()
        allowed_ips = parsed['Peer'].get('AllowedIPs', '0.0.0.0/0').strip()

        # Resolve Endpoint
        try:
            ep_host, ep_port = endpoint.split(':')
            ep_ip = socket.gethostbyname(ep_host)
            ep_port = int(ep_port)
        except Exception as e:
            logger.error(f"Failed to resolve endpoint {endpoint}: {e}")
            raise

        # 3. Create Interface & Configure WireGuard (NETLINK)
        with IPRoute() as ip:
            # Create interface
            # ip link add dev <ifname> type wireguard
            ip.link('add', ifname=ifname, kind='wireguard')
            
            # Get interface index
            idx = ip.link_lookup(ifname=ifname)[0]
            
            # Set MTU
            ip.link('set', index=idx, mtu=1280)
            
            # Add Address
            # ip addr add <address> dev <ifname>
            ip.addr('add', index=idx, address=address_cidr.split('/')[0], mask=int(address_cidr.split('/')[1]))
            
            # Bring Up
            ip.link('set', index=idx, state='up')

        # 4. Configure WireGuard (Keys/Peers)
        # We need to construct the peer dict for pyroute2.WireGuard
        # valid keys for set: 'private_key', 'listen_port', 'fwmark', 'peer_d'
        # peer_d is a list of dicts.
        
        wg = WireGuard()
        

        if allowed_ips:
            # Parse comma-separated IPs into list
            allowed_ips_list = [ip.strip() for ip in allowed_ips.split(',') if ip.strip()]
        else:
             allowed_ips_list = []

        peer_dict = {
            'public_key': peer_pub,
            'endpoint_addr': ep_ip,
            'endpoint_port': ep_port,
            'allowed_ips': allowed_ips_list,
            'persistent_keepalive': 25,
            'replace_allowed_ips': True
        }

        logger.info("Configuring WireGuard crypto details via Netlink")
        # Pass peer as a DICT, not a list.
        # Pass keys as STRINGS (Base64), not bytes.
        wg.set(ifname, private_key=priv_key, peer=peer_dict)
        wg.close()


        # 6. Pin Endpoint (Critical)
        self._pin_route(ep_ip)

        # 7. Add Default Route to Table
        logger.info(f"Adding default route to table {table_id}")
        with IPRoute() as ip:
            idx = ip.link_lookup(ifname=ifname)[0]
            # ip route add default dev ifname table table_id
            try:
                ip.route('add', dst='0.0.0.0/0', table=table_id, oif=idx)
            except Exception as e:
                logger.error(f"Failed to add default route: {e}")
                # EEXIST?
                pass

        # 8. Add Rule for return traffic
        # ip rule add from <WG_IP> lookup <table_id>
        wg_ip = address_cidr.split('/')[0]
        self._add_rule(wg_ip, table_id)

    def teardown_tunnel(self, name):
        profile = self.config_store.get_profile(name)
        if not profile:
             return

        ifname = profile['interface_name']
        
        with IPRoute() as ip:
            if ip.link_lookup(ifname=ifname):
                logger.info(f"Tearing down {name} ({ifname})")
                ip.link('del', ifname=ifname)
            
        pass

    def _pin_route(self, ip_addr):
        """
        Ensure traffic to the VPN endpoint goes through the physical gateway.
        Using pyroute2 to find default gateway and add host route.
        """
        with IPRoute() as ip:
            # Find default route in main table (254)
            # Avoid using get_routes(dst='default') as it causes EOPNOTSUPP
            routes = ip.get_routes(table=254)
            # Filter for default route (dst_len=0 and no RTA_DST)
            default_routes = [r for r in routes if r['dst_len'] == 0]
            if not default_routes:
                logger.warning("No default gateway found, skipping pinning.")
                return
            
            # Pick first default route
            r = default_routes[0]
            gw = None
            oif = None
            
            # Parse route attributes
            for attr, val in r['attrs']:
                if attr == 'RTA_GATEWAY':
                    gw = val
                if attr == 'RTA_OIF':
                    oif = val
            
            if gw and oif:
                ifname_out = ip.get_links(oif)[0].get_attr('IFLA_IFNAME')
                logger.info(f"Pinning {ip_addr} via {gw} ({ifname_out})")
                # ip route add <ip>/32 via <gw> dev <oif>
                try:
                    ip.route('add', dst=f"{ip_addr}/32", gateway=gw, oif=oif)
                except Exception as e:
                    # EEXIST is common
                    pass

    def _add_rule(self, ip_addr, table_id):
        with IPRoute() as ip:
            # ip rule add from <ip> lookup <table>
            # pyroute2 doesn't have a high level 'add_rule', we use 'rule' command
            try:
                ip.rule('add', src=ip_addr, table=table_id)
            except Exception:
                pass
