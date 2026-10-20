// Click a column header to sort that table by the column (primary sort only).
// Click again to reverse. A header with aria-sort in the markup is the
// table's default sort (the server already returns rows in that order).
// Cells sort by data-sort if present, else by a form control's value, else
// by their text; numbers sort numerically and blanks ("", "—") always last.
// Skipped: headers with no text (action columns) or data-nosort, and
// placeholder rows (a single colspan cell, like "No rows yet.").
(function () {
  function prepare(root) {
    root.querySelectorAll('.table-scroll table thead th').forEach(function (th) {
      if (th.hasAttribute('data-nosort') || !th.textContent.trim()) return;
      th.setAttribute('data-sortable', '');
      th.tabIndex = 0;
      th.setAttribute('role', 'columnheader');
    });
  }

  function cellValue(cell) {
    if (!cell) return '';
    if (cell.dataset.sort !== undefined) return cell.dataset.sort.trim();
    var control = cell.querySelector('input, select');
    if (control) return control.value.trim();
    return cell.textContent.trim();
  }

  function isBlank(v) { return v === '' || v === '—'; }

  function sortBy(th) {
    var table = th.closest('table');
    var body = table.tBodies[0];
    var index = th.cellIndex;
    var dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;

    table.querySelectorAll('th[aria-sort]').forEach(function (h) { h.removeAttribute('aria-sort'); });
    th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');

    var rows = Array.prototype.filter.call(body.rows, function (r) {
      return !(r.cells.length === 1 && r.cells[0].colSpan > 1);
    });
    var keyed = rows.map(function (r) { return { row: r, v: cellValue(r.cells[index]) }; });
    keyed.sort(function (a, b) {
      var ab = isBlank(a.v), bb = isBlank(b.v);
      if (ab || bb) return ab === bb ? 0 : (ab ? 1 : -1);
      var an = parseFloat(a.v), bn = parseFloat(b.v);
      var numeric = !isNaN(an) && !isNaN(bn) && /^-?[\d.]+$/.test(a.v) && /^-?[\d.]+$/.test(b.v);
      var c = numeric ? an - bn : a.v.localeCompare(b.v, undefined, { numeric: true, sensitivity: 'base' });
      return c * dir;
    });
    keyed.forEach(function (k) { body.appendChild(k.row); });
  }

  document.addEventListener('click', function (evt) {
    var th = evt.target.closest('th[data-sortable]');
    if (th) sortBy(th);
  });
  document.addEventListener('keydown', function (evt) {
    if (evt.key !== 'Enter' && evt.key !== ' ') return;
    var th = evt.target.closest && evt.target.closest('th[data-sortable]');
    if (th) { evt.preventDefault(); sortBy(th); }
  });

  prepare(document);
  document.addEventListener('htmx:afterSettle', function (evt) { prepare(evt.target || document); });
})();
