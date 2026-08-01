"use strict";

const state = {
  dataset: null,
  datasetPromise: null,
  payload: null,
  filter: "ALL",
  currentDate: "",
};

const elements = {
  form: document.querySelector("#search-form"),
  dateInput: document.querySelector("#date-input"),
  loading: document.querySelector("#loading"),
  errorPanel: document.querySelector("#error-panel"),
  errorMessage: document.querySelector("#error-message"),
  retryButton: document.querySelector("#retry-button"),
  resultsView: document.querySelector("#results-view"),
  dateHeading: document.querySelector("#date-heading"),
  updatedAt: document.querySelector("#updated-at"),
  filters: document.querySelector("#filters"),
  visibleCount: document.querySelector("#visible-count"),
  resultsList: document.querySelector("#results-list"),
  emptyState: document.querySelector("#empty-state"),
  withoutMatches: document.querySelector("#without-matches"),
  warningsPanel: document.querySelector("#warnings-panel"),
  warningsList: document.querySelector("#warnings-list"),
  statMatches: document.querySelector("#stat-matches"),
  statWins: document.querySelector("#stat-wins"),
  statLosses: document.querySelector("#stat-losses"),
  statOthers: document.querySelector("#stat-others"),
};

function localIsoDate(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function escapeHtml(value) {
  return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
}

function longDate(value) {
  return new Intl.DateTimeFormat("es-ES", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
    timeZone: "Europe/Madrid",
  }).format(new Date(`${value}T12:00:00+02:00`));
}

function shortGeneratedAt(value) {
  if (!value) return "";
  return `Actualizado ${new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid",
  }).format(new Date(value))}`;
}

function setView(view) {
  elements.loading.hidden = view !== "loading";
  elements.errorPanel.hidden = view !== "error";
  elements.resultsView.hidden = view !== "results";
}

async function loadResults(date) {
  state.currentDate = date;
  state.filter = "ALL";
  setView("loading");
  const url = new URL(window.location.href);
  url.searchParams.set("fecha", date);
  window.history.replaceState({}, "", url);

  try {
    if (!state.datasetPromise) {
      state.datasetPromise = fetch("/data/resultados.json", {
        headers: {Accept: "application/json"},
        cache: "no-cache",
      }).then(async (response) => {
        const dataset = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(`No se pudo cargar el archivo de resultados (${response.status})`);
        return dataset;
      });
    }
    state.dataset = await state.datasetPromise;
    const availableDates = Object.keys(state.dataset.dates || {}).sort();
    if (availableDates.length) {
      elements.dateInput.min = availableDates[0];
      elements.dateInput.max = availableDates.at(-1);
    }
    const payload = state.dataset.dates?.[date] || emptyPayload(date, state.dataset);
    state.payload = payload;
    render(payload);
    setView("results");
  } catch (error) {
    state.datasetPromise = null;
    elements.errorMessage.textContent = error.message || "Error desconocido";
    setView("error");
  }
}

function emptyPayload(date, dataset) {
  return {
    date,
    tournament: dataset.tournament,
    generatedAt: dataset.generatedAt,
    summary: {matches: 0, victories: 0, defeats: 0, others: 0},
    results: [],
    categoriesWithoutMatches: dataset.categories || [],
    warnings: [],
  };
}

function render(payload) {
  elements.dateHeading.textContent = longDate(payload.date);
  elements.updatedAt.textContent = shortGeneratedAt(payload.generatedAt);
  elements.statMatches.textContent = payload.summary?.matches ?? 0;
  elements.statWins.textContent = payload.summary?.victories ?? 0;
  elements.statLosses.textContent = payload.summary?.defeats ?? 0;
  elements.statOthers.textContent = payload.summary?.others ?? 0;
  renderFilters(payload.results || []);
  renderResults();
  renderNotices(payload);
}

function renderFilters(results) {
  const categories = [...new Map(results.map((result) => [
    result.categoryCode,
    result.category,
  ])).entries()];
  const options = [["ALL", "Todos"], ...categories];
  elements.filters.innerHTML = options.map(([code, label]) => `
    <button class="filter-button${code === state.filter ? " active" : ""}"
      type="button" data-filter="${escapeHtml(code)}" aria-pressed="${code === state.filter}">
      ${escapeHtml(label)}
    </button>
  `).join("");

  elements.filters.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      renderFilters(state.payload.results || []);
      renderResults();
    });
  });
}

function outcomeClass(outcome) {
  if (outcome === "Victoria") return "outcome-win";
  if (outcome === "Derrota") return "outcome-loss";
  return "outcome-other";
}

function resultCard(result) {
  const sets = result.sets?.length ? result.sets.join(" · ") : "Sin marcador por sets";
  return `
    <article class="result-card">
      <div class="result-time">
        <strong>${escapeHtml(result.time)}</strong>
        <span>${escapeHtml(result.status)}</span>
      </div>
      <div class="result-main">
        <div class="result-topline">
          <span class="outcome ${outcomeClass(result.outcome)}">${escapeHtml(result.outcome)}</span>
          <span class="category-label">${escapeHtml(result.category)} · ${escapeHtml(result.phase)} · J${escapeHtml(result.jornada)}</span>
        </div>
        <h3>${escapeHtml(result.team)} <span>vs</span> ${escapeHtml(result.opponent)}</h3>
        <div class="result-meta">
          ${result.venue ? `<span>${escapeHtml(result.venue)}</span>` : ""}
          <a href="${escapeHtml(result.source)}" target="_blank" rel="noopener noreferrer">Fuente oficial ↗</a>
        </div>
      </div>
      <div class="result-score">
        <div class="score">${escapeHtml(result.score)}</div>
        <div class="sets">${escapeHtml(sets)}</div>
      </div>
    </article>
  `;
}

function renderResults() {
  const allResults = state.payload?.results || [];
  const visible = state.filter === "ALL" ? allResults : allResults.filter(
      (result) => result.categoryCode === state.filter,
  );
  elements.resultsList.innerHTML = visible.map(resultCard).join("");
  elements.visibleCount.textContent = `${visible.length} ${visible.length === 1 ? "partido" : "partidos"}`;
  elements.emptyState.hidden = visible.length !== 0;
}

function renderNotices(payload) {
  const missing = payload.categoriesWithoutMatches || [];
  elements.withoutMatches.hidden = missing.length === 0;
  elements.withoutMatches.textContent = missing.length ? `Sin partido en esta fecha: ${missing.join(", ")}.` : "";

  const warnings = payload.warnings || [];
  elements.warningsPanel.hidden = warnings.length === 0;
  elements.warningsList.innerHTML = warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("");
}

function scrollToFirstResult() {
  const firstResult = elements.resultsList.querySelector(".result-card");
  if (!firstResult) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  firstResult.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "start",
  });
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.dateInput.value) return;
  await loadResults(elements.dateInput.value);
  scrollToFirstResult();
});
elements.retryButton.addEventListener("click", () => loadResults(state.currentDate));

const queryDate = new URLSearchParams(window.location.search).get("fecha");
const initialDate = /^\d{4}-\d{2}-\d{2}$/.test(queryDate || "") ? queryDate : localIsoDate();
elements.dateInput.value = initialDate;
loadResults(initialDate);
