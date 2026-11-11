// Circle cover demo UI.
//
// main.py feeds it, running one of the algorithms: threshold greedy (one Spark job per pick),
// Theorem 8 (Algorithms 6 and 7, two MapReduce rounds) or Algorithm 5. Every event they send
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
            'split across the Raspberry Pis, so the number of rounds grows with <i>k</i>. ' +
            'Each pick needs the one before it, so the rounds run one after another, and every round pays a ' +
            'fixed cost (scheduling the job, sending S to every Pi, waiting for the slowest) that more Pis do not ' +
            'shrink. That comes from the algorithm, not from Spark: the 2-round algorithms exist to avoid it. ' +
            'Guarantee: ½(1 − ε) of OPT.',
        code: [
            { id: 1, text: 'f(e) ← max single-circle coverage', note: '1 Spark job' },
            { id: 2, text: 'y ← ⌈log k / log(1+ε)⌉' },
            { id: 3, text: 'for j = 0 … y:' },
            { id: 4, text: 'τ ← (1+ε)<sup>j</sup> · f(e) / 2k', indent: 1 },
            { id: 5, text: 'S ← ∅', indent: 1 },
            { id: 6, text: 'while |S| &lt; k:', indent: 1 },
            { id: 7, text: 'find any c with Δf(c | S) ≥ τ', indent: 2, note: '1 Spark job' },
            { id: 8, text: 'if found:', indent: 2 },
            { id: '8b', text: 'S ← S ∪ {c}', indent: 3 },
            { id: 9, text: 'else:', indent: 2 },
            { id: '9b', text: 'stop this guess', indent: 3 },
            { id: 10, text: 'keep S if f(S) is the best so far', indent: 1 },
            { id: 11, text: 'return best S' }
        ]
    },
    theorem8: {
        name: '2 rounds (Thm 8)',
        title: 'Circle cover in two MapReduce rounds',
        lede: 'Liu &amp; Vondrák, Theorem 8: Algorithm 6 handles dense inputs and Algorithm 7 sparse ones. ' +
            'Run both and keep the better answer. Each Pi filters its own share of the circles in round 1, ' +
            'and one central machine finishes in round 2, however large the input. Guarantee: ½ − ε of OPT.',
        code: [
            { id: 'h6', head: 'Algorithm 6, dense inputs' },
            { id: 'a1', text: 'S ← sample of V, each circle w.p. 4√(k/n)' },
            { id: 'a1b', text: 'copy S to every machine' },
            { id: 'a2', text: 'v ← max<sub>e∈S</sub> f(e)' },
            { id: 'a3', text: 'round 1, on every machine i, for every guess j:', note: '1 Spark job' },
            { id: 'a4', text: 'τ<sub>j</sub> ← v(1+ε)<sup>j</sup> / k', indent: 1 },
            { id: 'a5', text: 'G₀ ← ThresholdGreedy(S, ∅, τ<sub>j</sub>)', indent: 1 },
            { id: 'a6', text: 'if |G₀| &lt; k:', indent: 1 },
            { id: 'a6b', text: 'send R<sub>i</sub> ← ThresholdFilter(V<sub>i</sub>, G₀, τ<sub>j</sub>)', indent: 2 },
            { id: 'a7', text: 'round 2, on the central machine, for every j:' },
            { id: 'a8', text: 'G ← ThresholdGreedy(∪<sub>i</sub> R<sub>i</sub>, G₀, τ<sub>j</sub>)', indent: 1 },
            { id: 'h7', head: 'Algorithm 7, sparse inputs' },
            { id: 'b1', text: 'round 1: every machine sends its 2k circles with the largest f(e)', note: '1 Spark job' },
            { id: 'b2', text: 'round 2, on the central machine, for every j:' },
            { id: 'b2b', text: 'G<sub>j</sub> ← ThresholdGreedy(S, ∅, τ<sub>j</sub>)', indent: 1 },
            { id: 'h8', head: 'Theorem 8' },
            { id: 'c1', text: 'return the better of the two answers (2 rounds in total)' }
        ]
    },
    alg5: {
        name: '2t + 2 rounds (Alg 5)',
        title: 'Circle cover in 2t + 2 MapReduce rounds',
        lede: 'Liu &amp; Vondrák, Algorithm 5: t thresholds, each costing two rounds (the Pis filter, the central ' +
            'machine extends every solution), plus one round to estimate OPT and one to pick the best. ' +
            'More rounds buy a better guarantee: 1 − (1 − 1/(t+1))<sup>t</sup> of OPT, which is ½ for t = 1, ' +
            '5/9 for t = 2, and tends to 1 − 1/e.',
        code: [
            { id: 'd1', text: 'round 1: v ← max<sub>e∈V</sub> f(e)', note: '1 Spark job' },
            { id: 'd1b', text: 'estimates OPT<sub>g</sub> ← v(1+ε)<sup>g</sup>' },
            { id: 'd2', text: 'for l = 1 … t:' },
            { id: 'd3', text: 'round 2l: S ← new random sample of V', indent: 1, note: '1 Spark job' },
            { id: 'd3b', text: 'on every machine i, for every g:', indent: 1 },
            { id: 'd4', text: 'α<sub>l</sub> ← (1 − 1/(t+1))<sup>l</sup> · OPT<sub>g</sub> / k', indent: 2 },
            { id: 'd5', text: 'G₀ ← ThresholdGreedy(S, G<sub>g</sub>, α<sub>l</sub>)', indent: 2 },
            { id: 'd5b', text: 'send R<sub>i</sub> ← ThresholdFilter(V<sub>i</sub>, G₀, α<sub>l</sub>)', indent: 2 },
            { id: 'd6', text: 'round 2l + 1, on the central machine, for every g:', indent: 1 },
            { id: 'd6b', text: 'G<sub>g</sub> ← ThresholdGreedy(∪<sub>i</sub> R<sub>i</sub>, G₀, α<sub>l</sub>)', indent: 2 },
            { id: 'd7', text: 'round 2t + 2: return the best G<sub>g</sub>' }
        ]
    }
};
// Plain-text subscript digits, for text set with textContent (α_1 -> α₁)
const subscript = n => String(n).replace(/\d/g, d => '₀₁₂₃₄₅₆₇₈₉'[d]);
const ALGO_LABEL = { alg6: 'Algorithm 6', alg7: 'Algorithm 7', alg5: 'Algorithm 5' };
const FIRST_LINE = { greedy: [1], theorem8: ['a1', 'a1b'], alg5: ['d1', 'd1b'] };
const LAST_LINE = { greedy: [11], theorem8: ['c1'], alg5: ['d7'] };
// The MapReduce algorithms build one solution G per guess; greedy grows a single S.
const isMapReduce = a => a !== 'greedy';

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
            s.t = e.config.t || null;
            s.lines = FIRST_LINE[s.algorithm];
            s.now = `${fmt(total)} points and ${fmt(e.config.n_circles)} candidate circles generated. ` +
                (s.algorithm === 'theorem8' ? 'Algorithm 6 starts by sampling the circles.'
                    : 'First, find the best single circle.');
            break;
        }
        case 'SAMPLE': {
            s.background = e.circles.map(c => ({ ...c, machine: SAMPLE }));
            s.backgroundNote = 'Faint grey circles: the sample S, copied to every machine.';
            s.fe = e.v;
            if (e.algo === 'alg5') {
                s.lines = ['d2', 'd3'];
                s.circles = []; s.gains = []; s.j = null; s.tau = null; s.coverage = null;
                s.now = `Threshold l = ${e.l} of ${s.t}: a fresh random sample S of ${fmt(e.circles.length)} ` +
                    `circles is copied to every machine.`;
                break;
            }
            s.lines = ['a1', 'a1b', 'a2'];
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
                s.lines = [9, '9b'];
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
            s.guesses.push({ algo: e.algo, l: e.l, j: e.j, tau: e.threshold, picks: e.circles.length,
                             coverage: e.coverage, gains: s.gains });
            if (e.algo === 'alg5') {
                const fromSample = e.g0 - e.kept, fromPis = e.circles.length - e.g0;
                s.lines = ['d6', 'd6b'];
                s.now = `Round ${2 * e.l + 1}, estimate g = ${e.j} (α = ${fmtTau(e.threshold)}): ` +
                    `${e.kept} circle${e.kept === 1 ? '' : 's'} kept from earlier thresholds, ` +
                    `${fromSample} added from the sample and ${fromPis} from what the Pis sent. ` +
                    `f(G) = ${fmt(e.coverage)}.`;
                break;
            }
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
                s.lines = ['b2', 'b2b'];
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
            s.lines = [8, '8b'];
            s.now = `Pick ${e.step}: gain Δf = ${fmt(e.gain)} ≥ τ, so the circle joins S. f(S) = ${fmt(e.coverage)}.`;
            break;
        }
        case 'FINAL_SOLUTION':
            s.circles = e.circles.map((c, i) => ({ ...c, step: i + 1, machine: null, animR: 0 }));
            s.isFinal = true;
            s.background = [];
            if (s.algorithm === 'alg5') {
                // Only the solutions after the last threshold count; the algorithm picks the first best.
                const best = s.guesses.find(g => g.algo === 'alg5' && g.l === s.t && g.j === e.best_guess);
                s.bestAlgo = 'alg5';
                s.bestGuess = e.best_guess;
                s.j = e.best_guess;
                if (best) { s.tau = best.tau; s.gains = best.gains; }
                s.coverage = e.coverage;
                s.lines = ['d7'];
                s.now = `After t = ${s.t} thresholds and ${2 * s.t + 2} rounds, estimate g = ${e.best_guess} is best: ` +
                    `${e.circles.length} circles cover ${fmt(e.coverage)} of ${fmt(e.total_points)} points ` +
                    `(${e.coverage_percentage}%).`;
                break;
            }
            if (s.algorithm === 'theorem8') {
                // The winner's best guess: the first one with the highest coverage, as the algorithm picks it.
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
            s.lines = LAST_LINE[s.algorithm];
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
    alg5_r0: e => ({
        lines: ['d1', 'd1b'],
        now: `Round 1: every Pi finds its best single circle; the best of those covers v = ${fmt(e.v)}. ` +
            `OPT lies between v and k·v, so the algorithm keeps one solution per estimate v(1+ε)^g.`
    }),
    alg5_filter: e => {
        const held = e.partitions.reduce((a, p) => a + p.held, 0);
        const sent = e.sent_circles ? e.sent_circles.length : 0;
        return {
            lines: ['d3', 'd3b', 'd4', 'd5', 'd5b'],
            now: `Round ${e.round}: each Pi takes its share of the ${fmt(held)} circles and, for all ` +
                `${e.estimates} estimates, keeps those that still clear α${subscript(e.l)} after G₀. ` +
                `${fmt(sent)} distinct circles go to the central machine.`
        };
    },
    alg5_central: e => ({
        lines: ['d6', 'd6b'],
        now: `Round ${e.round}: only the central machine (${e.partitions[0].host}) works, extending every ` +
            `estimate's solution with the ${fmt(e.partitions[0].held)} circles it received:`
    }),
    alg5_final: e => ({
        lines: ['d7'],
        now: `Round ${e.round}: the central machine compares the ${e.partitions[0].held} solutions and keeps the best.`
    }),
    alg6_r1: e => {
        const held = e.partitions.reduce((a, p) => a + p.held, 0);
        const sent = e.sent_circles ? e.sent_circles.length : 0;
        return {
            lines: ['a3', 'a4', 'a5', 'a6', 'a6b'],
            now: `Algorithm 6, round 1: each Pi takes its share of the ${fmt(held)} circles and, for all ` +
                `${e.guesses} guesses, keeps those that still clear τⱼ after G₀. ` +
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
        lines: ['b2', 'b2b'],
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

function selectedT() {
    return Number($('tSelect').value) || 2;
}

// The algorithm on screen: the loaded run's, else the one picked for the next run.
function shownAlgorithm() {
    return state.config ? state.algorithm : selectedAlgorithm();
}

let renderedCode = null;
function renderCode(algorithm) {
    // Keep the switch on the algorithm being shown, so the header never contradicts the page.
    if (state.config) {
        document.querySelector(`input[name="algorithm"][value="${algorithm}"]`).checked = true;
        if (state.t) $('tSelect').value = String(state.t);
        // and the size picker on the input being shown (dataset is "size/seed/std")
        const size = (state.config.dataset || '').split('/')[0];
        const sizeInput = document.querySelector(`input[name="jobSize"][value="${size}"]`);
        if (sizeInput) sizeInput.checked = true;
        renderTPicker();
    }
    const t = state.config ? state.t : selectedT();
    if (renderedCode === algorithm + t) return;
    renderedCode = algorithm + t;
    const a = ALGORITHMS[algorithm];
    $('title').textContent = a.title;
    $('lede').innerHTML = a.lede;
    $('codeTitle').textContent = { greedy: 'Algorithm', theorem8: 'Algorithm (Theorem 8)',
                                   alg5: `Algorithm 5, t = ${t}` }[algorithm];
    $('code').innerHTML = a.code.map(l => l.head
        ? `<li id="line-${l.id}" class="head">${l.head}</li>`
        : `<li id="line-${l.id}" class="${l.indent ? 'i' + l.indent : ''}">${l.text}` +
          `${l.note ? ` <em>(${l.note})</em>` : ''}</li>`).join('');
    $('gainHint').innerHTML = algorithm === 'alg5'
        ? 'Bar = gain of each circle of G for this estimate, in the order it was added. Grey = from a sample S. Dashed line = α<sub>l</sub>.'
        : algorithm === 'theorem8'
        ? 'Bar = gain of each circle of G for this guess, in the order it was added. Grey = from G₀ (the sample). Dashed line = τ<sub>j</sub>.'
        : 'Bar = Δ<i>f</i>(c | S) of the circle added at that step. Dashed line = τ. A circle is taken only if its gain clears τ.';
    $('sSizeLabel').textContent = isMapReduce(algorithm) ? '|G| / k' : '|S| / k';
    $('sCovLabel').textContent = isMapReduce(algorithm) ? 'f(G)' : 'f(S)';
    $('sGuessLabel').textContent = algorithm === 'alg5' ? 'Estimate g' : 'Guess j';
    $('sTauLabel').textContent = algorithm === 'alg5' ? 'Threshold α' : 'Threshold τ';
}

function renderPanels() {
    const s = state;
    renderCode(shownAlgorithm());
    $('emptyNote').hidden = s.points.length > 0;
    $('nowLine').textContent = s.now;

    const firstJ = s.algorithm === 'theorem8' ? 1 : 0;   // algorithms/alg6.py and alg7.py number Theorem 8's guesses from 1
    $('sGuess').textContent = s.j === null ? '–' : s.j;
    $('sGuessTotal').textContent = s.totalGuesses ? ` of ${firstJ}…${firstJ + s.totalGuesses - 1} (${s.totalGuesses})` : '';
    $('sTau').textContent = fmtTau(s.tau);
    $('sSize').textContent = s.config && (!isMapReduce(s.algorithm) || s.j !== null) ? s.circles.length : '–';
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
        if (s.isFinal && g.algo === s.bestAlgo && g.j === s.bestGuess && (g.algo !== 'alg5' || g.l === s.t)) cls.push('best');
        else if (!s.isFinal && i === s.guesses.length - 1) cls.push('current');
        const group = x => x.algo === 'alg5' ? `Threshold l = ${x.l}` : ALGO_LABEL[x.algo];
        const head = g.algo !== 'greedy' && (i === 0 || group(s.guesses[i - 1]) !== group(g))
            ? `<div class="g-head">${group(g)}</div>` : '';
        return `${head}<div class="${cls.join(' ')}">
            <span>${g.algo === 'alg5' ? 'g' : 'j'}=${g.j}</span>
            <span>${g.algo === 'alg5' ? 'α' : 'τ'}=${fmtTau(g.tau)}</span>
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
    $('roundLabel').textContent = {
        greedy: 'one Spark job per pick, about k·log k / ε',
        theorem8: 'Algorithms 6 and 7 share them',
        alg5: `2t + 2 = ${2 * (s.t || selectedT()) + 2} for t = ${s.t || selectedT()}`
    }[shownAlgorithm()];
    $('maxLoad').textContent = s.maxLoad ? fmt(s.maxLoad) : '–';
    $('sentTotal').textContent = s.rounds ? fmt(s.sentTotal) : '–';

    if (round) {
        const what = {
            oracle: () => 'scoring every circle on its own to find f(e)',
            threshold: () => `checking Δf(c | S) ≥ τ for pick ${round.step} of guess j = ${s.j}`,
            alg6_r1: () => `Algorithm 6 has every Pi filter its own circles against all ${round.guesses} guesses`,
            alg6_r2: () => 'Algorithm 6 finishes on the central machine alone',
            alg7_r1: () => `Algorithm 7 has every Pi send its ${round.top} circles with the largest f(e)`,
            alg7_r2: () => 'Algorithm 7 finishes on the central machine alone',
            alg5_r0: () => 'every Pi scores its circles on their own to estimate OPT',
            alg5_filter: () => `threshold l = ${round.l}: every Pi filters its circles for all ${round.estimates} estimates`,
            alg5_central: () => `threshold l = ${round.l}: the central machine extends every solution`,
            alg5_final: () => 'the central machine keeps the best solution'
        }[round.kind]();
        const times = round.partitions.map(p => p.ms).filter(ms => ms !== undefined);
        const slowest = times.length ? ` Slowest partition took ${fmt(Math.round(Math.max(...times)))} ms.` : '';
        $('roundHint').textContent = `Round ${round.number}: ${what}.${slowest}`;
    } else {
        $('roundHint').textContent = isMapReduce(shownAlgorithm())
            ? 'In round 1 every Pi works on its own share of the circles at the same time. ' +
              'In round 2 a single central machine combines what they sent.'
            : 'Each round, Spark splits the remaining candidate circles into partitions ' +
              'and the Pis score them at the same time.';
    }

    const total = Object.values(s.machineTotals).reduce((a, b) => a + b, 0);
    $('share').innerHTML = total ? keys.filter(k => s.machineTotals[k]).map(k =>
        `<i style="--c:${colorFor(k)}; flex-grow:${s.machineTotals[k]}"></i>`).join('') : '';
    $('shareCaption').innerHTML = total
        ? (isMapReduce(s.algorithm) ? 'Share of the circles each Pi worked on in the parallel rounds: '
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
                            style="--c:${colorFor(k)}"
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
                        style="--c:${colorFor(k)}"
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
    const two = isMapReduce(s.algorithm);
    const keys = [...new Set([...s.circles, ...s.background].map(c => c.machine).filter(Boolean))];
    let html = keys.map(k => `<span><i class="swatch" style="--c:${colorFor(k)}"></i>` +
        (k === SAMPLE ? 'from the sample S' : `${two ? 'sent by' : 'found by'} ${machineLabel(k)}`) + '</span>').join('');
    if (s.isFinal) html = `<span><i class="swatch" style="--c:${C.ink}"></i>best solution</span>`;
    $('legend').innerHTML = html;
    const winner = s.algorithm === 'alg5' ? `estimate g = ${s.bestGuess}`
        : two ? `${ALGO_LABEL[s.bestAlgo]}, guess j = ${s.bestGuess}` : `guess j = ${s.bestGuess}`;
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
        case 'SAMPLE': return e.algo === 'alg5' ? null : 'Sample S';
        case 'START_GUESS': return `j = ${e.value}`;
        case 'FINAL_SOLUTION': return 'Result';
        case 'ROUND':
            return {
                oracle: 'f(e)', alg6_r1: 'Alg 6 · round 1', alg6_r2: 'Alg 6 · round 2',
                alg7_r1: 'Alg 7 · round 1', alg7_r2: 'Alg 7 · round 2',
                alg5_r0: 'Round 1 · v', alg5_filter: `Round ${e.round} · l = ${e.l}`,
                alg5_central: `Round ${e.round} · central`, alg5_final: `Round ${e.round} · best`
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
        const newest = !s.isFinal && !isMapReduce(s.algorithm) && i === s.circles.length - 1;
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
        const label = `${state.algorithm === 'alg5' ? 'α' : 'τ'} = ${fmtTau(tau)}`;
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
            const label = r.e.algo === 'alg5' ? `R${r.e.round}` : `${r.e.algo === 'alg6' ? 'Alg 6' : 'Alg 7'} · R${r.e.round}`;
            if (colW > 8 * label.length) ctx.fillText(label, x + colW / 2, base + 5);
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
    if (e.key === 'Escape') { setPresenting(false); showCompare(false); showKfm(false); showSpeedup(false); return; }
    if (e.key === ' ') { e.preventDefault(); $('pbPlay').click(); }
    else if (e.key === 'ArrowRight') $('pbFwd').click();
    else if (e.key === 'ArrowLeft') $('pbBack').click();
    else if (e.key === ']' || e.key === 'PageDown') { e.preventDefault(); jumpChapter(1); }
    else if (e.key === '[' || e.key === 'PageUp') { e.preventDefault(); jumpChapter(-1); }
    else if (e.key === 'p' || e.key === 'P') setPresenting(!document.documentElement.classList.contains('presenting'));
    else if (e.key === 'c' || e.key === 'C') showCompare($('compareView').hidden);
    else if (e.key === 'f' || e.key === 'F') showKfm($('kfmView').hidden);
    else if (e.key === 's' || e.key === 'S') showSpeedup($('speedupView').hidden);
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

// "on 2 Pis (8 cores) · m = 23 machines", from a run's INIT config
function hardwareText(config) {
    const parts = [];
    if (config.pis) parts.push(`on ${config.pis} ${unitName('pis', config.pis)}` +
        (config.cores_per_pi ? ` (${config.pis * config.cores_per_pi} cores)` : ''));
    else if (config.cores) parts.push(`on ${config.cores} ${unitName('cores', config.cores)}`);
    if (config.machines) parts.push(`m = ${config.machines} machines`);
    return parts.join(' · ') || '&nbsp;';
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
            <p class="cv-hw">${hardwareText(r.init.config)}</p>
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

    // Like-for-like only if all runs drew the same points (same size, same generator).
    const done = Object.keys(ALGORITHMS).filter(a => summaries[a]);
    // The drivers name their input in config.dataset; older runs fall back to the points shown.
    const sig = r => r.init.config.dataset ||
        JSON.stringify([r.final.total_points, r.init.config.n_circles, r.init.points.slice(0, 50)]);
    const same = done.every(a => sig(summaries[a]) === sig(summaries[done[0]]));
    $('cvLede').textContent = !done.length
        ? 'No finished runs yet.'
        : !same
        ? 'These runs used different inputs, so they are not comparable. Run them on the same dataset size.'
        : `Same input: ${fmt(summaries[done[0]].final.total_points)} points and ` +
          `${fmt(summaries[done[0]].init.config.n_circles)} candidate circles. ` +
          done.map(a => `${ALGORITHMS[a].name}: ${fmt(summaries[a].final.coverage)} points in ` +
              `${fmt(summaries[a].rounds)} rounds`).join('; ') +
          '. All strips use the same scale: one column per round.';

    for (const a of Object.keys(ALGORITHMS)) {
        const r = summaries[a];
        if (!r) continue;
        drawMiniFigure($(`cvFig-${a}`), r);
        drawStrip($(`cvStrip-${a}`), r.events, r.events.length, { slots });
    }
    await refreshAnalysis();
}

// --- Speedup: the same run on more Pis (or cores) ---
// m, the number of machines (partitions), depends only on the input, so every hardware size gives the
// same answer and only the wall time changes. A full analysis runs every algorithm on 1, 2, ... N.
let analysis = { running: false, plan: [], done: 0, results: [] };
let hw = { unit: 'pis', max: 0 };   // what the next run can use, from /cluster-status
let hwTouched = false;               // keep the user's pick across polls

// Name of a run in an analysis plan: a circle cover algorithm, or the k-th frequency moment
const planName = a => ALGORITHMS[a] ? ALGORITHMS[a].name : 'Frequency moment';

const unitName = (unit, n) => unit === 'pis' ? (n === 1 ? 'Pi' : 'Pis') : (n === 1 ? 'core' : 'cores');

let analysisSeq = 0;   // replies to overlapping polls can arrive out of order: only the newest counts

async function refreshAnalysis() {
    const seq = ++analysisSeq;
    let next;
    try { next = await (await fetch('/analysis', { cache: 'no-store' })).json(); } catch (e) { return; }
    if (seq !== analysisSeq) return;   // a newer reply is already in (or on its way): don't go back to "running"
    const wasRunning = analysis.running;
    analysis = next;
    renderAnalysisButton();
    if (wasRunning && !analysis.running) {
        // finished: show the result, and the header is free again
        renderRunButton();
        if (analysis.kind === 'kfm') { $('kfmView').hidden = false; renderKfm(); }
        else if (analysis.kind === 'speedup') { $('speedupView').hidden = false; renderSpeedup(); }
        else showCompare(true);
    } else {
        if (!$('compareView').hidden) renderScaling();
        if (!$('speedupView').hidden) renderSpeedup();
        if (!$('kfmView').hidden) renderKfm();
    }
}

function renderAnalysisButton() {
    const btn = $('analysisBtn');
    btn.textContent = analysis.running ? `Stop ${analysis.kind === 'speedup' ? 'speedup' : 'analysis'} (${analysis.done + 1} of ${analysis.plan.length})` : 'Full analysis';
    btn.classList.toggle('btn-primary', analysis.running);
    btn.disabled = !wsOpen || (!analysis.running && runInProgress());
    // While the analysis runs it picks the algorithm, size and hardware itself: only Stop stays usable
    document.querySelectorAll('input[name="algorithm"], input[name="jobSize"], #tSelect, #hwSelect')
        .forEach(el => { el.disabled = analysis.running; });
    document.querySelectorAll('.run-block .segmented, #tPicker, #hwPicker')
        .forEach(el => el.classList.toggle('locked', analysis.running));
    renderAnalysisQueue();
}

// The analysis plan as a row of chips: done (with its wall time), running (with its time so far), up next.
function renderAnalysisQueue() {
    const q = $('analysisQueue');
    q.hidden = !analysis.running;
    if (!analysis.running) return;
    const unit = analysis.unit || 'pis';
    const timeOf = (a, n) => a === 'kfm'
        ? kfmRunOf({ n: analysis.n, alphabet: analysis.alphabet, k: analysis.moment }, unit, n)
        : (analysis.results || []).find(r => r.algorithm === a && r.parallel === n && r.unit === unit &&
            (r.dataset || '').startsWith(analysis.size + '/') && (a !== 'alg5' || r.t === analysis.t));
    const items = analysis.plan.map(([a, n], i) => {
        const label = `${planName(a)} · ${n} ${unitName(unit, n)}`;
        if (i < analysis.done) {
            const r = timeOf(a, n);
            return `<span class="aq-item done">${label}${r ? ` · ${fmtS(r.elapsed_s)}` : ''}</span>`;
        }
        if (i === analysis.done) {
            const since = analysis.current && analysis.now ? analysis.now - analysis.current.started_at : null;
            return `<span class="aq-item running">${label}${since != null ? ` · ${fmtS(since)}` : ''}</span>`;
        }
        return `<span class="aq-item">${label}</span>`;
    });
    const title = analysis.kind === 'kfm' ? `Frequency moment, n = ${shortCount(analysis.n)}, |Σ| = ${shortCount(analysis.alphabet)}, ` +
        `k = ${analysis.moment}, ${analysis.repeats} run${analysis.repeats === 1 ? '' : 's'} each:`
        : analysis.kind === 'speedup' ? `Speedup, ${planName(analysis.algorithm)}, ${analysis.size}:`
        : `Full analysis, ${analysis.size}:`;
    q.innerHTML = `<span class="aq-title">${title}</span>${items.join('')}`;
    if (analysis.kind === 'kfm') {
        $('kfmQueue').innerHTML = items.join('');
    }
    if (analysis.kind === 'speedup') {
        $('suQueue').innerHTML = items.join('');
    }
}

$('analysisBtn').addEventListener('click', async () => {
    try {
        if (analysis.running) {
            await fetch('/analysis/stop', { method: 'POST' });
        } else {
            const size = document.querySelector('input[name="jobSize"]:checked').value;
            await fetch('/analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ size, t: selectedT() })
            });
        }
    } catch (e) {
        console.error('Analysis request failed', e);
    }
    refreshAnalysis();
});

function renderHwPicker() {
    $('hwPicker').hidden = !hw.max;
    $('hwLabel').textContent = hw.unit === 'pis' ? 'Pis' : 'Cores';
    const sel = $('hwSelect');
    const current = hwTouched ? Number(sel.value) : hw.max;
    if (sel.options.length !== hw.max) {
        sel.innerHTML = Array.from({ length: hw.max }, (_, i) => `<option>${i + 1}</option>`).join('');
    }
    sel.value = String(Math.min(current || hw.max, hw.max));
}
$('hwSelect').addEventListener('change', () => { hwTouched = true; });

// The finished runs to compare: the dataset size picked in the header, and the t picked for Algorithm 5.
let sizeTouched = false;   // after the user picks a size, show that one instead of the last analysis'
document.querySelectorAll('input[name="jobSize"]').forEach(r => r.addEventListener('change', () => {
    sizeTouched = true;
    if (!$('compareView').hidden) renderScaling();
    if (!$('speedupView').hidden) renderSpeedup();
}));

function scalingRows() {
    const size = analysis.size && (analysis.running || !sizeTouched) ? analysis.size
        : document.querySelector('input[name="jobSize"]:checked').value;
    const t = analysis.running ? analysis.t : selectedT();
    const runs = (analysis.results || []).filter(r =>
        (r.dataset || '').startsWith(size + '/') && (r.algorithm !== 'alg5' || r.t === t));
    const unit = runs.some(r => r.unit === 'pis') ? 'pis' : 'cores';
    const mine = runs.filter(r => r.unit === unit);
    const sizes = [...new Set(mine.map(r => r.parallel))].sort((a, b) => a - b);
    const rows = Object.keys(ALGORITHMS).map(a => {
        const byN = new Map(mine.filter(r => r.algorithm === a).map(r => [r.parallel, r]));
        const base = sizes.map(n => byN.get(n)).find(Boolean);
        return { algorithm: a, byN, base, rounds: base ? base.rounds : null };
    }).filter(r => r.byN.size);
    return { size, t, unit, sizes, rows };
}

// The Compare view's section shows every algorithm; the Speedup view (only = one algorithm) just that one.
const COMPARE_SCALING = { title: 'cvScalingTitle', lede: 'cvScalingLede', progress: 'cvScalingProgress',
    headline: 'scalingHeadline', bars: 'scalingBars', table: 'scalingTable', why: 'scalingWhy', chart: 'scalingChart',
    minChart: 3 };
const SPEEDUP_SCALING = { title: 'suTitle', lede: 'suLede', progress: 'suProgress', headline: 'suHeadline',
    bars: 'suBars', table: 'suTable', why: 'suWhy', chart: 'suChart', minChart: 2 };

function renderScaling(V = COMPARE_SCALING, only = null) {
    const { size, t, unit, sizes: allSizes, rows: allRows } = scalingRows();
    const rows = only ? allRows.filter(r => r.algorithm === only) : allRows;
    const sizes = only ? allSizes.filter(n => rows.some(r => r.byN.has(n))) : allSizes;
    const U = unit === 'pis' ? 'Pis' : 'cores';
    $(V.title).textContent = only ? `${ALGORITHMS[only].name}${only === 'alg5' ? `, t = ${t}` : ''}: speedup with more ${U}`
        : `Speedup with more ${U}`;
    const progress = analysis.running
        ? `${analysis.kind === 'speedup' ? 'Speedup' : 'Full analysis'} running: run ${analysis.done + 1} of ${analysis.plan.length}` +
          (analysis.current ? ` (${planName(analysis.current.algorithm)} on ${analysis.current.parallel} ` +
              `${unitName(analysis.unit, analysis.current.parallel)})` : '') + '.'
        : '';
    $(V.progress).textContent = progress;
    $(V.progress).hidden = !progress;

    if (!rows.length) {
        $(V.lede).textContent = only ? `No timed runs of ${ALGORITHMS[only].name} on the ${size} dataset yet. ` +
            `Press Run to run it on 1, 2, … all ${U}.`
            : `No timed runs on the ${size} dataset yet. Press Full analysis to run every ` +
            `algorithm on 1, 2, … all ${U}, or pick a number in the header and run one.`;
        [V.headline, V.bars, V.table, V.why].forEach(id => { $(id).innerHTML = ''; });
        $(V.chart).hidden = true;
        return;
    }
    const lo = sizes[0], hi = sizes[sizes.length - 1];
    const hw = n => `${n} ${unitName(unit, n)}`;
    const nameOf = r => ALGORITHMS[r.algorithm].name + (r.algorithm === 'alg5' ? `, t = ${t}` : '');
    const covOf = r => [...r.byN.values()][0].coverage;
    // Wall time split into work on the machines and coordination (everything else), as viz_server estimates it
    const split = run => {
        const work = Math.min(run.work_s ?? run.elapsed_s, run.elapsed_s);
        return { work, coord: run.elapsed_s - work, share: (run.elapsed_s - work) / run.elapsed_s };
    };
    $(V.lede).textContent = `The same input (${size}) on ${sizes.map(hw).join(', ')}. ` +
        `Wall time is the algorithm itself, from its first Spark job to its answer, without starting Spark.`;

    // Headline: what more hardware bought each algorithm, and the MapReduce algorithms against greedy
    const greedy = rows.find(r => r.algorithm === 'greedy');
    const lines = rows.filter(r => r.byN.has(hi) && r.byN.get(hi) !== r.base).map(r => {
        const top = r.byN.get(hi);
        const x = r.base.elapsed_s / top.elapsed_s;
        return `<li><b>${nameOf(r)}</b>: ${x < 1.05 ? 'no faster' : `${x.toFixed(2)}× faster`} on ${hw(hi)} ` +
            `than on ${hw(r.base.parallel)} (${fmtS(r.base.elapsed_s)} → ${fmtS(top.elapsed_s)}).</li>`;
    });
    if (greedy && greedy.byN.has(hi)) {
        rows.filter(r => r !== greedy && r.byN.has(hi)).forEach(r => {
            const times = greedy.byN.get(hi).elapsed_s / r.byN.get(hi).elapsed_s;
            const more = 100 * (covOf(r) - covOf(greedy)) / covOf(greedy);
            lines.push(`<li><b>${nameOf(r)}</b> vs threshold greedy on ${hw(hi)}: ${times.toFixed(1)}× faster, ` +
                `${more >= 0 ? `${more.toFixed(1)}% more` : `${(-more).toFixed(1)}% fewer`} points covered, ` +
                `${fmt(r.rounds)} rounds instead of ${fmt(greedy.rounds)}.</li>`);
        });
    }
    $(V.headline).innerHTML = lines.length ? `<ul>${lines.join('')}</ul>` : '';

    // Wall-time bars: one bar per algorithm and hardware size, all on the same scale of seconds
    const maxS = Math.max(...rows.flatMap(r => [...r.byN.values()].map(x => x.elapsed_s)));
    $(V.bars).innerHTML = `<div class="sb-legend"><span><i class="k-work"></i>work on the machines</span>` +
        `<span><i class="k-coord"></i>coordination: scheduling, sending data, the driver's rounds</span></div>` +
        rows.map((r, i) => `
        <div class="sb-group">
            <div class="sb-name"><i class="swatch" style="--c:${C.machines[i % C.machines.length]}"></i>${nameOf(r)}</div>
            ${sizes.filter(n => r.byN.has(n)).map(n => {
                const run = r.byN.get(n);
                const speedup = r.base.elapsed_s / run.elapsed_s;
                const { work, coord, share } = split(run);
                return `<div class="sb-row" title="${nameOf(r)} on ${hw(n)}: ${run.elapsed_s.toFixed(1)} s in ${fmt(r.rounds)} rounds, ` +
                    `${speedup.toFixed(2)}× the speed on ${hw(r.base.parallel)}. About ${fmtS(work)} of work on the machines and ` +
                    `${fmtS(coord)} of coordination (${Math.round(100 * share)}%), ${(coord / Math.max(1, r.rounds)).toFixed(1)} s per round.">
                    <span class="sb-hw">${hw(n)}</span>
                    <span class="sb-track"><span class="sb-bar" style="width:${Math.max(0.5, 100 * run.elapsed_s / maxS)}%;--c:${C.machines[i % C.machines.length]}">
                        <span class="sb-work" style="flex:${work}"></span><span class="sb-coord" style="flex:${coord}"></span></span></span>
                    <span class="sb-val">${fmtS(run.elapsed_s)}${run === r.base ? '' : ` <small>${speedup.toFixed(2)}×</small>`}` +
                    ` <small>· ${Math.round(100 * share)}% coord.</small></span>
                </div>`;
            }).join('')}
        </div>`).join('');

    // Table: time, speedup and efficiency per hardware size
    const head = `<thead><tr><th>Algorithm</th>${sizes.map(n => `<th>${hw(n)}</th>`).join('')}` +
        `<th>Rounds</th><th>Points covered</th></tr></thead>`;
    const body = rows.map(r => {
        const cells = sizes.map(n => {
            const run = r.byN.get(n);
            if (!run) return `<td>–</td>`;
            const speedup = r.base.elapsed_s / run.elapsed_s;
            const efficiency = speedup / (n / r.base.parallel);
            return `<td>${run.elapsed_s.toFixed(1)} s<br><small>${speedup.toFixed(2)}× · ${Math.round(100 * efficiency)}% eff.</small></td>`;
        }).join('');
        const covs = [...new Set([...r.byN.values()].map(x => x.coverage))];
        const cov = covs.length === 1 ? fmt(covs[0]) : `<span class="warn">differs: ${covs.map(fmt).join(' / ')}</span>`;
        return `<tr><td>${nameOf(r)}</td>${cells}<td>${fmt(r.rounds)}</td><td>${cov}</td></tr>`;
    }).join('');
    $(V.table).innerHTML = head + `<tbody>${body}</tbody>`;

    // Why not linear: the m machines run in waves over the cores, and coordination does not spread out
    const any = rows[0].base;
    const coresOf = n => unit === 'pis' ? n * (any.cores_per_pi || 4) : n;
    const waves = n => Math.ceil(any.machines / coresOf(n));
    const g = greedy && greedy.byN.has(hi) ? split(greedy.byN.get(hi)) : null;
    $(V.why).innerHTML = any.machines ? `<b>Why not ${hi / lo}×?</b> The input is split into m = ${any.machines} ` +
        `machines (partitions), the same on any hardware. ${sizes.map(n => (unit === 'pis' ? `${hw(n)} = ${coresOf(n)} cores ` : `${hw(n)} `) +
        `run${unit !== 'pis' && n === 1 ? 's' : ''} them in ${waves(n)} wave${waves(n) === 1 ? '' : 's'}`).join(', ')}, so the work on the machines can get at most ` +
        `${(waves(lo) / waves(hi)).toFixed(1)}× faster. Coordination (scheduling each Spark job, sending the points and ` +
        `the current solution to every machine, the central rounds on the driver) does not shrink with more ${U}. ` +
        (g ? `Threshold greedy pays it in each of its ${fmt(greedy.rounds)} rounds: about ` +
            `${(g.coord / greedy.rounds).toFixed(1)} s per round on ${hw(hi)}, ${Math.round(100 * g.share)}% of its wall time. ` +
            `The more rounds an algorithm needs, the more coordination dominates.` : '') : '';

    $(V.chart).hidden = sizes.length < V.minChart;
    if (sizes.length >= V.minChart) drawScalingChart($(V.chart), unit, sizes, rows);
}

const fmtS = s => s >= 120 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${s.toFixed(1)} s`;

// Speedup against hardware size, one line per algorithm, with the ideal (linear) speedup dashed.
function drawScalingChart(canvas, unit, sizes, rows) {
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const pad = { l: 40, r: 12, t: 12, b: 36 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const lo = sizes[0], hi = sizes[sizes.length - 1];
    const speedups = rows.flatMap(r => [...r.byN.values()].map(x => r.base.elapsed_s / x.elapsed_s));
    const top = Math.max(hi / lo, ...speedups) * 1.05;
    const X = n => pad.l + ((n - lo) / (hi - lo)) * iw;
    const Y = v => pad.t + ih - (v / top) * ih;

    ctx.font = '11px ' + getComputedStyle(document.body).fontFamily;
    ctx.lineWidth = 1;
    for (let v = 0; v <= top; v += top > 6 ? 2 : 1) {
        ctx.strokeStyle = v === 0 ? C.ruleStrong : C.rule;
        ctx.beginPath(); ctx.moveTo(pad.l, Y(v)); ctx.lineTo(pad.l + iw, Y(v)); ctx.stroke();
        ctx.fillStyle = C.muted; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillText(`${v}×`, pad.l - 6, Y(v));
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    sizes.forEach(n => ctx.fillText(String(n), X(n), pad.t + ih + 6));
    ctx.fillText(unit === 'pis' ? 'Pis' : 'cores', pad.l + iw / 2, pad.t + ih + 20);

    // ideal: twice the hardware, twice as fast
    ctx.strokeStyle = C.muted; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(X(lo), Y(1)); ctx.lineTo(X(hi), Y(hi / lo)); ctx.stroke();
    ctx.setLineDash([]);

    const labels = [];
    rows.forEach((r, i) => {
        const color = C.machines[i % C.machines.length];
        const pts = sizes.filter(n => r.byN.has(n)).map(n => [X(n), Y(r.base.elapsed_s / r.byN.get(n).elapsed_s)]);
        ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 2;
        ctx.beginPath(); pts.forEach(([x, y], j) => j ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.stroke();
        pts.forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); });
        const [lx, ly] = pts[pts.length - 1];
        labels.push({ text: planName(r.algorithm), color, x: lx - 6, y: ly - 6 });
    });
    // labels at the lines' ends, pushed apart so close lines stay readable
    labels.sort((a, b) => a.y - b.y);
    labels.forEach((l, i) => { if (i && l.y - labels[i - 1].y < 14) l.y = labels[i - 1].y + 14; });
    ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
    ctx.lineWidth = 4; ctx.lineJoin = 'round'; ctx.strokeStyle = C.surface;   // a halo keeps them clear of the lines
    labels.forEach(l => { ctx.strokeText(l.text, l.x, l.y); ctx.fillStyle = l.color; ctx.fillText(l.text, l.x, l.y); });
}

$('compareBtn').addEventListener('click', () => showCompare(true));
$('cvClose').addEventListener('click', () => showCompare(false));
$('compareView').addEventListener('click', e => { if (e.target === $('compareView')) showCompare(false); });

// --- Speedup: the algorithm and parameters picked in the header, on 1, 2, ... N Pis (or cores) ---
// While its own run goes, the view follows that run; otherwise it follows the header.
const speedupAlgorithm = () => analysis.running && analysis.kind === 'speedup' ? analysis.algorithm : selectedAlgorithm();

async function showSpeedup(on) {
    $('speedupView').hidden = !on;
    if (!on) return;
    await refreshAnalysis();
    renderSpeedup();
}

function renderSpeedup() {
    const U = (analysis.unit || hw.unit) === 'pis' ? 'Pis' : 'cores';
    const mineRunning = analysis.running && analysis.kind === 'speedup';
    const btn = $('suRun');
    btn.textContent = mineRunning ? `Stop (run ${analysis.done + 1} of ${analysis.plan.length})` : `Run on 1, 2, … all ${U}`;
    btn.disabled = !wsOpen || (analysis.running && !mineRunning) || (!analysis.running && runInProgress());
    $('suQueue').hidden = !mineRunning;
    renderScaling(SPEEDUP_SCALING, speedupAlgorithm());
}

$('speedupBtn').addEventListener('click', () => showSpeedup(true));
$('suClose').addEventListener('click', () => showSpeedup(false));
$('speedupView').addEventListener('click', e => { if (e.target === $('speedupView')) showSpeedup(false); });
document.querySelectorAll('input[name="algorithm"], #tSelect').forEach(el => el.addEventListener('change', () => {
    if (!$('speedupView').hidden) renderSpeedup();
}));
$('suRun').addEventListener('click', async () => {
    try {
        if (analysis.running) {
            await fetch('/analysis/stop', { method: 'POST' });
        } else {
            sizeTouched = false;
            await fetch('/analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ size: document.querySelector('input[name="jobSize"]:checked').value,
                    t: selectedT(), algorithm: selectedAlgorithm() })
            });
        }
    } catch (e) {
        console.error('Speedup request failed', e);
    }
    await refreshAnalysis();
    renderSpeedup();
});

// --- The k-th frequency moment: the same string on 1, 2, ... N Pis (or cores) ---
// main.py --algorithm kfm sends one KFM_RESULT per run, with its wall time per Spark stage and the shuffle data
// each stage read from the other machines; viz_server saves every run. Its own analysis runs the string
// several times on every hardware size, so each hardware size gets a box plot of wall times, not one number.
const KFM_STAGES = ['μ₁', 'ρ₁ + μ₂', 'ρ₂'];
const KFM_CODE = [
    { head: 'Round 1' },
    { text: 'Mapper μ₁(⟨i; x<sub>i</sub>⟩) = ⟨x<sub>i</sub>; i⟩' },
    { note: 'shuffle: all positions of one symbol go to one reducer' },
    { text: 'Reducer ρ₁(⟨x<sub>i</sub>; {v₁, …, v<sub>m</sub>}⟩) = ⟨x<sub>i</sub>; m<sup>k</sup>⟩' },
    { head: 'Round 2' },
    { text: 'Mapper μ₂(⟨x<sub>i</sub>; v⟩) = ⟨$; v⟩' },
    { note: 'shuffle: every pair goes to the one reducer for $' },
    { text: 'Reducer ρ₂(⟨$; {v₁, …, v<sub>ℓ</sub>}⟩) = ⟨$; Σ<sub>i=1…ℓ</sub> v<sub>i</sub>⟩' },
    { head: 'Output' },
    { text: 'f<sub>k</sub>(x) = the value of ⟨$; …⟩' }
];
$('kfmCode').innerHTML = KFM_CODE.map(l => l.head ? `<li class="head">${l.head}</li>`
    : l.note ? `<li class="note i1">${l.note}</li>` : `<li>${l.text}</li>`).join('');

// Inputs to pick from: random strings of three lengths, and two badly skewed ones to show what goes wrong
const KFM_PRESETS = [
    { id: 'small', name: 'Random, n = 1M', n: 1e6, alphabet: 1000 },
    { id: 'medium', name: 'Random, n = 10M', n: 1e7, alphabet: 1000 },
    { id: 'large', name: 'Random, n = 30M', n: 3e7, alphabet: 1000 },
    { id: 'one', name: 'Skewed: one symbol (a a a …)', n: 1e6, alphabet: 1,
      note: 'Every pair has the same key, so all n pairs go to one reducer ρ₁ on one machine: more Pis cannot help, ' +
            'and a long enough string runs that reducer out of memory.' },
    { id: 'huge', name: 'Skewed: huge alphabet (|Σ| = n)', n: 1e6, alphabet: 1e6,
      note: 'Almost every symbol is different, so round 1 hardly combines anything and the one reducer for $ in ' +
            'round 2 gets about 0.63 n values instead of |Σ| = 1,000.' }
];
let kfmConfigs = [];       // custom inputs saved on the dashboard (viz_server keeps them in kfm_configs.json)
let kfmTouched = false;    // after the user changes the input or k, show those instead of the last analysis'
const shortCount = n => n >= 1e6 && n % 1e5 === 0 ? `${n / 1e6}M` : n >= 1e3 && n % 100 === 0 && n < 1e6 ? `${n / 1e3}K` : fmt(n);
const kfmFollowsAnalysis = () => analysis.kind === 'kfm' && analysis.n && (analysis.running || !kfmTouched);
const kfmField = id => Math.max(1, Math.round(Number($(id).value) || 1));
// The input, k and runs per size the view shows: the running analysis', or the pickers'
const kfmInput = () => kfmFollowsAnalysis()
    ? { n: analysis.n, alphabet: analysis.alphabet, k: analysis.moment }
    : { n: kfmField('kfmN'), alphabet: kfmField('kfmAlphabet'), k: Number($('kfmK').value) };
const sameInput = (r, inp) => r.n === inp.n && (r.alphabet ?? 1000) === inp.alphabet && r.k === inp.k;

function kfmOptions() {
    const saved = kfmConfigs.map(c => `<option value="saved:${c.name.replace(/"/g, '&quot;')}">Saved: ${c.name.replace(/</g, '&lt;')}</option>`);
    $('kfmPreset').innerHTML = KFM_PRESETS.map(p => `<option value="${p.id}">${p.name}</option>`).join('') +
        saved.join('') + '<option value="custom">Custom</option>';
}
// The preset or saved input that n and |Σ| match, or custom
function kfmMatch(n, alphabet) {
    const p = KFM_PRESETS.find(p => p.n === n && p.alphabet === alphabet);
    if (p) return { value: p.id, preset: p };
    const c = kfmConfigs.find(c => c.n === n && c.alphabet === alphabet);
    return c ? { value: `saved:${c.name}`, saved: c } : { value: 'custom' };
}
function kfmSetFields(n, alphabet) {
    $('kfmN').value = String(n);
    $('kfmAlphabet').value = String(alphabet);
}

// Every hardware size's runs of one input: all of them, the ones that finished, and the median run
const median = xs => { const s = [...xs].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
function quantile(sorted, q) {
    const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}
function kfmGroups(inp, unit) {
    const byN = new Map();
    (analysis.kfm_results || []).filter(r => r.parallel && r.unit === unit && sameInput(r, inp)).forEach(r => {
        if (!byN.has(r.parallel)) byN.set(r.parallel, []);
        byN.get(r.parallel).push(r);
    });
    return [...byN.entries()].sort((a, b) => a[0] - b[0]).map(([parallel, all]) => {
        const ok = all.filter(r => !r.error).sort((a, b) => a.elapsed_s - b.elapsed_s);
        const times = ok.map(r => r.elapsed_s);
        return { parallel, all, ok, failed: all.filter(r => r.error), times,
                 med: times.length ? median(times) : null, rep: ok.length ? ok[(ok.length - 1) >> 1] : null };
    });
}
function kfmRows() {
    const inp = kfmInput();
    const mine = (analysis.kfm_results || []).filter(r => r.parallel && sameInput(r, inp));
    const unit = mine.some(r => r.unit === (analysis.unit || hw.unit)) ? (analysis.unit || hw.unit)
        : mine.some(r => r.unit === 'pis') ? 'pis' : 'cores';
    return { inp, unit, groups: kfmGroups(inp, unit) };
}
// The analysis queue's chip for one hardware size: the median of its runs
const kfmRunOf = (inp, unit, n) => {
    const g = kfmGroups(inp, unit).find(g => g.parallel === n);
    return g && g.med != null ? { elapsed_s: g.med } : null;
};

async function loadKfmConfigs() {
    try { kfmConfigs = await (await fetch('/kfm/configs', { cache: 'no-store' })).json(); } catch (e) { kfmConfigs = []; }
    kfmOptions();
}

async function showKfm(on) {
    $('kfmView').hidden = !on;
    if (!on) return;
    await Promise.all([refreshAnalysis(), loadKfmConfigs()]);
    renderKfm();
}

// Box plots of every run's wall time per hardware size, with the medians joined and the ideal speedup dashed
function drawKfmBoxes(canvas, unit, groups) {
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const pad = { l: 44, r: 12, t: 22, b: 36 };
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const shown = groups.filter(g => g.times.length);
    const base = shown[0];
    const maxT = Math.max(...shown.flatMap(g => g.times)) * 1.08 || 1;
    const step = [0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600].find(s => maxT / s <= 6) || 1200;
    const slot = iw / groups.length;
    const X = i => pad.l + slot * (i + 0.5);
    const Y = v => pad.t + ih - (v / maxT) * ih;
    const font = getComputedStyle(document.body).fontFamily;
    ctx.font = '11px ' + font;
    ctx.lineWidth = 1;
    for (let v = 0; v <= maxT; v += step) {
        ctx.strokeStyle = v === 0 ? C.ruleStrong : C.rule;
        ctx.beginPath(); ctx.moveTo(pad.l, Y(v)); ctx.lineTo(pad.l + iw, Y(v)); ctx.stroke();
        ctx.fillStyle = C.muted; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillText(`${v} s`, pad.l - 6, Y(v));
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    groups.forEach((g, i) => ctx.fillText(String(g.parallel), X(i), pad.t + ih + 6));
    ctx.fillText(unit === 'pis' ? 'Pis' : 'cores', pad.l + iw / 2, pad.t + ih + 20);
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.fillText('wall time of every run · dashed: ideal (twice the hardware, half the time)', pad.l, 2);

    const idx = g => groups.indexOf(g);
    // ideal: the median on the fewest machines, divided by how many times more hardware there is
    if (base && shown.length > 1) {
        ctx.strokeStyle = C.muted; ctx.setLineDash([4, 4]);
        ctx.beginPath();
        shown.forEach((g, j) => { const y = Y(base.med * base.parallel / g.parallel); j ? ctx.lineTo(X(idx(g)), y) : ctx.moveTo(X(idx(g)), y); });
        ctx.stroke(); ctx.setLineDash([]);
    }
    // medians joined, so the trend reads at a glance
    const color = C.machines[1];
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.globalAlpha = 0.6;
    ctx.beginPath(); shown.forEach((g, j) => j ? ctx.lineTo(X(idx(g)), Y(g.med)) : ctx.moveTo(X(idx(g)), Y(g.med))); ctx.stroke();
    ctx.globalAlpha = 1;

    const bw = Math.min(36, slot * 0.45);
    shown.forEach(g => {
        const x = X(idx(g)), s = g.times;
        const q1 = quantile(s, 0.25), q3 = quantile(s, 0.75), iqr = q3 - q1;
        const inside = s.filter(t => t >= q1 - 1.5 * iqr && t <= q3 + 1.5 * iqr);
        const lo = Math.min(...inside), hi = Math.max(...inside);
        ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        // whiskers
        ctx.beginPath(); ctx.moveTo(x, Y(lo)); ctx.lineTo(x, Y(q1)); ctx.moveTo(x, Y(q3)); ctx.lineTo(x, Y(hi));
        ctx.moveTo(x - bw / 4, Y(lo)); ctx.lineTo(x + bw / 4, Y(lo)); ctx.moveTo(x - bw / 4, Y(hi)); ctx.lineTo(x + bw / 4, Y(hi)); ctx.stroke();
        // box from the first to the third quartile, the median across it
        ctx.fillStyle = C.surface;
        ctx.fillRect(x - bw / 2, Y(q3), bw, Math.max(1, Y(q1) - Y(q3)));
        ctx.globalAlpha = 0.18; ctx.fillStyle = color;
        ctx.fillRect(x - bw / 2, Y(q3), bw, Math.max(1, Y(q1) - Y(q3)));
        ctx.globalAlpha = 1;
        ctx.strokeRect(x - bw / 2, Y(q3), bw, Math.max(1, Y(q1) - Y(q3)));
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(x - bw / 2, Y(g.med)); ctx.lineTo(x + bw / 2, Y(g.med)); ctx.stroke();
        // every run as a dot beside the box; the ones beyond the whiskers (outliers) hollow and further out
        s.forEach((t, j) => {
            const out = t < lo || t > hi;
            const dx = x + bw / 2 + 6 + (j % 3) * 3;
            ctx.beginPath(); ctx.arc(out ? x : dx, Y(t), out ? 3.5 : 2, 0, Math.PI * 2);
            if (out) { ctx.lineWidth = 1.5; ctx.strokeStyle = C.machines[0]; ctx.stroke(); ctx.strokeStyle = color; }
            else { ctx.fillStyle = color; ctx.globalAlpha = 0.55; ctx.fill(); ctx.globalAlpha = 1; }
        });
    });
    // hardware sizes where every run failed
    groups.filter(g => !g.times.length).forEach(g => {
        ctx.fillStyle = C.machines[0]; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        ctx.fillText('failed', X(idx(g)), pad.t + ih - 4);
    });
}

function renderKfm() {
    const unitNow = analysis.unit || hw.unit;
    const U = unitNow === 'pis' ? 'Pis' : 'cores';
    const mineRunning = analysis.running && analysis.kind === 'kfm';
    const btn = $('kfmRun');
    btn.textContent = mineRunning ? `Stop (${analysis.done + 1} of ${analysis.plan.length})`
        : `Run on 1, 2, … all ${U}`;
    btn.disabled = !wsOpen || (analysis.running && !mineRunning) || (!analysis.running && runInProgress());
    document.querySelectorAll('#kfmPreset, #kfmN, #kfmAlphabet, #kfmK, #kfmRepeats, #kfmClear')
        .forEach(el => { el.disabled = mineRunning; });
    if (kfmFollowsAnalysis()) {
        // the pickers show what the results below were run with
        kfmSetFields(analysis.n, analysis.alphabet);
        $('kfmK').value = String(analysis.moment);
        if (analysis.repeats) $('kfmRepeats').value = String(analysis.repeats);
    }
    const m = kfmMatch(kfmField('kfmN'), kfmField('kfmAlphabet'));
    $('kfmPreset').value = m.value;
    $('kfmForget').hidden = !m.saved;
    $('kfmPresetNote').textContent = (m.preset && m.preset.note) || '';
    $('kfmQueue').hidden = !mineRunning;

    const { inp, unit, groups } = kfmRows();
    const hwText = n => `${n} ${unitName(unit, n)}`;
    // the title follows the runs shown (Pis or cores), or the hardware the next run uses when there are none
    document.querySelectorAll('.kfm-unit').forEach(el => { el.textContent = groups.length ? (unit === 'pis' ? 'Pis' : 'cores') : U; });
    const what = `n = ${shortCount(inp.n)}, |Σ| = ${shortCount(inp.alphabet)} and k = ${inp.k}`;
    $('kfmClear').hidden = !groups.length;
    const done = groups.filter(g => g.rep);
    if (!done.length) {
        const failures = groups.flatMap(g => g.failed);
        $('kfmLede').innerHTML = mineRunning
            ? `Running on 1 ${unitName(unitNow, 1)} first. Each bar appears as its runs finish.`
            : failures.length ? `Every run with ${what} failed.`
            : `No runs with ${what} yet. Press “${btn.textContent}” ` +
              `to run the algorithm ${$('kfmRepeats').value} times on every number of ${U}, one after another.`;
        $('kfmHeadline').innerHTML = failures.length
            ? `<ul><li class="warn">${failures.length} run${failures.length === 1 ? '' : 's'} failed: ${escapeText(failures[0].error)}</li></ul>` : '';
        ['kfmBars', 'kfmTable', 'kfmWhy'].forEach(id => { $(id).innerHTML = ''; });
        $('kfmChart').hidden = true;
        return;
    }
    const base = done[0], top = done[done.length - 1];
    const b = base.rep;
    const allOk = done.flatMap(g => g.ok);
    const fks = [...new Set(allOk.map(r => String(r.f_k)))];
    const failed = groups.flatMap(g => g.failed);
    $('kfmLede').innerHTML = `A random string of n = ${fmt(inp.n)} symbols drawn from |Σ| = ${fmt(inp.alphabet)} ` +
        `(${fmt(b.symbols)} of them occur), in ${b.partitions} input partitions, k = ${inp.k}. ` +
        `Wall time is the algorithm itself, from its first Spark job to f<sub>k</sub>(x), with the input already on the machines. ` +
        `Bars and table show each hardware size's median run.`;

    const lines = [];
    if (top !== base) {
        const x = base.med / top.med;
        lines.push(`<li><b>${hwText(top.parallel)}</b>: ${x.toFixed(2)}× faster than ${hwText(base.parallel)} ` +
            `(median ${fmtS(base.med)} → ${fmtS(top.med)}), ${Math.round(100 * x / (top.parallel / base.parallel))}% of linear.</li>`);
    }
    const spread = Math.max(...done.map(g => (g.times[g.times.length - 1] - g.times[0]) / g.med));
    if (done.some(g => g.times.length > 1)) {
        lines.push(`<li>${allOk.length} runs; on one hardware size they differ by up to ${Math.round(100 * spread)}% of the median.</li>`);
    }
    lines.push(fks.length === 1
        ? `<li>f<sub>${inp.k}</sub>(x) = <b>${fmt(Number(fks[0]))}</b> on every run` +
          (allOk.every(r => r.check) ? ', and the same as counting on the driver.' : '.') + '</li>'
        : `<li class="warn">The runs disagree on f<sub>${inp.k}</sub>(x): ${fks.join(' / ')}.</li>`);
    if (failed.length) {
        lines.push(`<li class="warn">${failed.length} run${failed.length === 1 ? '' : 's'} failed ` +
            `(${[...new Set(failed.map(r => hwText(r.parallel)))].join(', ')}): ${escapeText(failed[0].error)}</li>`);
    }
    $('kfmHeadline').innerHTML = `<ul>${lines.join('')}</ul>`;

    // One bar per hardware size (its median run), split into the 3 stages, all on the same scale. A stage that
    // reads a shuffle starts by fetching its pairs from the other machines; the hatched part is the share of the
    // stage's task time spent waiting for that data over the network (Spark's fetchWaitTime), so the
    // communication between the Pis.
    const stageS = r => KFM_STAGES.map((_, i) => (r.stages && r.stages[i]) ? r.stages[i].s : 0);
    const waitS = r => KFM_STAGES.map((_, i) => {
        const st = r.stages && r.stages[i];
        return st && st.task_ms ? st.s * Math.min(1, (st.fetch_wait_ms || 0) / st.task_ms) : 0;
    });
    const sum = a => a.reduce((x, y) => x + y, 0);
    const remoteMB = r => sum((r.stages || []).map(st => st.remote_bytes || 0)) / 1e6;
    const shuffledMB = r => sum((r.stages || []).map(st => (st.remote_bytes || 0) + (st.local_bytes || 0))) / 1e6;
    const remoteShare = r => Math.round(100 * remoteMB(r) / Math.max(1e-9, shuffledMB(r)));
    const hasNet = done.some(g => (g.rep.stages || []).some(st => st.task_ms !== undefined));
    const maxS = Math.max(...done.map(g => g.rep.elapsed_s));
    $('kfmBars').innerHTML = `<div class="sb-legend">${KFM_STAGES.map((name, i) =>
        `<span><i style="background:${C.machines[i]}"></i>${name}</span>`).join('')}` +
        (hasNet ? `<span><i class="kb-net" style="--c:var(--ink-3)"></i>waiting for data from the other ${unit === 'pis' ? 'Pis' : 'cores'}</span>` : '') +
        `<span>rest: scheduling the job</span></div>` +
        done.map(g => {
            const r = g.rep, parts = stageS(r), waits = waitS(r);
            const rest = Math.max(0, r.elapsed_s - sum(parts));
            const speedup = base.med / g.med;
            const tip = `${hwText(g.parallel)}, median of ${g.ok.length} run${g.ok.length === 1 ? '' : 's'}: ${r.elapsed_s.toFixed(1)} s` +
                (g.ok.length > 1 ? ` (all runs ${g.times[0].toFixed(1)}–${g.times[g.times.length - 1].toFixed(1)} s)` : '') + '. ' +
                parts.map((s, i) => `${KFM_STAGES[i]} ${s.toFixed(1)} s` +
                    (waits[i] >= 0.05 ? ` (${waits[i].toFixed(1)} s waiting for data)` : '')).join(', ') +
                `, other ${rest.toFixed(1)} s.` +
                (hasNet ? ` ${remoteMB(r).toFixed(1)} of ${shuffledMB(r).toFixed(1)} MB shuffled went between machines.` : '');
            return `<div class="kb-row" title="${tip}">
                <span class="kb-hw">${hwText(g.parallel)}</span>
                <span class="kb-track" style="width:${Math.max(1, 100 * r.elapsed_s / maxS)}%">
                    ${parts.map((s, i) => `<span class="kb-stage" style="flex:${s};--c:${C.machines[i]}">` +
                        `<span class="kb-net" style="flex:${waits[i]}"></span><span style="flex:${s - waits[i]}"></span></span>`).join('')}
                    <span style="flex:${rest};--c:var(--rule-strong)"></span></span>
                <span class="kb-val">${fmtS(r.elapsed_s)}${g === base ? '' : ` <small>${speedup.toFixed(2)}×</small>`}</span>
            </div>`;
        }).join('');

    // Every run's wall time per hardware size, as box plots
    $('kfmChart').hidden = false;
    drawKfmBoxes($('kfmChart'), unit, groups);

    // Table: per hardware size its runs, the median run's time per stage, the communication, and the machines
    const hostsOf = r => {
        const tasks = {};
        (r.stages || []).forEach(st => Object.entries(st.hosts || {}).forEach(([h, v]) => { tasks[h] = (tasks[h] || 0) + v.tasks; }));
        return Object.entries(tasks).sort().map(([h, n]) => `${h}: ${fmt(n)}`).join('<br>');
    };
    $('kfmTable').innerHTML = `<thead><tr><th>${unit === 'pis' ? 'Pis' : 'Cores'}</th><th>Runs</th><th>Wall time (median)</th>` +
        `<th>Speedup</th><th>Efficiency</th>${KFM_STAGES.map(n => `<th>${n}</th>`).join('')}` +
        (hasNet ? `<th>Between ${unit === 'pis' ? 'Pis' : 'cores'}</th><th>Waiting for it</th>` : '') +
        `<th>f<sub>${inp.k}</sub>(x)</th><th>Tasks per machine</th></tr></thead><tbody>` +
        groups.map(g => {
            const runs = `${g.ok.length}${g.failed.length ? ` <span class="warn">+ ${g.failed.length} failed</span>` : ''}`;
            if (!g.rep) return `<tr><td>${hwText(g.parallel)}</td><td>${runs}</td><td colspan="99" class="warn">${escapeText(g.failed[0].error)}</td></tr>`;
            const r = g.rep, speedup = base.med / g.med;
            return `<tr><td>${hwText(g.parallel)}</td><td>${runs}</td><td>${g.med.toFixed(1)} s` +
                (g.ok.length > 1 ? ` <small>(${g.times[0].toFixed(1)}–${g.times[g.times.length - 1].toFixed(1)})</small>` : '') + `</td>` +
                `<td>${speedup.toFixed(2)}×</td><td>${Math.round(100 * speedup / (g.parallel / base.parallel))}%</td>` +
                stageS(r).map(s => `<td>${s.toFixed(1)} s</td>`).join('') +
                (hasNet ? `<td>${remoteMB(r).toFixed(1)} MB <small>(${remoteShare(r)}%)</small></td><td>${sum(waitS(r)).toFixed(1)} s</td>` : '') +
                `<td>${fmt(r.f_k)}${g.ok.every(x => x.check) ? '' : ' <span class="warn">≠ driver</span>'}</td><td>${hostsOf(r)}</td></tr>`;
        }).join('') + '</tbody>';

    const cores = n => unit === 'pis' ? n * (b.cores_per_pi || 4) : n;
    const perCore = n => Math.ceil(b.partitions / cores(n));
    const skew = b.symbols === 1
        ? `<b>Skewed input.</b> Every pair has the same key, so round 1 has a single reducer: all ${fmt(inp.n)} pairs ` +
          `cross the network to one machine, which then does all of ρ₁'s work alone. Adding ${unit === 'pis' ? 'Pis' : 'cores'} only ` +
          `speeds up μ₁. `
        : b.symbols > inp.n / 10
        ? `<b>Skewed input.</b> With ${fmt(b.symbols)} different symbols, round 1 combines almost nothing, and the single ` +
          `reducer for $ in round 2 gets ${fmt(b.symbols)} values on one machine instead of a thousand. ` : '';
    $('kfmWhy').innerHTML = skew + `<b>Why it speeds up.</b> μ₁ works on the ${fmt(inp.n)} pairs in ${b.partitions} partitions and ` +
        `ρ₁ on the ${fmt(b.symbols)} symbols, each part independently of the others: ${done.map(g => `${hwText(g.parallel)} ` +
        `${g.parallel === 1 ? 'runs' : 'run'} ${perCore(g.parallel)} input partition${perCore(g.parallel) === 1 ? '' : 's'} per core`).join(', ')}. ` +
        `Both rounds are one Spark job, so the fixed cost of coordinating it is paid once, not once per step as in the threshold greedy. ` +
        `<b>Why not linear.</b> The shuffles send every pair ⟨x<sub>i</sub>; i⟩ over the network to its symbol's reducer, ` +
        `and ρ₂ runs on a single machine: all ${fmt(b.symbols)} values meet at the key $. ` +
        `The largest round-1 reducer holds ${fmt(b.largest_reducer)} of the ${fmt(inp.n)} pairs; a string of one repeated ` +
        `symbol would put all of them on one machine and nothing would speed up.` +
        (hasNet ? ` <b>Communication.</b> The shuffles move the same ${shuffledMB(top.rep).toFixed(1)} MB whatever the hardware; ` +
            `what changes is how much of it crosses the network: ${done.map(g => `${remoteShare(g.rep)}% on ${hwText(g.parallel)}`).join(', ')} ` +
            `(about (N − 1) / N on N machines). Every machine sends and receives its share at the same time, so the hatched ` +
            `wait grows much less than the data that crosses the network.` : '') +
        (done.some(g => g.times.length > 1) ? ` <b>Spread.</b> Each box holds the middle half of the runs, the thick line is ` +
            `the median and the whiskers reach the furthest run within 1.5 box lengths; hollow dots beyond them are outliers ` +
            `(often the first run, while the JVM warms up).` : '');
}

const escapeText = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

$('kfmBtn').addEventListener('click', () => showKfm(true));
$('kfmClose').addEventListener('click', () => showKfm(false));
$('kfmView').addEventListener('click', e => { if (e.target === $('kfmView')) showKfm(false); });
$('kfmPreset').addEventListener('change', () => {
    const v = $('kfmPreset').value;
    const p = KFM_PRESETS.find(p => p.id === v), c = kfmConfigs.find(c => `saved:${c.name}` === v);
    if (p || c) kfmSetFields((p || c).n, (p || c).alphabet);
    kfmTouched = true;
    renderKfm();
});
['kfmN', 'kfmAlphabet', 'kfmK', 'kfmRepeats'].forEach(id => $(id).addEventListener('change', () => { kfmTouched = true; renderKfm(); }));
$('kfmSave').addEventListener('click', async () => {
    const n = kfmField('kfmN'), alphabet = kfmField('kfmAlphabet');
    const name = prompt(`Name for this input (n = ${fmt(n)}, |Σ| = ${fmt(alphabet)}):`);
    if (!name || !name.trim()) return;
    try {
        const reply = await (await fetch('/kfm/configs', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim(), n, alphabet })
        })).json();
        if (reply.configs) { kfmConfigs = reply.configs; kfmOptions(); }
    } catch (e) { console.error('Saving the input failed', e); }
    renderKfm();
});
$('kfmForget').addEventListener('click', async () => {
    const m = kfmMatch(kfmField('kfmN'), kfmField('kfmAlphabet'));
    if (!m.saved || !confirm(`Delete the saved input “${m.saved.name}”? Its runs stay.`)) return;
    try {
        const reply = await (await fetch('/kfm/configs/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: m.saved.name })
        })).json();
        if (reply.configs) { kfmConfigs = reply.configs; kfmOptions(); }
    } catch (e) { console.error('Deleting the input failed', e); }
    renderKfm();
});
$('kfmClear').addEventListener('click', async () => {
    const inp = kfmInput();
    if (!confirm(`Forget every saved run with n = ${fmt(inp.n)}, |Σ| = ${fmt(inp.alphabet)} and k = ${inp.k}?`)) return;
    try {
        await fetch('/kfm/runs/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(inp) });
    } catch (e) { console.error('Clearing the runs failed', e); }
    await refreshAnalysis();
    renderKfm();
});
$('kfmRun').addEventListener('click', async () => {
    try {
        if (analysis.running) {
            await fetch('/analysis/stop', { method: 'POST' });
        } else {
            kfmTouched = false;
            await fetch('/kfm/analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ n: kfmField('kfmN'), alphabet: kfmField('kfmAlphabet'),
                                       k: Number($('kfmK').value), repeats: Number($('kfmRepeats').value) })
            });
        }
    } catch (e) {
        console.error('Frequency moment request failed', e);
    }
    await refreshAnalysis();
    renderKfm();
});
window.addEventListener('resize', () => { if (!$('kfmView').hidden) renderKfm(); });
kfmOptions();
kfmSetFields(1e7, 1000);

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
    if (!$('kfmView').hidden) renderKfm();
    if (!$('speedupView').hidden) renderSpeedup();
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
    const busy = submitting || runInProgress() || appState === 'WAITING' || analysis.running;
    const btn = $('runBtn');
    btn.disabled = busy || !wsOpen;
    btn.textContent = appState === 'WAITING' ? 'Waiting for cores…' : busy ? 'Running…' : 'Run on cluster';

    const dot = $('connDot');
    dot.className = 'dot ' + (!wsOpen ? 'bad' : busy ? 'busy' : 'ok');
    $('connText').textContent = !wsOpen ? 'Disconnected' : busy ? 'Job running' : 'Connected';
    renderAnalysisButton();
}

$('runBtn').addEventListener('click', async () => {
    submitting = true;
    renderRunButton();
    try {
        const size = document.querySelector('input[name="jobSize"]:checked').value;
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size, algorithm: selectedAlgorithm(), t: selectedT(),
                                   parallel: Number($('hwSelect').value) || null })
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
        // the frequency moment is not a circle run: it only feeds its own view, never the timeline
        if (e.type === 'KFM_RESULT') { refreshAnalysis(); return; }
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
    // /cluster-status asks the Spark master and can be slow while jobs run: don't let it hold up the analysis
    const analysisPolled = refreshAnalysis();
    try {
        const res = await fetch('/cluster-status');
        const data = await res.json();
        clusterWorkers = data.status === 'error' ? [] : (data.workers || []);
        hw = data.is_pi_cluster
            ? { unit: 'pis', max: clusterWorkers.filter(w => w.state === 'ALIVE').length }
            : { unit: 'cores', max: data.local_cores || 0 };
        // greedy runs as "CircleCover", theorem8 and alg5 as "CircleCoverMR"
        const mine = (data.activeapps || []).find(a => a.name.startsWith('CircleCover'));
        appState = mine ? mine.state : null;
    } catch (e) {
        clusterWorkers = [];
        appState = null;
    }
    renderCluster();
    renderHwPicker();
    await analysisPolled;
    renderRunButton();
}

function renderTPicker() {
    $('tPicker').hidden = selectedAlgorithm() !== 'alg5';
}
document.querySelectorAll('input[name="algorithm"]').forEach(r => r.addEventListener('change', () => {
    renderTPicker();
    // Only retitle the page when no run is loaded; a loaded run keeps its own algorithm.
    if (!state.config) renderPanels();
}));
$('tSelect').addEventListener('change', () => { if (!state.config) renderPanels(); });
renderTPicker();

renderPanels();
renderCompare();
renderRunButton();
requestAnimationFrame(frame);
connect();
pollCluster();
setInterval(pollCluster, 3000);
