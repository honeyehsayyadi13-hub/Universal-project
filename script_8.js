
    // Resolve + set the theme before paint (always set data-theme so the toggle
    // is never ambiguous on a fresh load).
    (function () {
      // Seasonal themes are only offered in-season (Halloween: Aug 15 - Oct 31,
      // Christmas: Nov 1 - Dec 31); out-of-season stored picks fall back to light/dark.
      var now = new Date(), m = now.getMonth(), d = now.getDate();   // m: 0=Jan .. 11=Dec
      var order = ['light', 'dark'];
      if ((m === 7 && d >= 15) || m === 8 || m === 9) order.push('halloween');
      if (m === 10 || m === 11) order.push('christmas');
      window.TD_THEME_ORDER = order;
      var valid = {}; order.forEach(function(x){ valid[x] = 1; });
      var t = localStorage.getItem('theme');
      // Dark is the default; a stored pick (set by the toggle) always wins.
      if (!valid[t]) { t = 'dark'; }
      document.documentElement.setAttribute('data-theme', t);
    })();
    // Auth flag + CSRF token for logged-in features (e.g. favorites).
    window.TD_AUTH = false;
    window.TD_CSRF = "0sQ559cnjmZddcTvJlOWgBfjR64k2TCydmSodgUbxqjhAhCgMAzGDlaXZba3mKog";
    // Prefer the LIVE csrftoken cookie over the value baked into this HTML: a
    // cached/stale page otherwise submits an outdated token and Django rejects
    // the POST with 403 "CSRF Failed".
    window.tdCsrf = function(){
      try {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (m && m[1]) return decodeURIComponent(m[1]);
      } catch (e) {}
      return window.TD_CSRF || '';
    };
    if (window.TD_AUTH) document.documentElement.classList.add('is-auth');
  