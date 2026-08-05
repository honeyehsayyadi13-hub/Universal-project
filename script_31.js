
(function(){
  var KEY = 'td.plusStrip.dismissed';
  var el = document.getElementById('plus-strip');
  if (!el) return;

  var until = 0;
  try { until = parseInt(localStorage.getItem(KEY) || '0', 10) || 0; } catch(e){}

  // Dismissal lapses after 30 days rather than being permanent — someone who
  // said "not now" in March is a fair ask again in April.
  if (Date.now() < until) return;

  el.hidden = false;
  if (window.tdTrackGate) window.tdTrackGate('plus_strip');

  document.getElementById('plus-strip-x').addEventListener('click', function(){
    el.hidden = true;
    try { localStorage.setItem(KEY, String(Date.now() + 30 * 24 * 60 * 60 * 1000)); } catch(e){}
  });
})();
