/* Summary for the Month: the four charts.
 *
 * The numbers are worked out on the server and arrive as JSON; this only draws
 * them. Amounts are in lakhs, because "17" reads faster on an axis than
 * "1,700,000". If the chart library cannot load (no network), the tables beside
 * each chart still carry every figure, so nothing is lost but the picture.
 */
(function () {
  "use strict";

  var holder = document.getElementById("mo-data");
  if (!holder || !window.Chart) return;
  var data = JSON.parse(holder.textContent);

  var PALETTE = ["#D4AF37", "#5B7CFA", "#34D399", "#FB7185", "#A78BFA", "#F59E0B", "#22D3EE", "#94A3B8", "#F472B6", "#84CC16", "#FB923C", "#38BDF8"];

  function ink() {
    return getComputedStyle(document.body).color || "#e6eaf4";
  }

  function lakh(value) {
    if (value == null) return "";
    return "₹" + (value >= 100 ? Math.round(value) : value.toFixed(1)).toString() + " L";
  }

  function theme() {
    Chart.defaults.color = ink();
    Chart.defaults.borderColor = "rgba(148, 163, 184, 0.18)";
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
  }
  theme();

  function draw(id, config) {
    var canvas = document.getElementById(id);
    if (canvas) new Chart(canvas, config);
  }

  var moneyTip = {
    callbacks: {
      label: function (context) {
        var value = context.parsed.y != null ? context.parsed.y : context.parsed;
        return " " + context.dataset.label + ": " + lakh(value);
      }
    }
  };
  var axisMoney = { beginAtZero: true, ticks: { callback: function (v) { return v + " L"; } } };

  // ---- orders by executive, against target
  var ex = data.executives;
  if (ex.labels.length) {
    var hasTargets = ex.targets.some(function (t) { return t != null; });
    var sets = [{ label: "Orders taken", data: ex.values, backgroundColor: PALETTE[0], borderRadius: 6, maxBarThickness: 46 }];
    if (hasTargets) {
      sets.push({
        label: "Target", data: ex.targets, backgroundColor: "rgba(91, 124, 250, 0.35)", borderColor: PALETTE[1],
        borderWidth: 1.5, borderRadius: 6, maxBarThickness: 46
      });
    }
    draw("chart-executives", {
      type: "bar",
      data: { labels: ex.labels, datasets: sets },
      options: { plugins: { tooltip: moneyTip }, scales: { y: axisMoney, x: { grid: { display: false } } } }
    });
  }

  // ---- six months, three lines of money
  var tr = data.trend;
  draw("chart-trend", {
    type: "bar",
    data: {
      labels: tr.labels,
      datasets: [
        { label: "Orders", data: tr.orders, backgroundColor: PALETTE[0], borderRadius: 5, maxBarThickness: 30 },
        { label: "Invoiced", data: tr.invoiced, backgroundColor: PALETTE[1], borderRadius: 5, maxBarThickness: 30 },
        { label: "Collected", data: tr.collected, backgroundColor: PALETTE[2], borderRadius: 5, maxBarThickness: 30 }
      ]
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: moneyTip, legend: { position: "bottom" } },
      scales: { y: axisMoney, x: { grid: { display: false } } }
    }
  });

  function ring(id, block, colours) {
    if (!block.labels.length) return;
    draw(id, {
      type: "doughnut",
      data: { labels: block.labels, datasets: [{ data: block.values, backgroundColor: colours, borderWidth: 0, hoverOffset: 6 }] },
      options: {
        cutout: "58%",
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (context) {
                var total = context.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                var share = total ? Math.round((context.parsed * 100) / total) : 0;
                return " " + context.label + ": " + lakh(context.parsed) + " (" + share + "%)";
              }
            }
          }
        }
      }
    });
  }

  // ---- which source won the orders, and how old the unpaid money is
  ring("chart-sources", data.sources, PALETTE);
  ring("chart-aging", data.aging, ["#34D399", "#F59E0B", "#FB7185"]);

  // Chart.js reads the default colours once, when a chart is made, and keeps them on
  // its axes and legend. So a change of colour has to be written into each chart.
  function redraw() {
    var text = Chart.defaults.color, grid = Chart.defaults.borderColor;
    Object.keys(Chart.instances).forEach(function (key) {
      var chart = Chart.instances[key], scales = chart.options.scales || {};
      Object.keys(scales).forEach(function (axis) {
        scales[axis].ticks.color = text;
        scales[axis].grid.color = grid;
      });
      chart.options.plugins.legend.labels.color = text;
      chart.update("none");
    });
  }

  // Follow the light/dark switch without a reload.
  new MutationObserver(function () { theme(); redraw(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-bs-theme"] });

  // A chart is pixels in a canvas, drawn in the screen's colours: pale text on a
  // navy page. Print styles cannot recolour it, so on paper it is redrawn in dark ink.
  function forPaper(printing) {
    if (printing) {
      Chart.defaults.color = "#111";
      Chart.defaults.borderColor = "rgba(0, 0, 0, 0.15)";
    } else {
      theme();
    }
    redraw();
  }
  window.addEventListener("beforeprint", function () { forPaper(true); });
  window.addEventListener("afterprint", function () { forPaper(false); });
  var paper = window.matchMedia("print");
  if (paper.addEventListener) paper.addEventListener("change", function (event) { forPaper(event.matches); });
})();
