// Evalgate — diagrama animado. Todo se dibuja desde T (tiempo de autor).
const TX = window.EG_TEXT;
const FONT = "'IBM Plex Sans', system-ui, sans-serif";
const MONO = "'IBM Plex Mono', ui-monospace, monospace";
const NAMES = ['Adopcion', 'Contabilidad', 'Desconexion', 'Telemetria', 'Degradacion', 'Precios', 'Emparejado', 'Estadistica', 'Puerta'];
const STATUS = ['hecho', 'hecho', 'hecho', 'hecho', 'hecho', 'en curso', 'pendiente', 'pendiente', 'pendiente'];
const PD = '8 6';

const THEMES = {
  oscuro: { bg: '#0c0e11', panel: '#14171c', ink: '#eeede8', dim: 'rgba(238,237,232,0.62)', line: 'rgba(238,237,232,0.36)', faint: 'rgba(238,237,232,0.16)', hair: 'rgba(238,237,232,0.08)', band: 'rgba(238,237,232,0.025)', traffic: '#f7f6f1', amber: '#f2b441', blue: '#5fb0f0', green: '#45d483', red: '#ff5d4f', gray: '#3a3f46', halo: 0.2 },
  claro: { bg: '#f3f2ee', panel: '#fbfbf9', ink: '#17191d', dim: 'rgba(23,25,29,0.64)', line: 'rgba(23,25,29,0.4)', faint: 'rgba(23,25,29,0.16)', hair: 'rgba(23,25,29,0.09)', band: 'rgba(23,25,29,0.03)', traffic: '#17191d', amber: '#b5770a', blue: '#1f6fb8', green: '#16934d', red: '#cf3426', gray: '#c6c9ce', halo: 0.12 },
};

// ── motion: exactly three curves ─────────────────────────────
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
const lerp = (a, b, t) => a + (b - a) * t;
const lin = (T, s, d) => clamp01((T - s) / d);
const MOTION = {
  enter: (T, s, d = 0.6) => Easing.easeOutCubic(lin(T, s, d)),
  draw: (T, s, d = 1) => Easing.easeInOutCubic(lin(T, s, d)),
  pop: (T, s, d = 0.5) => { const p = lin(T, s, d); return p <= 0 ? 0 : Easing.easeOutBack(p); },
};
const kf = (T, keys) => {
  if (T <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    if (T <= keys[i][0]) { const [t0, v0] = keys[i - 1], [t1, v1] = keys[i]; return lerp(v0, v1, MOTION.draw(T, t0, Math.max(t1 - t0, 0.001))); }
  }
  return keys[keys.length - 1][1];
};

// ── routes ───────────────────────────────────────────────────
const bez = (p0, c1, c2, p1, t) => { const u = 1 - t; return [0, 1].map((k) => u * u * u * p0[k] + 3 * u * u * t * c1[k] + 3 * u * t * t * c2[k] + t * t * t * p1[k]); };
function makeRoute(segs) {
  const pts = []; let d = '';
  segs.forEach((s, k) => {
    if (k === 0) { d += `M${s[1][0]},${s[1][1]}`; pts.push(s[1]); }
    if (s[0] === 'L') { d += ` L${s[2][0]},${s[2][1]}`; for (let i = 1; i <= 12; i++) pts.push([lerp(s[1][0], s[2][0], i / 12), lerp(s[1][1], s[2][1], i / 12)]); }
    else { d += ` C${s[2]} ${s[3]} ${s[4]}`; for (let i = 1; i <= 30; i++) pts.push(bez(s[1], s[2], s[3], s[4], i / 30)); }
  });
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const L = cum[cum.length - 1];
  const at = (u) => {
    const tg = clamp01(u) * L; let lo = 0, hi = cum.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] < tg) lo = m; else hi = m; }
    const f = (tg - cum[lo]) / ((cum[hi] - cum[lo]) || 1);
    return [lerp(pts[lo][0], pts[hi][0], f), lerp(pts[lo][1], pts[hi][1], f)];
  };
  const uOf = (x, y) => { let b = 0, bd = 1e9; pts.forEach((p, i) => { const dd = Math.hypot(p[0] - x, p[1] - y); if (dd < bd) { bd = dd; b = i; } }); return cum[b] / L; };
  return { d, at, uOf, L };
}
const R_MAIN = makeRoute([
  ['L', [420, 220], [520, 220]],
  ['C', [520, 220], [640, 220], [600, 505], [720, 505]],
  ['L', [720, 505], [1040, 505]],
  ['L', [1040, 505], [1040, 800]],
  ['C', [1040, 800], [1040, 845], [1060, 865], [1105, 865]],
  ['L', [1105, 865], [1440, 865]],
]);
const R_DIRECT = makeRoute([['C', [420, 220], [930, 220], [930, 865], [1440, 865]]]);
const SPEED = R_MAIN.L / 1.4; // px/s — the white traffic speed, constant everywhere
const THINK = 0.35, FALL = 0.45;
const U_TAP = R_MAIN.uOf(840, 505), U_CUT = R_MAIN.uOf(478, 220);

function callModel(o) {
  const R = o.direct ? R_DIRECT : R_MAIN, D = R.L / SPEED;
  const tok0 = o.t0 + D + THINK, toks = [];
  for (let i = 0; i < o.n; i++) {
    const ts = tok0 + i * o.gap, tap = ts + (1 - U_TAP) * D;
    toks.push({ ts, tap, land: tap + FALL, tc: ts + (1 - U_CUT) * D });
  }
  return Object.assign({}, o, { R, D, toks, blueT: toks[o.n - 1].tap + 0.15 });
}

// ── primitives ───────────────────────────────────────────────
function Dot({ x, y, r, fill, op = 1, halo = 0.18 }) {
  return (
    <g opacity={op}>
      {halo > 0 && <circle cx={x} cy={y} r={r * 2.6} fill={fill} opacity={halo} />}
      <circle cx={x} cy={y} r={r} fill={fill} />
    </g>
  );
}
function StatusGlyph({ x, y, status, c, r = 5 }) {
  if (status === 'hecho') return <circle cx={x} cy={y} r={r} fill={c.ink} />;
  if (status === 'en curso') return (
    <g><circle cx={x} cy={y} r={r} fill="none" stroke={c.ink} strokeWidth={1.5} /><path d={`M${x},${y - r} A${r},${r} 0 0 0 ${x},${y + r} Z`} fill={c.ink} /></g>
  );
  return <circle cx={x} cy={y} r={r} fill="none" stroke={c.ink} strokeWidth={1.5} strokeDasharray="2.2 2.2" />;
}
function StatusChip({ x, y, status, c, size = 15 }) {
  const label = TX.status[status];
  const w = 40 + label.length * size * 0.6, h = size + 15;
  return (
    <g transform={`translate(${x - w},${y})`}>
      <rect width={w} height={h} rx={h / 2} fill={c.bg} stroke={c.faint} strokeDasharray={status === 'pendiente' ? '4 4' : null} />
      <StatusGlyph x={17} y={h / 2} status={status} c={c} />
      <text x={30} y={h / 2 + size * 0.36} fontFamily={MONO} fontSize={size} fill={c.dim}>{label}</text>
    </g>
  );
}
function Block({ x, y, w, h, title, sub, status, c, pending, op = 1, scale = 1, titleSize = 26, textDy = 0, children }) {
  const cx = x + w / 2, cy = y + h / 2;
  return (
    <g opacity={op} transform={`translate(${cx},${cy}) scale(${scale}) translate(${-cx},${-cy})`}>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={pending ? PD : null} />
      <text x={x + 22} y={y + textDy + (sub ? h / 2 - 4 : h / 2 + titleSize * 0.35)} fontFamily={FONT} fontSize={titleSize} fontWeight={500} fill={c.ink}>{title}</text>
      {sub && <text x={x + 22} y={y + textDy + h / 2 + 26} fontFamily={MONO} fontSize={18} fill={c.dim}>{sub}</text>}
      {status && <StatusChip x={x + w} y={y - 40} status={status} c={c} />}
      {children}
    </g>
  );
}
function Lock({ x, y, c, s = 1 }) {
  return (
    <g transform={`translate(${x},${y}) scale(${s})`}>
      <path d="M3.5,8 V5 a4.5,4.5 0 0 1 9,0 V8" fill="none" stroke={c.dim} strokeWidth={1.8} />
      <rect x={0} y={8} width={16} height={12} rx={2} fill={c.dim} />
    </g>
  );
}
function Pill({ x, y, label, c, op = 1, scale = 1, ghost }) {
  return (
    <g opacity={op} transform={`translate(${x},${y}) scale(${scale})`}>
      <rect x={-100} y={-24} width={200} height={48} rx={24} fill={ghost ? 'none' : c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={PD} />
      <text x={0} y={7} textAnchor="middle" fontFamily={MONO} fontSize={19} fill={ghost ? c.dim : c.ink}>{label}</text>
    </g>
  );
}

const LANES = [{ y0: 110, y1: 330, k: 'app' }, { y0: 330, y1: 780, k: 'evalgate' }, { y0: 780, y1: 960, k: 'provider' }];
const SLOT = (k) => 1482.5 - k * 75;
const CASES = [0, 1, 2, 3, 4, 5];
const SCORES = [0.82, 0.64, 0.9, 0.7, 0.86, 0.6];
const rowY = (i) => 320 + i * 72;
const pad2 = (n) => String(n).padStart(2, '0');

// ── the piece ────────────────────────────────────────────────
function Piece({ tw }) {
  const { T, CUES: C, time, authoredTotal } = useComposition();
  const c = THEMES[tw.theme] || THEMES.oscuro;
  const green = tw.gate !== 'rojo';
  const A = C.Adopcion, B = C.Contabilidad, D3 = C.Desconexion, TL = C.Telemetria, DG = C.Degradacion;
  const P = C.Precios, E = C.Emparejado, F = C.Estadistica, G = C.Puerta;

  // part A (lanes) runs on ta; at the loop tail it resets to its opening frame while faded out
  const ta = T >= G + 3.4 ? 0 : T;
  const opA = T < E - 0.35 ? 1 : T < G + 3.4 ? 1 - lin(T, E - 0.35, 0.35) : MOTION.enter(T, G + 3.6, 1.6);
  const cutT = D3 + 3.4, tDead = DG + 0.6;

  const calls = [
    callModel({ t0: A + 0.5, n: 5, gap: 0.14, direct: true }),
    callModel({ t0: A + 3.7, n: 4, gap: 0.13 }),
    callModel({ t0: B + 0.6, n: 24, gap: 0.13, count: true }),
    callModel({ t0: D3 + 0.4, n: 30, gap: 0.13, count: true, cut: cutT }),
  ];
  for (let t = TL + 0.4; t < E - 2.4; t += 0.75) calls.push(callModel({ t0: t, n: 5, gap: 0.12, count: true, blue: true }));

  // counter: per-call in scenes 2–3, running total from scene 4
  const resetAt = [B, D3, TL].filter((r) => ta >= r).pop();
  let count = 0;
  if (resetAt != null) calls.forEach((cl) => { if (cl.count && cl.t0 >= resetAt) cl.toks.forEach((tk) => { if (tk.land <= ta) count++; }); });

  // telemetry
  let di = 0;
  const blues = calls.filter((cl) => cl.blue).map((cl) => { const qa = cl.blueT + 0.25; const dead = qa >= tDead; return { tb: cl.blueT, qa, dead, k: dead ? di++ : -1 }; });
  const dropped = blues.filter((b) => b.dead && b.k >= 4 && b.qa <= ta).length;
  const qFull = blues.some((b) => b.dead && b.k === 3 && ta >= b.qa + 0.35);
  const telOp = MOTION.enter(ta, TL + 0.1, 0.7);
  const dead = MOTION.enter(ta, tDead - 0.1, 0.5);

  // camera (part A)
  const camS = kf(ta, [[B, 1], [TL, 1.035], [P, 1.045]]);
  const camX = kf(ta, [[B, 960], [TL, 930], [P, 985]]);
  const camY = kf(ta, [[B, 540], [TL, 530], [P, 545]]);
  const dimA = kf(ta, [[P + 0.2, 1], [P + 1.2, 0.14]]);

  // scene 1
  const retract = MOTION.draw(ta, A + 2.5, 0.8);
  const routeIn = MOTION.draw(ta, A + 2.7, 1.0);
  const proxyP = MOTION.pop(ta, A + 1.8, 0.6);
  const envS = MOTION.enter(ta, A + 2.2, 0.6);
  // scene 3 cut
  const cutAmt = MOTION.enter(ta, cutT, 0.3) * (1 - MOTION.enter(ta, TL + 0.1, 0.5));
  const cntP = MOTION.pop(ta, B + 0.2, 0.5);
  const amberOp = ta >= TL ? 0.55 : 1;

  // record card → scene 6 zoom
  const recIn = MOTION.enter(ta, D3 + 7.2, 0.7);
  const s6 = MOTION.draw(ta, P + 0.2, 1.0);
  const tgtX = (220 - 960) / camS + camX, tgtY = (340 - 540) / camS + camY, tgtS = 1.5 / camS;
  const recX = lerp(lerp(560, 330, recIn), tgtX, s6), recY = lerp(610, tgtY, s6), recS = lerp(1, tgtS, s6);
  const recOp = lin(ta, D3 + 7.2, 0.4) * kf(ta, [[TL, 1], [TL + 0.6, 0.5], [P + 0.2, 0.5], [P + 1.2, 1]]);
  const priceOp = MOTION.enter(ta, P + 1.2, 0.6);
  const hl = MOTION.enter(ta, P + 2.6, 0.4);
  const conn = MOTION.draw(ta, P + 2.3, 0.7);
  const costP = MOTION.pop(ta, P + 3.8, 0.6);

  // dots
  const dotEls = [];
  calls.forEach((cl, ci) => {
    const ur = (ta - cl.t0) / cl.D;
    if (ur >= 0 && ur <= 1) { const [x, y] = cl.R.at(ur); dotEls.push(<Dot key={ci + 'r'} x={x} y={y} r={8} fill={c.traffic} halo={c.halo} op={Math.min(1, ur * 12, (1 - ur) * 12)} />); }
    cl.toks.forEach((tk, i) => {
      const age = ta - tk.ts;
      const lostLater = cl.cut != null && tk.tc >= cl.cut;
      if (lostLater && ta >= tk.tc) {
        const f = (ta - tk.tc) / 0.45;
        if (f <= 1) { const [x, y] = cl.R.at(U_CUT); dotEls.push(<Dot key={ci + 't' + i} x={x - 6 * f} y={y + 46 * f * f} r={5} fill={c.traffic} op={1 - f} halo={0} />); }
      } else if (age >= 0 && age <= cl.D) {
        const u = 1 - age / cl.D; const [x, y] = cl.R.at(u);
        dotEls.push(<Dot key={ci + 't' + i} x={x} y={y} r={5} fill={c.traffic} halo={c.halo * 0.7} op={Math.min(1, age * 10, u * 14)} />);
      }
      if (cl.count && ta >= tk.tap && ta <= tk.land) {
        const f = (ta - tk.tap) / FALL;
        dotEls.push(<Dot key={ci + 'a' + i} x={840} y={505 + 105 * f * f} r={4.5} fill={c.amber} halo={c.halo} op={amberOp * Math.min(1, (1 - f) * 6)} />);
      }
    });
  });
  const blueEls = blues.map((b, i) => {
    if (ta < b.tb) return null;
    let x, y = 470, op = 1;
    if (ta < b.qa) { const f = (ta - b.tb) / 0.25; x = lerp(1120, 1220, f); op = Math.min(1, f * 3); }
    else if (!b.dead) { const f = (ta - b.qa) / 0.5; if (f > 1.3) return null; x = lerp(1220, 1600, Math.min(f, 1)); op = f > 1 ? 1 - (f - 1) / 0.3 : 1; }
    else if (b.k < 4) { x = lerp(1220, SLOT(b.k), MOTION.enter(ta, b.qa, 0.35)); }
    else { const f = (ta - b.qa) / 0.8; if (f > 1) return null; x = 1220 - 26 * f; y = 470 - 50 * f + 300 * f * f; op = 1 - f; }
    return <Dot key={'b' + i} x={x} y={y} r={7} fill={c.blue} op={op} halo={c.halo} />;
  });

  // ── CI ──
  const ciOp = lin(T, E - 0.15, 0.4) * (1 - lin(T, G + 3.4, 1.0));
  const colS = kf(T, [[F, 1], [F + 1, 0.55]]), colTx = kf(T, [[F, 0], [F + 1, -133]]), colTy = kf(T, [[F, 0], [F + 1, 225]]);
  const colOp = 1 - MOTION.enter(T, G, 0.5);
  const judgeOp = MOTION.enter(T, E + 4.6, 0.5) * (1 - MOTION.enter(T, F, 0.6));
  const orphanOut = 1 - MOTION.enter(T, E + 4.5, 0.5);
  const mu = green ? -0.35 : -1.75;
  const xOf = (d) => 1200 + d * 166.67;
  const bins = Array.from({ length: 25 }, (_, j) => { const b = -3 + 0.24 * (j + 0.5); return { x: 700 + j * 40, b, h: 300 * Math.exp(-((b - mu) ** 2) / (2 * 0.25)) }; });
  const ranked = bins.map((_, j) => j).sort((a, b) => Math.abs(bins[a].b - mu) - Math.abs(bins[b].b - mu));
  const rankOf = {}; ranked.forEach((j, r) => { rankOf[j] = r; });
  const hS = kf(T, [[G, 1], [G + 0.8, 0.45]]), hTx = kf(T, [[G, 0], [G + 0.8, -215]]), hTy = kf(T, [[G, 0], [G + 0.8, 269]]);
  const hOp = kf(T, [[G, 1], [G + 0.8, 0.35]]);
  const statOut = 1 - MOTION.enter(T, G, 0.5);
  const bandOp = MOTION.enter(T, F + 4.6, 0.6);
  const markP = MOTION.enter(T, F + 6.8, 0.7);
  const doorOp = MOTION.enter(T, G + 0.1, 0.5);
  const dec = MOTION.enter(T, G + 1.1, 0.5);
  const open = green ? MOTION.draw(T, G + 1.1, 0.7) : 0;
  const verdictCol = green ? c.green : c.red;

  // change token
  let dx = 560, dy = 540, dr = 12, dop = 0;
  if (T >= G + 0.3) {
    dop = lin(T, G + 0.3, 0.3);
    dx = lerp(560, 760, MOTION.enter(T, G + 0.3, 0.7));
    if (green) {
      dx = lerp(dx, 1250, MOTION.draw(T, G + 1.7, 0.9));
      const f = MOTION.draw(T, G + 3.4, 1.6);
      dx = lerp(dx, 270, f); dy = lerp(540, 220, f); dr = lerp(12, 7, f);
      dop *= 1 - lin(T, G + 4.9, 0.5);
    } else {
      dx += 26 * Math.sin(Math.PI * lin(T, G + 1.1, 0.5));
      dop *= 1 - lin(T, G + 3.4, 0.6);
    }
  }

  const idx = T >= G + 3.4 ? 0 : NAMES.reduce((a, n, i) => (T >= C[n] ? i : a), 0);
  const capItems = NAMES.map((n, i) => ({ at: C[n] + 0.5, until: (i < 8 ? C[NAMES[i + 1]] : G + 3.6) - 0.25, text: TX.captions[n] }));
  const t1 = { fontFamily: MONO, fontSize: 18, fill: c.dim };

  return (
    <div data-screen-label={`t=${Math.floor(time)}s`} style={{ position: 'absolute', inset: 0, background: c.bg, overflow: 'hidden' }}>
      <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ position: 'absolute', inset: 0 }}>
        {/* ═══ PART A · carriles ═══ */}
        <g opacity={opA}>
          <g transform={`translate(960,540) scale(${camS}) translate(${-camX},${-camY})`}>
            <g opacity={dimA}>
              {LANES.map((l, i) => (
                <g key={l.k}>
                  {i === 1 && <rect x={-200} y={l.y0} width={2320} height={l.y1 - l.y0} fill={c.band} />}
                  {i === 0 && <line x1={-200} x2={2120} y1={l.y0} y2={l.y0} stroke={c.hair} />}
                  <line x1={-200} x2={2120} y1={l.y1} y2={l.y1} stroke={c.hair} />
                  <text x={80} y={l.y0 + 34} fontFamily={MONO} fontSize={16} letterSpacing={3} fill={c.dim}>{TX.lanes[l.k].toUpperCase()}</text>
                </g>
              ))}
              {/* routes */}
              <path d={R_DIRECT.d} fill="none" stroke={c.line} strokeWidth={2} pathLength={1} strokeDasharray="1 1" strokeDashoffset={-retract} opacity={1 - retract * 0.5} />
              <path d={R_MAIN.d} fill="none" stroke={c.line} strokeWidth={2} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - routeIn} />
              {/* telemetry wiring */}
              <g opacity={telOp}>
                <line x1={1120} y1={470} x2={1600} y2={470} stroke={c.blue} strokeOpacity={0.45} strokeWidth={2} />
                <rect x={1220} y={440} width={300} height={60} rx={8} fill={c.panel} stroke={c.blue} strokeOpacity={qFull ? 0.95 : 0.55} strokeWidth={1.5} />
                {[1, 2, 3].map((k) => <line key={k} x1={1220 + k * 75} x2={1220 + k * 75} y1={448} y2={492} stroke={c.blue} strokeOpacity={0.3} />)}
                <text x={1220} y={428} {...t1}>{TX.queue.title}{qFull ? ' · ' + TX.queue.full : ''}</text>
                <StatusChip x={1520} y={378} status="hecho" c={c} />
                <text x={1220} y={536} {...t1}>{TX.queue.dropped} <tspan fill={c.blue} fontWeight={600}>{dropped}</tspan></text>
                <rect x={1600} y={420} width={220} height={100} rx={10} fill={c.panel} stroke={c.blue} strokeOpacity={0.7 * (1 - dead)} strokeWidth={1.5} />
                <rect x={1600} y={420} width={220} height={100} rx={10} fill={c.gray} opacity={dead * 0.85} stroke={c.line} strokeWidth={1.5} />
                <text x={1622} y={466} fontFamily={FONT} fontSize={26} fontWeight={500} fill={dead > 0.5 ? c.dim : c.ink}>{TX.db.title}</text>
                <text x={1622} y={496} {...t1}>{dead > 0.5 ? TX.db.down : TX.db.sub}</text>
                <StatusChip x={1820} y={378} status="hecho" c={c} />
              </g>
              {/* blocks */}
              <Block x={120} y={170} w={300} h={100} title={TX.app.title} c={c} op={1 - 0.55 * cutAmt} />
              <g opacity={1 - 0.55 * cutAmt}>
                <text x={120} y={312} fontFamily={MONO} fontSize={18} fill={c.dim}>{TX.app.envKey}</text>
                <text x={293} y={312 - 12 * envS} fontFamily={MONO} fontSize={18} fill={c.dim} opacity={1 - envS}>{TX.app.envOld}</text>
                <text x={293} y={312 + 12 * (1 - envS)} fontFamily={MONO} fontSize={18} fontWeight={600} fill={c.ink} opacity={envS}>{TX.app.envNew}</text>
                <line x1={293} x2={293 + TX.app.envNew.length * 10.8 * envS} y1={320} y2={320} stroke={c.ink} strokeWidth={1.5} opacity={envS} />
              </g>
              {cutAmt > 0 && (
                <g opacity={cutAmt}>
                  <rect x={478 - 17 * cutAmt} y={210} width={34 * cutAmt} height={20} fill={c.bg} />
                  <line x1={478 - 17 * cutAmt} x2={478 - 17 * cutAmt} y1={210} y2={230} stroke={c.ink} strokeWidth={2} />
                  <line x1={478 + 17 * cutAmt} x2={478 + 17 * cutAmt} y1={210} y2={230} stroke={c.ink} strokeWidth={2} />
                  <text x={436} y={198} fontFamily={MONO} fontSize={17} fill={c.ink}>{TX.app.cut}</text>
                </g>
              )}
              <Block x={1410} y={815} w={450} h={100} title={TX.provider.title} sub={TX.provider.sub} c={c} titleSize={24} />
              <Block x={720} y={410} w={400} h={120} title={TX.proxy.title} sub={TX.proxy.sub} status="hecho" c={c} textDy={-22} op={clamp01(proxyP)} scale={0.7 + 0.3 * proxyP} />
              <g opacity={clamp01(cntP)} transform={`translate(840,655) scale(${0.8 + 0.2 * cntP}) translate(-840,-655)`}>
                <rect x={720} y={610} width={240} height={90} rx={10} fill={c.panel} stroke={c.amber} strokeOpacity={0.7} strokeWidth={1.5} />
                <text x={740} y={640} fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.counter.label}</text>
                <text x={740} y={684} fontFamily={MONO} fontSize={38} fontWeight={600} fill={c.amber}>{String(count).padStart(4, '0')}</text>
              </g>
              {dotEls}
              {blueEls}
            </g>
            {/* registro de uso (survives the dim; zooms in scene 6) */}
            <g opacity={recOp} transform={`translate(${recX},${recY}) scale(${recS})`}>
              <rect x={0} y={0} width={360} height={118} rx={10} fill={c.panel} stroke={c.amber} strokeWidth={1.5} strokeDasharray={s6 > 0.02 ? PD : null} />
              <text x={20} y={34} fontFamily={MONO} fontSize={18} fontWeight={600} fill={c.amber}>{TX.record.title}</text>
              <text x={20} y={68} fontFamily={MONO} fontSize={17} fill={c.ink}>{TX.record.l1}</text>
              <text x={20} y={96} fontFamily={MONO} fontSize={17} fill={c.dim}>{TX.record.l2}</text>
            </g>
          </g>

          {/* scene 6 · precios (pendiente) */}
          <g opacity={priceOp} transform={`translate(0,${(1 - priceOp) * 20})`}>
            {[2, 1].map((k) => (
              <g key={k} transform={`translate(${k * 30},${-k * 30})`}>
                <rect x={1000} y={330} width={620} height={290} rx={10} fill={c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={PD} />
                <text x={1560} y={358} textAnchor="end" fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.prices.old[2 - k]}</text>
                <Lock x={1574} y={341} c={c} />
              </g>
            ))}
            <rect x={1000} y={330} width={620} height={290} rx={10} fill={c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={PD} />
            <text x={1028} y={376} fontFamily={FONT} fontSize={26} fontWeight={500} fill={c.ink}>{TX.prices.title} · {TX.prices.version}</text>
            <text x={1592} y={376} textAnchor="end" fontFamily={MONO} fontSize={17} fill={c.dim}>{TX.prices.date}</text>
            <line x1={1000} x2={1620} y1={396} y2={396} stroke={c.faint} />
            {TX.prices.cols.map((h, k) => <text key={h} x={[1028, 1300, 1460][k]} y={428} fontFamily={MONO} fontSize={16} fill={c.dim}>{h}</text>)}
            <rect x={1012} y={444} width={596} height={38} rx={6} fill={c.amber} opacity={0.14 * hl} stroke={c.amber} strokeOpacity={hl} />
            {TX.prices.rows.map((r, i) => r.map((v, k) => <text key={i + '-' + k} x={[1028, 1300, 1460][k]} y={470 + i * 44} fontFamily={MONO} fontSize={20} fill={c.ink}>{v}</text>))}
            <text x={1028} y={600} fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.prices.unit}</text>
            <StatusChip x={1680} y={232} status="en curso" c={c} />
            <text x={1620} y={656} textAnchor="end" fontFamily={MONO} fontSize={15} fill={c.dim}>{TX.prices.example}</text>
            <path d="M760,410 L1012,463" fill="none" stroke={c.amber} strokeWidth={2} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - conn} />
            <path d="M886,436 L886,690" fill="none" stroke={c.amber} strokeWidth={2} strokeDasharray="6 6" opacity={clamp01(costP)} />
            <g opacity={clamp01(costP)} transform={`translate(886,750) scale(${0.85 + 0.15 * costP}) translate(-886,-750)`}>
              <rect x={646} y={690} width={480} height={124} rx={10} fill={c.panel} stroke={c.amber} strokeWidth={1.5} strokeDasharray={PD} />
              <text x={670} y={724} fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.prices.cost}</text>
              <text x={670} y={770} fontFamily={MONO} fontSize={38} fontWeight={600} fill={c.amber}>{TX.prices.costValue}</text>
              <text x={670} y={800} fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.prices.costSub}</text>
            </g>
          </g>

          {/* legend */}
          <g opacity={1 - s6 * 0.6}>
            {[['traffic', c.traffic], ['accounting', c.amber], ['telemetry', c.blue]].map(([k, col], i) => (
              <g key={k} transform={`translate(64,${984 + i * 30})`}>
                <circle cx={6} cy={-6} r={6} fill={col} />
                <text x={24} y={0} fontFamily={MONO} fontSize={16} fill={c.dim}>{TX.legend[k]}</text>
              </g>
            ))}
          </g>
        </g>

        {/* ═══ PART B · CI ═══ */}
        <g opacity={ciOp}>
          <text x={120} y={164} fontFamily={MONO} fontSize={16} letterSpacing={3} fill={c.dim} opacity={statOut}>{TX.ci.header.toUpperCase()}</text>
          {/* scene 7 · columnas */}
          <g transform={`translate(${colTx},${colTy}) scale(${colS})`} opacity={colOp}>
            <g opacity={MOTION.enter(T, E + 0.05)}>
              <rect x={590} y={184} width={280} height={38} rx={19} fill="none" stroke={c.faint} strokeDasharray="4 4" />
              <text x={730} y={209} textAnchor="middle" fontFamily={MONO} fontSize={17} fill={c.dim}>{TX.ci.generator}</text>
              <text x={560} y={272} textAnchor="middle" fontFamily={FONT} fontSize={24} fontWeight={500} fill={c.ink}>{TX.ci.base}</text>
              <text x={900} y={272} textAnchor="middle" fontFamily={FONT} fontSize={24} fontWeight={500} fill={c.ink}>{TX.ci.branch}</text>
            </g>
            {CASES.map((i) => {
              const lp = MOTION.draw(T, E + 1.1 + i * 0.15, 0.4);
              const ts = E + 5.4 + i * 0.55;
              const sc = MOTION.enter(T, ts + 0.45, 0.4);
              const label = TX.ci.caseLabel + ' ' + pad2(i + 1);
              return (
                <g key={i}>
                  <line x1={660} x2={660 + 140 * lp} y1={rowY(i)} y2={rowY(i)} stroke={c.ink} strokeWidth={2} />
                  <Pill x={560} y={rowY(i)} label={label} c={c} op={clamp01(MOTION.pop(T, E + 0.15 + i * 0.08))} />
                  <Pill x={900} y={rowY(i)} label={label} c={c} op={clamp01(MOTION.pop(T, E + 0.3 + i * 0.08))} />
                  <rect x={1014} y={rowY(i) - 4} width={70 * SCORES[i] * sc} height={8} rx={4} fill={c.ink} opacity={sc} />
                </g>
              );
            })}
            <g opacity={orphanOut}>
              <Pill x={560} y={rowY(6)} label="?" c={c} ghost op={MOTION.enter(T, E + 3.1, 0.4)} />
              <Pill x={900} y={rowY(6)} label={TX.ci.caseLabel + ' 07'} c={c} op={clamp01(MOTION.pop(T, E + 2.9))} />
              <g opacity={MOTION.enter(T, E + 3.3, 0.4)}>
                <rect x={1020} y={rowY(6) - 11} width={22} height={22} fill={c.ink} transform={`rotate(45 1031 ${rowY(6)})`} />
                <text x={1031} y={rowY(6) + 6} textAnchor="middle" fontFamily={MONO} fontSize={16} fontWeight={700} fill={c.bg}>!</text>
                <text x={1062} y={rowY(6) + 7} fontFamily={MONO} fontSize={19} fill={c.ink}>{TX.ci.orphan}</text>
              </g>
            </g>
          </g>
          {/* juez + caché */}
          <g opacity={judgeOp}>
            <Block x={1240} y={380} w={320} h={100} title={TX.ci.judge} sub={TX.ci.judgeSub} status="pendiente" c={c} pending />
            <rect x={1240} y={540} width={320} height={80} rx={10} fill={c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={PD} />
            <text x={1262} y={588} fontFamily={MONO} fontSize={18} fill={c.dim}>{TX.ci.cache}</text>
            {CASES.map((i) => <rect key={i} x={1360 + i * 30} y={570} width={20} height={20} rx={3} fill={c.ink} fillOpacity={MOTION.enter(T, E + 5.75 + i * 0.55, 0.3)} stroke={c.line} />)}
            {CASES.map((i) => {
              const f = lin(T, E + 5.4 + i * 0.55, 0.35);
              if (f <= 0 || f >= 1) return null;
              const e = MOTION.enter(T, E + 5.4 + i * 0.55, 0.35);
              return <Dot key={i} x={lerp(730, 1240, e)} y={lerp(rowY(i), 430, e)} r={6} fill={c.ink} halo={0} />;
            })}
          </g>
          {/* scene 8 · distribución */}
          <g transform={`translate(${hTx},${hTy}) scale(${hS})`} opacity={hOp}>
            <g opacity={MOTION.enter(T, F + 0.8)}>
              <line x1={700} x2={1700} y1={780} y2={780} stroke={c.line} strokeWidth={1.5} />
              <line x1={1200} x2={1200} y1={780} y2={792} stroke={c.line} strokeWidth={1.5} />
              <text x={1200} y={814} textAnchor="middle" fontFamily={MONO} fontSize={17} fill={c.dim}>0</text>
              <text x={1200} y={846} textAnchor="middle" fontFamily={MONO} fontSize={17} fill={c.dim} opacity={statOut}>{TX.stats.axis}</text>
              <text x={1700} y={410} textAnchor="end" fontFamily={MONO} fontSize={17} fill={c.dim} opacity={statOut}>{TX.stats.bootstrap}</text>
            </g>
            <g opacity={bandOp}>
              <rect x={xOf(-1.1)} y={430} width={xOf(1.1) - xOf(-1.1)} height={350} fill={c.ink} opacity={0.05} />
              <line x1={xOf(-1.1)} x2={xOf(-1.1)} y1={430} y2={780} stroke={c.ink} strokeDasharray="5 5" />
              <line x1={xOf(1.1)} x2={xOf(1.1)} y1={430} y2={780} stroke={c.ink} strokeDasharray="5 5" />
              <text x={1200} y={456} textAnchor="middle" fontFamily={MONO} fontSize={18} fill={c.ink}>{TX.stats.band}</text>
            </g>
            {bins.map((bn, j) => {
              const g = MOTION.enter(T, F + 1.0 + rankOf[j] * 0.09, 0.45);
              const h = bn.h * g;
              return h > 2 ? <rect key={j} x={bn.x + 3} y={780 - h} width={34} height={h} rx={2} fill={c.ink} opacity={0.42} stroke={c.ink} strokeOpacity={0.6} strokeDasharray="4 3" /> : null;
            })}
            <g opacity={markP}>
              <line x1={xOf(mu)} x2={xOf(mu)} y1={lerp(330, 420, markP)} y2={780} stroke={c.ink} strokeWidth={3} />
              <circle cx={xOf(mu)} cy={lerp(330, 420, markP)} r={7} fill={c.ink} />
              <text x={xOf(mu)} y={lerp(310, 400, markP)} textAnchor="middle" fontFamily={MONO} fontSize={18} fontWeight={600} fill={c.ink}>{TX.stats.measured}</text>
            </g>
          </g>
          <g opacity={statOut}>
            <g opacity={MOTION.enter(T, F + 5.4)}>
              <rect x={1360} y={130} width={380} height={170} rx={10} fill={c.panel} stroke={c.line} strokeWidth={1.5} strokeDasharray={PD} />
              <text x={1384} y={166} fontFamily={MONO} fontSize={18} fontWeight={600} fill={c.ink}>{TX.stats.goals[0]}</text>
              <text x={1384} y={206} fontFamily={MONO} fontSize={18} fill={c.dim}>{TX.stats.goals[1]}</text>
              <text x={1408} y={238} fontFamily={MONO} fontSize={18} fill={c.ink}>{TX.stats.goals[2]}</text>
              <text x={1408} y={270} fontFamily={MONO} fontSize={18} fill={c.dim}>{TX.stats.goals[3]}</text>
            </g>
            <path d={`M1380,300 L${xOf(-1.1)},430`} fill="none" stroke={c.ink} strokeWidth={2} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - MOTION.draw(T, F + 6.0, 0.6)} />
            <text x={xOf(-1.1) - 12} y={470} textAnchor="end" fontFamily={MONO} fontSize={17} fill={c.ink} opacity={MOTION.enter(T, F + 6.4)}>{TX.stats.threshold}</text>
            <text x={1200} y={900} textAnchor="middle" fontFamily={FONT} fontSize={30} fontWeight={500} fill={c.ink} opacity={MOTION.enter(T, F + 8.0)}>{green ? TX.stats.inside : TX.stats.outside}</text>
          </g>
          {/* scene 9 · puerta */}
          <g opacity={doorOp}>
            <StatusChip x={1120} y={290} status="pendiente" c={c} />
            <rect x={800} y={330} width={320} height={420} rx={6} fill="none" stroke={c.line} strokeWidth={2} strokeDasharray={PD} />
            {[0, 1].map((k) => {
              const w = 154 * (1 - 0.88 * open), x = k === 0 ? 806 : 1114 - w;
              return (
                <g key={k}>
                  <rect x={x} y={336} width={w} height={408} rx={3} fill={c.panel} stroke={c.line} strokeWidth={1.5} />
                  <rect x={x} y={336} width={w} height={408} rx={3} fill={verdictCol} opacity={0.22 * dec} stroke={verdictCol} strokeOpacity={dec} strokeWidth={2} />
                </g>
              );
            })}
            {!green && <g opacity={dec}><Lock x={944} y={516} c={{ dim: c.red }} s={2} /></g>}
            <g opacity={dec}>
              <text x={960} y={806} textAnchor="middle" fontFamily={MONO} fontSize={36} fontWeight={600} fill={verdictCol}>{green ? TX.gate.pass : TX.gate.fail}</text>
              <text x={960} y={844} textAnchor="middle" fontFamily={FONT} fontSize={24} fill={c.ink}>{green ? TX.gate.passSub : TX.gate.failSub}</text>
            </g>
            <text x={1380} y={300} fontFamily={MONO} fontSize={17} fill={c.dim} opacity={MOTION.enter(T, G + 1.6)}>{TX.gate.metersTitle}</text>
            {TX.gate.meters.map((m, i) => {
              const y = 380 + i * 140, p = clamp01(MOTION.pop(T, G + 1.8 + i * 0.25));
              return (
                <g key={m} opacity={p}>
                  <path d={`M1380,${y + 24} A44,44 0 0 1 1468,${y + 24}`} fill="none" stroke={c.line} strokeWidth={6} strokeDasharray="6 6" />
                  <line x1={1380} x2={1468} y1={y + 24} y2={y + 24} stroke={c.faint} />
                  <text x={1496} y={y + 4} fontFamily={FONT} fontSize={24} fontWeight={500} fill={c.ink}>{m}</text>
                  <text x={1496} y={y + 34} fontFamily={MONO} fontSize={17} fill={c.dim}>{TX.gate.unmeasured}</text>
                </g>
              );
            })}
          </g>
        </g>
        {/* the change token (crosses the gate, becomes "tu app") */}
        <g opacity={dop}>
          <text x={dx} y={dy - 30} textAnchor="middle" fontFamily={MONO} fontSize={17} fill={c.ink} opacity={1 - lin(T, G + 3.4, 0.4)}>{TX.gate.change}</text>
          <Dot x={dx} y={dy} r={dr} fill={c.traffic} halo={c.halo} />
        </g>

        {/* ═══ header ═══ */}
        <g>
          <text x={60} y={62} fontFamily={MONO} fontSize={22} fontWeight={600} fill={c.ink}>{TX.brand}</text>
          <line x1={190} x2={190} y1={40} y2={70} stroke={c.faint} />
          <text x={214} y={62} fontFamily={MONO} fontSize={22} fill={c.dim}>{pad2(idx + 1)} / 09</text>
          <text x={330} y={62} fontFamily={FONT} fontSize={26} fontWeight={500} fill={c.ink}>{TX.scenes[NAMES[idx]]}</text>
          {NAMES.map((n, i) => (
            <g key={n}>
              <StatusGlyph x={1250 + i * 36} y={54} status={STATUS[i]} c={c} r={i === idx ? 7 : 5} />
              {i === idx && <line x1={1240 + i * 36} x2={1260 + i * 36} y1={74} y2={74} stroke={c.ink} strokeWidth={2} />}
            </g>
          ))}
          <StatusChip x={1860} y={36} status={STATUS[idx]} c={c} size={17} />
        </g>
      </svg>
      {tw.captions && (
        <Captions items={capItems} style={{ left: '24%', right: '24%', bottom: '3.6%', fontFamily: FONT, fontSize: 38, fontWeight: 500, lineHeight: 1.25, color: c.ink, textShadow: 'none', textWrap: 'balance' }} />
      )}
    </div>
  );
}

function EvalgateApp() {
  const [t, setTweak] = useTweaks(window.TWEAK_DEFAULTS);
  const c = THEMES[t.theme] || THEMES.oscuro;
  return (
    <React.Fragment>
      <CompositionStage width={1920} height={1080} scenes={window.OM_SCENES} playback={window.OM_PLAYBACK} bg={c.bg}>
        <Piece tw={t} />
      </CompositionStage>
      <TweaksPanel>
        <TweakSection label="Aspecto" />
        <TweakRadio label="Tema" value={t.theme} options={['oscuro', 'claro']} onChange={(v) => setTweak('theme', v)} />
        <TweakToggle label="Rótulos" value={t.captions} onChange={(v) => setTweak('captions', v)} />
        <TweakSection label="Puerta (escenas 8–9)" />
        <TweakRadio label="Resultado" value={t.gate} options={['verde', 'rojo']} onChange={(v) => setTweak('gate', v)} />
        <TweakSection label="Editor" />
        <TweakToggle label="Motion editor" value={t.motionEditor} onChange={(v) => setTweak('motionEditor', v)} />
      </TweaksPanel>
    </React.Fragment>
  );
}
window.EvalgateApp = EvalgateApp;
