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
const repeatSection = document.querySelector("#repeat-section");
const repeatWeekdaysContainer = document.querySelector("#repeat-weekdays");
const repeatUntilInput = document.querySelector("#repeat-until");
const statusEl = document.querySelector("#duplicate-status");

const WEEKDAY_LABELS = [
  { value: 1, label: "Lun" },
  { value: 2, label: "Mar" },
  { value: 3, label: "Mié" },
  { value: 4, label: "Jue" },
  { value: 5, label: "Vie" },
  { value: 6, label: "Sáb" },
  { value: 0, label: "Dom" },
];

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

function renderRepeatWeekdays() {
  repeatWeekdaysContainer.replaceChildren();
  for (const { value, label } of WEEKDAY_LABELS) {
    const labelEl = document.createElement("label");
    labelEl.className = "checkbox-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    labelEl.append(input, document.createTextNode(label));
    repeatWeekdaysContainer.append(labelEl);
  }
}

function getCheckedWeekdays() {
  return [...repeatWeekdaysContainer.querySelectorAll("input:checked")].map((input) => Number(input.value));
}

function resetRepeatFields() {
  for (const input of repeatWeekdaysContainer.querySelectorAll("input")) input.checked = false;
  repeatUntilInput.value = "";
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
  repeatSection.hidden = !!editingShiftId;
  resetRepeatFields();
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

function showStatus(message) {
  statusEl.textContent = message;
}

// Additional occurrences for the "repetir en" pattern: same time-of-day and
// duration as the base shift, on each checked weekday strictly after the
// base date, up to and including `untilValue` (a yyyy-mm-dd string). Fixed
// 24h steps preserve the base time-of-day exactly since everything here is
// UTC (no DST to worry about).
function computeRepeatOccurrences(baseStart, baseEnd, weekdays, untilValue) {
  if (!weekdays.length || !untilValue) return [];
  const until = new Date(`${untilValue}T23:59:59Z`);
  const durationMs = baseEnd.getTime() - baseStart.getTime();
  const oneDayMs = 24 * 60 * 60 * 1000;

  const occurrences = [];
  let cursor = new Date(baseStart.getTime() + oneDayMs);
  while (cursor <= until) {
    if (weekdays.includes(cursor.getUTCDay())) {
      occurrences.push({ start: new Date(cursor), end: new Date(cursor.getTime() + durationMs) });
    }
    cursor = new Date(cursor.getTime() + oneDayMs);
  }
  return occurrences;
}

async function saveShift(event) {
  event.preventDefault();
  shiftError.hidden = true;

  const startsAt = fromUtcInputValue(startInput.value);
  const endsAt = fromUtcInputValue(endInput.value);
  const waiterId = Number(waiterSelect.value);
  const tableIds = getCheckedTables();
  const payload = {
    waiter_id: waiterId,
    starts_at: startsAt.toISOString(),
    ends_at: endsAt.toISOString(),
    table_ids: tableIds,
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

      const occurrences = computeRepeatOccurrences(
        startsAt,
        endsAt,
        getCheckedWeekdays(),
        repeatUntilInput.value,
      );
      if (occurrences.length && !confirm(`¿Crear ${occurrences.length} repetición(es) más de este turno?`)) {
        showStatus("Turno creado. Repeticiones canceladas.");
      } else if (occurrences.length) {
        const result = await fetchJson("/api/shifts/bulk", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shifts: occurrences.map((occurrence) => ({
              waiter_id: waiterId,
              starts_at: occurrence.start.toISOString(),
              ends_at: occurrence.end.toISOString(),
              table_ids: tableIds,
            })),
          }),
        });
        showStatus(
          `Turno creado. Repeticiones: ${result.created.length} creadas, ${result.conflicts.length} con conflicto (omitidas).`,
        );
      }
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

async function duplicateWeek() {
  const view = calendar.view;
  const weekStart = view.activeStart;
  const weekEnd = view.activeEnd;

  showStatus("Buscando turnos…");
  let shifts;
  try {
    shifts = await fetchJson(
      `/api/shifts?start=${weekStart.toISOString()}&end=${weekEnd.toISOString()}`,
    );
  } catch (reason) {
    showStatus(`Error: ${reason.message}`);
    return;
  }

  // /api/shifts returns anything that OVERLAPS the visible week, including a
  // shift that starts before it or runs past it (needed to render the
  // calendar edges correctly). Duplicating those as-is would copy their full
  // original span every time, growing further with each click. Only
  // duplicate shifts fully contained in the visible week.
  const contained = shifts.filter(
    (shift) => new Date(shift.starts_at) >= weekStart && new Date(shift.ends_at) <= weekEnd,
  );
  const skipped = shifts.length - contained.length;

  if (!contained.length) {
    showStatus(
      skipped
        ? `Ningun turno cabe completo dentro de la semana visible (${skipped} se salen del rango y se omitieron).`
        : "No hay turnos en la semana visible para duplicar.",
    );
    return;
  }

  const confirmed = confirm(
    `¿Duplicar ${contained.length} turno(s) a la semana siguiente?` +
      (skipped ? ` (${skipped} se salen del rango visible y no se van a duplicar)` : ""),
  );
  if (!confirmed) {
    showStatus("Duplicación cancelada.");
    return;
  }

  showStatus("Duplicando…");
  try {
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    const result = await fetchJson("/api/shifts/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shifts: contained.map((shift) => ({
          waiter_id: shift.waiter_id,
          starts_at: new Date(new Date(shift.starts_at).getTime() + weekMs).toISOString(),
          ends_at: new Date(new Date(shift.ends_at).getTime() + weekMs).toISOString(),
          table_ids: shift.table_ids,
        })),
      }),
    });
    showStatus(`${result.created.length} turnos creados, ${result.conflicts.length} con conflicto (omitidos).`);
    calendar.refetchEvents();
  } catch (reason) {
    showStatus(`Error: ${reason.message}`);
  }
}

async function init() {
  renderRepeatWeekdays();
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
document.querySelector("#duplicate-week-btn").addEventListener("click", duplicateWeek);

init();
