const error = document.querySelector("#error");
const startInput = document.querySelector("#range-start");
const endInput = document.querySelector("#range-end");
const tableBody = document.querySelector("#stats-table tbody");

const COLORS = { accent: "#93c5fd", occupied: "#f87171", grid: "rgba(255, 255, 255, 0.08)", muted: "#9ca3af" };
const PALETTE = ["#93c5fd", "#f87171", "#34d399", "#fbbf24", "#c084fc", "#22d3ee", "#fb923c"];

Chart.defaults.color = COLORS.muted;
Chart.defaults.borderColor = COLORS.grid;
Chart.defaults.font.family = "system-ui, sans-serif";

let servedChart = null;
let occupancyChart = null;

function pad(n) {
  return String(n).padStart(2, "0");
}

function toUtcInputValue(date) {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}

function fromUtcInputValue(value) {
  return new Date(`${value}:00Z`);
}

function defaultRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
  return { start, end };
}

function renderTable(stats) {
  tableBody.replaceChildren();
  for (const row of stats) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.waiter_name}</td>
      <td>${row.shifts}</td>
      <td>${row.hours_worked}</td>
      <td>${row.avg_occupancy}</td>
      <td>${row.people_served}</td>
    `;
    tableBody.append(tr);
  }
}

function renderCharts(stats) {
  const labels = stats.map((row) => row.waiter_name);
  const colors = labels.map((_, index) => PALETTE[index % PALETTE.length]);

  const servedConfig = {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Personas atendidas", data: stats.map((row) => row.people_served), backgroundColor: colors, borderRadius: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  };

  const occupancyConfig = {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Ocupación promedio", data: stats.map((row) => row.avg_occupancy), backgroundColor: colors, borderRadius: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, grid: { color: COLORS.grid } }, x: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    },
  };

  if (servedChart) {
    servedChart.data = servedConfig.data;
    servedChart.update();
  } else {
    servedChart = new Chart(document.querySelector("#chart-served"), servedConfig);
  }

  if (occupancyChart) {
    occupancyChart.data = occupancyConfig.data;
    occupancyChart.update();
  } else {
    occupancyChart = new Chart(document.querySelector("#chart-avg-occupancy"), occupancyConfig);
  }
}

async function loadStats() {
  const start = fromUtcInputValue(startInput.value).toISOString();
  const end = fromUtcInputValue(endInput.value).toISOString();

  try {
    const response = await fetch(`/api/waiters/stats?start=${start}&end=${end}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const stats = await response.json();
    renderTable(stats);
    renderCharts(stats);
    error.hidden = true;
  } catch (reason) {
    error.textContent = `No se pudieron cargar las estadísticas: ${reason.message}`;
    error.hidden = false;
  }
}

const { start, end } = defaultRange();
startInput.value = toUtcInputValue(start);
endInput.value = toUtcInputValue(end);

document.querySelector("#apply-range-btn").addEventListener("click", loadStats);
loadStats();
