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

    const SESSION_KEY = 'trackship_session_state';

    // Application State
    let state = {
        isTracking: false,
        progress: 0,
        taskId: null,
        shipments: [], // Full list of shipments tracked
        filteredShipments: [], // Screen filtered list
        stats: { total: 0, delivered: 0, transit: 0, failed: 0, api_calls: 0 },
        currentPage: 1,
        rowsPerPage: 50,
        activeColumnFilters: {} // Excel column filter tracking
    };

    // --- Session Storage State Persistence ---
    function saveSessionState() {
        try {
            const payload = {
                taskId: state.taskId,
                shipments: state.shipments,
                stats: state.stats,
                isTracking: state.isTracking,
                progress: state.progress || 0,
                progressText: progressText.textContent || '',
                currentPage: state.currentPage,
                activeColumnFilters: state.activeColumnFilters,
                fileSelected: selectedFileContainer.style.display !== 'none',
                fileName: selectedFileName.textContent,
                fileSize: selectedFileSize.textContent
            };
            sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
        } catch (e) {
            console.warn('Failed to save to sessionStorage:', e);
        }
    }

    async function syncTaskToBackendSilently() {
        if (!state.taskId || !state.shipments || state.shipments.length === 0) return;
        try {
            await fetch('/api/restore_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    shipments: state.shipments
                })
            });
        } catch (e) {
            // Silently ignore if server is sleeping or waking up
        }
    }

    async function restoreSessionState() {
        try {
            const raw = sessionStorage.getItem(SESSION_KEY);
            if (raw) {
                const saved = JSON.parse(raw);
                if (saved && saved.shipments && saved.shipments.length > 0) {
                    state.taskId = saved.taskId || ('task_' + Date.now());
                    state.shipments = saved.shipments;
                    state.stats = saved.stats || { total: saved.shipments.length, delivered: 0, transit: 0, failed: 0, api_calls: 0 };
                    state.currentPage = saved.currentPage || 1;
                    state.activeColumnFilters = saved.activeColumnFilters || {};
                    state.isTracking = !!saved.isTracking;
                    state.progress = saved.progress || 0;

                    if (saved.fileSelected && saved.fileName) {
                        selectedFileName.textContent = saved.fileName;
                        selectedFileSize.textContent = saved.fileSize || '';
                        dropZone.style.display = 'none';
                        selectedFileContainer.style.display = 'block';
                    }

                    startTrackingBtn.disabled = false;
                    exportBtn.disabled = false;
                    clearAllBtn.disabled = false;

                    updateStatsUI();
                    applyFilters(false);

                    if (state.isTracking && state.progress < 100) {
                        progressPanel.style.visibility = 'visible';
                        progressBarFill.style.width = `${state.progress}%`;
                        progressPercent.textContent = `${state.progress}%`;
                        progressText.textContent = saved.progressText || 'Resuming tracking...';
                        startTrackingBtn.disabled = true;
                        pollProgress();
                    } else if (state.progress >= 100) {
                        progressPanel.style.visibility = 'visible';
                        progressBarFill.style.width = `100%`;
                        progressPercent.textContent = `100%`;
                        progressText.textContent = 'Sync All Completed!';
                    }

                    // Background restore to backend in case Render woke up from sleep
                    syncTaskToBackendSilently();
                    return true;
                }
            }
        } catch (e) {
            console.warn('Failed to parse sessionStorage:', e);
        }
        return false;
    }

    // --- Drag and Drop File Handlers ---
    
    dropZone.addEventListener('click', (e) => {
        if (e.target.className !== 'browse-btn' && !e.target.closest('.browse-btn')) {
            // trigger file dialog
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
        state.progress = 0;
        sessionStorage.removeItem(SESSION_KEY);
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
            saveSessionState();
            
        } catch (error) {
            alert(`Error uploading file: ${error.message}`);
            resetUploadSection();
        }
    }

    // "Sync All" button triggers bulk simulation run
    startTrackingBtn.addEventListener('click', async () => {
        if (!state.taskId && state.shipments.length === 0) return;
        if (!state.taskId) {
            state.taskId = 'task_' + Date.now();
        }

        try {
            startTrackingBtn.disabled = true;
            progressPanel.style.visibility = 'visible';
            state.isTracking = true;
            state.progress = 0;
            progressBarFill.style.width = '0%';
            progressPercent.textContent = '0%';
            progressText.textContent = 'Starting courier tracking...';
            saveSessionState();
            renderCurrentPage();

            const startRes = await fetch('/api/track/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    shipments: state.shipments
                })
            });

            if (!startRes.ok) {
                const errData = await startRes.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to start tracking engine');
            }

            pollProgress();

        } catch (error) {
            alert(`Error starting tracking: ${error.message}`);
            startTrackingBtn.disabled = false;
            state.isTracking = false;
            saveSessionState();
        }
    });

    // Custom Delete Modal Elements
    const deleteModal = document.getElementById('delete-modal');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalConfirmBtn = document.getElementById('modal-confirm-btn');

    clearAllBtn.addEventListener('click', () => {
        deleteModal.style.display = 'flex';
    });

    modalCancelBtn.addEventListener('click', () => {
        deleteModal.style.display = 'none';
    });

    // Close modal if user clicks outside the modal card
    deleteModal.addEventListener('click', (e) => {
        if (e.target === deleteModal) {
            deleteModal.style.display = 'none';
        }
    });

    modalConfirmBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/clear', { method: 'DELETE' });
        } catch (e) {
            console.error('Failed to clear server data:', e);
        }
        deleteModal.style.display = 'none';
        resetUploadSection();
    });

    async function pollProgress() {
        if (!state.isTracking) return;

        try {
            const res = await fetch(`/api/track/progress?task_id=${state.taskId}`);
            if (!res.ok) {
                if (res.status === 404) {
                    // Task lost during server sleep/restart: auto-resume by starting with current shipments
                    console.log('Task missing in DB on poll, auto-recovering tracking session...');
                    await fetch('/api/track/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            task_id: state.taskId,
                            shipments: state.shipments
                        })
                    });
                    setTimeout(pollProgress, 1500);
                    return;
                }
                throw new Error('Progress fetch failed');
            }

            const data = await res.json();
            
            // Update local state
            state.shipments = data.shipments;
            const progress = data.progress;
            state.progress = progress;
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
            saveSessionState();

            if (data.status === 'completed' || progress >= 100) {
                state.isTracking = false;
                progressText.textContent = 'Sync All Completed!';
                startTrackingBtn.disabled = false;
                saveSessionState();
            } else if (data.status === 'failed') {
                state.isTracking = false;
                progressText.textContent = 'Sync All Failed.';
                startTrackingBtn.disabled = false;
                saveSessionState();
            } else {
                // Poll again in 1.5 seconds
                setTimeout(pollProgress, 1500);
            }

        } catch (error) {
            console.error('Polling error:', error);
            if (state.isTracking) {
                setTimeout(pollProgress, 2000);
            }
        }
    }

    // Individual Row Sync Handler
    async function syncSingleShipment(trackingNumber, courier, syncButton) {
        if (!state.taskId && state.shipments.length === 0) return;
        if (!state.taskId) state.taskId = 'task_' + Date.now();
        
        syncButton.innerHTML = `<img src="/static/loading.gif" alt="Syncing" style="width: 18px; height: 18px; vertical-align: middle;">`;
        syncButton.disabled = true;

        const currentItem = state.shipments.find(s => s.tracking_number === trackingNumber);

        try {
            const res = await fetch('/api/track/sync_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    tracking_number: trackingNumber,
                    courier: courier,
                    invoice_no: currentItem ? currentItem.invoice_no : '',
                    platform_status: currentItem ? currentItem.platform_status : ''
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
                state.shipments[idx].screenshot = data.screenshot || "-";
            }

            // Render and update stats
            applyFilters(false);
            recalculateStats();
            saveSessionState();

        } catch (error) {
            alert(`Error syncing AWB ${trackingNumber}: ${error.message}`);
        } finally {
            syncButton.innerHTML = `<i data-lucide="refresh-cw"></i>`;
            lucide.createIcons();
            syncButton.disabled = false;
        }
    }

    // Direct Excel export from client memory (guarantees export works even if Render woke up recently)
    exportBtn.addEventListener('click', async () => {
        if (!state.shipments || state.shipments.length === 0) return;

        const originalBtnHtml = exportBtn.innerHTML;
        exportBtn.innerHTML = `<img src="/static/loading.gif" alt="Exporting" style="width: 16px; height: 16px; vertical-align: middle; margin-right: 6px;"> Exporting...`;
        exportBtn.disabled = true;

        try {
            const res = await fetch('/api/export_direct', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId || 'export',
                    shipments: state.shipments
                })
            });

            if (!res.ok) throw new Error('Failed to generate Excel export');

            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const taskSuffix = state.taskId ? state.taskId.substring(0, 8) : 'export';
            a.download = `tracking_export_${taskSuffix}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            // Fallback to GET endpoint
            if (state.taskId) {
                window.location.href = `/api/export?task_id=${state.taskId}`;
            } else {
                alert(`Export error: ${e.message}`);
            }
        } finally {
            exportBtn.innerHTML = originalBtnHtml;
            exportBtn.disabled = false;
            lucide.createIcons();
        }
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

            // Excel Column Filters
            let matchesColumnFilters = true;
            for (const [col, selectedVals] of Object.entries(state.activeColumnFilters)) {
                if (selectedVals && selectedVals.length > 0) {
                    let itemVal = item[col] || '';
                    if (col === 'screenshot') {
                        itemVal = (item.screenshot && item.screenshot !== '-') ? 'Has Screenshot' : 'No Screenshot';
                    } else if (col === 'invoice_no' || col === 'platform_status') {
                        itemVal = itemVal || '-';
                    } else if (col === 'last_location') {
                        itemVal = itemVal || 'Pending scan';
                    } else if (col === 'timestamp' || col === 'last_sync') {
                        itemVal = itemVal || '-';
                    }
                    
                    if (!selectedVals.includes(String(itemVal))) {
                        matchesColumnFilters = false;
                        break;
                    }
                }
            }

            return matchesQuery && matchesCourier && matchesStatus && matchesColumnFilters;
        });

        // Highlight header buttons that have active filters
        document.querySelectorAll('.header-filter-btn').forEach(btn => {
            const th = btn.closest('th');
            if (th) {
                const colKey = th.getAttribute('data-col');
                const active = state.activeColumnFilters[colKey] && state.activeColumnFilters[colKey].length > 0;
                if (active) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
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
            saveSessionState();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredShipments.length / state.rowsPerPage) || 1;
        if (state.currentPage < totalPages) {
            state.currentPage++;
            renderCurrentPage();
            saveSessionState();
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
        saveSessionState();
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

    // --- 30 Unique AWB Color Palettes (bg, text) ---
    const AWB_COLORS = [
        { bg: '#dbeafe', text: '#1e40af' },  // Blue
        { bg: '#fce7f3', text: '#9d174d' },  // Pink
        { bg: '#d1fae5', text: '#065f46' },  // Emerald
        { bg: '#fef3c7', text: '#92400e' },  // Amber
        { bg: '#ede9fe', text: '#5b21b6' },  // Violet
        { bg: '#ffedd5', text: '#c2410c' },  // Orange
        { bg: '#cffafe', text: '#155e75' },  // Cyan
        { bg: '#fecdd3', text: '#9f1239' },  // Rose
        { bg: '#dcfce7', text: '#166534' },  // Green
        { bg: '#e0e7ff', text: '#3730a3' },  // Indigo
        { bg: '#fef9c3', text: '#854d0e' },  // Yellow
        { bg: '#f3e8ff', text: '#6b21a8' },  // Purple
        { bg: '#ccfbf1', text: '#134e4a' },  // Teal
        { bg: '#fee2e2', text: '#991b1b' },  // Red
        { bg: '#e0f2fe', text: '#075985' },  // Sky
        { bg: '#fae8ff', text: '#86198f' },  // Fuchsia
        { bg: '#ecfccb', text: '#3f6212' },  // Lime
        { bg: '#f1f5f9', text: '#334155' },  // Slate
        { bg: '#fff1f2', text: '#be123c' },  // Light Rose
        { bg: '#f0fdfa', text: '#115e59' },  // Light Teal
        { bg: '#fdf4ff', text: '#a21caf' },  // Light Fuchsia
        { bg: '#f0fdf4', text: '#14532d' },  // Light Green
        { bg: '#eff6ff', text: '#1e3a8a' },  // Light Blue
        { bg: '#fffbeb', text: '#78350f' },  // Light Amber
        { bg: '#fdf2f8', text: '#831843' },  // Light Pink
        { bg: '#f5f3ff', text: '#4c1d95' },  // Light Violet
        { bg: '#ecfdf5', text: '#064e3b' },  // Light Emerald
        { bg: '#fff7ed', text: '#9a3412' },  // Light Orange
        { bg: '#f8fafc', text: '#0f172a' },  // Light Slate
        { bg: '#fefce8', text: '#713f12' },  // Light Yellow
    ];

    function getAwbColorIndex(trackingNumber) {
        let hash = 0;
        for (let i = 0; i < trackingNumber.length; i++) {
            hash = ((hash << 5) - hash) + trackingNumber.charCodeAt(i);
            hash |= 0;
        }
        return Math.abs(hash) % AWB_COLORS.length;
    }

    // --- Helper UI Renderers ---

    function renderTable(dataList) {
        if (dataList.length === 0) {
            tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="10">
                        <div class="empty-state">
                            <i data-lucide="file-warning"></i>
                            <p>No matching shipments found.</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = '';
        dataList.forEach((item, index) => {
            const tr = document.createElement('tr');

            const statusKey = item.status.toLowerCase().replace(/[\s_]+/g, '_');
            let badgeClass = 'badge-pending';
            if (statusKey === 'delivered') badgeClass = 'badge-delivered';
            else if (statusKey === 'in_transit' || statusKey === 'in transit' || statusKey === 'picked_up' || statusKey === 'out_for_delivery' || statusKey === 'out for delivery' || statusKey === 'out_for_pickup') badgeClass = 'badge-transit';
            else if (statusKey === 'exception') badgeClass = 'badge-exception';

            // Determine timestamp filled/empty status
            const isTimestampEmpty = !item.timestamp || item.timestamp === '-';
            const timestampBadgeClass = isTimestampEmpty ? 'timestamp-empty' : 'timestamp-filled';
            const printTimestamp = isTimestampEmpty ? '-' : item.timestamp;

            // Determine last sync filled/empty status
            const isLastSyncEmpty = !item.last_sync || item.last_sync === '-';
            const lastSyncBadgeClass = isLastSyncEmpty ? 'lastsync-empty' : 'lastsync-filled';
            const printLastSync = isLastSyncEmpty ? '-' : item.last_sync;

            // Unique row color
            const awbColor = AWB_COLORS[index % AWB_COLORS.length];
            const rowTextColor = awbColor.text;

            // Spin single sync button if bulk tracking is in progress and this item is still pending
            const isSpinning = state.isTracking && item.status.toLowerCase() === 'pending';

            // Determine screenshot column markup
            const hasScreenshot = item.screenshot && item.screenshot !== '-';
            const screenshotHtml = hasScreenshot ? 
                `<a href="${item.screenshot}" download target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 500;">Link</a>` : 
                `-`;

            tr.innerHTML = `
                <td><span style="color:${rowTextColor}">${item.invoice_no || '-'}</span></td>
                <td><span class="awb-badge" style="color:${rowTextColor}">${item.tracking_number}</span></td>
                <td><span class="courier-badge ${getCourierBadgeClass(item.courier)}">${item.courier}</span></td>
                <td><span style="color:${rowTextColor}">${item.platform_status || '-'}</span></td>
                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                <td><span class="location-badge" style="color:${rowTextColor}">${item.last_location || 'Pending scan'}</span></td>
                <td><span class="timestamp-badge ${timestampBadgeClass}" style="color:${isTimestampEmpty ? '' : rowTextColor}">${printTimestamp}</span></td>
                <td><span class="lastsync-badge ${lastSyncBadgeClass}" style="color:${isLastSyncEmpty ? '' : rowTextColor}">${printLastSync}</span></td>
                <td style="text-align: center;">${screenshotHtml}</td>
                <td style="text-align: center;">
                    <button class="btn-sync-single" title="Sync Status" style="color:${rowTextColor}" ${isSpinning ? 'disabled' : ''}>
                        ${isSpinning ? 
                            `<img src="/static/loading.gif" alt="Syncing" style="width: 18px; height: 18px; vertical-align: middle;">` : 
                            `<i data-lucide="refresh-cw"></i>`
                        }
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

    // --- Auto-load latest data on page refresh if sessionStorage was empty ---
    async function loadLatestData() {
        try {
            const res = await fetch('/api/latest');
            if (!res.ok) return;
            const data = await res.json();
            if (data.task_id && data.shipments && data.shipments.length > 0) {
                state.taskId = data.task_id;
                state.shipments = data.shipments;
                state.stats = data.stats;
                state.filteredShipments = [...state.shipments];
                state.currentPage = 1;
                updateStatsUI();
                renderCurrentPage();
                exportBtn.disabled = false;
                clearAllBtn.disabled = false;
                startTrackingBtn.disabled = false;
                saveSessionState();
            }
        } catch (e) {
            console.log('No previous data to restore from server.');
        }
    }

    // --- Quick Track Single AWB Handler ---
    const quickAwbInput = document.getElementById('quick-awb-input');
    const quickCourierSelect = document.getElementById('quick-courier-select');
    const quickTrackBtn = document.getElementById('quick-track-btn');

    quickTrackBtn.addEventListener('click', async () => {
        const awb = quickAwbInput.value.trim();
        const courier = quickCourierSelect.value;

        if (!awb) {
            alert('Please enter an AWB number.');
            return;
        }
        if (!courier) {
            alert('Please select a courier partner.');
            return;
        }

        const originalBtnHtml = quickTrackBtn.innerHTML;
        quickTrackBtn.innerHTML = `<img src="/static/loading.gif" alt="Syncing" style="width: 16px; height: 16px; vertical-align: middle; margin-right: 6px;"> Syncing...`;
        quickTrackBtn.disabled = true;

        try {
            const res = await fetch('/api/track/query_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tracking_number: awb,
                    courier: courier
                })
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || 'Failed to query AWB');
            }

            const data = await res.json();

            // Update API Hits counter in state and UI
            state.stats.api_calls = data.api_calls;
            statApi.textContent = data.api_calls;

            // Clear inputs
            quickAwbInput.value = '';
            quickCourierSelect.value = '';

            // Populate and show Result Modal
            document.getElementById('res-awb').textContent = data.tracking_number;
            
            // Courier Badge
            const resCourier = document.getElementById('res-courier');
            resCourier.innerHTML = `<span class="courier-badge ${getCourierBadgeClass(data.courier)}">${data.courier}</span>`;
            
            // Status Badge
            const statusKey = data.status.toLowerCase().replace(/[\s_]+/g, '_');
            let badgeClass = 'badge-pending';
            if (statusKey === 'delivered') badgeClass = 'badge-delivered';
            else if (statusKey === 'in_transit' || statusKey === 'in transit' || statusKey === 'picked_up' || statusKey === 'out_for_delivery' || statusKey === 'out for delivery' || statusKey === 'out_for_pickup') badgeClass = 'badge-transit';
            else if (statusKey === 'exception') badgeClass = 'badge-exception';
            
            const resStatus = document.getElementById('res-status');
            resStatus.innerHTML = `<span class="badge ${badgeClass}">${data.status}</span>`;
            
            document.getElementById('res-location').textContent = data.last_location || 'Pending scan';
            document.getElementById('res-timestamp').textContent = data.timestamp || '-';
            
            // Populate screenshot and preview image if available
            const resScreenshot = document.getElementById('res-screenshot');
            const previewRow = document.getElementById('res-screenshot-preview-row');
            const previewImg = document.getElementById('res-screenshot-img');
            
            const hasScreenshot = data.screenshot && data.screenshot !== '-';
            if (hasScreenshot) {
                resScreenshot.innerHTML = `<a href="${data.screenshot}" download target="_blank" style="color: #2563eb; text-decoration: underline; font-weight: 500;">Link</a>`;
                previewImg.src = data.screenshot;
                previewRow.style.display = 'flex';
            } else {
                resScreenshot.textContent = '-';
                previewImg.src = '';
                previewRow.style.display = 'none';
            }
            
            // Show modal
            resultModal.style.display = 'flex';
            lucide.createIcons();

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            quickTrackBtn.innerHTML = originalBtnHtml;
            quickTrackBtn.disabled = false;
        }
    });

    // Result Modal close handlers
    const resultModal = document.getElementById('result-modal');
    const resModalCloseX = document.getElementById('result-modal-close-x');
    const resModalCloseBtn = document.getElementById('result-modal-close-btn');

    function closeResultModal() {
        resultModal.style.display = 'none';
    }

    resModalCloseX.addEventListener('click', closeResultModal);
    resModalCloseBtn.addEventListener('click', closeResultModal);
    resultModal.addEventListener('click', (e) => {
        if (e.target === resultModal) {
            closeResultModal();
        }
    });

    // Floating Excel-like Dropdown logic
    let activeDropdown = null;

    document.addEventListener('click', (e) => {
        if (activeDropdown && !activeDropdown.contains(e.target) && !e.target.closest('.header-filter-btn')) {
            closeActiveDropdown();
        }
    });

    function closeActiveDropdown() {
        if (activeDropdown) {
            activeDropdown.remove();
            activeDropdown = null;
        }
    }

    // Setup Column Header Filter Triggers
    document.querySelectorAll('.header-filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const th = btn.closest('th');
            const colKey = th.getAttribute('data-col');
            
            if (activeDropdown && activeDropdown.getAttribute('data-col') === colKey) {
                closeActiveDropdown();
                return;
            }
            
            closeActiveDropdown();
            openFilterDropdown(btn, colKey);
        });
    });

    function openFilterDropdown(btn, colKey) {
        // Get all distinct values of this column from state.shipments
        let allValues = state.shipments.map(item => {
            let val = item[colKey] || '';
            if (colKey === 'screenshot') {
                return (item.screenshot && item.screenshot !== '-') ? 'Has Screenshot' : 'No Screenshot';
            } else if (colKey === 'invoice_no') {
                return val || '-';
            } else if (colKey === 'last_location') {
                return val || 'Pending scan';
            } else if (colKey === 'timestamp' || colKey === 'last_sync') {
                return val || '-';
            }
            return String(val).trim();
        });
        
        // Remove duplicates and sort
        let uniqueValues = [...new Set(allValues)].filter(v => v !== '').sort((a, b) => {
            if (a === '-' || a === 'Pending scan') return 1;
            if (b === '-' || b === 'Pending scan') return -1;
            return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
        });
        
        // If no data
        if (uniqueValues.length === 0) {
            uniqueValues = ['No data'];
        }
        
        const activeSelections = state.activeColumnFilters[colKey] || [];
        
        const dropdown = document.createElement('div');
        dropdown.className = 'excel-filter-dropdown';
        dropdown.setAttribute('data-col', colKey);
        
        let dropdownHtml = `
            <div class="excel-filter-search-container">
                <input type="text" class="excel-filter-search" placeholder="Search values...">
            </div>
            <div class="excel-filter-list">
                <label class="excel-filter-item select-all-item">
                    <input type="checkbox" id="filter-select-all" ${activeSelections.length === 0 || activeSelections.length === uniqueValues.length ? 'checked' : ''}>
                    <span class="excel-filter-item-label" style="font-weight: 600;">(Select All)</span>
                </label>
        `;
        
        uniqueValues.forEach(val => {
            const isChecked = activeSelections.length === 0 || activeSelections.includes(val);
            dropdownHtml += `
                <label class="excel-filter-item val-item">
                    <input type="checkbox" class="excel-filter-val-cb" value="${val}" ${isChecked ? 'checked' : ''}>
                    <span class="excel-filter-item-label" title="${val}">${val}</span>
                </label>
            `;
        });
        
        dropdownHtml += `
            </div>
            <div class="excel-filter-actions">
                <button class="excel-filter-btn excel-filter-clear">Clear</button>
                <button class="excel-filter-btn excel-filter-apply">OK</button>
            </div>
        `;
        
        dropdown.innerHTML = dropdownHtml;
        document.body.appendChild(dropdown);
        activeDropdown = dropdown;
        
        // Position dropdown
        const btnRect = btn.getBoundingClientRect();
        const dropdownWidth = 250;
        let leftPos = btnRect.left + window.scrollX;
        if (leftPos + dropdownWidth > window.innerWidth) {
            leftPos = window.innerWidth - dropdownWidth - 10;
        }
        dropdown.style.top = `${btnRect.bottom + window.scrollY + 5}px`;
        dropdown.style.left = `${leftPos}px`;
        
        const searchInput = dropdown.querySelector('.excel-filter-search');
        const valItems = dropdown.querySelectorAll('.excel-filter-item.val-item');
        const selectAllCb = dropdown.querySelector('#filter-select-all');
        
        searchInput.focus();
        
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.toLowerCase().trim();
            valItems.forEach(item => {
                const text = item.querySelector('.excel-filter-item-label').textContent.toLowerCase();
                if (text.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        });
        
        selectAllCb.addEventListener('change', () => {
            const isChecked = selectAllCb.checked;
            valItems.forEach(item => {
                if (item.style.display !== 'none') {
                    item.querySelector('input').checked = isChecked;
                }
            });
        });
        
        dropdown.querySelectorAll('.excel-filter-val-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                const visibleCbs = Array.from(dropdown.querySelectorAll('.excel-filter-val-cb')).filter(c => c.closest('.excel-filter-item').style.display !== 'none');
                const checkedVisible = visibleCbs.filter(c => c.checked);
                selectAllCb.checked = (checkedVisible.length === visibleCbs.length);
            });
        });
        
        dropdown.querySelector('.excel-filter-apply').addEventListener('click', () => {
            const checkedValues = Array.from(dropdown.querySelectorAll('.excel-filter-val-cb'))
                .filter(cb => cb.checked)
                .map(cb => cb.value);
                
            if (checkedValues.length === uniqueValues.length || checkedValues.length === 0) {
                state.activeColumnFilters[colKey] = [];
            } else {
                state.activeColumnFilters[colKey] = checkedValues;
            }
            
            closeActiveDropdown();
            applyFilters(true);
            saveSessionState();
        });
        
        dropdown.querySelector('.excel-filter-clear').addEventListener('click', () => {
            state.activeColumnFilters[colKey] = [];
            closeActiveDropdown();
            applyFilters(true);
            saveSessionState();
        });
    }

    // Initialize State on Page Load (restore from session storage first)
    restoreSessionState().then(hasSession => {
        if (!hasSession) {
            loadLatestData();
        }
    });
});
