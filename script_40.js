
    // Wait MAGNITUDE bars appended to wait pills/tiles. The tier is park/ride-
    // specific: it's taken from the up/down/mid class the server already sets from
    // THIS ride's/park's own average wait (above / around / below normal), so each
    // ride is judged on its own scale rather than a meaningless fixed threshold.
    (function(){
      function add(el){
        if (el.dataset.magbar) return;
        var txt = el.textContent || '';
        // Only real wait values — skip price chips ($) and text-only chips.
        if (txt.indexOf('$') !== -1 || !/\d+\s*m(?:in)?\b/.test(txt)) { el.dataset.magbar = '0'; return; }
        el.dataset.magbar = '1';
        var tier = el.classList.contains('up') ? 'high' : el.classList.contains('down') ? 'low' : 'avg';
        var b = document.createElement('span');
        b.className = 'lvl-bars magbar ' + tier;
        b.setAttribute('title', 'Higher / lower than average for this ' + (el.classList.contains('wait-tile') ? 'park' : 'ride'));
        b.innerHTML = '<i></i><i></i><i></i>';
        // Wait tiles: sit the bars inline next to the number (.n); chips: after the text.
        var host = el;
        if (el.classList.contains('wait-tile')){ var nEl = el.querySelector('.n'); if (nEl) host = nEl; }
        host.appendChild(b);
      }
      function scan(root){
        (root || document).querySelectorAll(
          '.chip.up,.chip.down,.chip.mid,.wait-tile.up,.wait-tile.down,.wait-tile.mid'
        ).forEach(add);
      }
      window.TDMagBars = scan;
      if (document.readyState !== 'loading') scan(document);
      else document.addEventListener('DOMContentLoaded', function(){ scan(document); });
      try {
        new MutationObserver(function(muts){
          muts.forEach(function(mu){
            if (!mu.addedNodes) return;
            mu.addedNodes.forEach(function(n){ if (n.nodeType === 1) scan(n); });
          });
        }).observe(document.body, { childList:true, subtree:true });
      } catch(e){}
    })();
  