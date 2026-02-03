"""
Saferoute Web Server - Flask backend for managing WireGuard configs and mappings.
"""
import os
import subprocess
import yaml
from pathlib import Path
from flask import Flask, jsonify, request, render_template, send_from_directory

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Configuration
CONFIG_DIR = os.environ.get('CONFIG_DIR', '/app/data/configs')
WIREGUARD_DIR = os.path.join(CONFIG_DIR, 'wireguard')
MAPPINGS_FILE = os.path.join(CONFIG_DIR, 'mappings', 'devices.yaml')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.yaml')


def ensure_dirs():
    """Ensure required directories exist."""
    os.makedirs(WIREGUARD_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(MAPPINGS_FILE), exist_ok=True)


def run_cli(args):
    """Run a CLI command and return result."""
    cmd = ['python', '-m', 'src.app'] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd='/app')
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============ Frontend Routes ============

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


# ============ Config API ============

@app.route('/api/configs', methods=['GET'])
def list_configs():
    """List all WireGuard config files."""
    ensure_dirs()
    configs = []
    wg_path = Path(WIREGUARD_DIR)
    
    if wg_path.exists():
        for conf_file in wg_path.glob('*.conf'):
            configs.append({
                'name': conf_file.stem,
                'filename': conf_file.name,
                'size': conf_file.stat().st_size
            })
    
    return jsonify(configs)


@app.route('/api/configs/<name>', methods=['GET'])
def get_config(name):
    """Get content of a specific config file."""
    conf_path = Path(WIREGUARD_DIR) / f"{name}.conf"
    
    if not conf_path.exists():
        return jsonify({'error': 'Config not found'}), 404
    
    content = conf_path.read_text()
    return jsonify({
        'name': name,
        'content': content
    })


@app.route('/api/configs', methods=['POST'])
def create_config():
    """Create a new config file."""
    ensure_dirs()
    data = request.json
    
    name = data.get('name')
    content = data.get('content')
    
    if not name or not content:
        return jsonify({'error': 'Name and content required'}), 400
    
    # Sanitize name
    name = name.replace('/', '').replace('..', '')
    if not name.endswith('.conf'):
        filename = f"{name}.conf"
    else:
        filename = name
        name = name[:-5]
    
    conf_path = Path(WIREGUARD_DIR) / filename
    
    if conf_path.exists():
        return jsonify({'error': 'Config already exists'}), 409
    
    conf_path.write_text(content)
    
    return jsonify({
        'success': True,
        'name': name,
        'message': f'Config {name} created'
    })


@app.route('/api/configs/<name>', methods=['PUT'])
def update_config(name):
    """Update an existing config file."""
    conf_path = Path(WIREGUARD_DIR) / f"{name}.conf"
    
    if not conf_path.exists():
        return jsonify({'error': 'Config not found'}), 404
    
    data = request.json
    content = data.get('content')
    
    if not content:
        return jsonify({'error': 'Content required'}), 400
    
    conf_path.write_text(content)
    
    return jsonify({
        'success': True,
        'message': f'Config {name} updated'
    })


@app.route('/api/configs/<name>', methods=['DELETE'])
def delete_config(name):
    """Delete a config file."""
    conf_path = Path(WIREGUARD_DIR) / f"{name}.conf"
    
    if not conf_path.exists():
        return jsonify({'error': 'Config not found'}), 404
    
    conf_path.unlink()
    
    return jsonify({
        'success': True,
        'message': f'Config {name} deleted'
    })


# ============ Mappings API ============

@app.route('/api/mappings', methods=['GET'])
def list_mappings():
    """List all device mappings."""
    mappings_path = Path(MAPPINGS_FILE)
    
    if not mappings_path.exists():
        return jsonify([])
    
    try:
        with open(mappings_path) as f:
            data = yaml.safe_load(f)
            return jsonify(data.get('devices', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mappings', methods=['POST'])
def add_mapping():
    """Add a new device mapping."""
    ensure_dirs()
    data = request.json
    
    ip = data.get('ip')
    tunnel = data.get('tunnel')
    nickname = data.get('nickname', '')  # Optional nickname
    active = data.get('active', True)  # Default to active
    
    if not ip or not tunnel:
        return jsonify({'error': 'IP and tunnel required'}), 400
    
    # Load existing mappings
    mappings_path = Path(MAPPINGS_FILE)
    if mappings_path.exists():
        with open(mappings_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    devices = config.get('devices', [])
    
    # Check if IP already exists
    for d in devices:
        if d.get('ip') == ip:
            return jsonify({'error': 'IP already mapped'}), 409
    
    mapping = {'ip': ip, 'tunnel': tunnel, 'active': active}
    if nickname:
        mapping['nickname'] = nickname
    
    devices.append(mapping)
    config['devices'] = devices
    
    with open(mappings_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    return jsonify({
        'success': True,
        'message': f'Mapped {ip} → {tunnel}'
    })


@app.route('/api/mappings/<ip>', methods=['PUT'])
def update_mapping(ip):
    """Update an existing mapping."""
    data = request.json
    new_tunnel = data.get('tunnel')
    nickname = data.get('nickname', '')  # Optional nickname
    active = data.get('active')  # Optional active status
    
    if not new_tunnel:
        return jsonify({'error': 'Tunnel required'}), 400
    
    mappings_path = Path(MAPPINGS_FILE)
    if not mappings_path.exists():
        return jsonify({'error': 'No mappings file'}), 404
    
    with open(mappings_path) as f:
        config = yaml.safe_load(f) or {}
    
    devices = config.get('devices', [])
    found = False
    
    for d in devices:
        if d.get('ip') == ip:
            d['tunnel'] = new_tunnel
            if nickname:
                d['nickname'] = nickname
            elif 'nickname' in d:
                # Remove nickname if empty string provided
                del d['nickname']
            if active is not None:
                d['active'] = active
            found = True
            break
    
    if not found:
        return jsonify({'error': 'Mapping not found'}), 404
    
    config['devices'] = devices
    
    with open(mappings_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    return jsonify({
        'success': True,
        'message': f'Updated {ip} → {new_tunnel}'
    })


@app.route('/api/mappings/<path:ip>', methods=['DELETE'])
def delete_mapping(ip):
    """Delete a device mapping."""
    mappings_path = Path(MAPPINGS_FILE)
    if not mappings_path.exists():
        return jsonify({'error': 'No mappings file'}), 404
    
    with open(mappings_path) as f:
        config = yaml.safe_load(f) or {}
    
    devices = config.get('devices', [])
    original_len = len(devices)
    devices = [d for d in devices if d.get('ip') != ip]
    
    if len(devices) == original_len:
        return jsonify({'error': 'Mapping not found'}), 404
    
    config['devices'] = devices
    
    with open(mappings_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    return jsonify({
        'success': True,
        'message': f'Deleted mapping for {ip}'
    })


# ============ System API ============

@app.route('/api/apply', methods=['POST'])
def apply_changes():
    """Apply all changes by running startup command."""
    result = run_cli(['startup', CONFIG_FILE])
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': 'Changes applied successfully',
            'output': result['stdout']
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to apply changes',
            'error': result.get('stderr', result.get('error', 'Unknown error'))
        }), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current tunnel status."""
    try:
        result = subprocess.run(['wg', 'show'], capture_output=True, text=True)
        return jsonify({
            'success': True,
            'output': result.stdout if result.stdout else 'No tunnels active'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
