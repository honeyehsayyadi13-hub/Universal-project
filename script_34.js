
(function(){
  var root = document.getElementById('rd');
  var tabs = document.getElementById('ptabs');

  function runScripts(scope){
    scope.querySelectorAll('script').forEach(function(old){
      var s = document.createElement('script');
      if (old.src){ s.src = old.src; } else { s.textContent = old.textContent; }
      old.parentNode.replaceChild(s, old);
    });
  }
  function resizePlots(scope){
    if (!window.Plotly) return;
    (scope||document).querySelectorAll('.js-plotly-plot').forEach(function(g){ try { Plotly.Plots.resize(g); } catch(e){} });
  }
  function themePlots(scope){
    if (!window.Plotly) return;
    var cs = getComputedStyle(document.documentElement);
    var text = cs.getPropertyValue('--text').trim(), border = cs.getPropertyValue('--border').trim(),
        surface = cs.getPropertyValue('--surface').trim(), surface2 = cs.getPropertyValue('--surface2').trim(),
        muted = cs.getPropertyValue('--muted').trim(),
        brand = cs.getPropertyValue('--brand').trim(), brand2 = cs.getPropertyValue('--brand2').trim(),
        good = cs.getPropertyValue('--good').trim(), warn = cs.getPropertyValue('--warn').trim(), bad = cs.getPropertyValue('--bad').trim();
    var fam = '"sofia-pro", "Segoe UI", system-ui, sans-serif';
    (scope||document).querySelectorAll('.js-plotly-plot').forEach(function(gd){
      if (!gd.layout) return;
      var u = { paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', 'font.color': text, 'font.family': fam,
                colorway: [brand, brand2, good, warn, bad, '#8b6cf0', '#22b8cf', '#e06f9c'],
                'hoverlabel.bgcolor': surface, 'hoverlabel.bordercolor': brand, 'hoverlabel.font.color': text, 'hoverlabel.font.family': fam, 'hoverlabel.font.size': 13,
                'legend.font.color': text, 'legend.font.family': fam };
      Object.keys(gd.layout).forEach(function(k){
        if (/^[xy]axis\d*$/.test(k)){
          u[k+'.gridcolor'] = border; u[k+'.griddash'] = 'dot';
          u[k+'.zeroline'] = false; u[k+'.showline'] = false; u[k+'.ticks'] = '';
          u[k+'.color'] = text; u[k+'.tickfont.family'] = fam; u[k+'.tickfont.size'] = 11.5; u[k+'.tickfont.color'] = muted;
          u[k+'.title.font.family'] = fam; u[k+'.title.font.color'] = muted; u[k+'.title.font.size'] = 12.5;
          if (k.charAt(0) === 'x' && gd.layout[k].rangeselector){
            u[k+'.rangeselector.bgcolor'] = surface2; u[k+'.rangeselector.activecolor'] = brand;
            u[k+'.rangeselector.bordercolor'] = border; u[k+'.rangeselector.font.color'] = text;
          }
        }
      });
      try { Plotly.relayout(gd, u); } catch(e){}
      try {
        var idx = []; (gd.data||[]).forEach(function(tr,i){ if (tr.name === 'Rolling Average') idx.push(i); });
        if (idx.length) Plotly.restyle(gd, {'line.color': brand2}, idx);
      } catch(e){}
    });
  }
  window.TDThemePlots = themePlots;
  new MutationObserver(function(){ themePlots(document); })
    .observe(document.documentElement, { attributes:true, attributeFilter:['data-theme'] });

  // Native SVG wait curve (hero) — same renderer as the park overview.
  function drawCurves(scope){
    var cs = getComputedStyle(document.documentElement);
    var brand = cs.getPropertyValue('--brand').trim(), muted = cs.getPropertyValue('--muted').trim();
    (scope || document).querySelectorAll('svg.wa-curve:not([data-built])').forEach(function(svg){
      svg.setAttribute('data-built', '1');
      var raw = (svg.dataset.spark || '').split(',').map(Number).filter(function(n){ return !isNaN(n); });
      if (raw.length < 2){ svg.outerHTML = '<div class="ov-stat-s" style="text-align:center; padding:24px 0; color:var(--muted); font-weight:400;">No wait data collected yet today.</div>'; return; }
      var w = 600, h = 140, pad = 8, gid = 'ovg' + Math.random().toString(36).slice(2);
      var times = (svg.dataset.times || '').split('|');
      // Position points by real time so downtime shows as a proportional gap.
      function parseMin(t){ var m = /(\d+):(\d+)\s*(AM|PM)/i.exec(t || ''); if (!m) return null; var hh = (+m[1]) % 12; if (/PM/i.test(m[3])) hh += 12; return hh * 60 + (+m[2]); }
      var tmin = times.map(parseMin);
      var useTime = tmin.length === raw.length && tmin.every(function(v){ return v != null; }) && tmin[tmin.length - 1] > tmin[0];
      var gap = Infinity;
      if (useTime){
        var deltas = []; for (var di = 1; di < tmin.length; di++) deltas.push(tmin[di] - tmin[di - 1]);
        var srt = deltas.slice().sort(function(a, b){ return a - b; });
        var med = srt[Math.floor(srt.length / 2)] || 1;
        gap = Math.max(med * 3, 8);   // a jump bigger than this = the ride was down
      }
      // Average line aligned to the actual points (dashed). Scale both together.
      var typ = (svg.dataset.average || '').split(',').map(function(v){ var n = parseFloat(v); return isNaN(n) ? null : n; });
      var hasTyp = typ.length === raw.length && typ.filter(function(n){ return n != null; }).length >= 2;
      var all = raw.slice(); if (hasTyp){ typ.forEach(function(n){ if (n != null) all.push(n); }); }
      var max = Math.max.apply(null, all), min = Math.min.apply(null, all), rng = (max - min) || 1;
      var x = useTime ? function(i){ return (tmin[i] - tmin[0]) / ((tmin[tmin.length - 1] - tmin[0]) || 1) * w; }
                      : function(i){ return (i / (raw.length - 1)) * w; };
      var y = function(d){ return h - pad - ((d - min) / rng) * (h - 2 * pad); };
      // Split into continuous segments, breaking where the ride was down.
      var segs = [], cur = [];
      for (var si = 0; si < raw.length; si++){
        if (si > 0 && useTime && (tmin[si] - tmin[si - 1] > gap)){ if (cur.length) segs.push(cur); cur = []; }
        cur.push(si);
      }
      if (cur.length) segs.push(cur);
      var mag = window.tdMag || function(){ return brand; };
        var lgid = 'ovl' + gid, lstops = '';
        for (var gs = 0; gs <= 4; gs++){ var goff = gs / 4; lstops += '<stop offset="' + goff + '" stop-color="' + mag(1 - goff) + '"/>'; }
        // Line color follows wait magnitude vs THIS day's own min/max (top = highest, bottom = lowest).
        var out = '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">'
          + '<stop offset="0" stop-color="' + brand + '" stop-opacity="0.35"/>'
          + '<stop offset="1" stop-color="' + brand + '" stop-opacity="0"/></linearGradient>'
          + '<linearGradient id="' + lgid + '" gradientUnits="userSpaceOnUse" x1="0" y1="' + pad + '" x2="0" y2="' + (h - pad) + '">' + lstops + '</linearGradient>'
          + '</defs>';
      // Area fill (per segment)
      segs.forEach(function(seg){
        if (seg.length < 2) return;
        var sp = seg.map(function(i){ return x(i).toFixed(1) + ',' + y(raw[i]).toFixed(1); }).join(' ');
        out += '<polygon points="' + x(seg[0]).toFixed(1) + ',' + h + ' ' + sp + ' ' + x(seg[seg.length - 1]).toFixed(1) + ',' + h + '" fill="url(#' + gid + ')"/>';
      });
      // Typical line (continuous across gaps — it's the expected wait)
      if (hasTyp){
        var tpts = [];
        typ.forEach(function(n, i){ if (n != null) tpts.push(x(i).toFixed(1) + ',' + y(n).toFixed(1)); });
        out += '<polyline points="' + tpts.join(' ') + '" fill="none" stroke="' + muted + '" stroke-width="1.75" stroke-dasharray="5,5" opacity="0.8"><title>Average wait</title></polyline>';
      } else {
        var avg = parseFloat(svg.dataset.avg);
        if (!isNaN(avg) && avg >= min && avg <= max){
          out += '<line x1="0" y1="' + y(avg).toFixed(1) + '" x2="' + w + '" y2="' + y(avg).toFixed(1) + '" stroke="' + muted + '" stroke-width="1" stroke-dasharray="5,5" opacity="0.6"><title>Average: ' + avg + ' min</title></line>';
        }
      }
      // Main wait line (per segment, so gaps stay broken)
      segs.forEach(function(seg){
        if (seg.length >= 2){
          var sp = seg.map(function(i){ return x(i).toFixed(1) + ',' + y(raw[i]).toFixed(1); }).join(' ');
          out += '<polyline points="' + sp + '" fill="none" stroke="url(#' + lgid + ')" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
        } else {
          out += '<circle cx="' + x(seg[0]).toFixed(1) + '" cy="' + y(raw[seg[0]]).toFixed(1) + '" r="2.5" fill="' + brand + '"/>';
        }
      });
      out += '<circle cx="' + x(raw.length - 1).toFixed(1) + '" cy="' + y(raw[raw.length - 1]).toFixed(1) + '" r="4" fill="' + mag((raw[raw.length - 1] - min) / rng) + '"/>'
        + '<line class="ov-guide" x1="0" y1="0" x2="0" y2="' + h + '" stroke="' + brand + '" stroke-width="1" opacity="0" stroke-dasharray="3,3"/>'
        + '<circle class="ov-dot" r="4.5" fill="' + brand + '" stroke="#fff" stroke-width="1.5" opacity="0"/>';
      svg.innerHTML = out;
      var wrap = svg.closest('.ov-chart'), tip = wrap && wrap.querySelector('.ov-tip');
      var guide = svg.querySelector('.ov-guide'), dot = svg.querySelector('.ov-dot');
      function hideTip(){ if (tip) tip.hidden = true; guide.setAttribute('opacity', '0'); dot.setAttribute('opacity', '0'); }
      svg.addEventListener('mousemove', function(e){
        if (!tip) return;
        var r = svg.getBoundingClientRect();
        var mx = ((e.clientX - r.left) / r.width) * w;
        var bi = 0, bd = Infinity;
        for (var k = 0; k < raw.length; k++){ var d = Math.abs(x(k) - mx); if (d < bd){ bd = d; bi = k; } }
        var px = x(bi), py = y(raw[bi]);
        guide.setAttribute('x1', px); guide.setAttribute('x2', px); guide.setAttribute('opacity', '0.45');
        dot.setAttribute('cx', px); dot.setAttribute('cy', py); dot.setAttribute('opacity', '1');
        tip.innerHTML = (times[bi] ? '<span class="t">' + times[bi] + '</span> · ' : '') + raw[bi] + ' min' + (hasTyp && typ[bi] != null ? '<span class="t"> · avg ' + Math.round(typ[bi]) + '</span>' : '');
        tip.style.left = (px / w * r.width) + 'px';
        tip.style.top = (py / h * r.height) + 'px';
        tip.hidden = false;
      });
      svg.addEventListener('mouseleave', hideTip);
    });
  }
  drawCurves(document);

  function loadQuickGraphs(panel){
    panel.querySelectorAll('.quick-graph:not([data-loaded])').forEach(function(el){
      // Show the animated loader immediately, even for graphs in hidden sub-tabs.
      if (window.TDLoad && !el.querySelector('.js-plotly-plot')) el.innerHTML = window.TDLoad();
      var sub = el.closest('.gsub');
      if (sub && !sub.classList.contains('on')) return;
      el.dataset.loaded = '1';
      var keys = (el.dataset.key || '').split(',').filter(Boolean);
      fetch(el.dataset.url + '?' + el.dataset.params)
        .then(function(r){ return keys.length ? r.json() : r.text(); })
        .then(function(code){
          var html = keys.length ? keys.map(function(k){ return code[k] || ''; }).join('') : code;
          if (!html || html === 'fail' || code === 'fail' || (keys.length && code[keys[0]] === 'fail' && keys.length === 1)) {
            el.innerHTML = '<div style="text-align:center; color:var(--muted); font-weight:400; padding:12px;">No data available.</div>'; return;
          }
          el.innerHTML = html;
          runScripts(el);
          requestAnimationFrame(function(){ themePlots(el); resizePlots(el); });
        })
        .catch(function(){ el.innerHTML = '<div style="text-align:center; color:var(--muted); font-weight:400; padding:12px;">Could not load.</div>'; });
    });
  }

  // Per-ride view state (graph sub-tab + chosen graph types), so changing the
  // date brings you back to the same graph you were looking at.
  var stateKey = 'tdride:islands-of-adventure:jurassicworldvelocicoaster';
  function loadState(){ try { return JSON.parse(sessionStorage.getItem(stateKey)) || {}; } catch(e){ return {}; } }
  function saveState(fn){ var s = loadState(); fn(s); try { sessionStorage.setItem(stateKey, JSON.stringify(s)); } catch(e){} }
  function restoreState(panel){
    var s = loadState();
    if (s.sub){
      var btn = panel.querySelector('.gsub-btn[data-sub="' + s.sub + '"]');
      if (btn){
        panel.querySelectorAll('.gsub-btn').forEach(function(x){ x.classList.toggle('on', x === btn); });
        panel.querySelectorAll('.gsub').forEach(function(x){ x.classList.toggle('on', x.dataset.sub === s.sub); });
      }
    }
    Object.keys(s.tags || {}).forEach(function(id){
      var target = panel.querySelector('#' + id); if (!target) return;
      var tag = s.tags[id];
      target.dataset.params = target.dataset.params.replace(/tag=[^&]*/, 'tag=' + encodeURIComponent(tag));
      var wrap = panel.querySelector('.gbtns[data-for="' + id + '"]');
      if (wrap) wrap.querySelectorAll('.gbtn').forEach(function(x){ x.classList.toggle('on', x.dataset.tag === tag); });
      if (target.dataset.loaded){
        delete target.dataset.loaded;
        if (target.offsetHeight > 60) target.style.minHeight = target.offsetHeight + 'px';
        target.innerHTML = window.TDLoad ? window.TDLoad() : 'Loading…';
      }
    });
  }

  function activate(name){
    tabs.querySelectorAll('.ptab').forEach(function(b){ b.setAttribute('aria-selected', b.dataset.tab === name); });
    root.querySelectorAll('.ppanel').forEach(function(p){ p.classList.toggle('on', p.dataset.panel === name); });
    var panel = root.querySelector('.ppanel.on'); if (!panel) return;
    var tpl = panel.querySelector('template');
    if (tpl && !panel.dataset.loaded){
      panel.dataset.loaded = '1';
      panel.appendChild(document.importNode(tpl.content, true));
      tpl.remove();
      runScripts(panel);
      restoreState(panel);
    }
    loadQuickGraphs(panel);
    requestAnimationFrame(function(){ themePlots(panel); resizePlots(panel); });
  }

  function currentTab(){
    var cur = tabs.querySelector('.ptab[aria-selected="true"]');
    return cur ? cur.dataset.tab : '';
  }

  tabs.addEventListener('click', function(e){
    var b = e.target.closest('.ptab'); if (!b) return;
    activate(b.dataset.tab);
    if (history.replaceState) history.replaceState(null, '', '#' + b.dataset.tab);
  });

  // "More →" jump links (e.g. hero graph -> Graphs tab)
  document.addEventListener('click', function(e){
    var j = e.target.closest('.ov-jumplink'); if (!j || !j.dataset.tab) return;
    activate(j.dataset.tab);
    if (history.replaceState) history.replaceState(null, '', '#' + j.dataset.tab);
  });

  // Graph sub-tabs
  document.addEventListener('click', function(e){
    var b = e.target.closest('.gsub-btn'); if (!b) return;
    var panel = b.closest('.ppanel');
    panel.querySelectorAll('.gsub-btn').forEach(function(x){ x.classList.toggle('on', x === b); });
    panel.querySelectorAll('.gsub').forEach(function(s){ s.classList.toggle('on', s.dataset.sub === b.dataset.sub); });
    saveState(function(s){ s.sub = b.dataset.sub; });
    loadQuickGraphs(panel);
    var sub = panel.querySelector('.gsub.on');
    if (sub) requestAnimationFrame(function(){ themePlots(sub); resizePlots(sub); });
  });

  // Graph type buttons (swap tag param, refetch)
  document.addEventListener('click', function(e){
    var b = e.target.closest('.gbtn'); if (!b || b.classList.contains('dl-btn')) return;
    var wrap = b.closest('.gbtns'), target = document.getElementById(wrap.dataset.for);
    if (!target || b.classList.contains('on')) return;
    wrap.querySelectorAll('.gbtn').forEach(function(x){ x.classList.toggle('on', x === b); });
    target.dataset.params = target.dataset.params.replace(/tag=[^&]*/, 'tag=' + encodeURIComponent(b.dataset.tag));
    // Keep the graph description in sync with the selected type.
    if (b.dataset.desc){ var gi = b.closest('.card').querySelector('.ginfo'); if (gi) gi.textContent = b.dataset.desc; }
    saveState(function(s){ s.tags = s.tags || {}; s.tags[wrap.dataset.for] = b.dataset.tag; });
    delete target.dataset.loaded;
    if (target.offsetHeight > 60) target.style.minHeight = target.offsetHeight + 'px';
    target.innerHTML = window.TDLoad ? window.TDLoad() : 'Loading…';
    loadQuickGraphs(target.parentElement);
  });

  // Info buttons
  document.addEventListener('click', function(e){
    var b = e.target.closest('.ginfo-btn'); if (!b) return;
    var card = b.closest('.card'); var info = card && card.querySelector('.ginfo');
    if (info) info.hidden = !info.hidden;
  });

  // Data downloads (Thrill Data Plus): month buttons -> download link
  document.addEventListener('click', function(e){
    var b = e.target.closest('.dl-btn'); if (!b) return;
    var out = document.getElementById('dl-out'); if (!out) return;
    document.querySelectorAll('.dl-btn').forEach(function(x){ x.classList.toggle('on', x === b); });
    out.innerHTML = '<div style="text-align:center; color:var(--muted); font-weight:400; padding:10px;">Preparing your download…</div>';
    fetch('/waits/downloadride?download=' + b.dataset.dl + '&park=islands-of-adventure&ride=jurassicworldvelocicoaster')
      .then(function(r){ return r.json(); })
      .then(function(d){ out.innerHTML = d.link || '<div style="text-align:center; color:var(--muted); font-weight:400; padding:10px;">No data available for that period.</div>'; })
      .catch(function(){ out.innerHTML = '<div style="text-align:center; color:var(--muted); font-weight:400; padding:10px;">Could not prepare the download.</div>'; });
  });

  // Ride rating: click along the bar to set 1-100 (small header bar, park-style)
  (function(){
    var bar = document.getElementById('rd-rate-bar');
    if (!bar || !bar.classList.contains('can-rate')) return;
    var fill = document.getElementById('rd-rate-fill'), wrap = document.getElementById('rd-rate');
    bar.addEventListener('click', function(e){
      var r = bar.getBoundingClientRect();
      var val = Math.max(1, Math.min(100, Math.round(((e.clientX - r.left) / r.width) * 100)));
      var mine = document.getElementById('rd-mine');
      if (!mine){ mine = document.createElement('i'); mine.className = 'rd-mine'; mine.id = 'rd-mine'; bar.appendChild(mine); }
      mine.style.left = val + '%';
      mine.title = 'Your rating: ' + val + '/100';
      fetch('/rating/ride?rating=' + val + '&park=' + bar.dataset.park + '&name=' + bar.dataset.ride)
        .then(function(res){ return res.json(); })
        .then(function(d){
          var avg = parseInt(d.rideAvg, 10);
          if (!isNaN(avg) && fill) fill.style.width = avg + '%';
          if (!isNaN(avg) && wrap) wrap.title = 'Rating ' + avg + '/100 — your rating: ' + val + '/100';
        }).catch(function(){});
    });
  })();

  // Ride count (times ridden) toggle
  (function(){
    var btn = document.getElementById('rd-count'); if (!btn) return;
    btn.addEventListener('click', function(){
      fetch('/waits/countride?title=' + btn.dataset.park + '&ride=' + btn.dataset.ride)
        .then(function(r){ return r.json(); })
        .then(function(d){
          var on = d.css === 'remove';   // 'remove' = now counted
          btn.classList.toggle('on', on);
          var i = btn.querySelector('i'); if (i) i.className = 'fa-' + (on ? 'solid' : 'regular') + ' fa-circle-check';
        }).catch(function(){});
    });
  })();

  // Date navigation keeps you on the tab you were viewing (via the #hash,
  // which the deep-link handler restores on the next page load).
  document.addEventListener('click', function(e){
    var a = e.target.closest('.dn-btn'); if (!a || !a.href) return;
    var t = currentTab();
    if (t) a.href = a.href.split('#')[0] + '#' + t;
  });

  // Date picker jump (same tab)
  root.querySelectorAll('.dn-date input[type=date]').forEach(function(inp){
    inp.addEventListener('change', function(){
      if (!inp.value) return;
      var p = inp.value.split('-');
      var t = currentTab();
      window.location.href = '/waits/attraction/islands-of-adventure/jurassicworldvelocicoaster/' + p[0] + '/' + p[1] + '/' + p[2] + (t ? '#' + t : '');
    });
  });

  // Deep-link: open the tab in the URL hash
  var hash = (location.hash || '').replace('#','');
  if (hash && tabs.querySelector('.ptab[data-tab="' + hash + '"]')) activate(hash);
  else activate('overview');
})();
