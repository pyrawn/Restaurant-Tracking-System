const REFRESH_MS = 30_000;
const grid = document.querySelector("#table-grid");
const error = document.querySelector("#error");
const lastUpdated = document.querySelector("#last-updated");

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
    const waiter = document.createElement("p");
    waiter.textContent = table.assigned_waiter_name || "Mesero sin asignar";

    card.append(title, count, waiter);
    grid.append(card);
  }
  lastUpdated.textContent = `Actualizado: ${new Date().toLocaleTimeString()}`;
}

async function refresh() {
  try {
    const response = await fetch("/api/tables/latest", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderTables(await response.json());
    error.hidden = true;
  } catch (reason) {
    error.textContent = `No se pudo actualizar el dashboard: ${reason.message}`;
    error.hidden = false;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
