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
    const progressPanel = document.getElementById('progress-panel');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    const exportBtn = document.getElementById('export-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');
    const searchInput = document.getElementById('search-input');
    const filterCourier = document.getElementById('filter-courier');
    const filterStatus = document.getElementById('filter-status');
    const tableBody = document.getElementById('table-body');
    
    // Pagination Elements
    const prevPageBtn = document.getElementById('prev-page-btn');
    const nextPageBtn = document.getElementById('next-page-btn');
    const currentPageNum = document.getElementById('current-page-num');
    const totalPagesNum = document.getElementById('total-pages-num');
    const gotoPageInput = document.getElementById('goto-page-input');
    const gotoPageBtn = document.getElementById('goto-page-btn');
    
    // Stats elements
    const statTotal = document.getElementById('stat-total');
    const statDelivered = document.getElementById('stat-delivered');
    const statTransit = document.getElementById('stat-transit');
    const statFailed = document.getElementById('stat-failed');
    const statApi = document.getElementById('stat-api');

    // Application State
    let state = {
        isTracking: false,
        taskId: null,
        shipments: [], // Full list of shipments tracked
        filteredShipments: [], // Screen filtered list
        stats: { total: 0, delivered: 0, transit: 0, failed: 0, api_calls: 0 },
        currentPage: 1,
        rowsPerPage: 50
    };

    // --- Drag and Drop File Handlers ---
    
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

    async function handleFileSelect(file) {
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const fileName = file.name.toLowerCase();
        const isValid = validExtensions.some(ext => fileName.endsWith(ext));
        
        if (!isValid) {
            alert('Invalid file format. Please upload a CSV or Excel sheet.');
            return;
        }

        // Show file details in UI
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        dropZone.style.display = 'none';
        selectedFileContainer.style.display = 'block';

        // Auto Upload on Select (does not start tracking automatically)
        await uploadFile(file);
    }

    removeFileBtn.addEventListener('click', () => {
        resetUploadSection();
    });

    function resetUploadSection() {
        fileInput.value = '';
        dropZone.style.display = 'flex';
        selectedFileContainer.style.display = 'none';
        startTrackingBtn.disabled = true;
        exportBtn.disabled = true;
        clearAllBtn.disabled = true;
        progressPanel.style.visibility = 'hidden';
        state.taskId = null;
        state.shipments = [];
        state.filteredShipments = [];
        state.isTracking = false;
        renderTable([]);
        updateStatsUI();
    }

    // --- API Calls ---

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const uploadRes = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!uploadRes.ok) {
                const errData = await uploadRes.json();
                throw new Error(errData.detail || 'Failed to upload file');
            }

            const uploadData = await uploadRes.json();
            state.taskId = uploadData.task_id;
            state.shipments = uploadData.shipments || [];
            if (uploadData.stats) {
                state.stats = uploadData.stats;
            }
            
            // Enable buttons
            startTrackingBtn.disabled = false;
            exportBtn.disabled = false;
            clearAllBtn.disabled = false;
            
            // Render rows in table
            applyFilters();
            recalculateStats();
            
        } catch (error) {
            alert(`Error uploading file: ${error.message}`);
            resetUploadSection();
        }
    }

    // "Sync All" button triggers bulk simulation run
    startTrackingBtn.addEventListener('click', async () => {
        if (!state.taskId) return;

        try {
            startTrackingBtn.disabled = true;
            
            const startRes = await fetch('/api/track/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: state.taskId })
            });

            if (!startRes.ok) {
                throw new Error('Failed to start tracking engine');
            }

            progressPanel.style.visibility = 'visible';
            state.isTracking = true;
            
            pollProgress();

        } catch (error) {
            alert(`Error starting tracking: ${error.message}`);
            startTrackingBtn.disabled = false;
        }
    });

    clearAllBtn.addEventListener('click', () => {
        resetUploadSection();
    });

    async function pollProgress() {
        if (!state.isTracking) return;

        try {
            const res = await fetch(`/api/track/progress?task_id=${state.taskId}`);
            if (!res.ok) throw new Error('Progress fetch failed');

            const data = await res.json();
            
            // Update local state
            state.shipments = data.shipments;
            const progress = data.progress;
            if (data.stats) {
                state.stats = data.stats;
            }
            
            // Update progress elements
            progressBarFill.style.width = `${progress}%`;
            progressPercent.textContent = `${progress}%`;
            
            // Show latest log message as status text if any logs exist
            if (data.logs && data.logs.length > 0) {
                progressText.textContent = data.logs[data.logs.length - 1].message;
            } else {
                progressText.textContent = data.current_action || 'Processing...';
            }

            // Update Table and Stats without resetting active page
            applyFilters(false);
            recalculateStats();

            if (data.status === 'completed' || progress >= 100) {
                state.isTracking = false;
                progressText.textContent = 'Sync All Completed!';
                startTrackingBtn.disabled = false;
            } else if (data.status === 'failed') {
                state.isTracking = false;
                progressText.textContent = 'Sync All Failed.';
                startTrackingBtn.disabled = false;
            } else {
                // Poll again in 1.5 seconds
                setTimeout(pollProgress, 1500);
            }

        } catch (error) {
            console.error('Polling error:', error);
            setTimeout(pollProgress, 2000);
        }
    }

    // Individual Row Sync Handler
    async function syncSingleShipment(trackingNumber, courier, syncButton) {
        if (!state.taskId) return;
        
        const icon = syncButton.querySelector('svg') || syncButton.querySelector('i');
        if (icon) icon.classList.add('spinning');
        syncButton.disabled = true;

        try {
            const res = await fetch('/api/track/sync_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    tracking_number: trackingNumber,
                    courier: courier
                })
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || 'Sync failed');
            }

            const data = await res.json();

            // Update today's API hits count
            if (data.api_calls !== undefined) {
                state.stats.api_calls = data.api_calls;
            }

            // Update local state record
            const idx = state.shipments.findIndex(s => s.tracking_number === trackingNumber);
            if (idx !== -1) {
                state.shipments[idx].status = data.status;
                state.shipments[idx].last_location = data.last_location;
                state.shipments[idx].timestamp = data.timestamp;
                state.shipments[idx].last_sync = data.last_sync || "-";
            }

            // Render and update stats
            applyFilters();
            recalculateStats();

        } catch (error) {
            alert(`Error syncing AWB ${trackingNumber}: ${error.message}`);
        } finally {
            if (icon) icon.classList.remove('spinning');
            syncButton.disabled = false;
        }
    }

    exportBtn.addEventListener('click', () => {
        if (!state.taskId) return;
        window.location.href = `/api/export?task_id=${state.taskId}`;
    });

    // --- Search & Filters ---

    searchInput.addEventListener('input', () => applyFilters(true));
    filterCourier.addEventListener('change', () => applyFilters(true));
    filterStatus.addEventListener('change', () => applyFilters(true));

    function applyFilters(resetPage = true) {
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

        if (resetPage) {
            state.currentPage = 1;
        }
        renderCurrentPage();
    }

    function renderCurrentPage() {
        const total = state.filteredShipments.length;
        const totalPages = Math.ceil(total / state.rowsPerPage) || 1;
        
        if (state.currentPage > totalPages) {
            state.currentPage = totalPages;
        }
        if (state.currentPage < 1) {
            state.currentPage = 1;
        }

        // Update labels
        currentPageNum.textContent = state.currentPage;
        totalPagesNum.textContent = totalPages;
        gotoPageInput.max = totalPages;
        gotoPageInput.value = state.currentPage;

        // Buttons state
        prevPageBtn.disabled = (state.currentPage === 1);
        nextPageBtn.disabled = (state.currentPage === totalPages);

        // Slice data
        const start = (state.currentPage - 1) * state.rowsPerPage;
        const end = start + state.rowsPerPage;
        const pageData = state.filteredShipments.slice(start, end);

        renderTable(pageData);
    }

    // Pagination Listeners
    prevPageBtn.addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderCurrentPage();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredShipments.length / state.rowsPerPage) || 1;
        if (state.currentPage < totalPages) {
            state.currentPage++;
            renderCurrentPage();
        }
    });

    gotoPageBtn.addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredShipments.length / state.rowsPerPage) || 1;
        let page = parseInt(gotoPageInput.value);
        if (isNaN(page) || page < 1) {
            page = 1;
        } else if (page > totalPages) {
            page = totalPages;
        }
        state.currentPage = page;
        renderCurrentPage();
    });

    gotoPageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            gotoPageBtn.click();
        }
    });

    function mapStatusFilter(status) {
        status = status.toLowerCase();
        if (status.includes('delivered')) return 'delivered';
        if (status.includes('transit') || status.includes('picked') || status.includes('pickup') || status.includes('dispatched') || status.includes('shipped') || status.includes('route')) return 'transit';
        if (status.includes('out') || status.includes('delivery') || status.includes('schedule')) return 'out_for_delivery';
        if (status.includes('fail') || status.includes('except') || status.includes('error') || status.includes('invalid') || status.includes('return') || status.includes('cancel') || status.includes('undelivered')) return 'exception';
        return 'pending';
    }

    function recalculateStats() {
        const total = state.shipments.length;
        let delivered = 0;
        let transit = 0;
        let failed = 0;

        state.shipments.forEach(s => {
            const mapped = mapStatusFilter(s.status);
            if (mapped === 'delivered') delivered++;
            else if (mapped === 'transit' || mapped === 'out_for_delivery') transit++;
            else if (mapped === 'exception') failed++;
        });

        state.stats = { total, delivered, transit, failed, api_calls: state.stats.api_calls || 0 };
        updateStatsUI();
    }

    function getCourierBadgeClass(courier) {
        courier = courier.toLowerCase();
        if (courier.includes('delhivery')) return 'courier-delhivery';
        if (courier.includes('xpressbees')) return 'courier-xpressbees';
        if (courier.includes('shadowfax')) return 'courier-shadowfax';
        if (courier.includes('bluedart') || courier.includes('blue dart')) return 'courier-bluedart';
        if (courier.includes('dtdc')) return 'courier-dtdc';
        if (courier.includes('ecom')) return 'courier-ecom';
        if (courier.includes('ekart')) return 'courier-ekart';
        if (courier.includes('india post')) return 'courier-indiapost';
        return 'courier-default';
    }

    // --- Helper UI Renderers ---

    function renderTable(dataList) {
        if (dataList.length === 0) {
            tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="6">
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

            // Determine timestamp filled/empty status
            const isTimestampEmpty = !item.timestamp || item.timestamp === '-';
            const timestampBadgeClass = isTimestampEmpty ? 'timestamp-empty' : 'timestamp-filled';
            const printTimestamp = isTimestampEmpty ? '-' : item.timestamp;

            // Determine last sync filled/empty status
            const isLastSyncEmpty = !item.last_sync || item.last_sync === '-';
            const lastSyncBadgeClass = isLastSyncEmpty ? 'lastsync-empty' : 'lastsync-filled';
            const printLastSync = isLastSyncEmpty ? '-' : item.last_sync;

            tr.innerHTML = `
                <td><span class="awb-badge ${getCourierBadgeClass(item.courier)}">${item.tracking_number}</span></td>
                <td><span class="courier-badge ${getCourierBadgeClass(item.courier)}">${item.courier}</span></td>
                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                <td><span class="location-badge">${item.last_location || 'Pending scan'}</span></td>
                <td><span class="timestamp-badge ${timestampBadgeClass}">${printTimestamp}</span></td>
                <td><span class="lastsync-badge ${lastSyncBadgeClass}">${printLastSync}</span></td>
                <td style="text-align: center;">
                    <button class="btn-sync-single" title="Sync Status">
                        <i data-lucide="refresh-cw"></i>
                    </button>
                </td>
            `;

            // Bind single sync button handler
            const syncButton = tr.querySelector('.btn-sync-single');
            syncButton.addEventListener('click', () => {
                syncSingleShipment(item.tracking_number, item.courier, syncButton);
            });

            tableBody.appendChild(tr);
        });

        lucide.createIcons();
    }

    function updateStatsUI() {
        statTotal.textContent = state.stats.total || 0;
        statDelivered.textContent = state.stats.delivered || 0;
        statTransit.textContent = state.stats.transit || 0;
        statFailed.textContent = state.stats.failed || 0;
        statApi.textContent = state.stats.api_calls || 0;
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
