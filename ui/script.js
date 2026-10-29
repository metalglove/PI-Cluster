// Circle cover demo UI.
//
// Every event the Spark driver sends (INIT, ROUND, START_GUESS, CIRCLE_ADDED, ...) is kept
// in a timeline. A playhead walks through it at a readable pace, so a run can be paused,
// stepped through and rewound during a lecture. The page state is always "the result of
// applying events 0..cursor", which is what makes stepping backwards possible.

// --- Palette ---
const INK = '#1f1d1a';
const POINT = '#c4beb2';
const POINT_COVERED = '#57534c';
const RULE = '#e2ddd2';
const MUTED = '#8c877d';
// One colour per machine, in the order the machines are first seen.
const MACHINE_COLORS = ['#c0532c', '#2c6a96', '#5b7f35', '#8a4c86', '#b4861a', '#357d78'];

const machineColors = new Map();
function colorFor(key) {
    if (!machineColors.has(key)) {
        machineColors.set(key, MACHINE_COLORS[machineColors.size % MACHINE_COLORS.length]);
    }
    return machineColors.get(key);
}

// The Spark master lists workers by IP; partitions report hostname and IP.
const machineKey = p => p.ip || p.host;

const $ = id => document.getElementById(id);
const fmt = n => (n === null || n === undefined) ? '–' : Number(n).toLocaleString();
const fmtTau = t => (t === null || t === undefined) ? '–' : Number(t).toFixed(2);

// --- State ---
function emptyState() {
    return {
        config: null,
        bounds: { minX: 0, minY: 0, maxX: 1000, maxY: 1000 },
        points: [],
        sampling: null,
        totalGuesses: null,
        fe: null,
        j: null,
        tau: null,
        circles: [],          // {cx, cy, r, step, machine, animR}
        isFinal: false,
        gains: [],            // {step, gain, tau, machine}
        coverage: null,
        rounds: 0,
        lastRound: null,
        machineTotals: {},    // machine key -> candidates scored, all rounds
        machineNames: {},     // machine key -> {host, ip}
        guesses: [],          // {j, tau, picks, coverage, gains}
        bestGuess: null,
        lines: [],
        now: 'Waiting for a run.',
        finished: false
    };
}

let state = emptyState();

function reduce(s, e) {
    switch (e.type) {
        case 'INIT': {
            const fresh = emptyState();
            Object.assign(s, fresh);
            s.config = e.config;
            s.bounds = e.bounds;
            s.points = e.points;
            s.sampling = e.sampling || null;
            s.totalGuesses = e.total_guesses || null;
            s.lines = [1];
            const total = s.sampling ? s.sampling.total : e.config.n_points;
            s.now = `${fmt(total)} points and ${fmt(e.config.n_circles)} candidate circles generated. ` +
                `First, find the best single circle.`;
            break;
        }
        case 'STATUS':
            if (e.total_guesses !== undefined) s.totalGuesses = e.total_guesses;
            if (e.message && e.message.includes('max single')) s.lines = [1];
            break;

        case 'ROUND': {
            s.rounds += 1;
            s.lastRound = { ...e, number: s.rounds };
            for (const p of e.partitions) {
                const key = machineKey(p);
                s.machineTotals[key] = (s.machineTotals[key] || 0) + p.evaluated;
                s.machineNames[key] = { host: p.host, ip: p.ip };
            }
            const scored = e.partitions.reduce((a, p) => a + p.evaluated, 0);
            const machines = new Set(e.partitions.map(machineKey)).size;
            const spread = `${fmt(scored)} circles scored in ${e.partitions.length} partitions on ` +
                `${machines} machine${machines === 1 ? '' : 's'}`;
            if (e.kind === 'oracle') {
                s.fe = e.best;
                s.lines = [1, 2];
                s.now = `Round ${s.rounds}: ${spread}. The best single circle covers f(e) = ${fmt(e.best)} points.`;
            } else if (e.found_partition !== null && e.found_partition !== undefined) {
                const passed = e.partitions.reduce((a, p) => a + p.passed, 0);
                s.lines = [6, 7];
                s.now = `Round ${s.rounds}: ${spread}. ${fmt(passed)} clear τ = ${fmtTau(e.threshold)}; ` +
                    `the first one found is taken.`;
            } else {
                s.lines = [9];
                s.now = `Round ${s.rounds}: ${spread}. None clear τ = ${fmtTau(e.threshold)}, ` +
                    `so guess j = ${s.j} stops at |S| = ${s.circles.length}.`;
            }
            break;
        }
        case 'START_GUESS':
            s.j = e.value;
            s.tau = e.threshold;
            s.circles = [];
            s.coverage = 0;
            s.gains = [];
            s.guesses.push({ j: e.value, tau: e.threshold, picks: 0, coverage: 0, gains: s.gains });
            s.lines = [3, 4, 5];
            s.now = `Guess j = ${e.value}: threshold τ = ${fmtTau(e.threshold)}. Start again from S = ∅.`;
            break;

        case 'CIRCLE_ADDED': {
            let machine = e.host;
            if (s.lastRound) {
                const part = s.lastRound.partitions.find(p => p.partition === e.partition);
                if (part) machine = machineKey(part);
            }
            s.circles.push({ ...e.circle, step: e.step, machine, animR: 0 });
            s.gains.push({ step: e.step, gain: e.gain, tau: e.threshold, machine });
            s.coverage = e.coverage;
            const g = s.guesses[s.guesses.length - 1];
            if (g) { g.picks = s.circles.length; g.coverage = e.coverage; }
            s.lines = [8];
            s.now = `Pick ${e.step}: gain Δf = ${fmt(e.gain)} ≥ τ, so the circle joins S. f(S) = ${fmt(e.coverage)}.`;
            break;
        }
        case 'FINAL_SOLUTION':
            s.circles = e.circles.map((c, i) => ({ ...c, step: i + 1, machine: null, animR: 0 }));
            s.isFinal = true;
            s.bestGuess = e.best_guess;
            s.coverage = e.coverage;
            s.j = e.best_guess;
            {
                // Show the gain chart of the winning guess.
                const best = s.guesses.find(g => g.j === e.best_guess);
                if (best) {
                    s.tau = best.tau;
                    s.gains = best.gains;
                }
            }
            s.lines = [10, 11];
            s.now = `Best guess was j = ${e.best_guess}: ${e.circles.length} circles cover ` +
                `${fmt(e.coverage)} of ${fmt(e.total_points)} points (${e.coverage_percentage}%), ` +
                `after ${s.rounds} rounds.`;
            break;

        case 'FINISHED':
            s.finished = true;
            s.lines = [11];
            break;
    }
}

// --- Timeline / playback ---
let timeline = [];
let cursor = -1;          // index of the last applied event
let playing = true;
let replaying = false;    // true while the server sends history after (re)connecting
let timer = null;

const DWELL_MS = { ROUND: 500, CIRCLE_ADDED: 750, START_GUESS: 1000, FINAL_SOLUTION: 1500, INIT: 800 };

function speed() { return parseFloat($('pbSpeed').value) || 1; }

function seek(target) {
    target = Math.max(-1, Math.min(timeline.length - 1, target));
    if (target === cursor + 1) {
        cursor = target;
        reduce(state, timeline[cursor]);   // one step forward: let the new circle grow in
    } else {
        state = emptyState();
        for (let i = 0; i <= target; i++) reduce(state, timeline[i]);
        state.circles.forEach(c => { c.animR = c.r; });
        cursor = target;
    }
    renderPanels();
}

function schedule() {
    clearTimeout(timer);
    timer = null;
    const atEnd = cursor >= timeline.length - 1;
    if (atEnd && timeline.length && timeline[cursor].type === 'FINISHED') playing = false;  // Play again restarts
    if (!playing || replaying || atEnd) { renderPlayback(); return; }
    const last = timeline[cursor];
    const wait = cursor < 0 ? 0 : (DWELL_MS[last.type] || 200) / speed();
    timer = setTimeout(() => {
        seek(cursor + 1);
        schedule();
    }, wait);
    renderPlayback();
}

function setPlaying(p) { playing = p; schedule(); }

function receive(e) {
    if (e.type === 'REPLAY_DONE') {
        replaying = false;
        // Show where the run is now; ⏮ rewinds it for the class.
        seek(timeline.length - 1);
        schedule();
        return;
    }
    if (e.type === 'INIT' && timeline.length) {
        timeline = [];
        cursor = -1;
        state = emptyState();
        playing = true;
    }
    timeline.push(e);
    if (!timer) schedule(); else renderPlayback();
    renderRunButton();
}

// --- Rendering: panels ---
function renderPanels() {
    const s = state;
    $('emptyNote').hidden = s.points.length > 0;
    $('nowLine').textContent = s.now;

    $('sGuess').textContent = s.j === null ? '–' : s.j;
    $('sGuessTotal').textContent = s.totalGuesses ? ` of 0…${s.totalGuesses - 1}` : '';
    $('sTau').textContent = fmtTau(s.tau);
    $('sSize').textContent = s.config ? s.circles.length : '–';
    $('sK').textContent = s.config ? ` / ${s.config.k}` : '';
    $('sCov').textContent = fmt(s.coverage);

    document.querySelectorAll('.code li').forEach(li => li.classList.remove('active'));
    s.lines.forEach(n => $(`line-${n}`)?.classList.add('active'));

    renderGuesses();
    renderCluster();
    renderLegend();
    drawGainChart();
    renderPlayback();
}

function renderGuesses() {
    const s = state;
    const box = $('guesses');
    if (!s.guesses.length) {
        box.innerHTML = '<p class="hint">One row per threshold tried.</p>';
        return;
    }
    const max = Math.max(1, ...s.guesses.map(g => g.coverage));
    box.innerHTML = s.guesses.map((g, i) => {
        const cls = ['g-row'];
        if (s.isFinal && g.j === s.bestGuess) cls.push('best');
        else if (!s.isFinal && i === s.guesses.length - 1) cls.push('current');
        return `<div class="${cls.join(' ')}">
            <span>j=${g.j}</span>
            <span>τ=${fmtTau(g.tau)}</span>
            <span class="g-bar" title="${g.picks} circles"><i style="width:${100 * g.coverage / max}%"></i></span>
            <span class="g-cov">${fmt(g.coverage)}</span>
        </div>`;
    }).join('');
    const focus = box.querySelector('.current, .best');
    if (focus) box.scrollTop = focus.offsetTop - box.offsetTop - box.clientHeight / 2;
}

let clusterWorkers = [];   // from the Spark master, polled
let renderedRound = 0;

function machineList() {
    const keys = [];
    clusterWorkers.forEach(w => { if (!keys.includes(w.host)) keys.push(w.host); });
    Object.keys(state.machineNames).forEach(k => { if (!keys.includes(k)) keys.push(k); });
    return keys;
}

function renderCluster() {
    const s = state;
    const keys = machineList();
    const round = s.lastRound;
    $('roundCount').textContent = s.rounds;

    if (round) {
        const what = round.kind === 'oracle'
            ? 'scoring every circle on its own to find f(e)'
            : `checking Δf(c | S) ≥ τ for pick ${round.step} of guess j = ${s.j}`;
        const slowest = Math.max(...round.partitions.map(p => p.ms));
        $('roundHint').textContent = `Round ${round.number}: ${what}. Slowest partition took ${fmt(Math.round(slowest))} ms.`;
    } else {
        $('roundHint').textContent = 'Each round, Spark splits the remaining candidate circles into partitions ' +
            'and the Pis score them at the same time.';
    }

    const total = Object.values(s.machineTotals).reduce((a, b) => a + b, 0);
    $('share').innerHTML = total ? keys.filter(k => s.machineTotals[k]).map(k =>
        `<i style="--c:${colorFor(k)}; flex-grow:${s.machineTotals[k]}"></i>`).join('') : '';
    $('shareCaption').innerHTML = total
        ? 'Share of all circle checks so far: ' + keys.filter(k => s.machineTotals[k]).map(k =>
            `${machineLabel(k)} <b>${Math.round(100 * s.machineTotals[k] / total)}%</b>`).join(', ')
        : '';

    if (!keys.length) {
        $('lanes').innerHTML = '<div class="parts-empty">No workers reported yet.</div>';
        return;
    }

    const flash = round && round.number !== renderedRound;
    renderedRound = round ? round.number : 0;
    const localOnly = !clusterWorkers.length && keys.length === 1;

    $('lanes').innerHTML = keys.map(k => {
        const w = clusterWorkers.find(w => w.host === k);
        const name = state.machineNames[k];
        const sub = [];
        if (name && name.ip && name.ip !== name.host) sub.push(name.ip);
        if (w) sub.push(`${w.coresused}/${w.cores} cores busy`, w.state.toLowerCase());
        if (localOnly) sub.push('local mode, one machine');

        const parts = round ? round.partitions.filter(p => machineKey(p) === k)
            .sort((a, b) => a.partition - b.partition) : [];
        const cells = parts.length ? parts.map(p => {
            const picked = round.kind === 'threshold' && p.partition === round.found_partition;
            const share = round.kind === 'threshold' && p.evaluated ? p.passed / p.evaluated : 0;
            const detail = round.kind === 'oracle'
                ? `best ${fmt(p.best)}`
                : `${fmt(p.passed)} ≥ τ`;
            return `<div class="part${picked ? ' picked' : ''}${flash ? ' flash' : ''}"
                        style="--c:${colorFor(k)}; flex-grow:${Math.max(1, p.evaluated)}"
                        title="Partition ${p.partition}: ${p.evaluated} circles, ${detail}, ${p.ms} ms">
                    <span class="fill" style="height:${100 * share}%"></span>
                    <span class="pid">p${p.partition}</span>
                    <span class="num">${fmt(p.evaluated)} · ${detail}</span>
                </div>`;
        }).join('') : `<div class="parts-empty">${round ? 'No partitions this round.' : 'Idle.'}</div>`;

        return `<div class="lane">
            <div class="lane-name" style="--c:${colorFor(k)}">
                <b>${machineLabel(k)}</b>
                ${sub.map(t => `<span>${t}</span>`).join('')}
            </div>
            <div class="parts">${cells}</div>
        </div>`;
    }).join('');
}

function machineLabel(key) {
    const n = state.machineNames[key];
    return n ? n.host : key;
}

function renderLegend() {
    const keys = [...new Set(state.circles.map(c => c.machine).filter(Boolean))];
    let html = keys.map(k =>
        `<span><i class="swatch" style="--c:${colorFor(k)}"></i>found by ${machineLabel(k)}</span>`).join('');
    if (state.isFinal) html = `<span><i class="swatch" style="--c:${INK}"></i>best solution</span>`;
    $('legend').innerHTML = html;
    $('caption').textContent = state.isFinal
        ? `Final answer from guess j = ${state.bestGuess}. Dark points are covered.`
        : 'Each circle is coloured by the Pi whose partition found it. Dark points are covered by S.';
    if (state.sampling) {
        $('caption').textContent += ` Showing ${fmt(state.sampling.displayed)} of ${fmt(state.sampling.total)} points.`;
    }
}

function renderPlayback() {
    const n = timeline.length;
    $('pbScrub').max = Math.max(0, n - 1);
    $('pbScrub').value = Math.max(0, cursor);
    $('pbLabel').textContent = n ? `${cursor + 1} / ${n}` : '0 / 0';
    $('pbPlay').textContent = playing ? 'Pause' : 'Play';
    $('pbBack').disabled = cursor < 0;
    $('pbStart').disabled = cursor < 0;
    $('pbFwd').disabled = cursor >= n - 1;
    $('pbEnd').disabled = cursor >= n - 1;
}

// --- Rendering: canvases ---
function setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
}

// Which points are covered, recomputed only when the circle set changes.
let coverCache = { key: '', flags: [] };
function coveredFlags() {
    const key = state.points.length + '|' + state.circles.map(c => `${c.cx},${c.cy},${c.r}`).join(';');
    if (key !== coverCache.key) {
        coverCache = {
            key,
            flags: state.points.map(([x, y]) =>
                state.circles.some(c => (x - c.cx) ** 2 + (y - c.cy) ** 2 <= c.r * c.r))
        };
    }
    return coverCache.flags;
}

const vizCanvas = $('vizCanvas');
function drawFigure() {
    const { ctx, w, h } = setupCanvas(vizCanvas);
    ctx.clearRect(0, 0, w, h);
    const s = state;
    if (!s.points.length) return;

    const b = s.bounds;
    const rangeX = (b.maxX - b.minX) || 1, rangeY = (b.maxY - b.minY) || 1;
    // Leave room for circles centred near the edge of the bounds.
    const maxR = Math.max(0, ...s.circles.map(c => c.r));
    const scale = Math.min(w / (rangeX + 2 * maxR), h / (rangeY + 2 * maxR), w / rangeX * 0.94, h / rangeY * 0.94);
    const ox = (w - rangeX * scale) / 2, oy = (h - rangeY * scale) / 2;
    const X = x => ox + (x - b.minX) * scale;
    const Y = y => oy + (y - b.minY) * scale;

    ctx.strokeStyle = RULE;
    ctx.lineWidth = 1;
    ctx.strokeRect(X(b.minX), Y(b.minY), rangeX * scale, rangeY * scale);

    const flags = coveredFlags();
    const pr = s.points.length > 3000 ? 1.1 : 1.6;
    for (const covered of [false, true]) {
        ctx.fillStyle = covered ? POINT_COVERED : POINT;
        ctx.beginPath();
        s.points.forEach(([x, y], i) => {
            if (flags[i] !== covered) return;
            ctx.moveTo(X(x) + pr, Y(y));
            ctx.arc(X(x), Y(y), pr, 0, Math.PI * 2);
        });
        ctx.fill();
    }

    s.circles.forEach((c, i) => {
        if (c.animR < c.r) c.animR = Math.abs(c.r - c.animR) < 0.5 ? c.r : c.animR + (c.r - c.animR) * 0.12;
        const color = c.machine ? colorFor(c.machine) : INK;
        const newest = !s.isFinal && i === s.circles.length - 1;
        ctx.beginPath();
        ctx.arc(X(c.cx), Y(c.cy), c.animR * scale, 0, Math.PI * 2);
        ctx.fillStyle = hexAlpha(color, s.isFinal ? 0.07 : 0.1);
        ctx.fill();
        ctx.lineWidth = newest ? 3 : 1.8;
        ctx.strokeStyle = color;
        ctx.stroke();

        ctx.fillStyle = color;
        ctx.font = '500 12px "IBM Plex Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(c.step), X(c.cx), Y(c.cy));
    });
}

function hexAlpha(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

const gainCanvas = $('gainChart');
function drawGainChart() {
    const { ctx, w, h } = setupCanvas(gainCanvas);
    ctx.clearRect(0, 0, w, h);
    const s = state;
    const k = s.config ? s.config.k : 10;
    const pad = { l: 40, r: 8, t: 10, b: 22 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

    const tau = s.tau || 0;
    const maxV = Math.max(tau * 1.25, ...s.gains.map(g => g.gain), 1);
    const step = niceStep(maxV / 4);
    const top = Math.ceil(maxV / step) * step;
    const Y = v => pad.t + ih - (v / top) * ih;

    ctx.font = '11px "IBM Plex Mono", monospace';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';
    for (let v = 0; v <= top + 1e-9; v += step) {
        ctx.strokeStyle = v === 0 ? '#cdc6b8' : RULE;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.l, Math.round(Y(v)) + 0.5);
        ctx.lineTo(w - pad.r, Math.round(Y(v)) + 0.5);
        ctx.stroke();
        ctx.fillStyle = MUTED;
        ctx.fillText(fmt(Math.round(v)), pad.l - 6, Y(v));
    }

    const slot = iw / k;
    const bw = Math.min(28, slot * 0.6);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let i = 0; i < k; i++) {
        ctx.fillStyle = MUTED;
        ctx.fillText(String(i + 1), pad.l + slot * (i + 0.5), h - pad.b + 6);
    }
    {
        s.gains.forEach(g => {
            const x = pad.l + slot * (g.step - 0.5) - bw / 2;
            ctx.fillStyle = g.machine ? colorFor(g.machine) : INK;
            ctx.fillRect(x, Y(g.gain), bw, Y(0) - Y(g.gain));
        });
    }

    if (tau) {
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = INK;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(pad.l, Y(tau));
        ctx.lineTo(w - pad.r, Y(tau));
        ctx.stroke();
        ctx.setLineDash([]);
        // Label on a paper-coloured tab so bars behind it don't make it unreadable.
        const label = `τ = ${fmtTau(tau)}`;
        const lw = ctx.measureText(label).width + 8;
        ctx.fillStyle = '#fffdf8';
        ctx.fillRect(w - pad.r - lw, Y(tau) - 17, lw, 14);
        ctx.fillStyle = INK;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(label, w - pad.r - 4, Y(tau) - 4);
    }

    if (!s.gains.length) {
        ctx.fillStyle = MUTED;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '13px "IBM Plex Sans", sans-serif';
        const msg = s.j === null ? 'Picks appear here once a guess starts.' : 'No picks yet in this guess.';
        ctx.fillText(msg, pad.l + iw / 2, pad.t + ih / 2);
    }
}

function niceStep(raw) {
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const m = raw / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}

function frame() {
    drawFigure();
    requestAnimationFrame(frame);
}
window.addEventListener('resize', drawGainChart);

// --- Controls ---
$('pbPlay').addEventListener('click', () => {
    if (!playing && cursor >= timeline.length - 1 && timeline.length) seek(-1);  // play again from the top
    setPlaying(!playing);
});
$('pbBack').addEventListener('click', () => { setPlaying(false); seek(cursor - 1); });
$('pbFwd').addEventListener('click', () => { setPlaying(false); seek(cursor + 1); });
$('pbStart').addEventListener('click', () => { setPlaying(false); seek(-1); });
$('pbEnd').addEventListener('click', () => { seek(timeline.length - 1); setPlaying(true); });
$('pbScrub').addEventListener('input', e => { setPlaying(false); seek(parseInt(e.target.value, 10)); });
$('pbSpeed').addEventListener('change', schedule);

// Keep focus off buttons so space and the arrow keys always drive playback.
document.querySelectorAll('button').forEach(b => b.addEventListener('mouseup', () => b.blur()));
document.addEventListener('keydown', e => {
    if (e.target.closest('input, select')) return;
    if (e.key === ' ') { e.preventDefault(); $('pbPlay').click(); }
    else if (e.key === 'ArrowRight') $('pbFwd').click();
    else if (e.key === 'ArrowLeft') $('pbBack').click();
});

// --- Run button / connection ---
let wsOpen = false;
let submitting = false;
let appState = null;   // state of our app on the Spark master, if any

function runInProgress() {
    return timeline.length > 0 && timeline[timeline.length - 1].type !== 'FINISHED';
}

function renderRunButton() {
    const busy = submitting || runInProgress() || appState === 'WAITING';
    const btn = $('runBtn');
    btn.disabled = busy || !wsOpen;
    btn.textContent = appState === 'WAITING' ? 'Waiting for cores…' : busy ? 'Running…' : 'Run on cluster';

    const dot = $('connDot');
    dot.className = 'dot ' + (!wsOpen ? 'bad' : busy ? 'busy' : 'ok');
    $('connText').textContent = !wsOpen ? 'Disconnected' : busy ? 'Job running' : 'Connected';
}

$('runBtn').addEventListener('click', async () => {
    submitting = true;
    renderRunButton();
    try {
        const size = document.querySelector('input[name="jobSize"]:checked').value;
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size })
        });
        const data = await res.json();
        if (data.status !== 'started') console.error('Run failed', data);
    } catch (e) {
        console.error('Run failed', e);
    }
    // The run shows up as an INIT event; stop waiting on it after a while either way.
    setTimeout(() => { submitting = false; renderRunButton(); }, 15000);
});

function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
        wsOpen = true;
        timeline = [];
        cursor = -1;
        state = emptyState();
        replaying = true;
        ws.send(JSON.stringify({ action: 'replay' }));
        renderRunButton();
    };
    ws.onmessage = ev => {
        const e = JSON.parse(ev.data);
        if (e.type === 'INIT') submitting = false;
        receive(e);
    };
    ws.onclose = () => {
        wsOpen = false;
        renderRunButton();
        setTimeout(connect, 3000);
    };
}

async function pollCluster() {
    try {
        const res = await fetch('/cluster-status');
        const data = await res.json();
        clusterWorkers = data.status === 'error' ? [] : (data.workers || []);
        const mine = (data.activeapps || []).find(a => a.name === 'CircleCover');
        appState = mine ? mine.state : null;
    } catch (e) {
        clusterWorkers = [];
        appState = null;
    }
    renderCluster();
    renderRunButton();
}

renderPanels();
renderRunButton();
requestAnimationFrame(frame);
connect();
pollCluster();
setInterval(pollCluster, 3000);
