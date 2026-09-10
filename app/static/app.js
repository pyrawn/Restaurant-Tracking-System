const REFRESH_MS = 30_000;
const HISTORY_HOURS = 3;

const grid = document.querySelector("#table-grid");
const kpiStrip = document.querySelector("#kpi-strip");
const error = document.querySelector("#error");
const lastUpdated = document.querySelector("#last-updated");

const COLORS = {
  occupied: "#f87171",
  free: "#34d399",
  capacity: "rgba(147, 197, 253, 0.35)",
  accent: "#93c5fd",
  grid: "rgba(255, 255, 255, 0.08)",
  text: "#f9fafb",
  muted: "#9ca3af",
};

const TABLE_PALETTE = [
  "#93c5fd", "#f87171", "#34d399", "#fbbf24", "#c084fc", "#22d3ee", "#fb923c",
];

Chart.defaults.color = COLORS.muted;
Chart.defaults.borderColor = COLORS.grid;
Chart.defaults.font.family = "system-ui, sans-serif";

let currentChart = null;
let occupancyChart = null;
let trendChart = null;

function renderTables(tables) {
  grid.replaceChildren();
  for (const table of tables) {
    const card = document.createElement("article");
    const occupied = table.occupied === true;
    card.className = `table-card ${occupied ? "occupied" : "free"}`;

    const title = document.createElement("h2");
    title.textContent = table.table_name;
    const count = document.createElement("p");
    count.textContent = table.people_count == null
      ? "Sin observación"
      : `${table.people_count}/${table.capacity} personas`;

    card.append(title, count);
    grid.append(card);
  }
  lastUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
}

function renderKpis(tables) {
  const withData = tables.filter((table) => table.people_count != null);
  const totalPeople = withData.reduce((sum, table) => sum + table.people_count, 0);
  const totalCapacity = tables.reduce((sum, table) => sum + table.capacity, 0);
  const occupiedCount = tables.filter((table) => table.occupied === true).length;
  const occupancyRate = tables.length ? Math.round((occupiedCount / tables.length) * 100) : 0;
  const fillRate = totalCapacity ? Math.round((totalPeople / totalCapacity) * 100) : 0;
  const avgConfidence = withData.length
    ? Math.round((withData.reduce((sum, table) => sum + table.confidence, 0) / withData.length) * 100)
    : null;
  const busiest = withData.reduce(
    (best, table) => (best == null || table.people_count > best.people_count ? table : best),
    null,
  );

  const kpis = [
    { label: "Personas ahora", value: totalPeople, hint: `de ${totalCapacity} lugares` },
    { label: "Mesas ocupadas", value: `${occupiedCount}/${tables.length}`, hint: `${occupancyRate}% ocupación` },
    { label: "Aforo utilizado", value: `${fillRate}%`, hint: "capacidad total" },
    {
      label: "Mesa con más gente",
      value: busiest ? busiest.table_name : "—",
      hint: busiest ? `${busiest.people_count} personas` : "sin datos",
    },
    { label: "Confianza del modelo", value: avgConfidence == null ? "—" : `${avgConfidence}%`, hint: "promedio" },
  ];

  kpiStrip.replaceChildren();
  for (const kpi of kpis) {
    const card = document.createElement("article");
    card.className = "kpi-card";
    const label = document.createElement("p");
    label.className = "kpi-label";
    label.textContent = kpi.label;
    const value = document.createElement("p");
    value.className = "kpi-value";
    value.textContent = kpi.value;
    const hint = document.createElement("p");
    hint.className = "kpi-hint";
    hint.textContent = kpi.hint;
    card.append(label, value, hint);
    kpiStrip.append(card);
  }
}

function renderCurrentChart(tables) {
  const labels = tables.map((table) => table.table_name);
  const peopleData = tables.map((table) => table.people_count ?? 0);
  const capacityData = tables.map((table) => table.capacity);
  const barColors = tables.map((table) => (table.occupied ? COLORS.occupied : COLORS.free));

  const config = {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Personas", data: peopleData, backgroundColor: barColors, borderRadius: 6 },
        { label: "Capacidad", data: capacityData, backgroundColor: COLORS.capacity, borderRadius: 6 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } },
        x: { grid: { display: false } },
      },
      plugins: { legend: { labels: { color: COLORS.muted } } },
    },
  };

  if (currentChart) {
    currentChart.data = config.data;
    currentChart.update();
  } else {
    currentChart = new Chart(document.querySelector("#chart-current"), config);
  }
}

function renderOccupancyChart(tables) {
  const occupiedCount = tables.filter((table) => table.occupied === true).length;
  const freeCount = tables.length - occupiedCount;

  const config = {
    type: "doughnut",
    data: {
      labels: ["Ocupadas", "Libres"],
      datasets: [{
        data: [occupiedCount, freeCount],
        backgroundColor: [COLORS.occupied, COLORS.free],
        borderColor: "#111827",
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "65%",
      plugins: { legend: { position: "bottom", labels: { color: COLORS.muted } } },
    },
  };

  if (occupancyChart) {
    occupancyChart.data = config.data;
    occupancyChart.update();
  } else {
    occupancyChart = new Chart(document.querySelector("#chart-occupancy"), config);
  }
}

function renderTrendChart(history) {
  const timestamps = [...new Set(history.map((row) => row.processed_at))].sort();
  const tableNames = [...new Set(history.map((row) => row.table_name))].sort();

  const byTableAndTime = new Map();
  for (const row of history) {
    byTableAndTime.set(`${row.table_name}|${row.processed_at}`, row.people_count);
  }

  const labels = timestamps.map((ts) => new Date(ts).toLocaleTimeString());
  const datasets = tableNames.map((name, index) => ({
    label: name,
    data: timestamps.map((ts) => byTableAndTime.get(`${name}|${ts}`) ?? null),
    borderColor: TABLE_PALETTE[index % TABLE_PALETTE.length],
    backgroundColor: TABLE_PALETTE[index % TABLE_PALETTE.length],
    tension: 0.3,
    spanGaps: true,
    pointRadius: 0,
    borderWidth: 2,
  }));

  const config = {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } },
        x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: COLORS.muted } } },
    },
  };

  if (trendChart) {
    trendChart.data = config.data;
    trendChart.update();
  } else {
    trendChart = new Chart(document.querySelector("#chart-trend"), config);
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  try {
    const [tables, history] = await Promise.all([
      fetchJson("/api/tables/latest"),
      fetchJson(`/api/tables/history?hours=${HISTORY_HOURS}`),
    ]);

    renderTables(tables);
    renderKpis(tables);
    renderCurrentChart(tables);
    renderOccupancyChart(tables);
    renderTrendChart(history);
    error.hidden = true;
  } catch (reason) {
    error.textContent = `No se pudo actualizar el dashboard: ${reason.message}`;
    error.hidden = false;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
