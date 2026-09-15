const error = document.querySelector("#error");
const modal = document.querySelector("#shift-modal");
const form = document.querySelector("#shift-form");
const modalTitle = document.querySelector("#shift-modal-title");
const waiterSelect = document.querySelector("#shift-waiter");
const tablesContainer = document.querySelector("#shift-tables");
const startInput = document.querySelector("#shift-start");
const endInput = document.querySelector("#shift-end");
const shiftError = document.querySelector("#shift-error");
const deleteBtn = document.querySelector("#delete-shift-btn");

let tables = [];
let editingShiftId = null;
let calendar = null;

function pad(n) {
  return String(n).padStart(2, "0");
}

function toUtcInputValue(date) {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}

function fromUtcInputValue(value) {
  return new Date(`${value}:00Z`);
}

async function fetchJson(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error((body && body.error) || `HTTP ${response.status}`);
  }
  return body;
}

async function loadWaiters(selectedId) {
  const waiters = await fetchJson("/api/waiters");
  waiterSelect.replaceChildren();
  for (const waiter of waiters) {
    const option = document.createElement("option");
    option.value = waiter.id;
    option.textContent = waiter.name;
    waiterSelect.append(option);
  }
  if (selectedId != null) waiterSelect.value = selectedId;
}

async function loadTables() {
  tables = await fetchJson("/api/shift-tables");
  tablesContainer.replaceChildren();
  for (const table of tables) {
    const label = document.createElement("label");
    label.className = "checkbox-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = table.id;
    label.append(input, document.createTextNode(table.name));
    tablesContainer.append(label);
  }
}

function setCheckedTables(tableIds) {
  const ids = new Set(tableIds.map(String));
  for (const input of tablesContainer.querySelectorAll("input[type=checkbox]")) {
    input.checked = ids.has(input.value);
  }
}

function getCheckedTables() {
  return [...tablesContainer.querySelectorAll("input[type=checkbox]:checked")].map((input) =>
    Number(input.value),
  );
}

function openModal({ shiftId, waiterId, tableIds, start, end }) {
  editingShiftId = shiftId ?? null;
  modalTitle.textContent = editingShiftId ? "Editar turno" : "Nuevo turno";
  deleteBtn.hidden = !editingShiftId;
  shiftError.hidden = true;
  waiterSelect.value = waiterId ?? "";
  setCheckedTables(tableIds ?? []);
  startInput.value = toUtcInputValue(start);
  endInput.value = toUtcInputValue(end);
  modal.hidden = false;
}

function closeModal() {
  modal.hidden = true;
  form.reset();
  editingShiftId = null;
}

function showShiftError(message) {
  shiftError.textContent = message;
  shiftError.hidden = false;
}

async function saveShift(event) {
  event.preventDefault();
  shiftError.hidden = true;

  const payload = {
    waiter_id: Number(waiterSelect.value),
    starts_at: fromUtcInputValue(startInput.value).toISOString(),
    ends_at: fromUtcInputValue(endInput.value).toISOString(),
    table_ids: getCheckedTables(),
  };

  try {
    if (editingShiftId) {
      await fetchJson(`/api/shifts/${editingShiftId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await fetchJson("/api/shifts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    closeModal();
    calendar.refetchEvents();
  } catch (reason) {
    showShiftError(reason.message);
  }
}

async function deleteShift() {
  if (!editingShiftId) return;
  try {
    await fetchJson(`/api/shifts/${editingShiftId}`, { method: "DELETE" });
    closeModal();
    calendar.refetchEvents();
  } catch (reason) {
    showShiftError(reason.message);
  }
}

async function addWaiter() {
  const name = prompt("Nombre del nuevo mesero:");
  if (!name || !name.trim()) return;
  try {
    const waiter = await fetchJson("/api/waiters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    await loadWaiters(waiter.id);
  } catch (reason) {
    showShiftError(reason.message);
  }
}

async function updateShiftTimes(info) {
  const props = info.event.extendedProps;
  try {
    await fetchJson(`/api/shifts/${info.event.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        waiter_id: props.waiter_id,
        starts_at: info.event.start.toISOString(),
        ends_at: info.event.end.toISOString(),
        table_ids: props.table_ids,
      }),
    });
  } catch (reason) {
    error.textContent = reason.message;
    error.hidden = false;
    info.revert();
  }
}

async function init() {
  await Promise.all([loadWaiters(), loadTables()]);

  calendar = new FullCalendar.Calendar(document.querySelector("#calendar"), {
    initialView: "timeGridWeek",
    timeZone: "UTC",
    headerToolbar: { left: "prev,next today", center: "title", right: "timeGridWeek,timeGridDay" },
    slotMinTime: "06:00:00",
    slotMaxTime: "26:00:00",
    height: "auto",
    selectable: true,
    editable: true,
    nowIndicator: true,
    events: async (fetchInfo, successCallback, failureCallback) => {
      try {
        const shifts = await fetchJson(
          `/api/shifts?start=${fetchInfo.startStr}&end=${fetchInfo.endStr}`,
        );
        successCallback(
          shifts.map((shift) => ({
            id: shift.id,
            title: `${shift.waiter_name} · ${shift.table_names.join(", ") || "sin mesa"}`,
            start: shift.starts_at,
            end: shift.ends_at,
            extendedProps: { waiter_id: shift.waiter_id, table_ids: shift.table_ids },
          })),
        );
        error.hidden = true;
      } catch (reason) {
        error.textContent = `No se pudieron cargar los turnos: ${reason.message}`;
        error.hidden = false;
        failureCallback(reason);
      }
    },
    select: (selectInfo) => {
      openModal({ start: selectInfo.start, end: selectInfo.end });
      calendar.unselect();
    },
    eventClick: (clickInfo) => {
      openModal({
        shiftId: clickInfo.event.id,
        waiterId: clickInfo.event.extendedProps.waiter_id,
        tableIds: clickInfo.event.extendedProps.table_ids,
        start: clickInfo.event.start,
        end: clickInfo.event.end,
      });
    },
    eventDrop: updateShiftTimes,
    eventResize: updateShiftTimes,
  });

  calendar.render();
}

form.addEventListener("submit", saveShift);
deleteBtn.addEventListener("click", deleteShift);
document.querySelector("#cancel-shift-btn").addEventListener("click", closeModal);
document.querySelector("#new-waiter-btn").addEventListener("click", addWaiter);

init();
