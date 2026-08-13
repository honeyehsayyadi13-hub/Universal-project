
    // Stay22 hotel maps: match the map tiles to the site theme (mapstyle=dark in
    // dark themes, light otherwise) and re-point on theme toggle. Each iframe
    // carries its base URL in data-s22src and has no src until we set it here.
    (function(){
      function darkSurface(){
        var t = document.documentElement.getAttribute('data-theme');
        if (t === 'light') return false;
        if (t === 'dark' || t === 'halloween' || t === 'christmas') return true;
        return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
      }
      function apply(){
        var style = darkSurface() ? 'dark' : 'light';
        document.querySelectorAll('iframe.stay22-map[data-s22src]').forEach(function(f){
          var base = f.getAttribute('data-s22src');
          var url = base + (base.indexOf('?') > -1 ? '&' : '?') + 'mapstyle=' + style;
          if (f.getAttribute('src') !== url) f.setAttribute('src', url);
        });
      }
      apply();
      new MutationObserver(apply).observe(document.documentElement, {attributes:true, attributeFilter:['data-theme']});
      if (window.matchMedia){
        try { window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply); } catch(e){}
      }
    })();
  