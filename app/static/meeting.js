// Live meeting in the sidebar (admin only; see templates/_nav.html).
//
// The server renders each step's banked seconds plus, for the one that's
// running, when it started. The clocks here are recomputed from those every
// second, so they stay right across reloads and background tabs.
(function () {
  var offset = null; // server clock minus this browser's clock, in ms

  function fmt(seconds) {
    var neg = seconds < 0;
    var s = Math.abs(Math.round(seconds));
    var m = Math.floor(s / 60);
    var rest = s % 60;
    return (neg ? '-' : '') + m + ':' + (rest < 10 ? '0' : '') + rest;
  }

  function tick() {
    var panel = document.querySelector('.meeting-panel');
    if (!panel) { offset = null; return; }
    if (offset === null || panel.dataset.synced !== panel.dataset.serverNow) {
      offset = Number(panel.dataset.serverNow) - Date.now();
      panel.dataset.synced = panel.dataset.serverNow;
    }
    var now = Date.now() + offset;
    var used = 0;
    panel.querySelectorAll('.meeting-step').forEach(function (li) {
      var elapsed = Number(li.dataset.base);
      if (li.dataset.since) elapsed += Math.max(0, (now - Number(li.dataset.since)) / 1000);
      elapsed = Math.floor(elapsed);
      used += elapsed;
      var left = Number(li.dataset.allotted) - elapsed;
      var out = li.querySelector('[data-step-time]');
      out.textContent = fmt(left);
      out.classList.toggle('over', left < 0);
    });
    var total = Number(panel.dataset.totalAllotted);
    panel.querySelector('[data-total-used]').textContent = fmt(used);
    var leftEl = panel.querySelector('[data-total-left]');
    leftEl.textContent = fmt(total - used);
    leftEl.parentNode.classList.toggle('over', total - used < 0);
  }

  // Open a page in <main> without reloading, so the rail (and, on a phone,
  // the open drawer) and the clocks carry on undisturbed.
  function open(url) {
    if (!window.htmx) { window.location.href = url; return; }
    htmx.ajax('GET', url, { target: 'main', select: 'main', swap: 'outerHTML' }).then(function () {
      if (window.location.pathname !== url) history.pushState({ boosted: true }, '', url);
      markActive(url);
    }, function () { window.location.href = url; });
  }

  function markActive(url) {
    document.querySelectorAll('#site-nav > a, #site-nav .nav-row > a').forEach(function (a) {
      var href = a.getAttribute('href');
      var on = href === '/' ? url === '/' : url.indexOf(href) === 0;
      a.classList.toggle('active', on);
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }

  document.addEventListener('meetingNavigate', function (evt) {
    var url = evt.detail && (evt.detail.value || evt.detail);
    if (typeof url === 'string') open(url);
  });

  // While a meeting is running only a few links are left, and following them
  // loads the page in place too.
  document.addEventListener('click', function (evt) {
    var link = evt.target.closest('#site-nav a[href]');
    if (!link || !document.querySelector('.meeting-panel')) return;
    if (evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.button) return;
    evt.preventDefault();
    open(link.getAttribute('href'));
  });

  window.addEventListener('popstate', function () { window.location.reload(); });
  document.addEventListener('htmx:afterSwap', tick);
  document.addEventListener('DOMContentLoaded', tick);
  setInterval(tick, 1000);
})();
