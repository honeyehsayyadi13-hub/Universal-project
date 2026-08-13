
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    gtag('js', new Date());
    gtag('config', 'UA-143003108-1');

    /* ------------------------------------------------------------------
       Conversion instrumentation.

       Every Plus upsell points at the native /plus checkout (previously off-site),
       so without this there is no way to tell which page earned a subscription
       — or whether the graph tool's six upsells outperform a park page's one.
       Tagged clicks make that comparable.

       Reported dimensions:
         source_page  which template the click came from (path)
         source_area  nearest section heading, so "upsell in the hero" and
                      "upsell beside a locked feature" are distinguishable
         member_state logged_out | free | plus  (Plus should never fire an
                      upsell click; if it does, a gate is showing wrongly)
       ------------------------------------------------------------------ */
    (function(){
      var STATE = 'logged_out';

      function area(el){
        // Nearest preceding section label gives context without hand-tagging
        // every link; falls back to the containing card's heading.
        var card = el.closest && (el.closest('.card') || el.closest('section') || el.closest('.wm-panel'));
        var h = card && card.querySelector('h1,h2,h3,.sec-head h2,.eyebrow');
        var txt = (h && h.textContent) || (el.closest('header') ? 'header' : '') || 'page';
        return txt.trim().replace(/\s+/g, ' ').slice(0, 60);
      }

      function send(name, el, extra){
        var d = {
          source_page: location.pathname,
          source_area: area(el),
          link_text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
          member_state: STATE
        };
        if (extra) for (var k in extra) d[k] = extra[k];
        try { gtag('event', name, d); } catch (e) {}
      }

      document.addEventListener('click', function(e){
        var a = e.target.closest && e.target.closest('a');
        if (!a || !a.href) return;

        // The money link — the native /plus checkout (legacy off-site
        // /subscriptions links still count too, so old pages/emails keep tracking).
        if (a.pathname === '/plus' || a.pathname === '/plus/' || a.href.indexOf('/subscriptions') > -1) { send('plus_upsell_click', a); return; }

        // Free-account funnel: the step before Plus for logged-out visitors.
        if (/\/users\/signup/.test(a.href)) { send('signup_click', a); return; }
        if (/\/users\/login/.test(a.href))  { send('login_click', a);  return; }
      }, true);

      // Fires once per pageview so upsell clicks can be divided by the number
      // of people who actually saw a gate, rather than by all traffic.
      window.tdTrackGate = function(feature){
        try { gtag('event', 'plus_gate_view', { feature: feature, source_page: location.pathname, member_state: STATE }); } catch (e) {}
      };
    })();
  