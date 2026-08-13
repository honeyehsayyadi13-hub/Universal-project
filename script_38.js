
    // Drawer
    var body = document.body;
    function openNav(){ body.classList.add('nav-open'); }
    function closeNav(){ body.classList.remove('nav-open'); }
    document.getElementById('nav-open').addEventListener('click', openNav);
    document.getElementById('nav-close').addEventListener('click', closeNav);
    document.getElementById('scrim').addEventListener('click', closeNav);
    document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeNav(); });

    // Mobile search popup
    (function(){
      var openBtn = document.getElementById('search-open'); if (!openBtn) return;
      var input = document.getElementById('search-modal-input');
      function openSearch(){ body.classList.add('search-open'); if (input) setTimeout(function(){ input.focus(); }, 60); }
      function closeSearch(){ body.classList.remove('search-open'); }
      openBtn.addEventListener('click', openSearch);
      document.getElementById('search-scrim').addEventListener('click', closeSearch);
      document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeSearch(); });
    })();

    // Search autocomplete (chains, parks, rides) on every search field
    (function(){
      var forms = document.querySelectorAll('form.search, form.hero-search');
      forms.forEach(function(form){
        var input = form.querySelector('input[name="q"]'); if (!input) return;
        form.style.position = 'relative';
        var menu = document.createElement('div'); menu.className = 'ac-menu';
        form.appendChild(menu);
        var items = [], active = -1, timer = null, lastQ = '';

        function hide(){ menu.classList.remove('on'); active = -1; }
        function go(url){ if (url) window.location.href = url; }

        // Wait chip for a result: a live, color-coded current wait (with trend
        // arrow) when the park/ride is open, otherwise a neutral "~Nm" average.
        function acWait(r){
          if (r.wait == null) return '';
          if (r.waitKind === 'live'){
            var arrow = r.trend === 'up' ? '↑ ' : (r.trend === 'down' ? '↓ ' : (r.trend === 'steady' ? '→ ' : ''));
            return '<span class="chip ' + (r.waitClass || 'mid') + ' ac-wait" title="Current wait">' + arrow + r.wait + 'm</span>';
          }
          return '<span class="chip ac-wait ac-wait-avg" title="Average wait">~' + r.wait + 'm</span>';
        }

        function render(results){
          items = results || [];
          if (!items.length){ menu.innerHTML = '<div class="ac-empty">No matches</div>'; menu.classList.add('on'); return; }
          menu.innerHTML = items.map(function(r, i){
            var sub = r.sub ? '<div class="ac-sub">' + r.sub + '</div>' : '';
            return '<div class="ac-item" data-i="' + i + '"><div class="ac-main"><div class="ac-label">'
              + r.label + '</div>' + sub + '</div>' + acWait(r) + '<span class="ac-type">' + r.type + '</span></div>';
          }).join('');
          active = -1;
          menu.classList.add('on');
          menu.querySelectorAll('.ac-item').forEach(function(el){
            el.addEventListener('mousedown', function(e){ e.preventDefault(); go(items[+el.dataset.i].url); });
          });
        }

        function fetchSuggest(q){
          fetch('/wa/search-suggest?q=' + encodeURIComponent(q))
            .then(function(r){ return r.json(); })
            .then(function(d){ if (input.value.trim() === q) render(d.results); })
            .catch(function(){ hide(); });
        }

        input.addEventListener('input', function(){
          var q = input.value.trim();
          if (timer) clearTimeout(timer);
          if (q.length < 2){ hide(); return; }
          if (q === lastQ){ return; }
          lastQ = q;
          timer = setTimeout(function(){ fetchSuggest(q); }, 180);
        });

        function highlight(){
          menu.querySelectorAll('.ac-item').forEach(function(el, i){ el.classList.toggle('active', i === active); });
        }
        input.addEventListener('keydown', function(e){
          if (!menu.classList.contains('on') || !items.length) return;
          if (e.key === 'ArrowDown'){ e.preventDefault(); active = (active + 1) % items.length; highlight(); }
          else if (e.key === 'ArrowUp'){ e.preventDefault(); active = (active - 1 + items.length) % items.length; highlight(); }
          else if (e.key === 'Enter'){ if (active >= 0){ e.preventDefault(); go(items[active].url); } }
          else if (e.key === 'Escape'){ hide(); }
        });
        input.addEventListener('blur', function(){ setTimeout(hide, 120); });
      });
    })();

    // Theme cycle: Light -> Dark -> Halloween -> Christmas -> Light
    (function(){
      // There are TWO toggles now — one in the header (desktop) and one in the
      // mobile utility strip — so drive every .theme-toggle / .theme-icon
      // rather than a single id.
      var root = document.documentElement;
      var btns = [].slice.call(document.querySelectorAll('.theme-toggle'));
      var order = window.TD_THEME_ORDER || ['light', 'dark'];
      var icons = { light:'fa-solid fa-sun', dark:'fa-solid fa-moon', halloween:'fa-solid fa-ghost', christmas:'fa-solid fa-tree' };
      var labels = { light:'Light', dark:'Dark', halloween:'Halloween', christmas:'Christmas' };
      function current(){ var t = root.getAttribute('data-theme'); return icons[t] ? t : 'light'; }
      function paint(){
        var t = current();
        [].slice.call(document.querySelectorAll('.theme-icon')).forEach(function(ic){
          ic.className = 'theme-icon ' + icons[t];
        });
        btns.forEach(function(b){
          b.setAttribute('title', labels[t] + ' theme — click to change');
          b.setAttribute('aria-label', labels[t] + ' theme');
        });
      }
      paint();
      btns.forEach(function(b){
        b.addEventListener('click', function(){
          var next = order[(order.indexOf(current()) + 1) % order.length];
          root.setAttribute('data-theme', next);
          localStorage.setItem('theme', next);
          paint();
        });
      });
    })();

    // Loading state markup: spinning ferris wheel + a random on-theme message.
    (function(){
      var phrases = ['Loading some awesome data!', 'Riding the data coaster…', 'Measuring the wait times…',
        'Checking the queue…', 'Warming up the ferris wheel…', 'Crunching the crowd levels…',
        'Finding the shortest lines…', 'Consulting the ride ops…', 'Counting minutes so you don’t have to…'];
      window.TDLoad = function(msg){
        var m = msg || phrases[Math.floor((Date.now() / 1000) % phrases.length)];
        return '<div class="td-load"><i class="fa-solid fa-ferris-wheel fw"></i><span class="msg">' + m + '</span></div>';
      };
    })();

    // Parks-grid sort control (.pk-sort → reorders .park-tile in its target
    // grid). Delegated so it also works for grids injected lazily into tabs.
    document.addEventListener('change', function(e){
      var sel = e.target.closest('.pk-sort'); if (!sel) return;
      var grid = document.getElementById(sel.dataset.grid); if (!grid) return;
      var tiles = Array.prototype.slice.call(grid.querySelectorAll('.park-tile'));
      var mode = sel.value;
      tiles.sort(function(a, b){
        var na = a.dataset.name || '', nb = b.dataset.name || '';
        if (mode.indexOf('wait') === 0){
          var wa = parseFloat(a.dataset.wait), wb = parseFloat(b.dataset.wait);
          var ca = !(wa >= 0), cb = !(wb >= 0);          // closed/unknown → bottom
          if (ca && cb) return na.localeCompare(nb);
          if (ca) return 1; if (cb) return -1;
          return mode === 'wait-asc' ? wa - wb : wb - wa;
        }
        var r = na.localeCompare(nb);
        return mode === 'name-desc' ? -r : r;
      });
      tiles.forEach(function(t){ grid.appendChild(t); });
    });

    // Favorites (hearts) — shared: park cards (.pt-fav) + ride rows (.rf-fav).
    (function(){
      window.TD_FAVS = new Set();        // park slugs
      window.TD_RIDE_FAVS = new Set();   // ride slugs
      function paint(btn, on){ btn.classList.toggle('on', on); var i = btn.querySelector('i'); if (i) i.className = on ? 'fa-solid fa-heart' : 'fa-regular fa-heart'; }
      window.TDMarkFavs = function(scope){
        scope = scope || document;
        scope.querySelectorAll('.pt-fav').forEach(function(b){ if (window.TD_FAVS.has(b.dataset.slug)) paint(b, true); });
        scope.querySelectorAll('.rf-fav').forEach(function(b){ if (window.TD_RIDE_FAVS.has(b.dataset.slug)) paint(b, true); });
      };
      if (!window.TD_AUTH) return;
      fetch('/wa/favorites').then(function(r){ return r.json(); }).then(function(d){
        (d.slugs || []).forEach(function(s){ window.TD_FAVS.add(s); });
        (d.rideSlugs || []).forEach(function(s){ window.TD_RIDE_FAVS.add(s); });
        window.TDMarkFavs(document);
      }).catch(function(){});
      document.addEventListener('click', function(e){
        var rb = e.target.closest('.rf-fav'), pb = e.target.closest('.pt-fav'), btn = rb || pb;
        if (!btn) return;
        var isRide = !!rb, slug = btn.dataset.slug, set = isRide ? window.TD_RIDE_FAVS : window.TD_FAVS;
        var willFav = !btn.classList.contains('on');
        paint(btn, willFav);   // optimistic
        var body = isRide
          ? { ride_slug: slug, park_slug: btn.dataset.park, ride_name: btn.dataset.name, chain_slug: btn.dataset.chain, chain_name: btn.dataset.chainname }
          : { park_slug: slug, park_name: btn.dataset.name, chain_slug: btn.dataset.chain, chain_name: btn.dataset.chainName };
        fetch(isRide ? '/wa/favorite/ride/toggle' : '/wa/favorite/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.tdCsrf() },
          body: JSON.stringify(body)
        })
        .then(function(r){ return r.json(); })
        .then(function(d){ if (d && typeof d.favorited === 'boolean'){ paint(btn, d.favorited); if (d.favorited) set.add(slug); else set.delete(slug); } })
        .catch(function(){ paint(btn, !willFav); });   // revert on failure
      });
    })();

    // Wait Times modal (opened by any .wt-open element) — sortable table format
    (function(){
      var modal = document.getElementById('wt-modal'); if (!modal) return;
      var bodyEl = document.getElementById('wt-body'), titleEl = document.getElementById('wt-title');
      function open(){ document.body.classList.add('wt-open'); }
      function close(){ document.body.classList.remove('wt-open'); }
      document.addEventListener('click', function(e){
        // [data-park] keeps this from matching <body> (which carries the
        // .wt-open state class while the modal is open) on every click.
        var t = e.target.closest('.wt-open[data-park]'); if (!t) return;
        e.preventDefault();
        titleEl.textContent = (t.dataset.name || 'Park') + ' — Wait Times';
        bodyEl.innerHTML = window.TDLoad ? window.TDLoad() : '<div class="wt-empty">Loading…</div>';
        open();
        fetch('/wa/park-waits/' + t.dataset.park + '?fmt=table')
          .then(function(r){ return r.text(); })
          .then(function(html){ bodyEl.innerHTML = html; if (window.TDMarkFavs) window.TDMarkFavs(bodyEl); })
          .catch(function(){ bodyEl.innerHTML = '<div class="wt-empty">Could not load.</div>'; });
      });
      document.getElementById('wt-close').addEventListener('click', close);
      document.getElementById('wt-scrim').addEventListener('click', close);
      document.addEventListener('keydown', function(e){ if (e.key === 'Escape') close(); });
    })();

    // Rides table sorting (Live Waits tab + Wait Times modal): click a header
    // to sort; click again to flip direction.
    document.addEventListener('click', function(e){
      var th = e.target.closest('.rt-sort'); if (!th) return;
      var table = th.closest('table'), tbody = table.querySelector('tbody');
      var k = th.dataset.k, num = th.dataset.t === 'num';
      var dir = th.dataset.dir === 'asc' ? 'desc' : (th.dataset.dir === 'desc' ? 'asc' : (num ? 'desc' : 'asc'));
      table.querySelectorAll('.rt-sort').forEach(function(x){
        x.removeAttribute('data-dir');
        var i = x.querySelector('i'); if (i) i.className = 'fa-solid fa-sort';
      });
      th.dataset.dir = dir;
      var icon = th.querySelector('i'); if (icon) icon.className = dir === 'asc' ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
      var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b){
        var va = a.dataset[k] || '', vb = b.dataset[k] || '';
        var c = num ? (parseFloat(va) || 0) - (parseFloat(vb) || 0) : va.localeCompare(vb);
        return dir === 'asc' ? c : -c;
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  