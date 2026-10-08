// Activity page: show each entry's timestamp in the viewer's own time zone,
// relative when recent ("5 min ago", "Yesterday 3:12 PM"), with the full
// date/time on hover. The server-rendered text (UTC) is the no-JS fallback.
(function () {
  var timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
  var weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short' });
  var dateFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });
  var dateYearFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  var fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'short' });

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  }

  function describe(when, now) {
    var minutes = Math.floor((now - when) / 60000);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return minutes + ' min ago';
    var days = Math.round((startOfDay(now) - startOfDay(when)) / 86400000);
    var time = timeFmt.format(when);
    if (days === 0) return 'Today ' + time;
    if (days === 1) return 'Yesterday ' + time;
    if (days < 7) return weekdayFmt.format(when) + ' ' + time;
    var fmt = when.getFullYear() === now.getFullYear() ? dateFmt : dateYearFmt;
    return fmt.format(when) + ', ' + time;
  }

  function render() {
    var now = new Date();
    document.querySelectorAll('time.activity-time[datetime]').forEach(function (el) {
      var when = new Date(el.getAttribute('datetime'));
      if (isNaN(when)) return;
      el.textContent = describe(when, now);
      el.title = fullFmt.format(when);
    });
  }

  render();
  // "Show older" pages arrive via htmx; relative times also go stale.
  document.addEventListener('htmx:afterSettle', render);
  setInterval(render, 60000);
})();
