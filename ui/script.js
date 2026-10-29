// Circle cover demo UI.
//
// Two drivers feed it: main.py (threshold greedy, one Spark job per pick) and alg.py
// (Theorem 8: Algorithms 6 and 7, two MapReduce rounds). Every event they send
// (INIT, ROUND, START_GUESS, CIRCLE_ADDED, SAMPLE, GUESS_RESULT, ...) is kept
// in a timeline. A playhead walks through it at a readable pace, so a run can be paused,
// stepped through and rewound during a lecture. The page state is always "the result of
// applying events 0..cursor", which is what makes stepping backwards possible.

// --- Palette (read from the CSS variables, so it follows the light/dark theme) ---
let C = {};
function readPalette() {
    const css = getComputedStyle(document.documentElement);
    const v = name => css.getPropertyValue(name).trim();
    C = {
        ink: v('--ink'), point: v('--point'), pointCovered: v('--point-covered'),
        rule: v('--rule'), ruleStrong: v('--rule-strong'), muted: v('--ink-3'), surface: v('--surface'),
        machines: [0, 1, 2, 3, 4, 5].map(i => v(`--m${i}`))
    };
}
readPalette();

// One colour per machine, in the order the machines are first seen.
// Circles taken from Algorithm 6's random sample belong to no machine and are drawn grey.
const SAMPLE = 'sample';
const machineSlots = new Map();
function colorFor(key) {
    if (key === SAMPLE) return C.muted;
    if (!machineSlots.has(key)) machineSlots.set(key, machineSlots.size);
    return C.machines[machineSlots.get(key) % C.machines.length];
}

// The Spark master lists workers by IP; partitions report hostname and IP.
const machineKey = p => p.ip || p.host;

const $ = id => document.getElementById(id);
const fmt = n => (n === null || n === undefined) ? '–' : Number(n).toLocaleString();
const fmtTau = t => (t === null || t === undefined) ? '–' : Number(t).toFixed(2);

// --- Per-algorithm text ---
const ALGORITHMS = {
    greedy: {
        name: 'Threshold greedy',
        title: 'Circle cover, threshold greedy',
        lede: 'Pick <i>k</i> circles that cover as many points as possible. OPT is unknown, so the algorithm ' +
            'tries a ladder of thresholds τ and keeps the best run. Every candidate check is one Spark job, ' +
            'split across the Raspberry Pis, so the number of rounds grows with <i>k</i>.',
        code: [
            { id: 1, text: 'f(e) ← max single-circle coverage', note: '1 Spark job' },
            { id: 2, text: 'y ← ⌈log k / log(1+ε)⌉' },
            { id: 3, text: 'for j = 0 … y:' },
            { id: 4, text: 'τ ← (1+ε)<sup>j</sup> · f(e) / 2k', indent: 1 },
            { id: 5, text: 'S ← ∅', indent: 1 },
            { id: 6, text: 'while |S| &lt; k:', indent: 1 },
            { id: 7, text: 'find any c with Δf(c | S) ≥ τ', indent: 2, note: '1 Spark job' },
            { id: 8, text: 'if found: S ← S ∪ {c}', indent: 2 },
            { id: 9, text: 'else: stop this guess', indent: 2 },
            { id: 10, text: 'keep S if f(S) is the best so far', indent: 1 },
            { id: 11, text: 'return best S' }
        ]
    },
    theorem8: {
        name: '2 rounds (Thm 8)',
        title: 'Circle cover in two MapReduce rounds',
        lede: 'Liu &amp; Vondrák, Theorem 8: Algorithm 6 handles dense inputs and Algorithm 7 sparse ones. ' +
            'Run both and keep the better answer. Each Pi filters its own share of the circles in round 1, ' +
            'and one central machine finishes in round 2, however large the input.',
        code: [
            { id: 'h6', head: 'Algorithm 6, dense inputs' },
            { id: 'a1', text: 'S ← sample of V, each circle w.p. 4√(k/n); copy S to every machine' },
            { id: 'a2', text: 'v ← max<sub>e∈S</sub> f(e)' },
            { id: 'a3', text: 'round 1, on every machine i, for every guess j:', note: '1 Spark job' },
            { id: 'a4', text: 'τ<sub>j</sub> ← v(1+ε)<sup>j</sup> / k', indent: 1 },
            { id: 'a5', text: 'G₀ ← ThresholdGreedy(S, ∅, τ<sub>j</sub>)', indent: 1 },
            { id: 'a6', text: 'if |G₀| &lt; k: send R<sub>i</sub> ← ThresholdFilter(V<sub>i</sub>, G₀, τ<sub>j</sub>)', indent: 1 },
            { id: 'a7', text: 'round 2, on the central machine, for every j:' },
            { id: 'a8', text: 'G ← ThresholdGreedy(∪<sub>i</sub> R<sub>i</sub>, G₀, τ<sub>j</sub>)', indent: 1 },
            { id: 'h7', head: 'Algorithm 7, sparse inputs' },
            { id: 'b1', text: 'round 1: every machine sends its 2k circles with the largest f(e)', note: '1 Spark job' },
            { id: 'b2', text: 'round 2, central: G<sub>j</sub> ← ThresholdGreedy(S, ∅, τ<sub>j</sub>) for every j' },
            { id: 'h8', head: 'Theorem 8' },
            { id: 'c1', text: 'return the better of the two answers (2 rounds in total)' }
        ]
    }
};
const ALGO_LABEL = { alg6: 'Algorithm 6', alg7: 'Algorithm 7' };

// --- State ---
function emptyState() {
    return {
        config: null,
        algorithm: 'greedy',
        bounds: { minX: 0, minY: 0, maxX: 1000, maxY: 1000 },
        points: [],
        sampling: null,
        totalGuesses: null,
        fe: null,
        j: null,
        tau: null,
        circles: [],          // {cx, cy, r, step, machine, animR}
        background: [],       // faint circles: Algorithm 6's sample, or what round 1 sent
        backgroundNote: '',
        isFinal: false,
        gains: [],            // {step, gain, tau, machine}
        coverage: null,
        rounds: 0,
        roundSeq: 0,          // ROUND events so far (a round can span two events)
        lastRound: null,
        machineTotals: {},    // machine key -> candidates scored, all rounds
        maxLoad: 0,           // most circles one machine handled in one round (MPC: memory per machine)
        sentTotal: 0,         // circles sent to the driver / central machine (MPC: communication)
        machineNames: {},     // machine key -> {host, ip}
        guesses: [],          // {algo, j, tau, picks, coverage, gains}
        bestGuess: null,
        bestAlgo: 'greedy',
        lines: [],
        now: 'Waiting for a run.',
        finished: false
    };
}

let state = emptyState();

function reduce(s, e, index) {
    switch (e.type) {
        case 'INIT': {
            const fresh = emptyState();
            Object.assign(s, fresh);
            s.config = e.config;
            s.bounds = e.bounds;
            s.points = e.points;
            s.sampling = e.sampling || null;
            s.totalGuesses = e.total_guesses || null;
            s.algorithm = e.config.algorithm || 'greedy';
            const total = s.sampling ? s.sampling.total : e.config.n_points;
            s.lines = s.algorithm === 'theorem8' ? ['a1'] : [1];
            s.now = `${fmt(total)} points and ${fmt(e.config.n_circles)} candidate circles generated. ` +
                (s.algorithm === 'theorem8' ? 'Algorithm 6 starts by sampling the circles.'
                    : 'First, find the best single circle.');
            break;
        }
        case 'SAMPLE': {
            s.background = e.circles.map(c => ({ ...c, machine: SAMPLE }));
            s.backgroundNote = 'Faint grey circles: the sample S, copied to every machine.';
            s.fe = e.v;
            s.lines = ['a1', 'a2'];
            s.now = `Algorithm 6: S is a random sample of ${fmt(e.circles.length)} of the ${fmt(e.n)} circles, ` +
                `and every machine gets a copy. The best single circle in S covers v = ${fmt(e.v)} points.`;
            break;
        }
        case 'STATUS':
            if (e.total_guesses !== undefined) s.totalGuesses = e.total_guesses;
            if (e.message && e.message.includes('max single')) s.lines = [1];
            break;

        case 'ROUND': {
            // Theorem 8 numbers its rounds (both algorithms share rounds 1 and 2); greedy just counts.
            s.rounds = e.round ? Math.max(s.rounds, e.round) : s.rounds + 1;
            s.roundSeq += 1;
            s.lastRound = { ...e, number: e.round || s.rounds, seq: s.roundSeq, timelineIndex: index };
            for (const p of e.partitions) {
                const key = machineKey(p);
                if (!e.central) s.machineTotals[key] = (s.machineTotals[key] || 0) + (p.evaluated ?? p.held);
                s.machineNames[key] = { host: p.host, ip: p.ip };
            }
            const cost = roundCost(e);
            s.maxLoad = Math.max(s.maxLoad, ...Object.values(cost.load));
            s.sentTotal += cost.sent;
            if (e.kind in TWO_ROUND_TEXT) {
                if (e.sent_circles) {
                    s.background = e.sent_circles.map(c => ({ ...c, machine: machineKey(c) }));
                    s.backgroundNote = 'Faint circles: what each Pi sent to the central machine, in its colour.';
                }
                Object.assign(s, TWO_ROUND_TEXT[e.kind](e, s));
                break;
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
            s.guesses.push({ algo: 'greedy', j: e.value, tau: e.threshold, picks: 0, coverage: 0, gains: s.gains });
            s.lines = [3, 4, 5];
            s.now = `Guess j = ${e.value}: threshold τ = ${fmtTau(e.threshold)}. Start again from S = ∅.`;
            break;

        case 'GUESS_RESULT': {
            s.j = e.j;
            s.tau = e.threshold;
            s.circles = e.circles.map((c, i) => ({
                ...c, step: i + 1, animR: 0,
                machine: c.source === 'sample' ? SAMPLE : (machineKey(c) || null)
            }));
            s.gains = e.gains.map((g, i) => ({ step: i + 1, gain: g, tau: e.threshold, machine: s.circles[i].machine }));
            s.coverage = e.coverage;
            s.guesses.push({ algo: e.algo, j: e.j, tau: e.threshold, picks: e.circles.length,
                             coverage: e.coverage, gains: s.gains });
            const head = `${ALGO_LABEL[e.algo]}, round 2, guess j = ${e.j} (τ = ${fmtTau(e.threshold)})`;
            if (e.algo === 'alg6') {
                s.lines = ['a7', 'a8'];
                s.now = e.g0 >= s.config.k
                    ? `${head}: G₀ from the sample already has k = ${e.g0} circles, so this guess needs ` +
                      `nothing from round 1. f(G) = ${fmt(e.coverage)}.`
                    : `${head}: G₀ from the sample has ${e.g0} circle${e.g0 === 1 ? '' : 's'}. ` +
                      `Continuing with the ${fmt(e.candidates)} circles sent for this guess gives ` +
                      `|G| = ${e.circles.length}, f(G) = ${fmt(e.coverage)}.`;
            } else {
                s.lines = ['b2'];
                s.now = `${head}: ThresholdGreedy over the ${fmt(e.candidates)} circles sent in round 1 ` +
                    `picks ${e.circles.length}. f(G) = ${fmt(e.coverage)}.`;
            }
            break;
        }
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
            s.background = [];
            if (s.algorithm === 'theorem8') {
                // The winner's best guess: the first one with the highest coverage, as alg.py picks it.
                const own = s.guesses.filter(g => g.algo === e.algorithm);
                const best = own.reduce((a, g) => (!a || g.coverage > a.coverage) ? g : a, null);
                s.bestAlgo = e.algorithm;
                s.bestGuess = best ? best.j : null;
                s.j = s.bestGuess;
                if (best) { s.tau = best.tau; s.gains = best.gains; }
                s.coverage = e.coverage;
                s.lines = ['c1'];
                const c = e.coverages || {};
                s.now = `Algorithm 6 covers ${fmt(c.alg6)} points and Algorithm 7 covers ${fmt(c.alg7)}. ` +
                    `Theorem 8 keeps ${ALGO_LABEL[e.algorithm]}'s answer: ${e.circles.length} circles, ` +
                    `${e.coverage_percentage}% of the points, in ${s.rounds} rounds.`;
                break;
            }
            s.bestGuess = e.best_guess;
            s.coverage = e.coverage;
            s.j = e.best_guess;
            {
                // Show the gain chart of the winning guess.
                const best = s.guesses.find(g => g.algo === 'greedy' && g.j === e.best_guess);
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
            s.lines = s.algorithm === 'theorem8' ? ['c1'] : [11];
            break;
    }
}

// The MPC view of one round: circles each machine handled, and circles sent to the driver.
// Greedy collects every candidate that clears τ (it then takes the first); the oracle round
// collects every score. Theorem 8's round 1 sends Rᵢ or the top 2k; its round 2 sends nothing.
function roundCost(e) {
    const load = {};
    let sent = 0;
    for (const p of e.partitions) {
        const key = machineKey(p);
        load[key] = (load[key] || 0) + (p.evaluated ?? p.held ?? 0);
        if (!e.central) sent += p.sent_distinct ?? p.sent ?? p.passed ?? 0;
    }
    return { load, sent };
}

// What the page says for each of Theorem 8's rounds: {lines, now} merged into the state.
const TWO_ROUND_TEXT = {
    alg6_r1: e => {
        const held = e.partitions.reduce((a, p) => a + p.held, 0);
        const sent = e.sent_circles ? e.sent_circles.length : 0;
        return {
            lines: ['a3', 'a4', 'a5', 'a6'],
            now: `Algorithm 6, round 1: each Pi takes its share of the ${fmt(held)} circles and, for all ` +
                `${e.guesses} guesses, keeps those that still clear τ_j after G₀. ` +
                `${fmt(sent)} distinct circles go to the central machine.`
        };
    },
    alg6_r2: e => ({
        lines: ['a7'],
        now: `Algorithm 6, round 2: only the central machine (${e.partitions[0].host}) works now, ` +
            `on the ${fmt(e.partitions[0].held)} circles it received. One G per guess:`
    }),
    alg7_r1: e => {
        const held = e.partitions.reduce((a, p) => a + p.held, 0);
        const sent = e.partitions.reduce((a, p) => a + p.sent, 0);
        return {
            circles: [], gains: [], j: null, tau: null, coverage: null,
            lines: ['b1'],
            now: `Algorithm 7, round 1: each Pi scores its circles on their own and sends its ${e.top} best. ` +
                `${fmt(sent)} of ${fmt(held)} circles go to the central machine; the best covers v = ${fmt(e.v)}.`
        };
    },
    alg7_r2: e => ({
        lines: ['b2'],
        now: `Algorithm 7, round 2: the central machine (${e.partitions[0].host}) runs ThresholdGreedy ` +
            `over the ${fmt(e.partitions[0].held)} circles it received, once per guess:`
    })
};

// --- Timeline / playback ---
let timeline = [];
let cursor = -1;          // index of the last applied event
let playing = true;
let replaying = false;    // true while the server sends history after (re)connecting
let timer = null;

const DWELL_MS = {
    ROUND: 500, CIRCLE_ADDED: 750, START_GUESS: 1000, FINAL_SOLUTION: 1500, INIT: 800,
    SAMPLE: 1500, GUESS_RESULT: 1100
};

function speed() { return parseFloat($('pbSpeed').value) || 1; }

function seek(target) {
    target = Math.max(-1, Math.min(timeline.length - 1, target));
    if (target === cursor + 1) {
        cursor = target;
        reduce(state, timeline[cursor], cursor);   // one step forward: let the new circle grow in
    } else {
        state = emptyState();
        for (let i = 0; i <= target; i++) reduce(state, timeline[i], i);
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
    if (e.type === 'FINAL_SOLUTION') rememberRun(e);
    if (!timer) schedule(); else renderPlayback();
    renderRunButton();
}

// --- Last result of each algorithm, to compare them side by side ---
function loadRuns() {
    try { return JSON.parse(localStorage.getItem('lastRuns')) || {}; } catch (e) { return {}; }
}
function rememberRun(final) {
    const init = timeline.find(e => e.type === 'INIT');
    if (!init) return;
    const algorithm = init.config.algorithm || 'greedy';
    const rounds = timeline.filter(e => e.type === 'ROUND')
        .reduce((n, e) => e.round ? Math.max(n, e.round) : n + 1, 0);
    const runs = loadRuns();
    const sent = timeline.filter(e => e.type === 'ROUND').reduce((n, e) => n + roundCost(e).sent, 0);
    runs[algorithm] = {
        coverage: final.coverage, total: final.total_points, rounds, sent,
        elapsed: final.elapsed_s ?? null
    };
    try { localStorage.setItem('lastRuns', JSON.stringify(runs)); } catch (e) { /* comparison is optional */ }
    renderCompare();
}
function renderCompare() {
    const runs = loadRuns();
    const rows = Object.keys(ALGORITHMS).filter(a => runs[a]).map(a => {
        const r = runs[a];
        const time = r.elapsed !== null ? ` · ${fmt(Math.round(r.elapsed))} s` : '';
        return `<div><b>${ALGORITHMS[a].name}</b><span>${fmt(r.coverage)} / ${fmt(r.total)} pts · ` +
            `${r.rounds} round${r.rounds === 1 ? '' : 's'}` +
            `${r.sent !== undefined ? ` · ${fmt(r.sent)} sent` : ''}${time}</span></div>`;
    });
    $('compare').innerHTML = rows.length ? `<div>Last runs</div>${rows.join('')}` : '';
}

// --- Rendering: panels ---
function selectedAlgorithm() {
    return document.querySelector('input[name="algorithm"]:checked').value;
}

// The algorithm on screen: the loaded run's, else the one picked for the next run.
function shownAlgorithm() {
    return state.config ? state.algorithm : selectedAlgorithm();
}

let renderedCode = null;
function renderCode(algorithm) {
    // Keep the switch on the algorithm being shown, so the header never contradicts the page.
    if (state.config) document.querySelector(`input[name="algorithm"][value="${algorithm}"]`).checked = true;
    if (renderedCode === algorithm) return;
    renderedCode = algorithm;
    const a = ALGORITHMS[algorithm];
    $('title').textContent = a.title;
    $('lede').innerHTML = a.lede;
    $('codeTitle').textContent = algorithm === 'theorem8' ? 'Algorithm (Theorem 8)' : 'Algorithm';
    $('code').innerHTML = a.code.map(l => l.head
        ? `<li id="line-${l.id}" class="head">${l.head}</li>`
        : `<li id="line-${l.id}" class="${l.indent ? 'i' + l.indent : ''}">${l.text}` +
          `${l.note ? ` <em>(${l.note})</em>` : ''}</li>`).join('');
    $('gainHint').innerHTML = algorithm === 'theorem8'
        ? 'Bar = gain of each circle of G for this guess, in the order it was added. Grey = from G₀ (the sample). Dashed line = τ<sub>j</sub>.'
        : 'Bar = Δ<i>f</i>(c | S) of the circle added at that step. Dashed line = τ. A circle is taken only if its gain clears τ.';
    $('sSizeLabel').textContent = algorithm === 'theorem8' ? '|G| / k' : '|S| / k';
    $('sCovLabel').textContent = algorithm === 'theorem8' ? 'f(G)' : 'f(S)';
}

function renderPanels() {
    const s = state;
    renderCode(shownAlgorithm());
    $('emptyNote').hidden = s.points.length > 0;
    $('nowLine').textContent = s.now;

    const firstJ = s.algorithm === 'theorem8' ? 1 : 0;
    $('sGuess').textContent = s.j === null ? '–' : s.j;
    $('sGuessTotal').textContent = s.totalGuesses ? ` of ${firstJ}…${firstJ + s.totalGuesses - 1}` : '';
    $('sTau').textContent = fmtTau(s.tau);
    $('sSize').textContent = s.config && (s.algorithm !== 'theorem8' || s.j !== null) ? s.circles.length : '–';
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
        if (s.isFinal && g.algo === s.bestAlgo && g.j === s.bestGuess) cls.push('best');
        else if (!s.isFinal && i === s.guesses.length - 1) cls.push('current');
        const head = g.algo !== 'greedy' && (i === 0 || s.guesses[i - 1].algo !== g.algo)
            ? `<div class="g-head">${ALGO_LABEL[g.algo]}</div>` : '';
        return `${head}<div class="${cls.join(' ')}">
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
    $('roundLabel').textContent = shownAlgorithm() === 'theorem8'
        ? 'Algorithms 6 and 7 share them' : 'one Spark job per pick, about k·log k / ε';
    $('maxLoad').textContent = s.maxLoad ? fmt(s.maxLoad) : '–';
    $('sentTotal').textContent = s.rounds ? fmt(s.sentTotal) : '–';

    if (round) {
        const what = {
            oracle: () => 'scoring every circle on its own to find f(e)',
            threshold: () => `checking Δf(c | S) ≥ τ for pick ${round.step} of guess j = ${s.j}`,
            alg6_r1: () => `Algorithm 6 has every Pi filter its own circles against all ${round.guesses} guesses`,
            alg6_r2: () => 'Algorithm 6 finishes on the central machine alone',
            alg7_r1: () => `Algorithm 7 has every Pi send its ${round.top} circles with the largest f(e)`,
            alg7_r2: () => 'Algorithm 7 finishes on the central machine alone'
        }[round.kind]();
        const times = round.partitions.map(p => p.ms).filter(ms => ms !== undefined);
        const slowest = times.length ? ` Slowest partition took ${fmt(Math.round(Math.max(...times)))} ms.` : '';
        $('roundHint').textContent = `Round ${round.number}: ${what}.${slowest}`;
    } else {
        $('roundHint').textContent = shownAlgorithm() === 'theorem8'
            ? 'In round 1 every Pi works on its own share of the circles at the same time. ' +
              'In round 2 a single central machine combines what they sent.'
            : 'Each round, Spark splits the remaining candidate circles into partitions ' +
              'and the Pis score them at the same time.';
    }

    const total = Object.values(s.machineTotals).reduce((a, b) => a + b, 0);
    $('share').innerHTML = total ? keys.filter(k => s.machineTotals[k]).map(k =>
        `<i style="--c:${colorFor(k)}; flex-grow:${s.machineTotals[k]}"></i>`).join('') : '';
    $('shareCaption').innerHTML = total
        ? (s.algorithm === 'theorem8' ? 'Share of the circles each Pi worked on in round 1: '
            : 'Share of all circle checks so far: ') + keys.filter(k => s.machineTotals[k]).map(k =>
            `${machineLabel(k)} <b>${Math.round(100 * s.machineTotals[k] / total)}%</b>`).join(', ')
        : '';

    if (!keys.length) {
        $('lanes').innerHTML = '<div class="parts-empty">No workers reported yet.</div>';
        return;
    }

    const flash = round && round.seq !== renderedRound;
    renderedRound = round ? round.seq : 0;
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
            if (round.central) {
                return `<div class="part central${flash ? ' flash' : ''}" style="--c:${colorFor(k)}"
                            title="Round 2 runs here only">
                        <span class="pid">central machine</span>
                        <span class="num">${fmt(p.held)} circles received</span>
                    </div>`;
            }
            if (p.held !== undefined) {
                // Theorem 8, round 1: what this partition held and what it sent on.
                const sent = p.sent_distinct ?? p.sent;
                return `<div class="part${flash ? ' flash' : ''}"
                            style="--c:${colorFor(k)}; flex-grow:${Math.max(1, p.held)}"
                            title="Partition ${p.partition}: ${p.held} circles, sent ${p.sent} (${sent} distinct), ${p.ms} ms">
                        <span class="fill" style="height:${p.held ? 100 * Math.min(1, sent / p.held) : 0}%"></span>
                        <span class="pid">p${p.partition}</span>
                        <span class="num">${fmt(p.held)} · ${fmt(sent)} sent</span>
                    </div>`;
            }
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
        }).join('') : `<div class="parts-empty">${round ? 'Idle this round.' : 'Idle.'}</div>`;

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
    const s = state;
    const two = s.algorithm === 'theorem8';
    const keys = [...new Set([...s.circles, ...s.background].map(c => c.machine).filter(Boolean))];
    let html = keys.map(k => `<span><i class="swatch" style="--c:${colorFor(k)}"></i>` +
        (k === SAMPLE ? 'from the sample S' : `${two ? 'sent by' : 'found by'} ${machineLabel(k)}`) + '</span>').join('');
    if (s.isFinal) html = `<span><i class="swatch" style="--c:${C.ink}"></i>best solution</span>`;
    $('legend').innerHTML = html;
    const winner = two ? `${ALGO_LABEL[s.bestAlgo]}, guess j = ${s.bestGuess}` : `guess j = ${s.bestGuess}`;
    $('caption').textContent = s.isFinal
        ? `Final answer from ${winner}. Covered points are drawn stronger.`
        : two
            ? [s.backgroundNote, s.circles.length ? 'Solid circles: G for this guess.' : '',
               'Covered points are drawn stronger.'].filter(Boolean).join(' ')
            : 'Each circle is coloured by the Pi whose partition found it. Covered points are drawn stronger.';
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
    drawRoundStrip();
    renderChapters();
}

// --- Chapters: the moments worth stopping at in a lecture ---
function chapterLabel(e) {
    switch (e.type) {
        case 'SAMPLE': return 'Sample S';
        case 'START_GUESS': return `j = ${e.value}`;
        case 'FINAL_SOLUTION': return 'Result';
        case 'ROUND':
            return {
                oracle: 'f(e)', alg6_r1: 'Alg 6 · round 1', alg6_r2: 'Alg 6 · round 2',
                alg7_r1: 'Alg 7 · round 1', alg7_r2: 'Alg 7 · round 2'
            }[e.kind] || null;
    }
    return null;
}

function chapterList() {
    return timeline.map((e, i) => ({ i, label: chapterLabel(e) })).filter(c => c.label);
}

let renderedChapters = '';
function renderChapters() {
    const list = chapterList();
    const key = list.map(c => c.i).join(',') + '|' + cursor;
    if (key === renderedChapters) return;
    renderedChapters = key;
    const current = list.filter(c => c.i <= cursor).pop();
    $('chapters').innerHTML = list.map(c =>
        `<button data-i="${c.i}" class="${current && c.i === current.i ? 'on' : ''}">${c.label}</button>`).join('');
    const span = Math.max(1, timeline.length - 1);
    $('chapterTicks').innerHTML = list.map(c => `<i style="left:${100 * c.i / span}%"></i>`).join('');
}

function jumpChapter(dir) {
    const list = chapterList();
    const target = dir > 0 ? list.find(c => c.i > cursor) : list.filter(c => c.i < cursor).pop();
    setPlaying(false);
    seek(target ? target.i : (dir > 0 ? timeline.length - 1 : -1));
}

$('chapters').addEventListener('click', e => {
    const b = e.target.closest('button[data-i]');
    if (b) { setPlaying(false); seek(Number(b.dataset.i)); }
});

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
    const maxR = Math.max(0, ...s.circles.map(c => c.r), ...s.background.map(c => c.r));
    const scale = Math.min(w / (rangeX + 2 * maxR), h / (rangeY + 2 * maxR), w / rangeX * 0.94, h / rangeY * 0.94);
    const ox = (w - rangeX * scale) / 2, oy = (h - rangeY * scale) / 2;
    const X = x => ox + (x - b.minX) * scale;
    const Y = y => oy + (y - b.minY) * scale;

    ctx.strokeStyle = C.rule;
    ctx.lineWidth = 1;
    ctx.strokeRect(X(b.minX), Y(b.minY), rangeX * scale, rangeY * scale);

    const flags = coveredFlags();
    const pr = s.points.length > 3000 ? 1.1 : 1.6;
    for (const covered of [false, true]) {
        ctx.fillStyle = covered ? C.pointCovered : C.point;
        ctx.beginPath();
        s.points.forEach(([x, y], i) => {
            if (flags[i] !== covered) return;
            ctx.moveTo(X(x) + pr, Y(y));
            ctx.arc(X(x), Y(y), pr, 0, Math.PI * 2);
        });
        ctx.fill();
    }

    // Faint context circles (sample S / what round 1 sent) under everything else.
    ctx.lineWidth = 1;
    s.background.forEach(c => {
        ctx.beginPath();
        ctx.arc(X(c.cx), Y(c.cy), c.r * scale, 0, Math.PI * 2);
        ctx.strokeStyle = hexAlpha(c.machine ? colorFor(c.machine) : C.muted, 0.35);
        ctx.stroke();
    });

    s.circles.forEach((c, i) => {
        if (c.animR < c.r) c.animR = Math.abs(c.r - c.animR) < 0.5 ? c.r : c.animR + (c.r - c.animR) * 0.12;
        const color = c.machine ? colorFor(c.machine) : C.ink;
        const newest = !s.isFinal && s.algorithm !== 'theorem8' && i === s.circles.length - 1;
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
    const maxV = Math.max(tau * 1.25, ...s.gains.map(g => g.gain), 10);
    const step = niceStep(maxV / 4);
    const top = Math.ceil(maxV / step) * step;
    const Y = v => pad.t + ih - (v / top) * ih;

    ctx.font = '11px "IBM Plex Mono", monospace';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';
    for (let v = 0; v <= top + 1e-9; v += step) {
        ctx.strokeStyle = v === 0 ? C.ruleStrong : C.rule;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.l, Math.round(Y(v)) + 0.5);
        ctx.lineTo(w - pad.r, Math.round(Y(v)) + 0.5);
        ctx.stroke();
        ctx.fillStyle = C.muted;
        ctx.fillText(fmt(Math.round(v)), pad.l - 6, Y(v));
    }

    const slot = iw / k;
    const bw = Math.min(28, slot * 0.6);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (let i = 0; i < k; i++) {
        ctx.fillStyle = C.muted;
        ctx.fillText(String(i + 1), pad.l + slot * (i + 0.5), h - pad.b + 6);
    }
    {
        s.gains.forEach(g => {
            const x = pad.l + slot * (g.step - 0.5) - bw / 2;
            ctx.fillStyle = g.machine ? colorFor(g.machine) : C.ink;
            ctx.fillRect(x, Y(g.gain), bw, Y(0) - Y(g.gain));
        });
    }

    if (tau) {
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = C.ink;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(pad.l, Y(tau));
        ctx.lineTo(w - pad.r, Y(tau));
        ctx.stroke();
        ctx.setLineDash([]);
        // Label on a paper-coloured tab so bars behind it don't make it unreadable.
        const label = `τ = ${fmtTau(tau)}`;
        const lw = ctx.measureText(label).width + 8;
        ctx.fillStyle = C.surface;
        ctx.fillRect(w - pad.r - lw, Y(tau) - 17, lw, 14);
        ctx.fillStyle = C.ink;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(label, w - pad.r - 4, Y(tau) - 4);
    }

    if (!s.gains.length) {
        ctx.fillStyle = C.muted;
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

// --- Round strip: one column per Spark job / round, stacked by machine ---
// Built from the whole timeline so the layout stays put while stepping; rounds after the
// playhead are drawn as outlines, so the class sees how many are still to come.
const stripCanvas = $('roundStrip');
let stripColumns = [];   // [{x, w, index}] for click-to-seek

function drawRoundStrip() {
    stripColumns = drawStrip(stripCanvas, timeline, cursor, { mark: state.lastRound?.timelineIndex });
}

// Draws events' rounds on canvas; rounds after index `upto` as outlines. With `slots`, every
// column gets the width of 1/slots of the canvas, so two strips can share one scale.
function drawStrip(canvas, events, upto, { mark = null, slots = null } = {}) {
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const rounds = [];
    let guess = null;
    events.forEach((e, i) => {
        if (e.type === 'START_GUESS') guess = e.value;
        if (e.type === 'ROUND') rounds.push({ e, i, guess, cost: roundCost(e) });
    });
    const columns = [];
    if (!rounds.length) {
        ctx.fillStyle = C.muted;
        ctx.font = '13px "IBM Plex Sans", sans-serif';
        ctx.textBaseline = 'middle';
        ctx.fillText('Each round of the run will appear here as a column.', 0, h / 2);
        return columns;
    }
    const two = rounds.some(r => r.e.round);
    const labelH = 18;
    const top = 6, base = h - labelH;
    const n = slots || rounds.length;
    const gap = n > 60 ? 1 : 4;
    const colW = Math.max(2, Math.min(slots ? Infinity : (two ? 90 : 26), (w - gap * (n - 1)) / n));
    const maxTotal = Math.max(1, ...rounds.map(r => Object.values(r.cost.load).reduce((a, b) => a + b, 0)));
    const Y = v => (v / maxTotal) * (base - top);

    ctx.font = '11px "IBM Plex Mono", monospace';
    ctx.textBaseline = 'top';
    let lastGuess = undefined;
    let lastLabelX = -Infinity;
    rounds.forEach((r, k) => {
        const x = k * (colW + gap);
        const done = r.i <= upto;
        columns.push({ x, w: colW + gap, index: r.i });
        let y = base;
        Object.entries(r.cost.load).forEach(([key, v]) => {
            const hgt = Math.max(1, Y(v));
            y -= hgt;
            const color = colorFor(key);
            if (r.e.central) {
                ctx.setLineDash([3, 2]);
                ctx.strokeStyle = done ? color : hexAlpha(color, 0.35);
                ctx.strokeRect(x + 0.5, y + 0.5, colW - 1, hgt - 1);
                ctx.setLineDash([]);
            } else if (done) {
                ctx.fillStyle = color;
                ctx.fillRect(x, y, colW, hgt);
            } else {
                ctx.strokeStyle = hexAlpha(color, 0.35);
                ctx.strokeRect(x + 0.5, y + 0.5, colW - 1, hgt - 1);
            }
        });
        if (r.i === mark) {
            ctx.fillStyle = C.ink;
            ctx.fillRect(x, base + 2, colW, 2);
        }
        // Labels: Theorem 8 names each round; greedy marks where each guess starts.
        ctx.fillStyle = C.muted;
        if (two) {
            ctx.textAlign = 'center';
            const label = `${r.e.algo === 'alg6' ? 'Alg 6' : 'Alg 7'} · R${r.e.round}`;
            if (colW > 50) ctx.fillText(label, x + colW / 2, base + 5);
        } else if (r.guess !== lastGuess && r.guess !== null && r.guess !== undefined) {
            ctx.textAlign = 'left';
            ctx.fillRect(x, base + 2, 1, 6);
            if (x - lastLabelX > 38) {
                ctx.fillText(`j=${r.guess}`, x + 2, base + 5);
                lastLabelX = x;
            }
        }
        lastGuess = r.guess;
    });
    return columns;
}

stripCanvas.addEventListener('click', ev => {
    const x = ev.clientX - stripCanvas.getBoundingClientRect().left;
    const col = stripColumns.find(c => x >= c.x && x < c.x + c.w);
    if (col) { setPlaying(false); seek(col.index); }
});
window.addEventListener('resize', drawRoundStrip);

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
// Keys: space play/pause, ← → step, [ ] or PageUp/PageDown (presentation clickers) jump a
// chapter, P present, C compare, Esc close.
document.addEventListener('keydown', e => {
    if (e.target.closest('input, select')) return;
    if (e.key === 'Escape') { setPresenting(false); showCompare(false); return; }
    if (e.key === ' ') { e.preventDefault(); $('pbPlay').click(); }
    else if (e.key === 'ArrowRight') $('pbFwd').click();
    else if (e.key === 'ArrowLeft') $('pbBack').click();
    else if (e.key === ']' || e.key === 'PageDown') { e.preventDefault(); jumpChapter(1); }
    else if (e.key === '[' || e.key === 'PageUp') { e.preventDefault(); jumpChapter(-1); }
    else if (e.key === 'p' || e.key === 'P') setPresenting(!document.documentElement.classList.contains('presenting'));
    else if (e.key === 'c' || e.key === 'C') showCompare($('compareView').hidden);
});

// --- Presenter mode ---
function setPresenting(on) {
    document.documentElement.classList.toggle('presenting', on);
    try {
        if (on && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
        if (!on && document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    } catch (e) { /* fullscreen is optional */ }
    requestAnimationFrame(renderPanels);   // canvases resize with the layout
}
$('presentBtn').addEventListener('click', () => setPresenting(true));
$('exitPresent').addEventListener('click', () => setPresenting(false));
document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) setPresenting(false);
});

// --- Side-by-side comparison of the latest run of each algorithm ---
function summarizeRun(events) {
    const init = events.find(e => e.type === 'INIT');
    const final = events.find(e => e.type === 'FINAL_SOLUTION');
    if (!init || !final) return null;
    const rounds = events.filter(e => e.type === 'ROUND');
    return {
        events, init, final,
        rounds: rounds.reduce((n, e) => e.round ? Math.max(n, e.round) : n + 1, 0),
        jobs: rounds.filter(e => !e.central).length,
        sent: rounds.reduce((n, e) => n + roundCost(e).sent, 0),
        maxLoad: Math.max(0, ...rounds.map(e => Math.max(...Object.values(roundCost(e).load))))
    };
}

function drawMiniFigure(canvas, run) {
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const b = run.init.bounds, circles = run.final.circles;
    const pad = 110;   // room for circles near the edge
    const scale = Math.min(w / (b.maxX - b.minX + 2 * pad), h / (b.maxY - b.minY + 2 * pad));
    const X = x => (w - (b.maxX - b.minX) * scale) / 2 + (x - b.minX) * scale;
    const Y = y => (h - (b.maxY - b.minY) * scale) / 2 + (y - b.minY) * scale;
    for (const [x, y] of run.init.points) {
        const covered = circles.some(c => (x - c.cx) ** 2 + (y - c.cy) ** 2 <= c.r * c.r);
        ctx.fillStyle = covered ? C.pointCovered : C.point;
        ctx.fillRect(X(x) - 1, Y(y) - 1, 2, 2);
    }
    ctx.strokeStyle = C.ink;
    ctx.lineWidth = 1.6;
    for (const c of circles) {
        ctx.beginPath();
        ctx.arc(X(c.cx), Y(c.cy), c.r * scale, 0, Math.PI * 2);
        ctx.fillStyle = hexAlpha(C.ink, 0.06);
        ctx.fill();
        ctx.stroke();
    }
}

async function showCompare(on) {
    $('compareView').hidden = !on;
    if (!on) return;
    let runs = {};
    try { runs = await (await fetch('/runs')).json(); } catch (e) { /* shown as missing below */ }
    const summaries = Object.fromEntries(Object.keys(ALGORITHMS).map(a => [a, runs[a] ? summarizeRun(runs[a]) : null]));
    const slots = Math.max(1, ...Object.values(summaries).filter(Boolean)
        .map(r => r.events.filter(e => e.type === 'ROUND').length));

    $('cvCols').innerHTML = Object.keys(ALGORITHMS).map(a => {
        const r = summaries[a];
        if (!r) {
            return `<div class="cv-col"><h3>${ALGORITHMS[a].title}</h3>
                <p class="cv-empty">No finished run yet. Pick “${ALGORITHMS[a].name}” and press Run on cluster.</p></div>`;
        }
        const pct = r.final.coverage_percentage;
        const time = r.final.elapsed_s != null ? `${fmt(Math.round(r.final.elapsed_s))} s` : '–';
        return `<div class="cv-col">
            <h3>${ALGORITHMS[a].title}</h3>
            <canvas class="cv-fig" id="cvFig-${a}"></canvas>
            <dl>
                <div><dt>Points covered</dt><dd>${fmt(r.final.coverage)} <small>(${pct}%)</small></dd></div>
                <div><dt>Rounds</dt><dd>${fmt(r.rounds)}</dd></div>
                <div><dt>Wall time</dt><dd>${time}</dd></div>
                <div><dt>Spark jobs</dt><dd>${fmt(r.jobs)}</dd></div>
                <div><dt>Sent to driver</dt><dd>${fmt(r.sent)}</dd></div>
                <div><dt>Most on one machine</dt><dd>${fmt(r.maxLoad)}</dd></div>
            </dl>
            <canvas class="cv-strip" id="cvStrip-${a}"></canvas>
        </div>`;
    }).join('');

    const g = summaries.greedy, t = summaries.theorem8;
    // Like-for-like only if both runs drew the same points (same size, same generator).
    const same = g && t && g.final.total_points === t.final.total_points &&
        g.init.config.n_circles === t.init.config.n_circles &&
        JSON.stringify(g.init.points.slice(0, 50)) === JSON.stringify(t.init.points.slice(0, 50));
    $('cvLede').textContent = g && t && !same
        ? 'These two runs used different inputs, so they are not comparable. Run both on the same dataset size.'
        : g && t
        ? `Same input: ${fmt(g.final.total_points)} points and ${fmt(g.init.config.n_circles)} candidate circles. ` +
          `Theorem 8 needs ${t.rounds} rounds where threshold greedy needs ${fmt(g.rounds)}, and covers ` +
          `${fmt(t.final.coverage)} points against ${fmt(g.final.coverage)}. Both strips use the same scale: ` +
          `one column per Spark job.`
        : 'The latest finished run of each algorithm. Run both to compare them.';

    for (const a of Object.keys(ALGORITHMS)) {
        const r = summaries[a];
        if (!r) continue;
        drawMiniFigure($(`cvFig-${a}`), r);
        drawStrip($(`cvStrip-${a}`), r.events, r.events.length, { slots });
    }
}
$('compareBtn').addEventListener('click', () => showCompare(true));
$('cvClose').addEventListener('click', () => showCompare(false));
$('compareView').addEventListener('click', e => { if (e.target === $('compareView')) showCompare(false); });

// --- Theme ---
function renderThemeButton() {
    $('themeBtn').textContent = document.documentElement.dataset.theme === 'dark' ? 'Light' : 'Dark';
}
$('themeBtn').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) { /* private mode: still switches */ }
    readPalette();
    renderThemeButton();
    renderPanels();
});
renderThemeButton();

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
            body: JSON.stringify({ size, algorithm: selectedAlgorithm() })
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
        // main.py runs as "CircleCover", alg.py as "CircleCoverMR"
        const mine = (data.activeapps || []).find(a => a.name.startsWith('CircleCover'));
        appState = mine ? mine.state : null;
    } catch (e) {
        clusterWorkers = [];
        appState = null;
    }
    renderCluster();
    renderRunButton();
}

document.querySelectorAll('input[name="algorithm"]').forEach(r => r.addEventListener('change', () => {
    // Only retitle the page when no run is loaded; a loaded run keeps its own algorithm.
    if (!state.config) renderPanels();
}));

renderPanels();
renderCompare();
renderRunButton();
requestAnimationFrame(frame);
connect();
pollCluster();
setInterval(pollCluster, 3000);
