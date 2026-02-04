/**
 * Saferoute Web App - Frontend JavaScript
 */

// ============ State ============
let configs = [];
let mappings = [];
let editingConfig = null;
let editingMapping = null;
let hasUnsavedChanges = false;

// ============ Stats ============
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

async function fetchStats() {
    try {
        const stats = await api('/api/stats');

        // Update stats for each mapping
        document.querySelectorAll('.mapping-stats').forEach(el => {
            const tunnelName = el.dataset.tunnel;
            const tunnelStats = stats[tunnelName];

            if (tunnelStats) {
                el.innerHTML = `
                    <span class="stat-item" title="Download">↓ ${formatBytes(tunnelStats.rx_bytes)}</span>
                    <span class="stat-item" title="Upload">↑ ${formatBytes(tunnelStats.tx_bytes)}</span>
                `;
            } else {
                el.innerHTML = '<span class="stat-item dimmed">-</span>';
            }
        });
    } catch (error) {
        console.error('Failed to fetch stats:', error);
    }
}

// Start polling
setInterval(fetchStats, 3000);


// ============ Init ============
document.addEventListener('DOMContentLoaded', () => {
    loadConfigs();
    loadMappings();
    refreshStatus();
    fetchStats(); // Initial fetch
});

// ... (Rest of the file remains similar, but need to update renderMappings)

// ============ API Helpers ============
async function api(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options,
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'API error');
        }

        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// ============ Configs ============
async function loadConfigs() {
    try {
        configs = await api('/api/configs');
        renderConfigs();
    } catch (error) {
        document.getElementById('configsList').innerHTML =
            '<p class="empty-message">Failed to load configs</p>';
        showToast('Failed to load configs', 'error');
    }
}

function renderConfigs() {
    const container = document.getElementById('configsList');

    if (configs.length === 0) {
        container.innerHTML = '<p class="empty-message">No configs found. Add one to get started!</p>';
        return;
    }

    container.innerHTML = configs.map(config => `
        <div class="list-item" onclick="viewConfig('${config.name}')">
            <span class="list-item-name">
                📄 ${config.name}
            </span>
            <span class="list-item-info">${config.filename}</span>
        </div>
    `).join('');
}

async function viewConfig(name) {
    try {
        const data = await api(`/api/configs/${name}`);
        editingConfig = name;

        document.getElementById('configModalTitle').textContent = `Edit: ${name}`;
        document.getElementById('configName').value = name;
        document.getElementById('configName').disabled = true;
        document.getElementById('configNameGroup').style.display = 'none';
        document.getElementById('configContent').value = data.content;
        document.getElementById('deleteConfigBtn').style.display = 'inline-flex';

        openModal('configModal');
    } catch (error) {
        showToast('Failed to load config', 'error');
    }
}

function showAddConfigModal() {
    editingConfig = null;

    document.getElementById('configModalTitle').textContent = 'Add Config';
    document.getElementById('configName').value = '';
    document.getElementById('configName').disabled = false;
    document.getElementById('configNameGroup').style.display = 'block';
    document.getElementById('configContent').value = '';
    document.getElementById('deleteConfigBtn').style.display = 'none';

    openModal('configModal');
}

async function saveConfig() {
    const name = document.getElementById('configName').value.trim();
    const content = document.getElementById('configContent').value;

    if (!editingConfig && !name) {
        showToast('Please enter a name', 'error');
        return;
    }

    if (!content) {
        showToast('Please enter config content', 'error');
        return;
    }

    try {
        if (editingConfig) {
            await api(`/api/configs/${editingConfig}`, {
                method: 'PUT',
                body: JSON.stringify({ content }),
            });
            showToast('Config updated', 'success');
        } else {
            await api('/api/configs', {
                method: 'POST',
                body: JSON.stringify({ name, content }),
            });
            showToast('Config created', 'success');
        }

        markUnsavedChanges();
        closeModal('configModal');
        loadConfigs();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteConfig() {
    if (!editingConfig) return;

    if (!confirm(`Delete config "${editingConfig}"?`)) return;

    try {
        await api(`/api/configs/${editingConfig}`, { method: 'DELETE' });
        showToast('Config deleted', 'success');
        closeModal('configModal');
        loadConfigs();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ============ Mappings ============
async function loadMappings() {
    try {
        mappings = await api('/api/mappings');
        renderMappings();
    } catch (error) {
        document.getElementById('mappingsList').innerHTML =
            '<p class="empty-message">Failed to load mappings</p>';
    }
}

function renderMappings() {
    const container = document.getElementById('mappingsList');

    if (mappings.length === 0) {
        container.innerHTML = '<p class="empty-message">No mappings found. Add one to route devices!</p>';
        return;
    }

    container.innerHTML = mappings.map(m => {
        const displayName = m.nickname ? `${m.nickname} (${m.ip})` : m.ip;
        const nickname = m.nickname || '';
        const active = m.active !== false; // Default to true if not specified
        const inactiveClass = active ? '' : ' inactive';
        const statusBadge = active
            ? '<span class="status-badge status-active">Active</span>'
            : '<span class="status-badge status-inactive">Inactive</span>';

        return `
            <div class="list-item${inactiveClass}">
                <div onclick='editMapping(${JSON.stringify(m.ip)}, ${JSON.stringify(m.tunnel)}, ${JSON.stringify(nickname)}, ${active})' style="flex: 1; cursor: pointer;">
                    <div class="list-item-header">
                        <span class="list-item-name">
                            🖥️ ${displayName}
                        </span>
                        ${statusBadge}
                    </div>
                    <div class="list-item-details">
                        <span class="list-item-info">
                            → ${m.tunnel}
                        </span>
                        <div class="mapping-stats" data-tunnel="${m.tunnel}">
                            <span class="stat-item dimmed">Loading...</span>
                        </div>
                    </div>
                </div>
                <label class="inline-toggle" onclick="event.stopPropagation()">
                    <input type="checkbox" ${active ? 'checked' : ''} 
                           onchange="toggleMappingActive('${m.ip}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
            </div>
        `;
    }).join('');
}


async function toggleMappingActive(ip, active) {
    try {
        // Find the mapping to get current values
        const mapping = mappings.find(m => m.ip === ip);
        if (!mapping) return;

        await api(`/api/mappings/${ip}`, {
            method: 'PUT',
            body: JSON.stringify({
                tunnel: mapping.tunnel,
                nickname: mapping.nickname || '',
                active: active
            }),
        });

        showToast(active ? 'Mapping enabled' : 'Mapping disabled', 'success');
        markUnsavedChanges();
        loadMappings();
    } catch (error) {
        showToast(error.message, 'error');
        loadMappings(); // Reload to reset toggle
    }
}

function showAddMappingModal() {
    editingMapping = null;

    document.getElementById('mappingModalTitle').textContent = 'Add Mapping';
    document.getElementById('mappingIp').value = '';
    document.getElementById('mappingIp').disabled = false;
    document.getElementById('mappingNickname').value = '';
    document.getElementById('mappingActive').checked = true;
    document.getElementById('deleteMappingBtn').style.display = 'none';

    // Populate tunnel dropdown
    const select = document.getElementById('mappingTunnel');
    select.innerHTML = '<option value="">Select tunnel...</option>' +
        configs.map(c => `<option value="${c.name}">${c.name}</option>`).join('');

    openModal('mappingModal');
}

function editMapping(ip, tunnel, nickname = '', active = true) {
    editingMapping = ip;

    document.getElementById('mappingModalTitle').textContent = 'Edit Mapping';
    document.getElementById('mappingIp').value = ip;
    document.getElementById('mappingIp').disabled = true;
    document.getElementById('mappingNickname').value = nickname;
    document.getElementById('mappingActive').checked = active;
    document.getElementById('deleteMappingBtn').style.display = 'inline-flex';

    // Populate tunnel dropdown
    const select = document.getElementById('mappingTunnel');
    select.innerHTML = '<option value="">Select tunnel...</option>' +
        configs.map(c => `<option value="${c.name}" ${c.name === tunnel ? 'selected' : ''}>${c.name}</option>`).join('');

    openModal('mappingModal');
}

async function saveMapping() {
    const ip = document.getElementById('mappingIp').value.trim();
    const tunnel = document.getElementById('mappingTunnel').value;
    const nickname = document.getElementById('mappingNickname').value.trim();
    const active = document.getElementById('mappingActive').checked;

    if (!ip || !tunnel) {
        showToast('Please fill in IP and tunnel', 'error');
        return;
    }

    try {
        if (editingMapping) {
            await api(`/api/mappings/${editingMapping}`, {
                method: 'PUT',
                body: JSON.stringify({ tunnel, nickname, active }),
            });
            showToast('Mapping updated', 'success');
        } else {
            await api('/api/mappings', {
                method: 'POST',
                body: JSON.stringify({ ip, tunnel, nickname, active }),
            });
            showToast('Mapping added', 'success');
        }

        markUnsavedChanges();
        closeModal('mappingModal');
        loadMappings();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteMapping() {
    if (!editingMapping) return;

    if (!confirm(`Delete mapping for "${editingMapping}"?`)) return;

    try {
        await api(`/api/mappings/${editingMapping}`, { method: 'DELETE' });
        showToast('Mapping deleted', 'success');
        closeModal('mappingModal');
        loadMappings();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ============ Unsaved Changes Tracking ============
function markUnsavedChanges() {
    hasUnsavedChanges = true;
    const applyBtn = document.getElementById('applyBtn');
    applyBtn.classList.add('has-changes');
    applyBtn.innerHTML = '🚀 Apply All <span class="badge-dot"></span>';
}

function clearUnsavedChanges() {
    hasUnsavedChanges = false;
    const applyBtn = document.getElementById('applyBtn');
    applyBtn.classList.remove('has-changes');
    applyBtn.innerHTML = '🚀 Apply All';
}

// ============ Status & Apply ============
async function refreshStatus() {
    try {
        const data = await api('/api/status');
        document.getElementById('tunnelStatus').textContent = data.output;

        // Update status dot
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');

        if (data.output && data.output.includes('interface:')) {
            dot.className = 'status-dot active';
            const count = (data.output.match(/interface:/g) || []).length;
            text.textContent = `${count} tunnel${count > 1 ? 's' : ''} active`;
        } else {
            dot.className = 'status-dot';
            text.textContent = 'No tunnels active';
        }
    } catch (error) {
        document.getElementById('tunnelStatus').textContent = 'Failed to get status';
        document.getElementById('statusDot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'Error';
    }
}

async function applyChanges() {
    const btn = document.getElementById('applyBtn');
    btn.disabled = true;
    btn.innerHTML = '⏳ Applying...';

    try {
        const data = await api('/api/apply', { method: 'POST' });
        showToast('Changes applied successfully!', 'success');
        clearUnsavedChanges();
        await refreshStatus();
    } catch (error) {
        showToast('Failed to apply changes: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        if (!hasUnsavedChanges) {
            btn.innerHTML = '🚀 Apply All';
        }
    }
}

// ============ Modal Helpers ============
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// Close modal on backdrop click
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(modal => {
            modal.classList.remove('active');
        });
    }
});

// ============ Toast Notifications ============
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        ${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}
        ${message}
    `;

    container.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'toastSlide 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
