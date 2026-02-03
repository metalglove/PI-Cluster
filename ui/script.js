// --- Configuration ---
const COLORS = {
    bg: '#050510',
    point: '#2a2a40',  // Darker, subtle
    pointActive: '#ffffff',
    primary: '#00f2ff',
    secondary: '#7000ff',
    success: '#00ff9d',
    danger: '#ff0055',
    text_muted: '#a0a0b0'
};

// --- State ---
let points = [];
let circles = []; // Array of {cx, cy, r, animRadius}
let bounds = { minX: 0, maxX: 1000, minY: 0, maxY: 1000 };
let metrics = { k: 0, coverage: 0, j: 0 };
let isReplaying = false;

let ws;
const statusEl = document.getElementById('status');

// --- Canvas ---
const canvas = document.getElementById('vizCanvas');
const ctx = canvas.getContext('2d');
let requestID;

function resizeCanvas() {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    // No redraw needed here per se as animation loop handles it
}
window.addEventListener('resize', resizeCanvas);

// --- Animation Loop ---
function animate() {
    render();
    requestID = requestAnimationFrame(animate);
}

function render() {
    // Clear
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Calc Scale
    const rangeX = bounds.maxX - bounds.minX || 1;
    const rangeY = bounds.maxY - bounds.minY || 1;
    const scaleX = canvas.width / rangeX;
    const scaleY = canvas.height / rangeY;
    const scale = Math.min(scaleX, scaleY) * 0.9;
    const offsetX = (canvas.width - rangeX * scale) / 2;
    const offsetY = (canvas.height - rangeY * scale) / 2;

    const toScreen = (x, y) => ({
        x: offsetX + (x - bounds.minX) * scale,
        y: offsetY + (y - bounds.minY) * scale
    });

    // 1. Draw Points (Starfield effect)
    ctx.fillStyle = COLORS.point;
    for (let p of points) {
        const pos = toScreen(p[0], p[1]);
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 1.5, 0, Math.PI * 2);
        ctx.fill();
    }

    // 2. Draw Circles with Glow and Animation
    circles.forEach(c => {
        // Animate expansion
        if (c.animR < c.r) {
            c.animR += (c.r - c.animR) * 0.1; // Ease out
            if (Math.abs(c.r - c.animR) < 0.1) c.animR = c.r;
        }

        const pos = toScreen(c.cx, c.cy);
        const rScreen = c.animR * scale;

        // Glow style
        ctx.shadowBlur = 15;
        ctx.shadowColor = COLORS.primary;
        ctx.strokeStyle = COLORS.primary;
        ctx.lineWidth = 2;
        ctx.fillStyle = 'rgba(0, 242, 255, 0.1)';

        ctx.beginPath();
        ctx.arc(pos.x, pos.y, rScreen, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Center point
        ctx.shadowBlur = 0;
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 3, 0, Math.PI * 2);
        ctx.fill();
    });

    // Reset effects
    ctx.shadowBlur = 0;
}

// --- Charts Setup ---
Chart.defaults.color = '#a0a0b0';
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.scale.grid.color = 'rgba(255, 255, 255, 0.05)';

const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: {
        legend: { labels: { usePointStyle: true, boxWidth: 6 } },
        tooltip: {
            backgroundColor: 'rgba(5, 5, 16, 0.9)',
            titleColor: '#fff',
            bodyColor: '#ccc',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1
        }
    },
    scales: { x: { display: false }, y: { beginAtZero: true } }
};

const gainCtx = document.getElementById('gainChart').getContext('2d');
const gainChart = new Chart(gainCtx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Marginal Gain',
            data: [],
            borderColor: COLORS.primary,
            backgroundColor: 'rgba(0, 242, 255, 0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: '#000',
            pointBorderColor: COLORS.primary,
            pointBorderWidth: 2
        }, {
            label: 'Threshold',
            data: [],
            borderColor: COLORS.danger,
            borderDash: [5, 5],
            pointRadius: 0,
            tension: 0
        }]
    },
    options: {
        ...commonOptions,
        plugins: { ...commonOptions.plugins, title: { display: true, text: 'MARGINAL GAIN / STEP' } }
    }
});

const coverageCtx = document.getElementById('coverageChart').getContext('2d');
const coverageChart = new Chart(coverageCtx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Total Coverage',
            data: [],
            borderColor: COLORS.success,
            backgroundColor: 'rgba(0, 255, 157, 0.1)',
            fill: true,
            tension: 0.3,
            pointRadius: 0
        }]
    },
    options: {
        ...commonOptions,
        plugins: { ...commonOptions.plugins, title: { display: true, text: 'TOTAL POINTS COVERED' } }
    }
});

// --- Logic ---
function highlightLines(ids) {
    document.querySelectorAll('.code-line').forEach(el => el.classList.remove('active'));
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('active');
    });
}

// --- WebSocket ---
function connect() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/ws`);

    ws.onopen = () => {
        statusEl.textContent = 'SYSTEM CONNECTED';
        statusEl.style.color = COLORS.success;
        statusEl.style.borderColor = COLORS.success;
        // Auto-replay history in case we missed events
        ws.send(JSON.stringify({ action: 'replay' }));
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    ws.onclose = () => {
        statusEl.textContent = 'DISCONNECTED';
        statusEl.style.color = COLORS.danger;
        statusEl.style.borderColor = COLORS.danger;
        setTimeout(connect, 3000);
    };
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'INIT':
            points = msg.points;
            bounds = msg.bounds;
            circles = [];

            // Update Config
            if (msg.config) {
                document.getElementById('conf-points').textContent = msg.config.n_points;
                document.getElementById('conf-circles').textContent = msg.config.n_circles;
                document.getElementById('conf-k').textContent = msg.config.k;
                document.getElementById('conf-eps').textContent = msg.config.epsilon;
            }

            // Reset charts
            gainChart.data.labels = [];
            gainChart.data.datasets[0].data = [];
            gainChart.data.datasets[1].data = [];
            coverageChart.data.labels = [];
            coverageChart.data.datasets[0].data = [];

            gainChart.update();
            coverageChart.update();

            highlightLines(['line-1', 'line-2']);
            setWorkerStatus(true);
            break;

        case 'STATUS':
            document.getElementById('algo-status').textContent = msg.message;
            if (msg.total_guesses !== undefined) {
                document.getElementById('total-guesses').textContent = msg.total_guesses;
            }
            if (msg.message.includes("Calculating max single")) highlightLines(['line-1']);
            break;

        case 'START_GUESS':
            metrics.j = msg.value;
            // Display as 1-indexed for user-friendliness
            document.getElementById('guess-value').textContent = metrics.j + 1;
            document.getElementById('algo-status').textContent = `GUESS ${metrics.j + 1}`;

            if (msg.threshold !== undefined) {
                document.getElementById('threshold-value').textContent = msg.threshold.toFixed(2);
            }

            // Soft reset circles for new guess
            circles = [];

            // Charts clear
            gainChart.data.labels = [];
            gainChart.data.datasets[0].data = [];
            gainChart.data.datasets[1].data = [];
            coverageChart.data.labels = [];
            coverageChart.data.datasets[0].data = [];
            gainChart.update();
            coverageChart.update();

            highlightLines(['line-3', 'line-4', 'line-5']);
            break;

        case 'CIRCLE_ADDED':
            // Add circle with animation prop
            circles.push({ ...msg.circle, animR: 0 }); // Start radius at 0 for animation

            metrics.k = circles.length;
            metrics.coverage = msg.coverage;

            document.getElementById('k-value').textContent = metrics.k;
            document.getElementById('coverage-value').textContent = metrics.coverage;

            if (msg.threshold) document.getElementById('threshold-value').textContent = msg.threshold.toFixed(2);

            // Update Charts
            const step = msg.step || circles.length;
            gainChart.data.labels.push(step);
            gainChart.data.datasets[0].data.push(msg.gain);
            gainChart.data.datasets[1].data.push(msg.threshold);
            gainChart.update('none'); // Perf opt

            coverageChart.data.labels.push(step);
            coverageChart.data.datasets[0].data.push(msg.coverage);
            coverageChart.update('none');

            highlightLines(['line-6', 'line-7', 'line-8']);
            break;

        case 'FINISHED':
            statusEl.textContent = 'OPTIMIZATION COMPLETE';
            statusEl.style.color = COLORS.primary;
            document.getElementById('algo-status').textContent = 'DONE';
            highlightLines(['line-11']);
            setWorkerStatus(false);
            break;
    }
}

// --- Init ---
animate(); // Start canvas loop
connect();
resizeCanvas();

// --- Control Panel ---
const runBtn = document.getElementById('runBtn');
const workerDot = document.getElementById('worker-dot');
const workerText = document.getElementById('worker-text');

function setWorkerStatus(state) {
    // state: 'IDLE', 'BUSY', 'WAITING'
    workerDot.classList.remove('active', 'waiting');

    if (state === 'BUSY' || state === true) {
        workerDot.classList.add('active');
        workerText.textContent = 'Workers Busy';
        workerText.style.color = COLORS.success;
        runBtn.disabled = true;
        runBtn.textContent = 'Simulation Running...';
    } else if (state === 'WAITING') {
        workerDot.classList.add('waiting');
        workerText.textContent = 'Waiting for Resources';
        workerText.style.color = COLORS.warning;
        runBtn.disabled = true;
        runBtn.textContent = 'Queued...';
    } else {
        // IDLE
        workerText.textContent = 'Workers Idle';
        workerText.style.color = COLORS.text_muted;
        runBtn.disabled = false;
        runBtn.textContent = 'Run New Simulation';
    }
}

runBtn.addEventListener('click', async () => {
    try {
        statusEl.textContent = 'STARTING...';
        runBtn.disabled = true;

        // Use fetch with timeout or fire-and-forget logic if needed
        // Assuming current viz_server handles it well
        const res = await fetch('/run', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'started') {
            statusEl.textContent = 'JOB SUBMITTED';
            // We assume it becomes active shortly
        } else {
            statusEl.textContent = 'ERROR';
            console.error(data);
            runBtn.disabled = false;
        }
    } catch (e) {
        console.error("Run failed", e);
        statusEl.textContent = 'REQ FAILED';
        runBtn.disabled = false;
    }
});

document.getElementById('replayBtn').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        statusEl.textContent = 'REPLAYING...';
        ws.send(JSON.stringify({ action: 'replay' }));
    }
});

// --- Worker Stats Polling ---
async function updateClusterStats() {
    try {
        const res = await fetch('/cluster-status');
        const data = await res.json();
        const list = document.getElementById('worker-list');

        // Check App Status & Render Queue
        const queueList = document.getElementById('job-queue');
        let myAppFound = false;

        if (data.activeapps && data.activeapps.length > 0) {
            let firstCircleCover = true;
            queueList.innerHTML = data.activeapps.map(app => {
                const isMine = app.name === 'CircleCover' && firstCircleCover;
                if (isMine) {
                    myAppFound = true;
                    firstCircleCover = false; // Only mark the first one
                }

                const stateColor = app.state === 'RUNNING' ? COLORS.primary : COLORS.warning;
                const stateBg = app.state === 'RUNNING' ? 'rgba(0, 242, 255, 0.2)' : 'rgba(255, 189, 46, 0.2)';

                // Duration
                const durationMs = Date.now() - app.starttime; // Ensure app.starttime is provided by backend
                const seconds = Math.floor(durationMs / 1000);
                const mins = Math.floor(seconds / 60);
                const secs = seconds % 60;
                const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

                return `
                    <div class="queue-item ${isMine ? 'mine' : ''}">
                        <div style="display:flex; flex-direction:column; gap:2px;">
                            <span style="font-weight:600; color:#fff;">
                                ${app.name} ${isMine ? '<span style="color:var(--text-muted); font-weight:400; font-size:10px;">(You)</span>' : ''}
                            </span>
                            <div style="display:flex; gap:8px; font-size:10px; color:var(--text-muted);">
                                <span>Cores: ${app.cores}</span>
                                <span>Time: ${timeStr}</span>
                            </div>
                        </div>
                        <div class="job-state" style="color:${stateColor}; background:${stateBg};">
                            ${app.state}
                        </div>
                    </div>
                `;
            }).join('');

            // Logic to update main status button based on "my" app
            const myApp = data.activeapps.find(a => a.name === 'CircleCover');
            if (myApp) {
                if (myApp.state === 'WAITING') {
                    statusEl.textContent = 'WAITING FOR RESOURCES...';
                    statusEl.style.color = COLORS.warning;
                    statusEl.style.borderColor = COLORS.warning;
                    setWorkerStatus('WAITING');
                } else if (myApp.state === 'RUNNING') {
                    if (statusEl.textContent === 'JOB SUBMITTED' ||
                        statusEl.textContent === 'WAITING FOR RESOURCES...' ||
                        statusEl.textContent === 'SYSTEM CONNECTED') {

                        statusEl.textContent = 'CLUSTER RUNNING';
                        statusEl.style.color = COLORS.primary;
                        statusEl.style.borderColor = COLORS.primary;
                        setWorkerStatus('BUSY');
                    }
                }
            }

        } else {
            queueList.innerHTML = '';
        }

        if (!data.workers || data.workers.length === 0) {
            list.innerHTML = '<div style="text-align:center; color: var(--text-muted); padding: 10px;">No Active Workers</div>';
            return;
        }

        list.innerHTML = data.workers.map(w => `
            <div class="worker-item">
                <div class="worker-header">
                    <span>${w.host}</span>
                    <span style="color: ${w.state === 'ALIVE' ? 'var(--success)' : 'var(--danger)'}">
                        ${w.state}
                    </span>
                </div>
                <div class="worker-stats">
                    <div class="stat-group">
                        <span>Cores</span>
                        <span class="stat-val">${w.cores}</span>
                    </div>
                    <div class="stat-group">
                        <span>Mem</span>
                        <span class="stat-val">${(w.memory / 1024).toFixed(1)} GB</span>
                    </div>
                    <div class="stat-group">
                        <span>ID</span>
                        <span class="stat-val" style="font-size:10px">${w.id.split('-').pop()}</span>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error("Cluster stats failed", e);
    }
}

// Start polling
setInterval(updateClusterStats, 3000);
updateClusterStats(); // Initial fetch
