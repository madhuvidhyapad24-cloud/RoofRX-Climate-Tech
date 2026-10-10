/* RoofRx website UI. All numbers come from web/engine.js (checked against Python). */
(function () {
  'use strict';
  var R = window.RoofRx, D = window.ROOFRX_DATA;
  var $ = function (id) { return document.getElementById(id); };
  var N_SEEDS = 30, CURVE_PTS = 40, MAT = R.MATERIALS.map(function (m) { return m.name; });

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function inr(x) { return '₹' + Math.round(x).toLocaleString('en-IN'); }
  function f1(x) { return (Math.round(x * 10) / 10).toFixed(1); }
  function f2(x) { return (Math.round(x * 100) / 100).toFixed(2); }
  function compactInr(x) {
    if (x >= 1e7) return '₹' + (x / 1e7).toFixed(x % 1e7 ? 1 : 0).replace(/\.0$/, '') + ' Cr';
    if (x >= 1e5) return '₹' + (x / 1e5).toFixed(x % 1e5 ? 1 : 0).replace(/\.0$/, '') + ' L';
    if (x >= 1e3) return '₹' + (x / 1e3).toFixed(x % 1e3 ? 1 : 0).replace(/\.0$/, '') + 'k';
    return '₹' + Math.round(x);
  }
  function pct(x) { return x !== x ? 'n/a' : (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(1) + '%'; }
  function niceCeil(x) {
    var p = Math.pow(10, Math.floor(Math.log10(x))), m = x / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
  }
  var toastTimer;
  function toast(t) {
    var el = $('toast'); el.textContent = t; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.hidden = true; }, 2200);
  }

  var S = {
    b: null, eng: null, sc: null, cb: null, roofOrder: null, orders: null, curve: null,
    sel: [], rank: null, cmp: null, maxBudget: 5000000, view: 'treated', synthetic: true,
    px: null, py: null, showAll: false, geom: null,
    metric: 'degree', weather: R.syntheticWeather(), wxKey: 'synthetic'
  };
  var CITIES = {
    erode: ['Erode', 11.341, 77.717], chennai: ['Chennai', 13.083, 80.270], hyderabad: ['Hyderabad', 17.385, 78.487],
    ahmedabad: ['Ahmedabad', 23.023, 72.572], nagpur: ['Nagpur', 21.146, 79.088], jaipur: ['Jaipur', 26.912, 75.787], delhi: ['Delhi', 28.614, 77.209]
  };
  function fmtHeat(v) { return S.metric === 'degree' ? Math.round(v).toLocaleString('en-IN') : f1(v); }
  function U() {
    var thr = f1(params().thr);
    return S.metric === 'degree'
      ? { unit: '°C·h', legend: 'Degree-hours per day above ' + thr + ' °C', now: 'Heat above', avoided: 'Heat avoided', head: '°C·h/day above', headAv: '°C·h avoided', kpi: 'less heat per day above ' + thr + ' °C in each treated home (degree-hours), on average' }
      : { unit: 'h', legend: 'Hours per day above ' + thr + ' °C', now: 'Hours above', avoided: 'Avoided', head: 'Hours/day above', headAv: 'Hours avoided', kpi: 'fewer hours per day above ' + thr + ' °C in each treated home, on average' };
  }

  /* ---------- parameters ---------- */
  function params() {
    var cost = parseFloat($('cost').value), fixed = parseFloat($('fixed').value);
    return {
      budget: parseFloat($('budget').value),
      cost: cost > 0 ? cost : 250,
      fixed: fixed >= 0 ? fixed : 0,
      thr: parseFloat($('thr').value)
    };
  }

  /* ---------- map ---------- */
  function buildMap() {
    var b = S.b, n = b.n, i;
    var minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity, sLat = 0;
    for (i = 0; i < n; i++) {
      minLat = Math.min(minLat, b.lat[i]); maxLat = Math.max(maxLat, b.lat[i]);
      minLon = Math.min(minLon, b.lon[i]); maxLon = Math.max(maxLon, b.lon[i]); sLat += b.lat[i];
    }
    var kx = Math.cos((sLat / n) * Math.PI / 180);
    var w = Math.max((maxLon - minLon) * kx, 1e-4), h = Math.max(maxLat - minLat, 1e-4);
    var pad = 30, W = 1000, Hmax = 640;
    var s = Math.min((W - 2 * pad) / w, (Hmax - 2 * pad) / h);
    var VW = w * s + 2 * pad, VH = h * s + 2 * pad;
    S.px = new Float64Array(n); S.py = new Float64Array(n);
    for (i = 0; i < n; i++) { S.px[i] = pad + (b.lon[i] - minLon) * kx * s; S.py[i] = pad + (maxLat - b.lat[i]) * s; }
    var unit = s / 111; // viewBox units per km
    var steps = [0.25, 0.5, 1, 2, 5, 10, 25, 50, 100], gk = 100;
    for (i = 0; i < steps.length; i++) if (steps[i] * unit >= 80) { gk = steps[i]; break; }
    var grid = '', x;
    for (x = pad; x <= VW - pad + 0.1; x += gk * unit) grid += '<line x1="' + x.toFixed(1) + '" y1="' + pad + '" x2="' + x.toFixed(1) + '" y2="' + (VH - pad).toFixed(1) + '"/>';
    for (x = pad; x <= VH - pad + 0.1; x += gk * unit) grid += '<line x1="' + pad + '" y1="' + x.toFixed(1) + '" x2="' + (VW - pad).toFixed(1) + '" y2="' + x.toFixed(1) + '"/>';
    var wl = '', nW = b.wardNames.length, cx = new Float64Array(nW), cy = new Float64Array(nW), cn = new Float64Array(nW);
    for (i = 0; i < n; i++) { cx[b.ward[i]] += S.px[i]; cy[b.ward[i]] += S.py[i]; cn[b.ward[i]]++; }
    if (nW <= 40) for (i = 0; i < nW; i++) if (cn[i]) wl += '<text class="wardlabel" style="font-size:' + (15 * k).toFixed(1) + 'px;stroke-width:' + (4 * k).toFixed(1) + 'px" text-anchor="middle" x="' + (cx[i] / cn[i]).toFixed(1) + '" y="' + (cy[i] / cn[i]).toFixed(1) + '">' + esc(b.wardNames[i]) + '</text>';
    var cw = $('map').clientWidth || 800, k = Math.max(1, 720 / cw), kd = Math.min(k, 1.7);
    S.mapK = Math.round(k * 10) / 10;
    var r = (n > 2500 ? 2.4 : n > 1500 ? 3.2 : 4) * kd;
    var dots = '';
    for (i = 0; i < n; i++) dots += '<circle class="d h0" cx="' + S.px[i].toFixed(1) + '" cy="' + S.py[i].toFixed(1) + '" r="' + r + '" data-i="' + i + '"/>';
    var gtxt = gk >= 1 ? gk + ' km' : (gk * 1000) + ' m';
    $('map').setAttribute('viewBox', '0 0 ' + VW.toFixed(1) + ' ' + VH.toFixed(1));
    $('map').innerHTML = '<g class="grid">' + grid + '</g><g id="g-ward">' + wl + '</g><g id="g-base">' + dots + '</g><g id="g-sel"></g>' +
      '<text class="scale" x="' + pad + '" y="' + (VH - 8).toFixed(1) + '" style="fill:var(--muted);font:500 ' + (13 * k).toFixed(1) + 'px var(--font-body)">Grid squares are ' + gtxt + ' wide</text>';
    S.geom = { r: r, selR: r + 2.6 * kd };
    S.dots = $('g-base').children;
  }

  function paintHeat() {
    var h = S.sc.hNow, n = S.b.n, mn = Infinity, mx = -Infinity, i;
    for (i = 0; i < n; i++) { if (h[i] < mn) mn = h[i]; if (h[i] > mx) mx = h[i]; }
    var span = Math.max(mx - mn, 1e-9);
    for (i = 0; i < n; i++) {
      var bin = Math.min(4, Math.floor(5 * (h[i] - mn) / span));
      S.dots[i].setAttribute('class', 'd h' + bin);
    }
    S.heatRange = [mn, mx];
  }

  function paintSelected() {
    var out = '', k, i;
    for (k = 0; k < S.sel.length; k++) {
      i = S.sel[k];
      out += '<circle class="sel" cx="' + S.px[i].toFixed(1) + '" cy="' + S.py[i].toFixed(1) + '" r="' + S.geom.selR + '" data-i="' + i + '"/>';
    }
    $('g-sel').innerHTML = out;
    $('g-sel').setAttribute('display', S.view === 'treated' ? 'inline' : 'none');
    $('map').setAttribute('aria-label', 'Map of ' + S.b.n.toLocaleString('en-IN') + ' roofs. ' + S.sel.length + ' selected for treatment.');
  }

  function paintLegend() {
    var p = params(), r = S.heatRange || [0, 0];
    var heat = '<span class="key"><span class="ramp"><i></i><i></i><i></i><i></i><i></i></span>' + U().legend + ': ' + fmtHeat(r[0]) + ' to ' + fmtHeat(r[1]) + '</span>';
    $('legend').innerHTML = S.view === 'treated'
      ? '<span class="key"><span class="sw sel"></span>Treated with a cool coating</span>' + heat
      : heat;
  }

  /* ---------- tooltip on the map ---------- */
  function showTip(e) {
    var t = e.target, tip = $('tip');
    if (!t || !t.getAttribute || t.getAttribute('data-i') === null) { tip.hidden = true; return; }
    var i = +t.getAttribute('data-i'), b = S.b, wrap = $('mapwrap').getBoundingClientRect();
    var rk = S.rank[i];
    tip.innerHTML = '<b>Roof ' + esc(b.id[i]) + (rk ? ' · rank ' + rk : '') + '</b>' +
      '<span><em>Ward</em>' + esc(b.wardNames[b.ward[i]]) + '</span>' +
      '<span><em>Roof</em>' + MAT[b.mat[i]] + ', ' + b.storeys[i] + (b.storeys[i] === 1 ? ' storey' : ' storeys') + '</span>' +
      '<span><em>Area</em>' + f1(b.area[i]) + ' m²</span>' +
      '<span><em>' + U().now + '</em>' + fmtHeat(S.sc.hNow[i]) + ' ' + U().unit + '/day</span>' +
      '<span><em>' + U().avoided + '</em>' + fmtHeat(S.sc.avoided[i]) + ' ' + U().unit + '/day</span>';
    tip.hidden = false;
    var x = e.clientX - wrap.left + 14, y = e.clientY - wrap.top + 14;
    if (x + tip.offsetWidth > wrap.width - 4) x = e.clientX - wrap.left - tip.offsetWidth - 14;
    if (y + tip.offsetHeight > wrap.height - 4) y = e.clientY - wrap.top - tip.offsetHeight - 14;
    tip.style.left = Math.max(4, x) + 'px'; tip.style.top = Math.max(4, y) + 'px';
  }

  /* ---------- KPIs ---------- */
  function paintKpis(p) {
    var c = S.cmp, k = S.sel.length, i, s = 0;
    for (i = 0; i < k; i++) s += S.sc.avoided[S.sel[i]];
    $('k-gain').textContent = pct(c.gainWard);
    $('k-gain-note').textContent = k
      ? 'more modelled relief than treating random roofs in the hottest wards. ' + pct(c.gainRand) + ' versus random roofs anywhere.'
      : S.roofOrder.length === 0
        ? 'At ' + f1(p.thr) + ' °C no roof gets hot enough in this weather. Lower the danger threshold.'
        : 'Raise the budget to treat at least one roof.';
    $('k-roofs').textContent = k.toLocaleString('en-IN') + ' of ' + S.b.n.toLocaleString('en-IN');
    $('k-spent').textContent = inr(c.roof.spent) + ' of ' + inr(p.budget);
    $('k-hours').textContent = (k ? fmtHeat(s / k) : '0') + ' ' + U().unit;
    $('k-hours-note').textContent = U().kpi;
  }

  /* ---------- chart ---------- */
  var CH = { W: 640, H: 300, l: 58, r: 88, t: 26, b: 40 };
  function xs(v) { return CH.l + v / S.maxBudget * (CH.W - CH.l - CH.r); }
  function ys(v) { return CH.H - CH.b - v / S.yMax * (CH.H - CH.t - CH.b); }

  function paintChart(p) {
    var c = S.curve, i, last = c.x.length - 1;
    var cw = Math.round($('chartwrap').clientWidth) || 640, narrow = cw < 480;
    CH.W = Math.max(300, Math.min(760, cw)); CH.H = narrow ? 270 : 300; CH.l = narrow ? 58 : 58; CH.r = narrow ? 76 : 88;
    $('chart').setAttribute('viewBox', '0 0 ' + CH.W + ' ' + CH.H);
    $('chart-note').textContent = 'Relief score = heat avoided per day (' + U().unit + ') × ' + (S.b.people ? 'people in the building' : 'roof area in m². Area stands in for the number of people, which is an assumption') + '. Baselines average ' + N_SEEDS + ' random draws.';
    var top = Math.max(c.roof[last], c.ward[last], c.rand[last], 1e-9);
    var ystep = niceCeil(top / 4 * 0.999);
    S.yMax = Math.ceil(top / ystep) * ystep;
    var g = '', t;
    for (t = 0; t <= S.yMax + 1e-9; t += ystep) {
      g += '<line class="' + (t === 0 ? 'axis' : 'gridl') + '" x1="' + CH.l + '" x2="' + (CH.W - CH.r) + '" y1="' + ys(t).toFixed(1) + '" y2="' + ys(t).toFixed(1) + '"/>' +
        '<text x="' + (CH.l - 8) + '" y="' + (ys(t) + 4).toFixed(1) + '" text-anchor="end" class="num">' + Math.round(t).toLocaleString('en-IN') + '</text>';
    }
    var xt = niceCeil(S.maxBudget / (CH.W < 480 ? 3 : 5));
    for (t = 0; t <= S.maxBudget + 1e-9; t += xt) {
      g += '<text x="' + xs(t).toFixed(1) + '" y="' + (CH.H - CH.b + 18) + '" text-anchor="middle" class="num">' + compactInr(t) + '</text>';
    }
    g += '<text x="' + ((CH.l + CH.W - CH.r) / 2) + '" y="' + (CH.H - 4) + '" text-anchor="middle">Budget</text>';
    function path(a) { return a.map(function (v, k) { return (k ? 'L' : 'M') + xs(c.x[k]).toFixed(1) + ' ' + ys(v).toFixed(1); }).join(''); }
    g += '<path class="ln l-rand" d="' + path(c.rand) + '"/><path class="ln l-ward" d="' + path(c.ward) + '"/><path class="ln l-roof" d="' + path(c.roof) + '"/>';
    // end labels, pushed apart so they never overlap
    var labs = [{ k: 'roof', t: 'Roof-level', y: ys(c.roof[last]) }, { k: 'ward', t: 'Ward-level', y: ys(c.ward[last]) }, { k: 'rand', t: 'Random', y: ys(c.rand[last]) }];
    labs.sort(function (a, b2) { return a.y - b2.y; });
    for (i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 16) labs[i].y = labs[i - 1].y + 16;
    labs.forEach(function (L) { g += '<text class="endl ' + L.k + '" x="' + (CH.W - CH.r + 8) + '" y="' + (L.y + 4).toFixed(1) + '">' + L.t + '</text>'; });
    // current budget
    var cx = xs(p.budget);
    g += '<line class="cur" x1="' + cx.toFixed(1) + '" x2="' + cx.toFixed(1) + '" y1="' + CH.t + '" y2="' + (CH.H - CH.b) + '"/>';
    var anchor = cx > CH.W - CH.r - 70 ? 'end' : 'start', lx = anchor === 'end' ? cx - 6 : cx + 6;
    g += '<text class="curlab" x="' + lx.toFixed(1) + '" y="' + (CH.t - 8) + '" text-anchor="' + anchor + '">Your budget ' + compactInr(p.budget) + '</text>';
    var cm = S.cmp;
    g += '<circle class="pt pt-rand" cx="' + cx.toFixed(1) + '" cy="' + ys(cm.randMean).toFixed(1) + '" r="4.5"/>' +
      '<circle class="pt pt-ward" cx="' + cx.toFixed(1) + '" cy="' + ys(cm.wardMean).toFixed(1) + '" r="4.5"/>' +
      '<circle class="pt pt-roof" cx="' + cx.toFixed(1) + '" cy="' + ys(cm.roof.benefit).toFixed(1) + '" r="5.5"/>';
    g += '<line class="hov" id="hov" y1="' + CH.t + '" y2="' + (CH.H - CH.b) + '" hidden/>';
    $('chart').innerHTML = g;

    var rows = '<thead><tr><th>Budget</th><th>Roof-level</th><th>Ward-level</th><th>Random</th></tr></thead><tbody>';
    for (i = 0; i <= last; i += 4) rows += '<tr><td>' + inr(c.x[i]) + '</td><td>' + Math.round(c.roof[i]).toLocaleString('en-IN') + '</td><td>' + Math.round(c.ward[i]).toLocaleString('en-IN') + '</td><td>' + Math.round(c.rand[i]).toLocaleString('en-IN') + '</td></tr>';
    $('chart-table').innerHTML = rows + '</tbody>';
  }

  function chartIndex(e) {
    var r = $('chart').getBoundingClientRect(), vx = (e.clientX - r.left) / r.width * CH.W;
    var f = (vx - CH.l) / (CH.W - CH.l - CH.r) * CURVE_PTS;
    return Math.max(0, Math.min(CURVE_PTS, Math.round(f)));
  }
  function chartHover(e) {
    var k = chartIndex(e), c = S.curve, hv = $('hov'), tip = $('ctip'), r = $('chart').getBoundingClientRect();
    var x = xs(c.x[k]);
    hv.setAttribute('x1', x); hv.setAttribute('x2', x); hv.removeAttribute('hidden');
    tip.innerHTML = '<b>Budget ' + inr(c.x[k]) + '</b>' +
      '<span><em>Roof-level</em>' + Math.round(c.roof[k]).toLocaleString('en-IN') + '</span>' +
      '<span><em>Ward-level</em>' + Math.round(c.ward[k]).toLocaleString('en-IN') + '</span>' +
      '<span><em>Random</em>' + Math.round(c.rand[k]).toLocaleString('en-IN') + '</span>';
    tip.hidden = false;
    var px = x / CH.W * r.width, w = tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(r.width - w, px + 12 + w > r.width ? px - w - 12 : px + 12)) + 'px';
  }
  function chartLeave() { $('ctip').hidden = true; var hv = $('hov'); if (hv) hv.setAttribute('hidden', ''); }
  function chartClick(e) {
    var k = chartIndex(e), el = $('budget'), step = +el.step, mn = +el.min, mx = +el.max;
    var v = Math.round(S.curve.x[k] / step) * step;
    el.value = Math.max(mn, Math.min(mx, v));
    schedule(0);
  }

  /* ---------- who gets picked ---------- */
  function paintMix() {
    var b = S.b, n = b.n, k = S.sel.length, i, rows = [], matAll = [0, 0, 0, 0], matSel = [0, 0, 0, 0], one = [0, 0], oneSel = [0, 0];
    if (!k) { $('mix').innerHTML = '<p class="hint">No roofs are treated at this budget.</p>'; return; }
    for (i = 0; i < n; i++) { matAll[b.mat[i]]++; one[b.storeys[i] === 1 ? 0 : 1]++; }
    S.sel.forEach(function (j) { matSel[b.mat[j]]++; oneSel[b.storeys[j] === 1 ? 0 : 1]++; });
    function row(name, a, s2, tot) {
      var pa = 100 * a / n, ps = 100 * s2 / k;
      return '<div class="item"><div class="name"><span>' + name + '</span></div>' +
        '<div class="bar"><span class="track"><span class="fill t" style="width:' + ps.toFixed(1) + '%"></span></span><span class="num">' + Math.round(ps) + '%</span></div>' +
        '<div class="bar"><span class="track"><span class="fill a" style="width:' + pa.toFixed(1) + '%"></span></span><span class="num">' + Math.round(pa) + '%</span></div></div>';
    }
    var html = '<div class="keyrow"><span><i style="background:var(--accent)"></i>Share of treated roofs</span><span><i style="background:var(--muted)"></i>Share of all roofs</span></div>';
    for (i = 0; i < 4; i++) if (matAll[i]) html += row(MAT[i].charAt(0).toUpperCase() + MAT[i].slice(1), matAll[i], matSel[i]);
    html += row('One storey', one[0], oneSel[0]) + row('Two or more storeys', one[1], oneSel[1]);
    $('mix').innerHTML = html;
  }

  /* ---------- work order ---------- */
  var COLS = ['rank', 'building_id', 'ward', 'material', 'storeys', 'area_m2', 'hours_now', 'hours_avoided', 'mean_drop_c', 'cost'];
  function rowVals(k) {
    var i = S.sel[k], b = S.b;
    return [k + 1, b.id[i], b.wardNames[b.ward[i]], MAT[b.mat[i]], b.storeys[i], b.area[i], S.sc.hNow[i], S.sc.avoided[i], S.eng.meanDrop[i], S.cb.cost[i]];
  }
  function paintTable() {
    var k = S.sel.length, show = S.showAll ? k : Math.min(k, 12), j, html;
    html = '<thead><tr><th>Rank</th><th>Roof</th><th class="l">Ward</th><th class="l">Material</th><th>Storeys</th><th>Area m²</th><th>' + U().head + '</th><th>' + U().headAv + '</th><th>Mean drop °C</th><th>Cost</th></tr></thead><tbody>';
    for (j = 0; j < show; j++) {
      var v = rowVals(j);
      html += '<tr><td>' + v[0] + '</td><td>' + esc(v[1]) + '</td><td class="l">' + esc(v[2]) + '</td><td class="l">' + v[3] + '</td><td>' + v[4] + '</td><td>' + f1(v[5]) + '</td><td>' + fmtHeat(v[6]) + '</td><td><span class="pill">' + fmtHeat(v[7]) + '</span></td><td>' + f2(v[8]) + '</td><td>' + inr(v[9]) + '</td></tr>';
    }
    if (!k) html += '<tr><td colspan="10" class="l">No roofs fit in this budget.</td></tr>';
    $('wo').innerHTML = html + '</tbody>';
    $('wo-count').textContent = k ? 'Showing ' + show.toLocaleString('en-IN') + ' of ' + k.toLocaleString('en-IN') + ' roofs, best first' : '';
    $('btn-all').hidden = k <= 12;
    $('btn-all').textContent = S.showAll ? 'Show top 12' : 'Show all ' + k.toLocaleString('en-IN');
  }
  function csvText() {
    var out = [COLS.map(function (c) { return S.metric === 'degree' ? c.replace('hours_', 'degree_hours_') : c; }).join(',')], j;
    for (j = 0; j < S.sel.length; j++) {
      var v = rowVals(j);
      out.push([v[0], '"' + String(v[1]).replace(/"/g, '""') + '"', '"' + String(v[2]).replace(/"/g, '""') + '"', v[3], v[4], f2(v[5]), f2(v[6]), f2(v[7]), f2(v[8]), Math.round(v[9])].join(','));
    }
    return out.join('\n');
  }
  function copyText(text, okMsg) {
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      var ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      toast(ok ? okMsg : 'Copy was blocked. Select the table and copy it by hand.');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { toast(okMsg); }, fallback);
    else fallback();
  }

  /* ---------- pipeline (cheap steps re-run on cheap inputs) ---------- */
  function recomputeBudget() {
    var p = params(), take = [], i;
    R.walk(S.roofOrder, S.cb.cost, S.cb.benefit, p.budget, take);
    S.sel = take;
    S.rank = new Int32Array(S.b.n);
    for (i = 0; i < take.length; i++) S.rank[take[i]] = i + 1;
    S.cmp = R.compareAt(S.roofOrder, S.orders, S.cb, p.budget);
    $('o-budget').textContent = inr(p.budget);
    paintKpis(p); paintSelected(); paintChart(p); paintMix(); paintTable();
  }
  function recomputeCost() {
    var p = params();
    S.cb = R.costBenefit(S.b, S.sc.avoided, p.cost, p.fixed);
    S.roofOrder = R.rankRoofs(S.cb, S.b, S.eng.meanDrop);
    S.curve = R.curve(S.roofOrder, S.orders, S.cb, S.maxBudget, CURVE_PTS);
    recomputeBudget();
  }
  function recomputeThreshold() {
    var p = params();
    $('o-thr').textContent = f1(p.thr) + ' °C';
    S.sc = R.scoreAt(S.eng, p.thr, S.metric);
    S.orders = R.baselineOrders(S.b, S.sc.hNow, N_SEEDS);
    paintHeat(); paintLegend();
    recomputeCost();
  }
  var pending = -1, queued = false;
  function schedule(level) { // 2 = threshold, 1 = cost, 0 = budget
    pending = Math.max(pending, level);
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () {
      queued = false; var l = pending; pending = -1;
      if (l >= 2) recomputeThreshold(); else if (l === 1) recomputeCost(); else recomputeBudget();
    });
  }

  /* ---------- data ---------- */
  function setBudgetRange(synthetic) {
    var el = $('budget'), p = params(), mx, st, def;
    if (synthetic) { mx = 5000000; st = 50000; def = 1000000; }
    else {
      var tot = 0, i; for (i = 0; i < S.b.n; i++) tot += S.b.area[i] * p.cost + p.fixed;
      mx = niceCeil(tot * 0.5); st = niceCeil(mx / 100) / (niceCeil(mx / 100) / (mx / 100) > 2 ? 2 : 1);
      st = Math.max(1, Math.round(st)); def = Math.round(mx * 0.2 / st) * st;
    }
    el.min = st; el.max = mx; el.step = st; el.value = def;
    S.maxBudget = mx;
  }
  function setData(b, synthetic) {
    S.b = b; S.synthetic = synthetic; S.showAll = false;
    S.eng = R.prepare(b, S.weather);
    buildMap();
    setBudgetRange(synthetic);
    recomputeThreshold();
    paintNotice();
  }
  function loadSample() { setData(R.fromRows(D.rows, D.wards), true); $('data-msg').className = 'msg'; $('data-msg').textContent = 'Showing ' + S.b.n.toLocaleString('en-IN') + ' synthetic buildings in ' + S.b.wardNames.length + ' wards.'; }
  function onFile(e) {
    var f = e.target.files && e.target.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      try {
        var b = R.parseCsv(rd.result);
        setData(b, false);
        $('data-msg').className = 'msg';
        $('data-msg').textContent = 'Loaded ' + b.n.toLocaleString('en-IN') + ' buildings from ' + f.name + (b.people ? ', using the occupants column as the number of people.' : '.');
      } catch (err) {
        $('data-msg').className = 'msg err';
        $('data-msg').textContent = 'Could not read ' + f.name + '. ' + err.message;
      }
      e.target.value = '';
    };
    rd.onerror = function () { $('data-msg').className = 'msg err'; $('data-msg').textContent = 'Could not read that file.'; };
    rd.readAsText(f);
  }

  /* ---------- static tables ---------- */
  function paintSanity() {
    var rows = R.sanity(), html = '<thead><tr><th class="l">Roof</th><th>1 storey, mean</th><th>1 storey, peak</th><th>2 storeys, mean</th><th>2 storeys, peak</th></tr></thead><tbody>', m;
    for (m = 0; m < rows.length; m += 2) {
      html += '<tr><td class="l">' + rows[m].material.charAt(0).toUpperCase() + rows[m].material.slice(1) + '</td><td>' + f1(rows[m].mean) + ' °C</td><td>' + f1(rows[m].peak) + ' °C</td><td>' + f1(rows[m + 1].mean) + ' °C</td><td>' + f1(rows[m + 1].peak) + ' °C</td></tr>';
    }
    $('sanity').innerHTML = html + '</tbody>';
  }


  /* ---------- weather ---------- */
  function paintNotice() {
    $('notice').textContent = (S.synthetic ? 'Synthetic demo city. ' : 'Your uploaded buildings. ') +
      (S.wxKey === 'synthetic' ? 'Idealised hot-week weather. ' : 'Real weather for ' + CITIES[S.wxKey][0] + '. ') +
      'Indoor temperatures are modelled from assumed roof properties, not measured.';
  }
  function fetchWeather(key) {
    var c = CITIES[key], ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 15000);
    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + c[1] + '&longitude=' + c[2] +
      '&hourly=temperature_2m,shortwave_radiation&past_days=6&forecast_days=1&timezone=auto';
    return fetch(url, ctl ? { signal: ctl.signal } : {}).then(function (r) {
      if (!r.ok) throw new Error('The weather service answered with status ' + r.status + '.');
      return r.json().catch(function () { throw new Error('The weather service sent an unreadable reply.'); });
    }).then(function (j) {
      if (!j || !j.hourly || !j.hourly.temperature_2m || !j.hourly.shortwave_radiation) throw new Error('The weather service sent an unexpected reply.');
      return R.weatherFromArrays(j.hourly.temperature_2m, j.hourly.shortwave_radiation);
    }).then(function (w) { clearTimeout(timer); return w; }, function (e) {
      clearTimeout(timer);
      if (e && e.name === 'AbortError') throw new Error('The weather service took too long.');
      if (e instanceof TypeError) throw new Error('Could not reach the weather service. Check your connection.');
      throw e;
    });
  }
  function wxSummary(w) {
    var i, sum = 0, mx = -Infinity, g = 0;
    for (i = 0; i < w.n; i++) { sum += w.temp[i]; if (w.temp[i] > mx) mx = w.temp[i]; if (w.ghi[i] > g) g = w.ghi[i]; }
    return 'mean ' + f1(sum / w.n) + ' °C, hottest hour ' + f1(mx) + ' °C, peak sun ' + Math.round(g) + ' W/m²';
  }
  function applyWeather(w, key, msg) {
    S.weather = w; S.wxKey = key; S.eng = R.prepare(S.b, w);
    $('wx').value = key; $('wx-msg').className = 'msg'; $('wx-msg').textContent = msg;
    paintNotice(); recomputeThreshold();
  }
  function onWeather() {
    var key = $('wx').value;
    if (key === 'synthetic') { var w = R.syntheticWeather(); applyWeather(w, 'synthetic', 'Idealised hot week, synthetic: ' + wxSummary(w) + '.'); return; }
    $('wx').disabled = true; $('wx-msg').className = 'msg'; $('wx-msg').textContent = 'Loading real weather for ' + CITIES[key][0] + '...';
    fetchWeather(key).then(function (w) {
      $('wx').disabled = false;
      applyWeather(w, key, 'Real weather for ' + CITIES[key][0] + ' from Open-Meteo, last 6 days plus today, loaded ' + new Date().toLocaleTimeString() + ': ' + wxSummary(w) + '.');
    }).catch(function (e) {
      $('wx').disabled = false; $('wx').value = S.wxKey;
      $('wx-msg').className = 'msg err';
      $('wx-msg').textContent = e.message + ' Still using ' + (S.wxKey === 'synthetic' ? 'the synthetic week.' : CITIES[S.wxKey][0] + '.');
    });
  }
  var METRIC_NOTE = {
    degree: 'Adds up how far indoor air is above the threshold, hour by hour. Tells very hot roofs apart from barely hot ones.',
    hours: 'Counts the hours above the threshold. A roof just over the line can tie with a much hotter one.'
  };
  function download(name, text) {
    try {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' })); a.download = name;
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      toast('Downloaded ' + name);
    } catch (e) { copyText(text, 'Download was blocked, so the CSV was copied instead'); }
  }

  /* ---------- wire up ---------- */
  function init() {
    paintSanity();
    $('budget').addEventListener('input', function () { schedule(0); });
    $('cost').addEventListener('input', function () { schedule(1); });
    $('fixed').addEventListener('input', function () { schedule(1); });
    $('thr').addEventListener('input', function () { schedule(2); });
    Array.prototype.forEach.call(document.getElementsByName('view'), function (r) {
      r.addEventListener('change', function () { if (r.checked) { S.view = r.value; paintSelected(); paintLegend(); } });
    });
    $('map').addEventListener('pointermove', showTip);
    $('map').addEventListener('pointerdown', showTip);
    $('map').addEventListener('pointerleave', function () { $('tip').hidden = true; });
    $('chart').addEventListener('pointermove', chartHover);
    $('chart').addEventListener('pointerleave', chartLeave);
    $('chart').addEventListener('click', chartClick);
    Array.prototype.forEach.call(document.getElementsByName('metric'), function (r) {
      r.addEventListener('change', function () { if (r.checked) { S.metric = r.value; $('metric-note').textContent = METRIC_NOTE[S.metric]; schedule(2); } });
    });
    $('metric-note').textContent = METRIC_NOTE[S.metric];
    $('wx').addEventListener('change', onWeather);
    var wx0 = S.weather; $('wx-msg').textContent = 'Idealised hot week, synthetic: ' + wxSummary(wx0) + '.';
    if ($('btn-dl')) $('btn-dl').addEventListener('click', function () { download(S.metric === 'degree' ? 'roofrx_work_order.csv' : 'roofrx_work_order_hours.csv', csvText()); });
    $('btn-all').addEventListener('click', function () { S.showAll = !S.showAll; paintTable(); });
    $('btn-copy').addEventListener('click', function () { copyText(csvText(), 'Copied ' + S.sel.length + ' roofs as CSV'); });
    $('btn-copyhdr').addEventListener('click', function () { copyText($('csv-hdr').textContent, 'Copied the header'); });
    $('btn-sample').addEventListener('click', loadSample);
    $('btn-upload').addEventListener('click', function () { $('file').click(); });
    $('file').addEventListener('change', onFile);
    var lastW = window.innerWidth, rt;
    window.addEventListener('resize', function () {
      cancelAnimationFrame(rt);
      rt = requestAnimationFrame(function () {
        if (window.innerWidth === lastW || !S.cmp) return;
        lastW = window.innerWidth;
        var k = Math.round(Math.max(1, 720 / ($('map').clientWidth || 800)) * 10) / 10;
        if (k !== S.mapK) { buildMap(); paintHeat(); paintSelected(); }
        paintChart(params());
      });
    });
    loadSample();
  }
  init();
})();
