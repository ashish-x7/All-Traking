// UI Controller and State Management for TrackShip

document.addEventListener('DOMContentLoaded', () => {
    // Initialise Lucide icons
    lucide.createIcons();
    
    // UI Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const selectedFileContainer = document.getElementById('selected-file-container');
    const selectedFileName = document.getElementById('selected-file-name');
    const selectedFileSize = document.getElementById('selected-file-size');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const startTrackingBtn = document.getElementById('start-tracking-btn');
    const statsSection = document.getElementById('stats-section');
    const uploadPanel = document.getElementById('upload-panel');
    const progressPanel = document.getElementById('progress-panel');
    const trackingStatusBadge = document.getElementById('tracking-status-badge');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    const consoleLog = document.getElementById('console-log');
    const exportBtn = document.getElementById('export-btn');
    const searchInput = document.getElementById('search-input');
    const filterCourier = document.getElementById('filter-courier');
    const filterStatus = document.getElementById('filter-status');
    const tableBody = document.getElementById('table-body');
    
    // Stats elements
    const statTotal = document.getElementById('stat-total');
    const statDelivered = document.getElementById('stat-delivered');
    const statTransit = document.getElementById('stat-transit');
    const statFailed = document.getElementById('stat-failed');

    // Application State
    let state = {
        selectedFile: null,
        isTracking: false,
        taskId: null,
        shipments: [], // Full list of shipments tracked
        filteredShipments: [], // Screen filtered list
        logs: [],
        stats: { total: 0, delivered: 0, transit: 0, failed: 0 }
    };

    // --- Drag and Drop File Handlers ---
    
    // Browse button click triggers input click
    dropZone.addEventListener('click', (e) => {
        if (e.target.className !== 'browse-btn' && !e.target.closest('.browse-btn')) {
            // only trigger if user clicked browse or surrounding area
        }
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelect(file) {
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const fileName = file.name.toLowerCase();
        const isValid = validExtensions.some(ext => fileName.endsWith(ext));
        
        if (!isValid) {
            alert('Invalid file format. Please upload a CSV or Excel sheet.');
            return;
        }

        state.selectedFile = file;
        
        // Show file details
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        
        // Update UI
        dropZone.style.display = 'none';
        selectedFileContainer.style.display = 'block';
    }

    removeFileBtn.addEventListener('click', () => {
        resetUploadSection();
    });

    function resetUploadSection() {
        state.selectedFile = null;
        fileInput.value = '';
        dropZone.style.display = 'flex';
        selectedFileContainer.style.display = 'none';
    }

    // --- Actions ---

    startTrackingBtn.addEventListener('click', async () => {
        if (!state.selectedFile) return;

        // Create FormData and upload the file
        const formData = new FormData();
        formData.append('file', state.selectedFile);

        addLogEntry('Uploading list of tracking numbers...', 'info');
        
        try {
            // Disable start tracking button
            startTrackingBtn.disabled = true;
            
            const uploadRes = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!uploadRes.ok) {
                throw new Error('Failed to upload file');
            }

            const uploadData = await uploadRes.json();
            state.taskId = uploadData.task_id;
            state.shipments = uploadData.shipments || [];
            
            addLogEntry(`File uploaded successfully. Found ${state.shipments.length} tracking records.`, 'success');
            
            // Start the background tracking service
            const startRes = await fetch('/api/track/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: state.taskId })
            });

            if (!startRes.ok) {
                throw new Error('Failed to start tracking engine');
            }

            // Move panels: hide upload, show stats and progress
            uploadPanel.style.display = 'none';
            progressPanel.style.display = 'flex';
            statsSection.style.display = 'grid';
            
            state.isTracking = true;
            
            // Render initial stubs into table
            renderTable(state.shipments);
            updateStatsUI();

            // Begin polling progress
            pollProgress();

        } catch (error) {
            addLogEntry(`Error starting process: ${error.message}`, 'error');
            startTrackingBtn.disabled = false;
        }
    });

    async function pollProgress() {
        if (!state.isTracking) return;

        try {
            const res = await fetch(`/api/track/progress?task_id=${state.taskId}`);
            if (!res.ok) throw new Error('Progress fetch failed');

            const data = await res.json();
            
            // Update state
            state.shipments = data.shipments;
            state.stats = data.stats;
            const progress = data.progress;
            
            // Render logs
            if (data.logs && data.logs.length > 0) {
                data.logs.forEach(log => {
                    addLogEntry(log.message, log.level);
                });
            }

            // Update progress elements
            progressBarFill.style.width = `${progress}%`;
            progressPercent.textContent = `${progress}%`;
            progressText.textContent = data.current_action || 'Processing...';

            // Update Table and Stats
            renderTable(state.shipments);
            updateStatsUI();

            if (data.status === 'completed' || progress >= 100) {
                state.isTracking = false;
                trackingStatusBadge.textContent = 'Completed';
                trackingStatusBadge.classList.remove('badge-pulse');
                trackingStatusBadge.classList.add('badge-delivered');
                addLogEntry('Tracking run completed successfully. Result export ready.', 'success');
                exportBtn.disabled = false;
            } else if (data.status === 'failed') {
                state.isTracking = false;
                trackingStatusBadge.textContent = 'Failed';
                trackingStatusBadge.classList.remove('badge-pulse');
                trackingStatusBadge.classList.add('badge-exception');
                addLogEntry('Tracking run aborted due to an internal error.', 'error');
            } else {
                // Poll again in 1 second
                setTimeout(pollProgress, 1000);
            }

        } catch (error) {
            addLogEntry(`Polling error: ${error.message}`, 'error');
            // Try again in 2 seconds
            setTimeout(pollProgress, 2000);
        }
    }

    exportBtn.addEventListener('click', () => {
        if (!state.taskId) return;
        window.location.href = `/api/export?task_id=${state.taskId}`;
    });

    // --- Search & Filters ---

    searchInput.addEventListener('input', applyFilters);
    filterCourier.addEventListener('change', applyFilters);
    filterStatus.addEventListener('change', applyFilters);

    function applyFilters() {
        const query = searchInput.value.toLowerCase().trim();
        const courier = filterCourier.value;
        const status = filterStatus.value;

        state.filteredShipments = state.shipments.filter(item => {
            const matchesQuery = item.tracking_number.toLowerCase().includes(query) || 
                                 item.courier.toLowerCase().includes(query) ||
                                 (item.last_location || '').toLowerCase().includes(query);
            
            const matchesCourier = courier === 'all' || item.courier.toLowerCase() === courier.toLowerCase();
            const matchesStatus = status === 'all' || mapStatusFilter(item.status) === status;

            return matchesQuery && matchesCourier && matchesStatus;
        });

        renderTable(state.filteredShipments);
    }

    function mapStatusFilter(status) {
        status = status.toLowerCase();
        if (status.includes('delivered')) return 'delivered';
        if (status.includes('transit')) return 'transit';
        if (status.includes('out')) return 'out_for_delivery';
        if (status.includes('fail') || status.includes('exception') || status.includes('error')) return 'exception';
        return 'pending';
    }

    // --- Helper UI Renderers ---

    function renderTable(dataList) {
        if (dataList.length === 0) {
            tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="5">
                        <div class="empty-state">
                            <i data-lucide="file-warning"></i>
                            <p>No matching shipments found.</p>
                        </div>
                    </td>
                </tr>
            `;
            lucide.createIcons();
            return;
        }

        tableBody.innerHTML = '';
        dataList.forEach(item => {
            const tr = document.createElement('tr');
            
            // Badge style mapping
            let badgeClass = 'badge-pending';
            const statusKey = mapStatusFilter(item.status);
            if (statusKey === 'delivered') badgeClass = 'badge-delivered';
            else if (statusKey === 'transit') badgeClass = 'badge-transit';
            else if (statusKey === 'out_for_delivery') badgeClass = 'badge-out_for_delivery';
            else if (statusKey === 'exception') badgeClass = 'badge-exception';

            tr.innerHTML = `
                <td class="courier-label">${item.courier}</td>
                <td class="tracking-id">${item.tracking_number}</td>
                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                <td>${item.last_location || 'Pending scan'}</td>
                <td>${item.timestamp || '-'}</td>
            `;
            tableBody.appendChild(tr);
        });
    }

    function updateStatsUI() {
        statTotal.textContent = state.stats.total || 0;
        statDelivered.textContent = state.stats.delivered || 0;
        statTransit.textContent = state.stats.transit || 0;
        statFailed.textContent = state.stats.failed || 0;
    }

    function addLogEntry(message, level = 'info') {
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;
        
        let prefix = '[INFO]';
        if (level === 'success') prefix = '[SUCCESS]';
        if (level === 'warning') prefix = '[WARN]';
        if (level === 'error') prefix = '[ERROR]';
        if (level === 'system') prefix = '[SYSTEM]';

        entry.textContent = `[${time}] ${prefix}: ${message}`;
        consoleLog.appendChild(entry);
        consoleLog.scrollTop = consoleLog.scrollHeight;
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
