/* RoofRx engine: JavaScript port of roofrx/thermal.py and roofrx/optimizer.py.
 * Pure functions, no DOM. Used by the website and by web/check_parity.py (node).
 * Material values are ASSUMED placeholders, same as roofrx/materials.py. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.RoofRx = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MATERIALS = [
    { name: 'metal', alpha: 0.75, u: 5.0 },
    { name: 'concrete', alpha: 0.65, u: 2.5 },
    { name: 'tile', alpha: 0.60, u: 2.0 },
    { name: 'other', alpha: 0.70, u: 3.5 }
  ];
  var COOL_ALPHA = 0.30, H_OUT = 17.0, C0 = 6.0e4, H0 = 2.5, SPINUP = 2, SUB = 6;

  /* ---------- weather (idealised hot week, synthetic) ---------- */
  function syntheticWeather(days) {
    days = days || 7;
    var n = days * 24, temp = new Float64Array(n), ghi = new Float64Array(n);
    for (var k = 0; k < n; k++) {
      var h = k % 24;
      temp[k] = 34 + 6 * Math.sin(2 * Math.PI * (h - 9) / 24);
      var g = Math.max(900 * Math.sin(Math.PI * (h - 6) / 12), 0);
      ghi[k] = (h < 6 || h > 18) ? 0 : g;
    }
    return { temp: temp, ghi: ghi, n: n };
  }

  /* Turn hourly arrays (e.g. from Open-Meteo) into a model weather object. Throws if unusable. */
  function weatherFromArrays(temp, ghi) {
    var n = Math.floor(Math.min(temp.length, ghi.length) / 24) * 24, i, gaps = 0;
    if (n < 72) throw new Error('Need at least 3 full days of hourly weather.');
    var t = new Float64Array(n), g = new Float64Array(n), lt = null, lg = 0;
    for (i = 0; i < n; i++) {
      var a = temp[i], b = ghi[i];
      if (a === null || a === undefined || !isFinite(a)) { gaps++; a = lt; }
      if (b === null || b === undefined || !isFinite(b)) { gaps++; b = lg; }
      if (a === null) throw new Error('Weather data starts with a gap.');
      if (a < -60 || a > 60 || b < 0 || b > 1600) throw new Error('Weather values look wrong (temperature or radiation out of range).');
      t[i] = a; g[i] = b; lt = a; lg = b;
    }
    if (gaps > 24) throw new Error('Too many gaps in the weather data.');
    return { temp: t, ghi: g, n: n };
  }

  /* ---------- buildings ---------- */
  function makeBuildings(o) {
    o.n = o.id.length;
    return o;
  }

  function fromRows(rows, wardNames) {
    var n = rows.length;
    var b = {
      id: new Array(n), wardNames: wardNames, ward: new Int32Array(n),
      lat: new Float64Array(n), lon: new Float64Array(n), area: new Float64Array(n),
      mat: new Int8Array(n), storeys: new Float64Array(n)
    };
    for (var i = 0; i < n; i++) {
      var r = rows[i];
      b.id[i] = r[0]; b.ward[i] = r[1]; b.lat[i] = r[2]; b.lon[i] = r[3];
      b.area[i] = r[4]; b.mat[i] = r[5]; b.storeys[i] = r[6];
    }
    return makeBuildings(b);
  }

  function splitCsvLine(line) {
    var out = [], cur = '', q = false;
    for (var i = 0; i < line.length; i++) {
      var ch = line[i];
      if (q) {
        if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (ch === '"') q = false;
        else cur += ch;
      } else if (ch === '"') q = true;
      else if (ch === ',') { out.push(cur); cur = ''; }
      else cur += ch;
    }
    out.push(cur);
    return out;
  }

  /* Same rules as roofrx/data.py load_buildings. Throws Error with a readable message. */
  function parseCsv(text) {
    var lines = String(text).replace(/^﻿/, '').split(/\r?\n/).filter(function (l) { return l.trim() !== ''; });
    if (lines.length < 2) throw new Error('The CSV has no rows.');
    var head = splitCsvLine(lines[0]).map(function (s) { return s.trim().toLowerCase(); });
    var req = ['building_id', 'ward', 'lat', 'lon', 'area_m2', 'material'];
    var missing = req.filter(function (c) { return head.indexOf(c) < 0; });
    if (missing.length) throw new Error('Missing columns: ' + missing.join(', ') + '. Required: ' + req.join(', ') + '.');
    var ix = {}; head.forEach(function (c, i) { ix[c] = i; });
    var n = lines.length - 1;
    var b = {
      id: new Array(n), wardNames: [], ward: new Int32Array(n),
      lat: new Float64Array(n), lon: new Float64Array(n), area: new Float64Array(n),
      mat: new Int8Array(n), storeys: new Float64Array(n),
      people: ix.occupants !== undefined ? new Float64Array(n) : null
    };
    var wardIx = {}, seen = {}, matIx = {};
    MATERIALS.forEach(function (m, i) { matIx[m.name] = i; });
    var badMat = {};
    for (var r = 0; r < n; r++) {
      var f = splitCsvLine(lines[r + 1]);
      var row = r + 2;
      var lat = Number(f[ix.lat]), lon = Number(f[ix.lon]), area = Number(f[ix.area_m2]);
      if (f[ix.lat] === '' || !isFinite(lat)) throw new Error("Row " + row + ": 'lat' is missing or not a number.");
      if (f[ix.lon] === '' || !isFinite(lon)) throw new Error("Row " + row + ": 'lon' is missing or not a number.");
      if (f[ix.area_m2] === '' || !isFinite(area)) throw new Error("Row " + row + ": 'area_m2' is missing or not a number.");
      if (lat < -90 || lat > 90 || lon < -180 || lon > 180) throw new Error('Row ' + row + ': lat must be in [-90, 90] and lon in [-180, 180].');
      if (area <= 0) throw new Error('Row ' + row + ': area_m2 must be positive.');
      var id = String(f[ix.building_id]).trim();
      if (seen[id]) throw new Error("building_id '" + id + "' appears more than once. IDs must be unique.");
      seen[id] = 1;
      var mname = String(f[ix.material]).trim().toLowerCase();
      if (!(mname in matIx)) badMat[mname] = 1;
      var wname = String(f[ix.ward]).trim();
      if (!(wname in wardIx)) { wardIx[wname] = b.wardNames.length; b.wardNames.push(wname); }
      var st = ix.storeys !== undefined ? Number(f[ix.storeys]) : 1;
      b.id[r] = id; b.ward[r] = wardIx[wname]; b.lat[r] = lat; b.lon[r] = lon; b.area[r] = area;
      b.mat[r] = matIx[mname] === undefined ? 3 : matIx[mname];
      b.storeys[r] = isFinite(st) && st >= 1 ? st : 1;
      if (b.people) {
        var oc = Number(f[ix.occupants]);
        if (f[ix.occupants] === '' || !isFinite(oc) || oc < 0) throw new Error('Row ' + row + ": 'occupants' must be a number of 0 or more.");
        b.people[r] = oc;
      }
    }
    var bad = Object.keys(badMat);
    if (bad.length) throw new Error('Unknown materials: ' + bad.join(', ') + '. Allowed: ' + MATERIALS.map(function (m) { return m.name; }).join(', ') + '.');
    return makeBuildings(b);
  }

  /* ---------- thermal model ---------- */
  function simulate(w, alpha, u, storeys) {
    var nH = w.n, n = alpha.length, out = new Float64Array(nH * n);
    var tin = new Float64Array(n).fill(w.temp[0]);
    var dt = 3600 / SUB;
    for (var h = 0; h < nH; h++) {
      var to = w.temp[h], g = w.ghi[h];
      for (var i = 0; i < n; i++) {
        var C = C0 * storeys[i], H = H0 * storeys[i];
        var tsa = to + alpha[i] * g / H_OUT;
        var t = tin[i];
        for (var s = 0; s < SUB; s++) {
          var dT = (u[i] * (tsa - t) + H * (to - t)) / C;
          t = t + dt * dT;
        }
        tin[i] = t; out[h * n + i] = t;
      }
    }
    return out;
  }

  /* metric 'hours': hours/day above thr.  metric 'degree': degree-hours/day above thr. */
  function heatLoad(T, nH, n, thr, metric) {
    var out = new Float64Array(n), days = (nH - SPINUP * 24) / 24, deg = metric === 'degree';
    for (var h = SPINUP * 24; h < nH; h++)
      for (var i = 0; i < n; i++) {
        var d = T[h * n + i] - thr;
        if (d > 0) out[i] += deg ? d : 1;
      }
    for (var j = 0; j < n; j++) out[j] /= days;
    return out;
  }

  function meanSteady(T, nH, n) {
    var out = new Float64Array(n), cnt = nH - SPINUP * 24;
    for (var h = SPINUP * 24; h < nH; h++) for (var i = 0; i < n; i++) out[i] += T[h * n + i];
    for (var j = 0; j < n; j++) out[j] /= cnt;
    return out;
  }

  /* Run the (slow) simulation once per building set. */
  function prepare(b, weather) {
    var w = weather || syntheticWeather(), n = b.n;
    var alpha = new Float64Array(n), cool = new Float64Array(n), u = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var m = MATERIALS[b.mat[i]];
      alpha[i] = m.alpha; cool[i] = Math.min(m.alpha, COOL_ALPHA); u[i] = m.u;
    }
    var now = simulate(w, alpha, u, b.storeys), cl = simulate(w, cool, u, b.storeys);
    var mNow = meanSteady(now, w.n, n), mCool = meanSteady(cl, w.n, n), drop = new Float64Array(n);
    for (var k = 0; k < n; k++) drop[k] = mNow[k] - mCool[k];
    return { n: n, nH: w.n, now: now, cool: cl, meanDrop: drop, weather: w };
  }

  /* Cheap: depends on the danger threshold only. */
  function scoreAt(eng, thr, metric) {
    var hNow = heatLoad(eng.now, eng.nH, eng.n, thr, metric);
    var hCool = heatLoad(eng.cool, eng.nH, eng.n, thr, metric);
    var av = new Float64Array(eng.n);
    for (var i = 0; i < eng.n; i++) av[i] = Math.max(hNow[i] - hCool[i], 0);
    return { hNow: hNow, hCool: hCool, avoided: av };
  }

  function sanity() {
    var w = syntheticWeather(), rows = [];
    MATERIALS.forEach(function (m) {
      [1, 2].forEach(function (st) {
        var a = simulate(w, [m.alpha], [m.u], [st]);
        var c = simulate(w, [Math.min(m.alpha, COOL_ALPHA)], [m.u], [st]);
        var s = 0, mx = -Infinity, cnt = 0;
        for (var h = SPINUP * 24; h < w.n; h++) { var d = a[h] - c[h]; s += d; cnt++; if (d > mx) mx = d; }
        rows.push({ material: m.name, storeys: st, mean: s / cnt, peak: mx });
      });
    });
    return rows;
  }

  /* ---------- optimizer ---------- */
  function costBenefit(b, avoided, costPerM2, fixed) {
    var n = b.n, benefit = new Float64Array(n), cost = new Float64Array(n), ratio = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      benefit[i] = avoided[i] * (b.people ? b.people[i] : b.area[i]);
      cost[i] = b.area[i] * costPerM2 + fixed;
      ratio[i] = benefit[i] / cost[i];
    }
    return { benefit: benefit, cost: cost, ratio: ratio };
  }

  /* Ties on benefit per cost are common (hours are whole hours), so break them by the
   * continuous indoor drop, then larger area, then row order. Same rule as roofrx/optimizer.py. */
  function rankRoofs(cb, b, meanDrop) {
    var idx = [], top = 0, i;
    for (i = 0; i < cb.ratio.length; i++) if (cb.ratio[i] > top) top = cb.ratio[i];
    var key = new Float64Array(cb.ratio.length);
    for (i = 0; i < cb.ratio.length; i++) { key[i] = top > 0 ? Math.round(cb.ratio[i] / top * 1e9) : cb.ratio[i]; if (cb.benefit[i] > 0) idx.push(i); }
    idx.sort(function (a, c) {
      return (key[c] - key[a]) || (meanDrop[c] - meanDrop[a]) || (b.area[c] - b.area[a]) || (a - c);
    });
    return Int32Array.from(idx);
  }

  function walk(order, cost, benefit, budget, take) {
    var spent = 0, ben = 0, cnt = 0;
    for (var k = 0; k < order.length; k++) {
      var i = order[k], c = cost[i];
      if (c + spent <= budget) { spent += c; ben += benefit[i]; cnt++; if (take) take.push(i); }
    }
    return { spent: spent, benefit: ben, count: cnt };
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffle(arr, rnd) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(rnd() * (i + 1)), t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  /* Baseline orders depend on hours (threshold) only, not on budget or cost. */
  function baselineOrders(b, hNow, nSeeds) {
    var nW = b.wardNames.length, sum = new Float64Array(nW), cnt = new Float64Array(nW), pos = [], i, w;
    for (w = 0; w < nW; w++) pos.push([]);
    for (i = 0; i < b.n; i++) { sum[b.ward[i]] += hNow[i]; cnt[b.ward[i]]++; pos[b.ward[i]].push(i); }
    var rank = [];
    for (w = 0; w < nW; w++) rank.push(w);
    rank.sort(function (a, c) { return (sum[c] / cnt[c]) - (sum[a] / cnt[a]) || a - c; });
    var ward = [], rand = [];
    for (var s = 0; s < nSeeds; s++) {
      var rnd = mulberry32(1000 + s), o = [];
      rank.forEach(function (wi) { shuffle(pos[wi].slice(), rnd).forEach(function (p) { o.push(p); }); });
      ward.push(Int32Array.from(o));
      var all = []; for (i = 0; i < b.n; i++) all.push(i);
      rand.push(Int32Array.from(shuffle(all, mulberry32(5000 + s))));
    }
    return { ward: ward, rand: rand };
  }

  function meanStd(a) {
    var m = 0, i; for (i = 0; i < a.length; i++) m += a[i]; m /= a.length;
    var v = 0; for (i = 0; i < a.length; i++) v += (a[i] - m) * (a[i] - m);
    return { mean: m, std: Math.sqrt(v / a.length) };
  }

  function compareAt(roofOrder, orders, cb, budget) {
    var roof = walk(roofOrder, cb.cost, cb.benefit, budget);
    var wb = orders.ward.map(function (o) { return walk(o, cb.cost, cb.benefit, budget).benefit; });
    var rb = orders.rand.map(function (o) { return walk(o, cb.cost, cb.benefit, budget).benefit; });
    var w = meanStd(wb), r = meanStd(rb);
    return {
      roof: roof, wardMean: w.mean, wardStd: w.std, randMean: r.mean,
      gainWard: w.mean > 0 ? 100 * (roof.benefit / w.mean - 1) : NaN,
      gainRand: r.mean > 0 ? 100 * (roof.benefit / r.mean - 1) : NaN
    };
  }

  function curve(roofOrder, orders, cb, maxBudget, points) {
    var xs = [], roof = [], ward = [], rand = [];
    for (var k = 0; k <= points; k++) {
      var bud = maxBudget * k / points, c = compareAt(roofOrder, orders, cb, bud);
      xs.push(bud); roof.push(c.roof.benefit); ward.push(c.wardMean); rand.push(c.randMean);
    }
    return { x: xs, roof: roof, ward: ward, rand: rand };
  }

  return {
    MATERIALS: MATERIALS, syntheticWeather: syntheticWeather, weatherFromArrays: weatherFromArrays, fromRows: fromRows, parseCsv: parseCsv,
    prepare: prepare, scoreAt: scoreAt, sanity: sanity, costBenefit: costBenefit, rankRoofs: rankRoofs,
    walk: walk, baselineOrders: baselineOrders, compareAt: compareAt, curve: curve
  };
});
