
    // Shared magnitude color for f in [0,1]: the Plasma colormap, THEME-ADAPTIVE.
    // A single ramp can't span dark-navy to bright-yellow and stay visible on both
    // surfaces, so each theme uses the half of plasma that reads on its background
    // (mirrors the --mag1..5 CSS split):
    //   • light theme -> lower half  (navy -> orange), dark enough for white
    //   • dark themes  -> upper half  (magenta -> yellow), light enough for dark
    // Dark theme passes CVD outright (OKLab dE ~11); light theme leans on the
    // bars/numbers. Always paired with a bar/number.
    window.tdMag = (function(){
      // Light = true viridis (dark-purple high end reads on white). Dark swaps the
      // too-dark purple for a brighter violet so the high end stays visible on dark.
      var LIGHT = ['#440154','#482878','#3e4a89','#31688e','#26828e','#1f9e89','#35b779','#6ece58','#a5d63f','#9acd32'];
      var DARK  = ['#a259d6','#8a54c8','#6b52b0','#3f5f97','#2c8a8e','#1f9e89','#35b779','#6ece58','#b5de2b','#fde725'];
      function parse(a){ return a.map(function(h){ return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]; }); }
      var PL = parse(LIGHT), PD = parse(DARK);
      function interp(pts, f){
        var x = f * (pts.length - 1), i = Math.floor(x), t = x - i;
        if (i >= pts.length - 1){ i = pts.length - 2; t = 1; }
        var a = pts[i], b = pts[i + 1];
        return 'rgb(' + Math.round(a[0] + (b[0]-a[0])*t) + ',' +
                        Math.round(a[1] + (b[1]-a[1])*t) + ',' +
                        Math.round(a[2] + (b[2]-a[2])*t) + ')';
      }
      function darkSurface(){
        var t = document.documentElement.getAttribute('data-theme');
        if (t === 'light') return false;
        if (t === 'dark' || t === 'halloween' || t === 'christmas') return true;
        return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
      }
      return function(f){
        f = Math.max(0, Math.min(1, f));
        var dark = darkSurface();
        var hi = 1.00;   // both arrays span full range (LIGHT ends at yellow-green, DARK at yellow); reversed so low value = bright end
        return interp(dark ? PD : PL, hi * (1 - f));
      };
    })();
  