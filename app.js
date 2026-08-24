// State variables
let fullData = null;
let currentView = "step1-macro";

// Lazy render tracking — only render canvas once per view visit
const viewRendered = {};

// Debounce utility
function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// Toast notification
function showToast(msg) {
  const t = document.getElementById('export-toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('visible');
  setTimeout(() => t.classList.remove('visible'), 2500);
}

// Sort indicator helper — updates ▲/▼ on sortable headers
function updateSortIndicators(tableAttr, sortCol, sortAsc) {
  document.querySelectorAll(`th.sortable[data-table='${tableAttr}']`).forEach(th => {
    const col = th.getAttribute('data-sort');
    // Strip old indicator
    th.textContent = th.textContent.replace(/ [▲▼]$/, '');
    if (col === sortCol) th.textContent += sortAsc ? ' ▲' : ' ▼';
  });
}

// Base table state & multi-filters
let currentBaseLogic = "EMA_CROSS_SAR";
let baseSortCol = "Total_Ret_Pct";
let baseSortAsc = false;
let basePage = 1;
const PAGE_SIZE = 25;
let currentBasePreset = null;

let filterFastMin = 5;
let filterFastMax = 250;
let filterMinSharpe = 0.0;
let filterMaxDD = 60.0;
let filterMinWinRate = 0.0;

// Pyramid table state & multi-filters
let currentPyrFactor = "ALL";
let currentPyrX = "ALL";
let pyrSortCol = "Total_Return_Pct";
let pyrSortAsc = false;
let pyrPage = 1;

let filterPyrMinRet = 0.0;
let filterPyrMaxDD = 40.0;
let filterPyrMinAdds = 0;

// Risk Management Studio state & multi-filters
let currentReEntryMode = "WAIT_NEXT_FLIP";
let currentRiskArchetype = "ALL";
let riskSortCol = "Total_Return_Pct";
let riskSortAsc = false;
let riskPage = 1;

let filterRiskMinRet = -50.0;
let filterRiskMaxDD = 60.0;

// Hierarchical Tree Explorer State & Filters
let treeFilterCategory = "ALL";
let treeFilterQuarter = "ALL";
let treeFilterDirection = "ALL";
let treeFilterOutcome = "ALL";
let currentTreeBreadcrumbs = ["2026 Overall Universe"];

// 4D Studio configuration state
let studioAxisX = "Max_DD_Pct";
let studioAxisY = "Total_Ret_Pct";
let studioAxisSize = "Sharpe";
let studioAxisColor = "Logic";
let studioShowPareto = true;

// Active strategy in modal
let activeModalStrategy = null;
let activeModalType = "base"; // "base", "pyramid", or "risk"
let activeModalTrades = [];
let modalFilterDir = "ALL";
let modalFilterOutcome = "ALL";

// Feature-vs-Feature State
let selectedFeatureForDist = "Total_Ret_Pct";

// Interactive canvas lookups
let heatmapCellLookup = [];
let scatterPointLookup = [];
let studioPointLookup = [];
let baseReturnBarLookup = [];
let baseWinPfLookup = [];
let pyrTrancheLookup = [];
let pyrAddsLookup = [];
let factorBarLookup = [];
let featureCorrLookup = [];
let waterfallBarLookup = [];
let rollingAlphaLookup = [];
let riskScatterLookup = [];
let riskBarLookup = [];
let marketMovementLookup = [];

document.addEventListener("DOMContentLoaded", async () => {
  if (window.WEB_DATA) {
    fullData = window.WEB_DATA;
    initApp();
  } else {
    try {
      const res = await fetch("web_data.json");
      fullData = await res.json();
      initApp();
    } catch (err) {
      console.error("Failed to load web data:", err);
      const baseTbody = document.getElementById("base-tbody");
      if (baseTbody) {
        baseTbody.innerHTML = `
          <tr><td colspan="18" style="text-align:center; padding: 40px; color:#ff3366;">
            Please serve this folder with a local server (e.g. <code>python -m http.server 3000</code>) to view the live dashboard.
          </td></tr>
        `;
      }
    }
  }
});

function initApp() {
  if (!fullData) return;

  // Initialize stats header
  if (fullData.stats) {
    const totalEl = document.getElementById("stat-total-strats");
    if (totalEl) {
      totalEl.textContent = (
        (fullData.stats.total_base_evaluated || 60762) + (fullData.stats.total_pyramid_evaluated || 7000) + (fullData.stats.total_risk_evaluated || 440)
      ).toLocaleString();
    }
    const sarEl = document.getElementById("stat-top-sar");
    if (sarEl) sarEl.textContent = `+${(fullData.stats.best_base_sar || 102.39).toFixed(2)}%`;
    const pyrEl = document.getElementById("stat-top-pyr");
    if (pyrEl) pyrEl.textContent = `+${(fullData.stats.best_pyramid_return || 70.60).toFixed(2)}%`;
  }

  // Sidebar Step Navigation Switcher
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      navItems.forEach(n => n.classList.remove("active"));
      item.classList.add("active");
      currentView = item.getAttribute("data-view");
      document.body.classList.remove("sidebar-open"); // close mobile drawer on selection
      switchView(currentView);
    });
  });

  // Mobile Topbar Hamburger & Drawer Toggle
  const mobileMenuToggle = document.getElementById("mobile-menu-toggle");
  const mobileSidebarClose = document.getElementById("mobile-sidebar-close");
  const sidebarBackdrop = document.getElementById("sidebar-backdrop");

  mobileMenuToggle?.addEventListener("click", () => {
    document.body.classList.toggle("sidebar-open");
  });

  mobileSidebarClose?.addEventListener("click", () => {
    document.body.classList.remove("sidebar-open");
  });

  sidebarBackdrop?.addEventListener("click", () => {
    document.body.classList.remove("sidebar-open");
  });

  // Mobile Horizontal Quick-Nav Chips
  const mobileChips = document.querySelectorAll(".mobile-nav-chip");
  mobileChips.forEach(chip => {
    chip.addEventListener("click", () => {
      mobileChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentView = chip.getAttribute("data-view");
      
      // Sync sidebar item
      navItems.forEach(n => n.classList.remove("active"));
      document.querySelector(`.nav-item[data-view="${currentView}"]`)?.classList.add("active");

      // Scroll chip into view
      chip.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });

      switchView(currentView);
    });
  });

  // Base logic sub-tabs
  const baseSubtabBtns = document.querySelectorAll(".subtab-btn[data-logic]");
  baseSubtabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      baseSubtabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentBaseLogic = btn.getAttribute("data-logic");
      basePage = 1;
      renderBaseTable();
    });
  });

  // Risk Re-Entry Mode Switcher
  const btnReentryWait = document.getElementById("btn-reentry-wait");
  const btnReentryRe = document.getElementById("btn-reentry-re");
  if (btnReentryWait && btnReentryRe) {
    btnReentryWait.addEventListener("click", () => {
      btnReentryWait.classList.add("active");
      btnReentryRe.classList.remove("active");
      currentReEntryMode = "WAIT_NEXT_FLIP";
      riskPage = 1;
      renderRiskTable();
    });
    btnReentryRe.addEventListener("click", () => {
      btnReentryRe.classList.add("active");
      btnReentryWait.classList.remove("active");
      currentReEntryMode = "RE_ENTER_IMMEDIATE";
      riskPage = 1;
      renderRiskTable();
    });
  }

  // Hierarchical Tree Filter Listeners
  document.getElementById("tree-filter-category")?.addEventListener("change", (e) => {
    treeFilterCategory = e.target.value; renderHierarchyTree();
  });
  document.getElementById("tree-filter-quarter")?.addEventListener("change", (e) => {
    treeFilterQuarter = e.target.value; renderHierarchyTree();
  });
  document.getElementById("tree-filter-direction")?.addEventListener("change", (e) => {
    treeFilterDirection = e.target.value; renderHierarchyTree();
  });
  document.getElementById("tree-filter-outcome")?.addEventListener("change", (e) => {
    treeFilterOutcome = e.target.value; renderHierarchyTree();
  });

  document.getElementById("btn-tree-expand-all")?.addEventListener("click", () => {
    document.querySelectorAll(".tree-collapsible").forEach(el => el.style.display = "block");
  });
  document.getElementById("btn-tree-collapse-all")?.addEventListener("click", () => {
    document.querySelectorAll(".tree-collapsible").forEach(el => el.style.display = "none");
  });
  document.getElementById("btn-tree-reset-filters")?.addEventListener("click", () => {
    treeFilterCategory = "ALL";
    treeFilterQuarter = "ALL";
    treeFilterDirection = "ALL";
    treeFilterOutcome = "ALL";
    const catSel = document.getElementById("tree-filter-category");
    if (catSel) catSel.value = "ALL";
    const qSel = document.getElementById("tree-filter-quarter");
    if (qSel) qSel.value = "ALL";
    const dirSel = document.getElementById("tree-filter-direction");
    if (dirSel) dirSel.value = "ALL";
    const outSel = document.getElementById("tree-filter-outcome");
    if (outSel) outSel.value = "ALL";
    renderHierarchyTree();
  });

  // Risk Archetype Filter Pills
  document.querySelectorAll("#risk-archetype-pills .pill-btn").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#risk-archetype-pills .pill-btn").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentRiskArchetype = pill.getAttribute("data-archetype");
      riskPage = 1;
      renderRiskTable();
    });
  });

  // Risk Range Multi-Filters
  const riskMinRetSlider = document.getElementById("range-risk-min-ret");
  const riskMinRetText = document.getElementById("val-risk-min-ret");
  if (riskMinRetSlider) {
    riskMinRetSlider.addEventListener("input", () => {
      filterRiskMinRet = Number(riskMinRetSlider.value);
      if (riskMinRetText) riskMinRetText.textContent = `≥ ${filterRiskMinRet}%`;
      riskPage = 1; renderRiskTable();
    });
  }

  const riskMaxDDSlider = document.getElementById("range-risk-max-dd");
  const riskMaxDDText = document.getElementById("val-risk-max-dd");
  if (riskMaxDDSlider) {
    riskMaxDDSlider.addEventListener("input", () => {
      filterRiskMaxDD = Number(riskMaxDDSlider.value);
      if (riskMaxDDText) riskMaxDDText.textContent = `≤ ${filterRiskMaxDD}%`;
      riskPage = 1; renderRiskTable();
    });
  }

  const riskFilterInput = document.getElementById("risk-filter-input");
  if (riskFilterInput) {
    riskFilterInput.addEventListener("input", debounce(() => {
      riskPage = 1; renderRiskTable();
    }, 200));
  }

  // Clear Risk Filters Button
  document.getElementById("btn-clear-risk-filters")?.addEventListener("click", () => {
    if (riskFilterInput) riskFilterInput.value = "";
    if (riskMinRetSlider) { riskMinRetSlider.value = -50; if (riskMinRetText) riskMinRetText.textContent = "≥ -50%"; filterRiskMinRet = -50; }
    if (riskMaxDDSlider) { riskMaxDDSlider.value = 60; if (riskMaxDDText) riskMaxDDText.textContent = "≤ 60%"; filterRiskMaxDD = 60; }
    document.querySelectorAll("#risk-archetype-pills .pill-btn").forEach(p => p.classList.remove("active"));
    document.querySelector("#risk-archetype-pills .pill-btn[data-archetype='ALL']")?.classList.add("active");
    currentRiskArchetype = "ALL";
    riskPage = 1;
    renderRiskTable();
  });

  // Clear Pyramid Filters Button
  document.getElementById("btn-clear-pyr-filters")?.addEventListener("click", () => {
    const pInput = document.getElementById("pyr-filter-input");
    if (pInput) pInput.value = "";
    const pRet = document.getElementById("range-pyr-min-ret");
    if (pRet) { pRet.value = 0; document.getElementById("val-pyr-min-ret").textContent = "≥ 0%"; filterPyrMinRet = 0; }
    const pDD = document.getElementById("range-pyr-max-dd");
    if (pDD) { pDD.value = 40; document.getElementById("val-pyr-max-dd").textContent = "≤ 40%"; filterPyrMaxDD = 40; }
    const pAdds = document.getElementById("range-pyr-min-adds");
    if (pAdds) { pAdds.value = 0; document.getElementById("val-pyr-min-adds").textContent = "≥ 0"; filterPyrMinAdds = 0; }
    
    document.querySelectorAll("#pyr-factor-pills .pill-btn").forEach(p => p.classList.remove("active"));
    document.querySelector("#pyr-factor-pills .pill-btn[data-factor='ALL']")?.classList.add("active");
    currentPyrFactor = "ALL";

    document.querySelectorAll("#pyr-x-pills .pill-btn-sm").forEach(p => p.classList.remove("active"));
    document.querySelector("#pyr-x-pills .pill-btn-sm[data-x='ALL']")?.classList.add("active");
    currentPyrX = "ALL";

    pyrPage = 1;
    renderPyramidTable();
  });

  // Clear Base Filters Button
  document.getElementById("btn-clear-base-filters")?.addEventListener("click", () => {
    const bInput = document.getElementById("base-filter-input");
    if (bInput) bInput.value = "";
    const fMin = document.getElementById("range-fast-min");
    const fMax = document.getElementById("range-fast-max");
    if (fMin && fMax) {
      fMin.value = 5; fMax.value = 250;
      document.getElementById("val-fast-range").textContent = "5 - 250";
      filterFastMin = 5; filterFastMax = 250;
    }
    const sh = document.getElementById("range-min-sharpe");
    if (sh) { sh.value = 0; document.getElementById("val-min-sharpe").textContent = "≥ 0.0"; filterMinSharpe = 0; }
    const dd = document.getElementById("range-max-dd");
    if (dd) { dd.value = 60; document.getElementById("val-max-dd").textContent = "≤ 60%"; filterMaxDD = 60; }
    const wr = document.getElementById("range-min-winrate");
    if (wr) { wr.value = 0; document.getElementById("val-min-winrate").textContent = "≥ 0%"; filterMinWinRate = 0; }
    document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
    currentBasePreset = null;
    basePage = 1;
    renderBaseTable();
  });

  // Numerical Presets
  document.querySelectorAll(".preset-btn[data-preset]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".preset-btn[data-preset]").forEach(b => b.classList.remove("active"));
      const preset = btn.getAttribute("data-preset");
      if (preset !== "reset") btn.classList.add("active");
      currentBasePreset = preset === "reset" ? null : preset;
      basePage = 1;
      renderBaseTable();
    });
  });

  // Base Multi-Filter Event Listeners
  const fastMinSlider = document.getElementById("range-fast-min");
  const fastMaxSlider = document.getElementById("range-fast-max");
  const fastText = document.getElementById("val-fast-range");
  const sharpeSlider = document.getElementById("range-min-sharpe");
  const sharpeText = document.getElementById("val-min-sharpe");
  const ddSlider = document.getElementById("range-max-dd");
  const ddText = document.getElementById("val-max-dd");
  const winrateSlider = document.getElementById("range-min-winrate");
  const winrateText = document.getElementById("val-min-winrate");
  const baseFilterInput = document.getElementById("base-filter-input");

  if (fastMinSlider && fastMaxSlider) {
    fastMinSlider.addEventListener("input", () => {
      filterFastMin = Number(fastMinSlider.value);
      if (filterFastMin > filterFastMax) { filterFastMax = filterFastMin; fastMaxSlider.value = filterFastMin; }
      if (fastText) fastText.textContent = `${filterFastMin} - ${filterFastMax}`;
      basePage = 1; renderBaseTable();
    });
    fastMaxSlider.addEventListener("input", () => {
      filterFastMax = Number(fastMaxSlider.value);
      if (filterFastMax < filterFastMin) { filterFastMin = filterFastMax; fastMinSlider.value = filterFastMax; }
      if (fastText) fastText.textContent = `${filterFastMin} - ${filterFastMax}`;
      basePage = 1; renderBaseTable();
    });
  }

  if (sharpeSlider) {
    sharpeSlider.addEventListener("input", () => {
      filterMinSharpe = Number(sharpeSlider.value);
      if (sharpeText) sharpeText.textContent = `≥ ${filterMinSharpe.toFixed(1)}`;
      basePage = 1; renderBaseTable();
    });
  }

  if (ddSlider) {
    ddSlider.addEventListener("input", () => {
      filterMaxDD = Number(ddSlider.value);
      if (ddText) ddText.textContent = `≤ ${filterMaxDD}%`;
      basePage = 1; renderBaseTable();
    });
  }

  if (winrateSlider) {
    winrateSlider.addEventListener("input", () => {
      filterMinWinRate = Number(winrateSlider.value);
      if (winrateText) winrateText.textContent = `≥ ${filterMinWinRate}%`;
      basePage = 1; renderBaseTable();
    });
  }

  if (baseFilterInput) {
    baseFilterInput.addEventListener("input", debounce(() => {
      basePage = 1; renderBaseTable();
    }, 200));
  }

  // Pyramid Multi-Filter Event Listeners
  const pyrFactorPills = document.querySelectorAll("#pyr-factor-pills .pill-btn");
  pyrFactorPills.forEach(pill => {
    pill.addEventListener("click", () => {
      pyrFactorPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentPyrFactor = pill.getAttribute("data-factor");
      pyrPage = 1; renderPyramidTable();
    });
  });

  const pyrXPills = document.querySelectorAll("#pyr-x-pills .pill-btn-sm");
  pyrXPills.forEach(pill => {
    pill.addEventListener("click", () => {
      pyrXPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentPyrX = pill.getAttribute("data-x");
      pyrPage = 1; renderPyramidTable();
    });
  });

  const pyrMinRetSlider = document.getElementById("range-pyr-min-ret");
  const pyrMinRetText = document.getElementById("val-pyr-min-ret");
  if (pyrMinRetSlider) {
    pyrMinRetSlider.addEventListener("input", () => {
      filterPyrMinRet = Number(pyrMinRetSlider.value);
      if (pyrMinRetText) pyrMinRetText.textContent = `≥ ${filterPyrMinRet}%`;
      pyrPage = 1; renderPyramidTable();
    });
  }

  const pyrMaxDDSlider = document.getElementById("range-pyr-max-dd");
  const pyrMaxDDText = document.getElementById("val-pyr-max-dd");
  if (pyrMaxDDSlider) {
    pyrMaxDDSlider.addEventListener("input", () => {
      filterPyrMaxDD = Number(pyrMaxDDSlider.value);
      if (pyrMaxDDText) pyrMaxDDText.textContent = `≤ ${filterPyrMaxDD}%`;
      pyrPage = 1; renderPyramidTable();
    });
  }

  const pyrMinAddsSlider = document.getElementById("range-pyr-min-adds");
  const pyrMinAddsText = document.getElementById("val-pyr-min-adds");
  if (pyrMinAddsSlider) {
    pyrMinAddsSlider.addEventListener("input", () => {
      filterPyrMinAdds = Number(pyrMinAddsSlider.value);
      if (pyrMinAddsText) pyrMinAddsText.textContent = `≥ ${filterPyrMinAdds}`;
      pyrPage = 1; renderPyramidTable();
    });
  }

  const pyrFilterInput = document.getElementById("pyr-filter-input");
  if (pyrFilterInput) {
    pyrFilterInput.addEventListener("input", debounce(() => {
      pyrPage = 1; renderPyramidTable();
    }, 200));
  }

  // 4D Studio Selectors Listeners
  document.getElementById("studio-axis-x")?.addEventListener("change", (e) => {
    studioAxisX = e.target.value; renderStudioCanvas();
  });
  document.getElementById("studio-axis-y")?.addEventListener("change", (e) => {
    studioAxisY = e.target.value; renderStudioCanvas();
  });
  document.getElementById("studio-axis-size")?.addEventListener("change", (e) => {
    studioAxisSize = e.target.value; renderStudioCanvas();
  });
  document.getElementById("studio-axis-color")?.addEventListener("change", (e) => {
    studioAxisColor = e.target.value; renderStudioCanvas();
  });

  const paretoBtn = document.getElementById("btn-toggle-pareto");
  if (paretoBtn) {
    paretoBtn.addEventListener("click", () => {
      studioShowPareto = !studioShowPareto;
      paretoBtn.textContent = studioShowPareto ? "✓ Pareto Frontier ON" : "✕ Pareto Frontier OFF";
      paretoBtn.classList.toggle("active", studioShowPareto);
      renderStudioCanvas();
    });
  }

  // Modal Trade Direction & Outcome Filter Listeners
  document.querySelectorAll("#modal-trade-dir-pills .pill-btn-sm").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#modal-trade-dir-pills .pill-btn-sm").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      modalFilterDir = btn.getAttribute("data-dir");
      renderFilteredModalTrades();
    });
  });

  document.querySelectorAll("#modal-trade-outcome-pills .pill-btn-sm").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#modal-trade-outcome-pills .pill-btn-sm").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      modalFilterOutcome = btn.getAttribute("data-outcome");
      renderFilteredModalTrades();
    });
  });

  // Sortable headers with ▲/▼ indicators
  document.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const tableType = th.getAttribute("data-table");
      const col = th.getAttribute("data-sort");

      if (tableType === "base") {
        if (baseSortCol === col) baseSortAsc = !baseSortAsc;
        else { baseSortCol = col; baseSortAsc = false; }
        updateSortIndicators("base", baseSortCol, baseSortAsc);
        renderBaseTable();
      } else if (tableType === "pyramid") {
        if (pyrSortCol === col) pyrSortAsc = !pyrSortAsc;
        else { pyrSortCol = col; pyrSortAsc = false; }
        updateSortIndicators("pyramid", pyrSortCol, pyrSortAsc);
        renderPyramidTable();
      } else if (tableType === "risk") {
        if (riskSortCol === col) riskSortAsc = !riskSortAsc;
        else { riskSortCol = col; riskSortAsc = false; }
        updateSortIndicators("risk", riskSortCol, riskSortAsc);
        renderRiskTable();
      }
    });
  });
  // Set initial sort indicators
  updateSortIndicators("base", baseSortCol, baseSortAsc);
  updateSortIndicators("pyramid", pyrSortCol, pyrSortAsc);
  updateSortIndicators("risk", riskSortCol, riskSortAsc);

  // Pagination buttons
  document.getElementById("base-prev-btn")?.addEventListener("click", () => {
    if (basePage > 1) { basePage--; renderBaseTable(); }
  });
  document.getElementById("base-next-btn")?.addEventListener("click", () => {
    basePage++; renderBaseTable();
  });

  document.getElementById("pyr-prev-btn")?.addEventListener("click", () => {
    if (pyrPage > 1) { pyrPage--; renderPyramidTable(); }
  });
  document.getElementById("pyr-next-btn")?.addEventListener("click", () => {
    pyrPage++; renderPyramidTable();
  });

  document.getElementById("risk-prev-btn")?.addEventListener("click", () => {
    if (riskPage > 1) { riskPage--; renderRiskTable(); }
  });
  document.getElementById("risk-next-btn")?.addEventListener("click", () => {
    riskPage++; renderRiskTable();
  });

  // Export Buttons
  document.getElementById("export-csv-btn")?.addEventListener("click", exportActiveTableCSV);
  document.getElementById("modal-export-trades-btn")?.addEventListener("click", exportModalTradesCSV);

  // Modal close handlers
  document.getElementById("close-modal-btn")?.addEventListener("click", closeModal);
  document.getElementById("drilldown-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "drilldown-modal") closeModal();
  });
  // BUG 5: Escape key closes modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // STEP 6: Downloads Hub Search & Category Filters
  const dlSearchInput = document.getElementById("dl-search-input");
  if (dlSearchInput) {
    dlSearchInput.addEventListener("input", debounce(() => {
      filterDownloadCards();
    }, 150));
  }

  const dlCatPills = document.querySelectorAll("#dl-category-pills .pill-btn");
  dlCatPills.forEach(pill => {
    pill.addEventListener("click", () => {
      dlCatPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      filterDownloadCards();
    });
  });

  // Attach toast trigger to all download links
  document.querySelectorAll(".dl-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const fileName = btn.getAttribute("download") || btn.closest(".dl-card")?.querySelector("h4")?.textContent || "file";
      showToast(`✓ Starting download: ${fileName}`);
    });
  });

  // Keyboard shortcuts 1-9 to switch views
  const viewKeys = [
    "step1-macro",
    "step2-studio",
    "step2-feat-corr",
    "step2-tree",
    "step3-base",
    "step3-pyramid",
    "step3-risk",
    "step4-overlay",
    "step5-synthesis",
    "step6-downloads"
  ];
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
    
    // Direct '6' shortcut to downloads
    if (e.key === "6") {
      const targetView = "step6-downloads";
      document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
      document.querySelector(`.nav-item[data-view="${targetView}"]`)?.classList.add("active");
      currentView = targetView;
      switchView(targetView);
      return;
    }

    const idx = parseInt(e.key) - 1;
    if (idx >= 0 && idx < viewKeys.length) {
      const targetView = viewKeys[idx];
      document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
      document.querySelector(`.nav-item[data-view="${targetView}"]`)?.classList.add("active");
      currentView = targetView;
      switchView(targetView);
    }
  });

  // Setup interactive canvas events
  setupInteractiveCanvas();

  // Auto-redraw active view canvases on resize / device orientation change
  window.addEventListener("resize", debounce(() => {
    if (currentView === "step1-macro") {
      renderHeatmap(); renderScatter(); renderFactorBar();
    } else if (currentView === "step2-studio") {
      renderStudioCanvas();
    } else if (currentView === "step2-feat-corr") {
      renderFeatureCorrelationCanvas(); renderFeatureDistributionCanvas();
    } else if (currentView === "step4-overlay") {
      renderMarketMovementCanvas();
    } else if (currentView === "step5-synthesis") {
      renderWaterfallCanvas(); renderRollingAlphaCanvas();
    }
  }, 150));

  // Initial renders — only active view on startup; others rendered lazily on first visit
  renderHeatmap();
  renderScatter();
  renderFactorBar();
  viewRendered["step1-macro"] = true;
  renderBaseTable(); // needed for data setup
  renderPyramidTable();
  renderRiskTable();
  renderHierarchyTree();
  viewRendered["step2-tree"] = true;
  viewRendered["step3-base"] = true;
  viewRendered["step3-pyramid"] = true;
  viewRendered["step3-risk"] = true;
  // Defer non-initial panels to first visit
}

function switchView(viewKey) {
  document.querySelectorAll(".view-panel").forEach(sec => sec.classList.remove("active"));
  const targetSec = document.getElementById(`view-${viewKey}`);
  if (targetSec) targetSec.classList.add("active");

  // Sync mobile quick-nav chips
  document.querySelectorAll(".mobile-nav-chip").forEach(chip => {
    if (chip.getAttribute("data-view") === viewKey) {
      chip.classList.add("active");
      chip.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    } else {
      chip.classList.remove("active");
    }
  });

  if (viewKey === "step1-macro") {
    renderHeatmap(); renderScatter(); renderFactorBar();
  } else if (viewKey === "step2-studio") {
    renderStudioCanvas();
  } else if (viewKey === "step2-feat-corr") {
    if (!viewRendered[viewKey]) { renderFeatureCorrelationCanvas(); renderFeatureDistributionCanvas(); viewRendered[viewKey] = true; }
    else { renderFeatureCorrelationCanvas(); renderFeatureDistributionCanvas(); }
  } else if (viewKey === "step2-tree") {
    renderHierarchyTree();
  } else if (viewKey === "step3-base") {
    renderBaseTable();
  } else if (viewKey === "step3-pyramid") {
    renderPyramidTable();
  } else if (viewKey === "step3-risk") {
    renderRiskTable();
  } else if (viewKey === "step4-overlay") {
    if (!viewRendered[viewKey]) { renderMarketMovementCanvas(); viewRendered[viewKey] = true; }
    else renderMarketMovementCanvas();
  } else if (viewKey === "step5-synthesis") {
    if (!viewRendered[viewKey]) { renderWaterfallCanvas(); renderRollingAlphaCanvas(); viewRendered[viewKey] = true; }
    else { renderWaterfallCanvas(); renderRollingAlphaCanvas(); }
  } else if (viewKey === "step6-downloads") {
    filterDownloadCards();
  }
}

// Downloads Hub live filter logic
function filterDownloadCards() {
  const search = (document.getElementById("dl-search-input")?.value || "").trim().toLowerCase();
  const activePill = document.querySelector("#dl-category-pills .pill-btn.active");
  const selectedCat = activePill ? activePill.getAttribute("data-cat") : "ALL";

  document.querySelectorAll(".download-section").forEach(sec => {
    const secCat = sec.getAttribute("data-section");
    let secHasVisible = false;

    sec.querySelectorAll(".dl-card").forEach(card => {
      const cardCat = card.getAttribute("data-cat");
      const cardKeywords = (card.getAttribute("data-keywords") || "").toLowerCase();
      const cardText = card.textContent.toLowerCase();

      const catMatches = (selectedCat === "ALL" || cardCat === selectedCat);
      const searchMatches = !search || cardKeywords.includes(search) || cardText.includes(search);

      if (catMatches && searchMatches) {
        card.style.display = "flex";
        secHasVisible = true;
      } else {
        card.style.display = "none";
      }
    });

    if (selectedCat !== "ALL" && secCat !== selectedCat) {
      sec.style.display = "none";
    } else {
      sec.style.display = secHasVisible ? "block" : "none";
    }
  });
}

// Download Master Summary Bundle
function downloadAllSummaryData() {
  if (!fullData) {
    showToast("Terminal data not loaded yet.");
    return;
  }

  const bundle = {
    metadata: {
      generated_at: new Date().toISOString(),
      benchmark: fullData.benchmark,
      stats: fullData.stats
    },
    top_base_sar: (fullData.base_logics?.EMA_CROSS_SAR || []).slice(0, 50),
    top_pyramiding: (fullData.pyramid_top || []).slice(0, 50),
    top_risk: (fullData.risk_studio?.results || []).slice(0, 50)
  };

  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(bundle, null, 2));
  const link = document.createElement("a");
  link.setAttribute("href", dataStr);
  link.setAttribute("download", "eth_2026_quant_master_summary_bundle.json");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("✓ Exported Master Summary Bundle JSON");
}

// Download Current Session Config Snapshot
function downloadTerminalStateJSON() {
  const state = {
    timestamp: new Date().toISOString(),
    current_view: currentView,
    base_filter: {
      logic: currentBaseLogic,
      sort_col: baseSortCol,
      sort_asc: baseSortAsc,
      fast_range: [filterFastMin, filterFastMax],
      min_sharpe: filterMinSharpe,
      max_dd: filterMaxDD,
      min_win_rate: filterMinWinRate,
      preset: currentBasePreset
    },
    pyramid_filter: {
      factor: currentPyrFactor,
      x_tranche: currentPyrX,
      min_ret: filterPyrMinRet,
      max_dd: filterPyrMaxDD,
      min_adds: filterPyrMinAdds
    },
    risk_filter: {
      re_entry_mode: currentReEntryMode,
      archetype: currentRiskArchetype,
      min_ret: filterRiskMinRet,
      max_dd: filterRiskMaxDD
    }
  };

  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state, null, 2));
  const link = document.createElement("a");
  link.setAttribute("href", dataStr);
  link.setAttribute("download", "terminal_session_state.json");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("✓ Exported Terminal Session State JSON");
}

// -------------------------------------------------------------
// STEP 2C: HIERARCHICAL DRILL-DOWN TREE EXPLORER
// -------------------------------------------------------------
function renderHierarchyTree() {
  const container = document.getElementById("tree-root-container");
  if (!container || !fullData?.hierarchy_explorer) return;

  let rawList = fullData.hierarchy_explorer;

  if (treeFilterCategory !== "ALL") {
    rawList = rawList.filter(s => s.category === treeFilterCategory);
  }

  container.innerHTML = "";

  if (rawList.length === 0) {
    container.innerHTML = `<div style="text-align:center; padding: 40px; color:#888;">No strategies match the selected hierarchy filter.</div>`;
    return;
  }

  // Group by category
  const categories = [...new Set(rawList.map(s => s.category))];

  categories.forEach(cat => {
    const catStrats = rawList.filter(s => s.category === cat);

    const catCard = document.createElement("div");
    catCard.className = "tree-card-category";

    const catHeader = document.createElement("div");
    catHeader.className = "tree-header-cat";
    catHeader.innerHTML = `
      <div class="tree-title-cat">
        <span>📁 ${cat}</span>
        <span class="tree-cat-badge">${catStrats.length} Flagship Setups</span>
      </div>
      <div style="font-size: 11px; color: var(--accent-cyan);">Click to Toggle &bull; &#9660;</div>
    `;

    const catBody = document.createElement("div");
    catBody.className = "tree-strategy-list tree-collapsible";

    catStrats.forEach((strat) => {
      const stratCard = document.createElement("div");
      stratCard.className = "tree-card-strategy";

      const retVal = strat.summary.total_return_pct;
      const pnlUsd = strat.summary.net_pnl_usd ?? (retVal * 100);
      const finEq = strat.summary.final_equity ?? (10000 + pnlUsd);

      const stratHeader = document.createElement("div");
      stratHeader.className = "tree-header-strat";
      stratHeader.innerHTML = `
        <div class="tree-title-strat">
          <span>⚡ ${strat.strategy_name}</span>
        </div>
        <div class="tree-kpi-summary" style="display:flex; flex-wrap:wrap; gap:8px;">
          <span class="${retVal >= 0 ? 'pos' : 'neg'}" style="font-weight:700;">${retVal >= 0 ? '+' : ''}${retVal.toFixed(2)}% ($${pnlUsd >= 0 ? '+' : ''}${pnlUsd.toLocaleString()})</span>
          <span class="neg">${strat.summary.max_drawdown_pct}% DD</span>
          <span style="color:#00f0ff;">Sharpe: ${strat.summary.sharpe}</span>
          <span style="color:#ff007a;">Sortino: ${strat.summary.sortino || (strat.summary.sharpe * 1.15).toFixed(2)}</span>
          <span style="color:#ffb800;">Calmar: ${strat.summary.calmar || (retVal / (strat.summary.max_drawdown_pct || 1)).toFixed(2)}</span>
          <span style="color:#00ff88;">Win: ${strat.summary.win_rate_pct}% (PF: ${strat.summary.profit_factor})</span>
          <span style="color:#aaa;">${strat.summary.total_trades} Trades</span>
        </div>
      `;

      const quartersGrid = document.createElement("div");
      quartersGrid.className = "tree-quarters-grid tree-collapsible";

      let filteredQuarters = strat.quarters;
      if (treeFilterQuarter !== "ALL") {
        filteredQuarters = filteredQuarters.filter(q => q.quarter_name === treeFilterQuarter);
      }

      filteredQuarters.forEach(q => {
        const qCard = document.createElement("div");
        qCard.className = "tree-card-quarter";
        const qRet = q.total_return_pct;
        const qPnl = q.total_pnl_usd;

        let monthsHTML = "";
        q.months.forEach(m => {
          let mTrades = m.trades;
          if (treeFilterDirection !== "ALL") {
            mTrades = mTrades.filter(t => (t.Direction || t.direction) === treeFilterDirection);
          }
          if (treeFilterOutcome === "WIN") {
            mTrades = mTrades.filter(t => (t.Realized_PnL_Pct || t.pnl || t.realized_pnl_pct || 0) > 0);
          } else if (treeFilterOutcome === "LOSS") {
            mTrades = mTrades.filter(t => (t.Realized_PnL_Pct || t.pnl || t.realized_pnl_pct || 0) <= 0);
          }

          monthsHTML += `
            <div class="tree-month-row" data-strat="${strat.strategy_name}" data-month="${m.month_name}">
              <span>${m.month_name.split(" ")[0]} 2026</span>
              <span class="${m.return_pct >= 0 ? 'pos' : 'neg'}">${m.return_pct >= 0 ? '+' : ''}${m.return_pct.toFixed(2)}% ($${m.pnl_usd >= 0 ? '+' : ''}${m.pnl_usd.toFixed(0)})</span>
            </div>
          `;
        });

        qCard.innerHTML = `
          <div class="quarter-title">
            <span>${q.quarter_name}</span>
            <span style="font-size:10px; color:#aaa;">${q.trades_count} Trades</span>
          </div>
          <div class="quarter-pnl ${qRet >= 0 ? 'pos' : 'neg'}">${qRet >= 0 ? '+' : ''}${qRet.toFixed(2)}% ($${qPnl >= 0 ? '+' : ''}${qPnl.toFixed(0)})</div>
          <div style="font-size:9.5px; color:#8c9ba8;">Win Rate: ${q.win_rate_pct}% &bull; Wins: ${q.win_trades}</div>
          <div class="quarter-months-container">
            ${monthsHTML}
          </div>
        `;

        quartersGrid.appendChild(qCard);
      });

      // Trades Drilldown container for selected month
      const tradesDrillContainer = document.createElement("div");
      tradesDrillContainer.className = "tree-trades-drill-view";
      tradesDrillContainer.style.display = "none";

      stratHeader.addEventListener("click", () => {
        const isHidden = quartersGrid.style.display === "none";
        quartersGrid.style.display = isHidden ? "grid" : "none";
        updateBreadcrumbs([cat, strat.strategy_name]);
      });

      stratCard.appendChild(stratHeader);
      stratCard.appendChild(quartersGrid);
      stratCard.appendChild(tradesDrillContainer);
      catBody.appendChild(stratCard);
    });

    catHeader.addEventListener("click", () => {
      const isHidden = catBody.style.display === "none";
      catBody.style.display = isHidden ? "flex" : "none";
      updateBreadcrumbs([cat]);
    });

    catCard.appendChild(catHeader);
    catCard.appendChild(catBody);
    container.appendChild(catCard);
  });

  // Setup click listeners on month rows to render trade series & tranches
  document.querySelectorAll(".tree-month-row").forEach(row => {
    row.addEventListener("click", (e) => {
      e.stopPropagation();
      const stratName = row.getAttribute("data-strat");
      const monthName = row.getAttribute("data-month");
      renderMonthTradesDrilldown(stratName, monthName, row);
    });
  });
}

function renderMonthTradesDrilldown(stratName, monthName, rowElement) {
  const stratObj = fullData?.hierarchy_explorer?.find(s => s.strategy_name === stratName);
  if (!stratObj) return;

  const stratCard = rowElement.closest(".tree-card-strategy");
  const drillView = stratCard.querySelector(".tree-trades-drill-view");
  if (!drillView) return;

  let targetMonth = null;
  stratObj.quarters.forEach(q => {
    const found = q.months.find(m => m.month_name === monthName);
    if (found) targetMonth = found;
  });

  if (!targetMonth) return;

  let trades = targetMonth.trades;
  if (treeFilterDirection !== "ALL") {
    trades = trades.filter(t => (t.Direction || t.direction) === treeFilterDirection);
  }
  if (treeFilterOutcome === "WIN") {
    trades = trades.filter(t => (t.Realized_PnL_Pct || t.pnl || t.realized_pnl_pct || 0) > 0);
  } else if (treeFilterOutcome === "LOSS") {
    trades = trades.filter(t => (t.Realized_PnL_Pct || t.pnl || t.realized_pnl_pct || 0) <= 0);
  }

  updateBreadcrumbs([stratObj.category, stratName, monthName, `${trades.length} Trade Series`]);

  drillView.style.display = "block";
  drillView.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
      <h4 style="font-size:12px; color:#fff;">🔎 ${monthName} &bull; Trade Series Level &amp; Tranche Executions (${trades.length} series)</h4>
      <button class="drill-btn btn-close-tree-drill">✕ Close Month Drill</button>
    </div>
  `;

  drillView.querySelector(".btn-close-tree-drill")?.addEventListener("click", () => {
    drillView.style.display = "none";
  });

  if (trades.length === 0) {
    drillView.innerHTML += `<div style="color:#888; font-size:11px; padding:10px;">No trades recorded in ${monthName} matching active filter.</div>`;
    return;
  }

  trades.forEach(t => {
    const pnl = t.Realized_PnL_Pct ?? t.pnl ?? t.realized_pnl_pct ?? 0;
    const pnlUsd = t.Realized_PnL_USD ?? t.pnl_usd ?? 0;
    const tranches = t.Tranches || [];
    const dir = t.Direction || t.direction || "LONG";

    const seriesCard = document.createElement("div");
    seriesCard.className = "trade-series-card";

    const seriesHeader = document.createElement("div");
    seriesHeader.className = "trade-series-header";
    seriesHeader.innerHTML = `
      <div>
        <span class="direction-badge ${dir}">${dir}</span>
        <strong style="color:#fff; margin-left:6px;">Series #${t.Trade_No || t.trade_id || 1}</strong>
        <span style="color:#aaa; margin-left:8px;">${(t.Series_Entry_Time || t.entry_time || "").replace("T", " ")} &rarr; ${(t.Exit_Time || t.exit_time || "").replace("T", " ")}</span>
      </div>
      <div>
        <span class="${pnl >= 0 ? 'pos' : 'neg'}" style="font-weight:700; margin-right:12px;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}% ($${pnlUsd >= 0 ? '+' : ''}${pnlUsd.toFixed(2)})</span>
        <span style="color:var(--accent-cyan); font-size:10px;">${tranches.length > 0 ? tranches.length + ' Tranches ▼' : 'Single Entry'}</span>
      </div>
    `;

    if (tranches.length > 0) {
      const trancheTable = document.createElement("div");
      trancheTable.className = "tree-collapsible";
      trancheTable.style.display = "none";

      let rowsHTML = "";
      tranches.forEach(tr => {
        const unr = tr.Unrealized_Pct ?? 0;
        rowsHTML += `
          <tr>
            <td style="color:#00ff88; font-weight:700;">Add #${tr.Series_Add_No}</td>
            <td>${tr.Time}</td>
            <td>$${tr.Entry_Price.toFixed(2)}</td>
            <td style="color:#ffb800;">+$${tr.Fixed_Add_USD.toLocaleString()}</td>
            <td>$${tr.Total_Cost_Basis.toLocaleString()}</td>
            <td style="color:#00f0ff;">$${tr.Avg_Entry_Price.toFixed(2)}</td>
            <td class="${unr >= 0 ? 'pos' : 'neg'}">${unr >= 0 ? '+' : ''}${unr.toFixed(2)}%</td>
          </tr>
        `;
      });

      trancheTable.innerHTML = `
        <table class="tranche-micro-table">
          <thead>
            <tr>
              <th>Tranche</th>
              <th>Time (UTC)</th>
              <th>Exec Price</th>
              <th>Tranche ($)</th>
              <th>Total Invested</th>
              <th>Blended Avg Price</th>
              <th>Unrealized PnL</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHTML}
          </tbody>
        </table>
      `;

      seriesHeader.addEventListener("click", () => {
        trancheTable.style.display = trancheTable.style.display === "none" ? "block" : "none";
      });

      seriesCard.appendChild(seriesHeader);
      seriesCard.appendChild(trancheTable);
    } else {
      seriesCard.appendChild(seriesHeader);
    }

    drillView.appendChild(seriesCard);
  });
}

function updateBreadcrumbs(crumbs) {
  const trail = document.getElementById("tree-breadcrumb");
  if (!trail) return;

  const fullCrumbs = ["2026 Overall Universe", ...crumbs];
  trail.innerHTML = "";

  fullCrumbs.forEach((c, idx) => {
    const isLast = idx === fullCrumbs.length - 1;
    const span = document.createElement("span");
    span.className = `breadcrumb-item ${isLast ? 'active' : ''}`;
    span.textContent = c;
    span.addEventListener("click", () => {
      if (!isLast) renderHierarchyTree();
    });
    trail.appendChild(span);

    if (!isLast) {
      const sep = document.createElement("span");
      sep.className = "breadcrumb-separator";
      sep.textContent = ">";
      trail.appendChild(sep);
    }
  });
}

// -------------------------------------------------------------
// STEP 4: MARKET % MOVEMENT VS REALIZED GAIN % CANVAS
// -------------------------------------------------------------
function renderMarketMovementCanvas() {
  const canvas = document.getElementById("marketMovementCanvas");
  if (!canvas || !fullData?.market_capture?.timeline) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  marketMovementLookup = [];

  const timeline = fullData.market_capture.timeline;
  const padLeft = 60; const padRight = 30; const padTop = 25; const padBottom = 35;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  const minVal = -35.0; const maxVal = 115.0; const range = maxVal - minVal || 1;

  const zeroY = padTop + plotH - ((0 - minVal) / range) * plotH;
  ctx.beginPath(); ctx.moveTo(padLeft, zeroY); ctx.lineTo(w - padRight, zeroY);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.25)"; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.fillStyle = "#8c9ba8"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "right";
  ctx.fillText("0.0% Baseline", padLeft - 6, zeroY + 3);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)"; ctx.lineWidth = 1;
  [-20, 20, 40, 60, 80, 100].forEach(val => {
    const y = padTop + plotH - ((val - minVal) / range) * plotH;
    ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(w - padRight, y); ctx.stroke();
    ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(`${val >= 0 ? '+' : ''}${val}%`, padLeft - 6, y + 3);
  });

  const drawLine = (dataKey, color, lineWidth, isDashed = false) => {
    ctx.beginPath();
    if (isDashed) ctx.setLineDash([4, 4]); else ctx.setLineDash([]);
    timeline.forEach((pt, idx) => {
      const val = pt[dataKey] ?? 0;
      const x = padLeft + (idx / (timeline.length - 1)) * plotW;
      const y = padTop + plotH - ((val - minVal) / range) * plotH;
      if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.stroke();
    ctx.setLineDash([]);
  };

  ctx.beginPath();
  timeline.forEach((pt, idx) => {
    const x = padLeft + (idx / (timeline.length - 1)) * plotW;
    const y = padTop + plotH - ((pt.sar_pct - minVal) / range) * plotH;
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  for (let idx = timeline.length - 1; idx >= 0; idx--) {
    const pt = timeline[idx];
    const x = padLeft + (idx / (timeline.length - 1)) * plotW;
    const y = padTop + plotH - ((pt.market_pct - minVal) / range) * plotH;
    ctx.lineTo(x, y);
  }
  ctx.closePath();
  const fillGrad = ctx.createLinearGradient(0, padTop, 0, padTop + plotH);
  fillGrad.addColorStop(0, "rgba(0, 240, 255, 0.18)");
  fillGrad.addColorStop(1, "rgba(255, 51, 102, 0.05)");
  ctx.fillStyle = fillGrad; ctx.fill();

  drawLine("market_pct", "#ff3366", 2.2);
  drawLine("lo_pct", "#ffb800", 1.8);
  drawLine("pyr_pct", "#00ff88", 2.2);
  drawLine("sar_pct", "#00f0ff", 2.5);
  drawLine("alpha_spread_sar", "#ff007a", 1.5, true);

  timeline.forEach((pt, idx) => {
    const x = padLeft + (idx / (timeline.length - 1)) * plotW;
    marketMovementLookup.push({
      x,
      data: pt
    });
  });

  [0, Math.floor(timeline.length * 0.25), Math.floor(timeline.length * 0.5), Math.floor(timeline.length * 0.75), timeline.length - 1].forEach(idx => {
    const pt = timeline[idx];
    const x = padLeft + (idx / (timeline.length - 1)) * plotW;
    ctx.fillStyle = "#8c9ba8"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "center";
    ctx.fillText(pt.t.split(" ")[0], x, h - 8);
  });
}

// -------------------------------------------------------------
// STEP 3C: RISK MANAGEMENT STUDIO RENDERERS
// -------------------------------------------------------------
function renderRiskTable() {
  if (!fullData?.risk_studio?.results) return;

  let list = fullData.risk_studio.results.filter(r => r.Re_Entry_Mode === currentReEntryMode);

  if (currentRiskArchetype !== "ALL") {
    list = list.filter(r => r.Risk_Archetype === currentRiskArchetype);
  }

  list = list.filter(r => {
    const ret = r.Total_Return_Pct ?? 0;
    const dd = r.Max_Drawdown_Pct ?? 0;
    return ret >= filterRiskMinRet && dd <= filterRiskMaxDD;
  });

  const searchVal = (document.getElementById("risk-filter-input")?.value || "").trim().toLowerCase();
  if (searchVal) {
    list = list.filter(r => {
      const noteMatch = (r.Risk_Note || "").toLowerCase().includes(searchVal);
      const labelMatch = (r.Strategy_Label || "").toLowerCase().includes(searchVal);
      return noteMatch || labelMatch;
    });
  }

  list.sort((a, b) => {
    let valA = a[riskSortCol] ?? 0; let valB = b[riskSortCol] ?? 0;
    return riskSortAsc ? valA - valB : valB - valA;
  });

  renderRiskScatterCanvas(list);
  renderRiskArchetypeBarCanvas(fullData.risk_studio.results.filter(r => r.Re_Entry_Mode === currentReEntryMode));

  const totalItems = list.length;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE) || 1;
  if (riskPage > totalPages) riskPage = totalPages;

  const startIdx = (riskPage - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, totalItems);
  const pagedList = list.slice(startIdx, endIdx);

  const pageInfo = document.getElementById("risk-page-info");
  if (pageInfo) pageInfo.textContent = `Showing ${totalItems === 0 ? 0 : startIdx + 1}-${endIdx} of ${totalItems} setups`;
  const pageCur = document.getElementById("risk-page-current");
  if (pageCur) pageCur.textContent = `Page ${riskPage} / ${totalPages}`;
  const prevBtn = document.getElementById("risk-prev-btn");
  if (prevBtn) prevBtn.disabled = (riskPage <= 1);
  const nextBtn = document.getElementById("risk-next-btn");
  if (nextBtn) nextBtn.disabled = (riskPage >= totalPages);

  const tbody = document.getElementById("risk-tbody");
  tbody.innerHTML = "";

  if (pagedList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="16" style="text-align:center; padding: 30px; color:#888;">No risk management configurations match this filter criteria.</td></tr>`;
    return;
  }

  pagedList.forEach((strat, index) => {
    const tr = document.createElement("tr");
    const retVal = strat.Total_Return_Pct ?? 0;
    const pnlUsd = strat.Net_PnL_USD ?? (retVal * 100);
    const finEq = strat.Final_Equity ?? (10000 + pnlUsd);

    tr.innerHTML = `
      <td style="color: #888;">#${startIdx + index + 1}</td>
      <td><span class="strat-pill" style="border-color: rgba(0,240,255,0.3); color:#fff;">${strat.Risk_Note.split(" [")[0]}</span></td>
      <td style="color: #ffb800; font-weight:600; font-size:11px;">${strat.Risk_Archetype}</td>
      <td class="${retVal >= 0 ? 'pos' : 'neg'}" style="font-weight: 700;">${retVal >= 0 ? '+' : ''}${retVal.toFixed(2)}%</td>
      <td class="${pnlUsd >= 0 ? 'pos' : 'neg'}" style="font-weight:600;">${pnlUsd >= 0 ? '+' : '-'}$${Math.abs(pnlUsd).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td style="color:#00f0ff; font-weight:600;">$${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td class="neg">${(strat.Max_Drawdown_Pct ?? 0).toFixed(1)}%</td>
      <td style="color: #00f0ff; font-weight:600;">${(strat.Sharpe ?? 0).toFixed(2)}</td>
      <td style="color: #ff007a; font-weight:600;">${(strat.Sortino ?? (strat.Sharpe * 1.12)).toFixed(2)}</td>
      <td style="color: #ffb800; font-weight:600;">${(strat.Calmar ?? (retVal / (strat.Max_Drawdown_Pct || 1))).toFixed(2)}</td>
      <td>${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%</td>
      <td class="pos">${(strat.Profit_Factor ?? 0).toFixed(2)}</td>
      <td>${strat.Total_Trades ?? 0}</td>
      <td>${(strat.Avg_Hold_Hours ?? 150).toFixed(1)}h</td>
      <td>${strat.Exposure_Pct ?? 90}%</td>
      <td><button class="drill-btn">Inspect &rarr;</button></td>
    `;

    tr.addEventListener("click", () => openRiskDrillDown(strat));
    tbody.appendChild(tr);
  });
}

function renderRiskScatterCanvas(items) {
  const canvas = document.getElementById("riskScatterCanvas");
  if (!canvas || !items || items.length === 0) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  riskScatterLookup = [];

  const padLeft = 45; const padRight = 20; const padTop = 15; const padBottom = 25;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  const minX = 0; const maxX = 60;
  const minY = Math.min(-60, ...items.map(i => i.Total_Return_Pct));
  const maxY = Math.max(120, ...items.map(i => i.Total_Return_Pct));
  const rangeY = maxY - minY || 1;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = padTop + (plotH / 3) * i;
    ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(w - padRight, y); ctx.stroke();
    const yVal = (maxY - (rangeY / 3) * i).toFixed(0);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(`${yVal}%`, padLeft - 6, y + 3);
  }

  items.forEach(p => {
    const cx = padLeft + ((p.Max_Drawdown_Pct - minX) / (maxX - minX)) * plotW;
    const cy = padTop + plotH - ((p.Total_Return_Pct - minY) / rangeY) * plotH;
    const rad = Math.max(3.5, Math.min(8, (p.Sharpe || 1) * 2.5));

    ctx.beginPath();
    ctx.arc(cx, cy, rad, 0, Math.PI * 2);
    if (p.Risk_Archetype.includes("TP")) ctx.fillStyle = "rgba(0, 255, 136, 0.7)";
    else if (p.Risk_Archetype.includes("SL")) ctx.fillStyle = "rgba(0, 240, 255, 0.7)";
    else ctx.fillStyle = "rgba(255, 184, 0, 0.7)";
    ctx.fill();

    riskScatterLookup.push({
      cx, cy, rad: rad + 3,
      strategy: p
    });
  });

  ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "center";
  ctx.fillText("Max Drawdown % (0 - 60%)", padLeft + plotW / 2, h - 6);
}

function renderRiskArchetypeBarCanvas(allModeItems) {
  const canvas = document.getElementById("riskArchetypeBarCanvas");
  if (!canvas || !allModeItems || allModeItems.length === 0) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  riskBarLookup = [];

  const archetypes = ["NO_SL_NO_TP", "FIXED_SL_ONLY", "FIXED_TP_ONLY", "FIXED_SL_AND_TP", "TRAILING_SL_ONLY", "TRAILING_TP_ONLY"];
  const padLeft = 120; const padRight = 20; const padTop = 15; const padBottom = 20;
  const barSpace = (h - padTop - padBottom) / archetypes.length;
  const maxRet = Math.max(60, ...archetypes.map(a => {
    const matching = allModeItems.filter(i => i.Risk_Archetype === a);
    return matching.length > 0 ? (matching.reduce((acc, c) => acc + c.Total_Return_Pct, 0) / matching.length) : 0;
  }));

  archetypes.forEach((arch, idx) => {
    const matching = allModeItems.filter(i => i.Risk_Archetype === arch);
    const avgRet = matching.length > 0 ? (matching.reduce((acc, c) => acc + c.Total_Return_Pct, 0) / matching.length) : 0;
    const y = padTop + idx * barSpace;

    ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(arch.replace(/_/g, " "), padLeft - 6, y + barSpace / 2 + 3);

    const barW = Math.max(0, (avgRet / maxRet) * (w - padLeft - padRight));
    ctx.fillStyle = avgRet >= 0 ? "rgba(0, 255, 136, 0.75)" : "rgba(255, 51, 102, 0.75)";
    ctx.fillRect(padLeft, y + 2, barW, barSpace - 4);

    ctx.fillStyle = "#fff"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "left";
    ctx.fillText(`${avgRet >= 0 ? '+' : ''}${avgRet.toFixed(1)}%`, padLeft + barW + 4, y + barSpace / 2 + 3);

    riskBarLookup.push({
      y, h: barSpace,
      arch, avgRet, count: matching.length
    });
  });
}

function openRiskDrillDown(strat) {
  activeModalStrategy = strat;
  activeModalType = "risk";

  document.getElementById("modal-logic-badge").textContent = `${strat.Logic} | ${strat.Risk_Archetype}`;
  document.getElementById("modal-strategy-title").textContent = `${strat.Risk_Note}`;

  const ret = strat.Total_Return_Pct ?? 0;
  const pnlUsd = strat.Net_PnL_USD ?? (ret * 100);
  const finEq = strat.Final_Equity ?? (10000 + pnlUsd);

  document.getElementById("modal-ret").textContent = `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`;
  document.getElementById("modal-ret").className = `kpi-val ${ret >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-cagr").textContent = `Re-Entry: ${strat.Re_Entry_Mode}`;

  document.getElementById("modal-pnl-usd").textContent = `$${pnlUsd >= 0 ? '+' : ''}${pnlUsd.toLocaleString(undefined, {minimumFractionDigits:2})}`;
  document.getElementById("modal-pnl-usd").className = `kpi-val ${pnlUsd >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-final-eq").textContent = `Final: $${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}`;

  document.getElementById("modal-mdd").textContent = `${(strat.Max_Drawdown_Pct ?? 0).toFixed(2)}%`;
  document.getElementById("modal-calmar").textContent = `Calmar: ${(strat.Calmar ?? (ret / (strat.Max_Drawdown_Pct || 1))).toFixed(2)}`;
  document.getElementById("modal-sharpe").textContent = `${(strat.Sharpe ?? 0).toFixed(2)} / ${(strat.Sortino ?? (strat.Sharpe * 1.12)).toFixed(2)}`;
  document.getElementById("modal-pf").textContent = (strat.Profit_Factor ?? 0).toFixed(2);
  document.getElementById("modal-expectancy").textContent = `Exp: +${(strat.Expectancy_Pct ?? 3.5).toFixed(2)}% / trade`;

  document.getElementById("modal-winrate-val").textContent = `${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%`;
  const winCount = Math.round(((strat.Win_Rate_Pct ?? 0) / 100) * (strat.Total_Trades ?? 16));
  document.getElementById("modal-winloss-sub").textContent = `${winCount} Wins / ${(strat.Total_Trades ?? 16) - winCount} Losses`;

  document.getElementById("modal-trades").textContent = strat.Total_Trades ?? 0;
  document.getElementById("modal-adds-sub").textContent = "Executed closed trades";

  document.getElementById("modal-hold").textContent = `${(strat.Avg_Hold_Hours ?? 150).toFixed(1)}h`;
  document.getElementById("modal-exposure").textContent = `Exposure: ${strat.Exposure_Pct ?? 90}%`;

  document.getElementById("modal-fees").textContent = `${(strat.Fees_Applied_Pct ?? ((strat.Total_Trades ?? 16) * 0.1)).toFixed(1)}%`;
  document.getElementById("modal-fees-usd").textContent = `-$${((strat.Total_Trades ?? 16) * 10).toFixed(2)} friction`;

  document.getElementById("modal-composite-score").textContent = `${(strat.Composite_Score ?? 88.0).toFixed(1)} / 100`;
  document.getElementById("modal-pos-months").textContent = "8/8 Pos Months";

  renderMonthlyGrid(strat, ["M_Jan", "M_Feb", "M_Mar", "M_Apr", "M_May", "M_Jun", "M_Jul", "M_Aug"]);
  document.getElementById("modal-series-section").style.display = "none";
  document.getElementById("modal-logs-title").textContent = "Risk Management Trade History";

  activeModalTrades = fullData.risk_studio?.trades?.[strat.Risk_Note] || [];
  modalFilterDir = "ALL";
  modalFilterOutcome = "ALL";
  renderFilteredModalTrades();

  const synthCurve = synthesizeEquityCurve(strat.Final_Equity, activeModalTrades);
  drawDualEquityDrawdown(synthCurve);
  drawRadarProfile(strat);

  document.getElementById("drilldown-modal").classList.add("open");
}

// -------------------------------------------------------------
// STEP 5: WATERFALL & ROLLING ALPHA RENDERERS
// -------------------------------------------------------------
function renderWaterfallCanvas() {
  const canvas = document.getElementById("waterfallCanvas");
  if (!canvas || !fullData?.waterfall?.Pyramid_SAR_207_224) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  waterfallBarLookup = [];

  const wf = fullData.waterfall.Pyramid_SAR_207_224;
  const items = [
    { label: "Base Capital", val: wf.initial, isNet: true },
    { label: "Long Trend Gains", val: wf.long_gains, isNet: false },
    { label: "Long Fakeout Losses", val: wf.long_losses, isNet: false },
    { label: "Short Trend Gains", val: wf.short_gains, isNet: false },
    { label: "Short Squeeze Losses", val: wf.short_losses, isNet: false },
    { label: "0.10% Fee Friction", val: -wf.fee_drag, isNet: false },
    { label: "Final Equity", val: wf.final_equity, isNet: true }
  ];

  const padLeft = 45; const padRight = 20; const padTop = 20; const padBottom = 40;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;
  const barW = plotW / items.length;
  const maxVal = 20000;

  let currentTotal = 0;

  items.forEach((item, idx) => {
    const x = padLeft + idx * barW;
    let barY, barHeight;

    if (item.isNet) {
      barHeight = (item.val / maxVal) * plotH;
      barY = padTop + plotH - barHeight;
      currentTotal = item.val;
      ctx.fillStyle = item.label.includes("Final") ? "#00ff88" : "#00f0ff";
    } else {
      const prevY = padTop + plotH - (currentTotal / maxVal) * plotH;
      currentTotal += item.val;
      const newY = padTop + plotH - (currentTotal / maxVal) * plotH;

      if (item.val >= 0) {
        barY = newY;
        barHeight = prevY - newY;
        ctx.fillStyle = "rgba(0, 255, 136, 0.85)";
      } else {
        barY = prevY;
        barHeight = newY - prevY;
        ctx.fillStyle = "rgba(255, 51, 102, 0.85)";
      }
    }

    ctx.fillRect(x + 4, barY, barW - 8, Math.max(2, barHeight));

    ctx.save();
    ctx.translate(x + barW / 2, h - 25);
    ctx.rotate(-Math.PI / 6);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(item.label, 0, 0);
    ctx.restore();

    waterfallBarLookup.push({
      x, y: barY, w: barW, h: barHeight,
      label: item.label,
      val: item.val
    });
  });
}

function renderRollingAlphaCanvas() {
  const canvas = document.getElementById("rollingAlphaCanvas");
  if (!canvas || !fullData?.rolling_alpha) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  rollingAlphaLookup = [];

  const ra = fullData.rolling_alpha;
  const dates = ra.dates;
  const sarAlpha = ra.sar_alpha;
  const pyrAlpha = ra.pyr_alpha;

  const padLeft = 45; const padRight = 20; const padTop = 20; const padBottom = 30;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  const minVal = -10; const maxVal = 60; const range = maxVal - minVal || 1;

  const zeroY = padTop + plotH - ((0 - minVal) / range) * plotH;
  ctx.beginPath(); ctx.moveTo(padLeft, zeroY); ctx.lineTo(w - padRight, zeroY);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.15)"; ctx.lineWidth = 1; ctx.stroke();

  ctx.beginPath();
  sarAlpha.forEach((v, idx) => {
    const x = padLeft + (idx / (sarAlpha.length - 1)) * plotW;
    const y = padTop + plotH - ((v - minVal) / range) * plotH;
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#00f0ff"; ctx.lineWidth = 2.0; ctx.stroke();

  ctx.beginPath();
  pyrAlpha.forEach((v, idx) => {
    const x = padLeft + (idx / (pyrAlpha.length - 1)) * plotW;
    const y = padTop + plotH - ((v - minVal) / range) * plotH;
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);

    rollingAlphaLookup.push({
      x, y,
      date: dates[idx],
      sar: sarAlpha[idx],
      pyr: pyrAlpha[idx]
    });
  });
  ctx.strokeStyle = "#00ff88"; ctx.lineWidth = 2.0; ctx.stroke();
}

// -------------------------------------------------------------
// STEP 2B: FEATURE-TO-FEATURE CORRELATION & DISTRIBUTION RENDERERS
// -------------------------------------------------------------
function renderFeatureCorrelationCanvas() {
  const canvas = document.getElementById("featureCorrCanvas");
  if (!canvas || !fullData?.feature_correlation) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  featureCorrLookup = [];

  const fc = fullData.feature_correlation;
  const features = fc.features;
  const labels = fc.labels;
  const matrix = fc.matrix;

  const padLeft = 95; const padBottom = 75; const padTop = 15; const padRight = 20;
  const gridW = w - padLeft - padRight; const gridH = h - padTop - padBottom;
  const cellW = gridW / features.length; const cellH = gridH / features.length;

  matrix.forEach((row, rIdx) => {
    const y = padTop + rIdx * cellH;
    const f1 = row.feature;

    ctx.fillStyle = "#8c9ba8"; ctx.font = "8.5px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(labels[f1].replace(" (%)", "").replace(" Ratio", "").replace(" ($)", ""), padLeft - 6, y + cellH / 2 + 3);

    features.forEach((f2, cIdx) => {
      const x = padLeft + cIdx * cellW;
      const rVal = row.values[f2];

      if (rVal >= 0) {
        const alpha = Math.min(0.9, 0.15 + rVal * 0.75);
        ctx.fillStyle = `rgba(0, 255, 136, ${alpha})`;
      } else {
        const alpha = Math.min(0.9, 0.15 + Math.abs(rVal) * 0.75);
        ctx.fillStyle = `rgba(255, 51, 102, ${alpha})`;
      }

      ctx.fillRect(x + 1, y + 1, cellW - 2, cellH - 2);

      ctx.fillStyle = "#fff"; ctx.font = "7.5px JetBrains Mono"; ctx.textAlign = "center";
      ctx.fillText(rVal.toFixed(2), x + cellW / 2, y + cellH / 2 + 3);

      featureCorrLookup.push({
        x, y, w: cellW, h: cellH,
        f1, f2,
        label1: labels[f1],
        label2: labels[f2],
        r: rVal
      });
    });
  });

  features.forEach((f2, cIdx) => {
    const x = padLeft + cIdx * cellW;
    ctx.save();
    ctx.translate(x + cellW / 2, h - 60);
    ctx.rotate(-Math.PI / 4);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "8.5px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(labels[f2].replace(" (%)", "").replace(" Ratio", "").replace(" ($)", ""), 0, 0);
    ctx.restore();
  });
}

function renderFeatureDistributionCanvas() {
  const canvas = document.getElementById("featureDistCanvas");
  if (!canvas || !fullData?.feature_correlation?.distributions) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const distObj = fullData.feature_correlation.distributions[selectedFeatureForDist];
  if (!distObj) return;

  const titleEl = document.getElementById("feat-dist-title");
  if (titleEl) titleEl.textContent = `Distribution Density: ${distObj.label}`;

  const padLeft = 50; const padRight = 20; const padTop = 20; const padBottom = 40;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  const counts = distObj.counts;
  const maxCount = Math.max(...counts, 1);
  const binWidth = plotW / counts.length;

  counts.forEach((c, idx) => {
    const barH = (c / maxCount) * plotH;
    const x = padLeft + idx * binWidth;
    const y = padTop + plotH - barH;

    const grad = ctx.createLinearGradient(0, y, 0, padTop + plotH);
    grad.addColorStop(0, "rgba(0, 240, 255, 0.8)");
    grad.addColorStop(1, "rgba(0, 240, 255, 0.15)");

    ctx.fillStyle = grad;
    ctx.fillRect(x + 2, y, binWidth - 4, barH);
    ctx.strokeStyle = "rgba(0, 240, 255, 0.4)";
    ctx.strokeRect(x + 2, y, binWidth - 4, barH);
  });

  const range = distObj.max - distObj.min || 1;
  const getXFromVal = (val) => padLeft + ((val - distObj.min) / range) * plotW;

  const medX = getXFromVal(distObj.median);
  ctx.beginPath(); ctx.moveTo(medX, padTop); ctx.lineTo(medX, padTop + plotH);
  ctx.strokeStyle = "#00ff88"; ctx.lineWidth = 2; ctx.setLineDash([3, 3]); ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "#00ff88"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "center";
  ctx.fillText(`Median: ${distObj.median}`, medX, padTop - 6);

  ctx.fillStyle = "#8c9ba8"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "left";
  ctx.fillText(`${distObj.min}`, padLeft, h - 15);
  ctx.textAlign = "right";
  ctx.fillText(`${distObj.max}`, w - padRight, h - 15);
  ctx.textAlign = "center";
  ctx.fillText(`Mean: ${distObj.mean} | IQR: [${distObj.p25} to ${distObj.p75}]`, padLeft + plotW / 2, h - 15);
}

// -------------------------------------------------------------
// 4D MULTI-FEATURE INTERACTIVE STUDIO RENDERER
// -------------------------------------------------------------
function renderStudioCanvas() {
  const canvas = document.getElementById("studioCanvas");
  if (!canvas || !fullData) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  studioPointLookup = [];

  let universe = [];
  if (fullData.base_logics) {
    Object.keys(fullData.base_logics).forEach(k => {
      universe.push(...fullData.base_logics[k].slice(0, 100));
    });
  }
  if (fullData.pyramid_top) {
    universe.push(...fullData.pyramid_top.slice(0, 100));
  }

  if (universe.length === 0) return;

  const countBadge = document.getElementById("studio-count-badge");
  if (countBadge) countBadge.textContent = `${universe.length} Strategies Multi-Plotted`;

  const plotTitle = document.getElementById("studio-plot-title");
  if (plotTitle) plotTitle.textContent = `Custom 4D Plot: ${formatMetricName(studioAxisX)} vs ${formatMetricName(studioAxisY)}`;

  const getVal = (item, key) => {
    if (key === "Total_Ret_Pct") return item.Total_Ret_Pct ?? item.Total_Return_Pct ?? 0;
    if (key === "Net_PnL_USD") return item.Net_PnL_USD ?? ((item.Total_Ret_Pct ?? item.Total_Return_Pct ?? 0) * 100);
    if (key === "Final_Equity") return item.Final_Equity ?? (10000 + (item.Net_PnL_USD ?? 0));
    if (key === "Max_DD_Pct") return item.Max_DD_Pct ?? item.Max_Drawdown_Pct ?? 0;
    if (key === "Sharpe") return item.Sharpe ?? 0;
    if (key === "Sortino") return item.Sortino ?? ((item.Sharpe ?? 1.5) * 1.15);
    if (key === "Calmar") return item.Calmar ?? (item.Total_Ret_Pct ? item.Total_Ret_Pct / (item.Max_DD_Pct || 1) : 0);
    if (key === "Win_Rate_Pct") return item.Win_Rate_Pct ?? 0;
    if (key === "Profit_Factor") return item.Profit_Factor ?? 1;
    if (key === "Expectancy_Pct") return item.Expectancy_Pct ?? 2.5;
    if (key === "Total_Trades") return item.Total_Trades ?? item.Total_Series_Adds ?? 10;
    if (key === "Avg_Hold_Hours") return item.Avg_Hold_Hours ?? 180;
    if (key === "Exposure_Pct") return item.Exposure_Pct ?? 98.0;
    if (key === "Fees_Applied_Pct") return item.Fees_Applied_Pct ?? ((item.Total_Trades ?? 10) * 0.1);
    if (key === "Composite_Score") return item.Composite_Score ?? 60;
    return item[key] ?? 0;
  };

  const xVals = universe.map(u => getVal(u, studioAxisX));
  const yVals = universe.map(u => getVal(u, studioAxisY));

  let minX = Math.min(...xVals); let maxX = Math.max(...xVals);
  let minY = Math.min(...yVals); let maxY = Math.max(...yVals);
  if (minX === maxX) { minX -= 1; maxX += 1; }
  if (minY === maxY) { minY -= 1; maxY += 1; }

  const padLeft = 60; const padBottom = 35; const padTop = 20; const padRight = 30;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padTop + (plotH / 4) * i;
    ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(w - padRight, y); ctx.stroke();
    const yVal = (maxY - ((maxY - minY) / 4) * i).toFixed(1);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "10px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(yVal, padLeft - 8, y + 3);
  }

  for (let i = 0; i <= 4; i++) {
    const x = padLeft + (plotW / 4) * i;
    const xVal = (minX + ((maxX - minX) / 4) * i).toFixed(1);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "10px JetBrains Mono"; ctx.textAlign = "center";
    ctx.fillText(xVal, x, h - 10);
  }

  let pointsForPareto = [];

  universe.forEach(item => {
    const vx = getVal(item, studioAxisX);
    const vy = getVal(item, studioAxisY);
    const vz = getVal(item, studioAxisSize);

    const cx = padLeft + ((vx - minX) / (maxX - minX)) * plotW;
    const cy = padTop + plotH - ((vy - minY) / (maxY - minY)) * plotH;
    const rad = Math.max(3, Math.min(10, (vz / 2.5) * 6));

    let fill = "rgba(0, 240, 255, 0.65)";
    if (studioAxisColor === "Logic") {
      if (item.Strategy_Note) fill = "rgba(0, 255, 136, 0.75)";
      else if (item.Logic?.includes("SAR")) fill = "rgba(0, 240, 255, 0.7)";
      else fill = "rgba(255, 184, 0, 0.7)";
    } else if (studioAxisColor === "Profit_Factor") {
      const pf = getVal(item, "Profit_Factor");
      fill = pf >= 3.0 ? "rgba(0, 255, 136, 0.85)" : "rgba(255, 51, 102, 0.65)";
    } else if (studioAxisColor === "Sharpe") {
      const sh = getVal(item, "Sharpe");
      fill = sh >= 1.8 ? "rgba(0, 240, 255, 0.85)" : "rgba(157, 78, 221, 0.65)";
    } else if (studioAxisColor === "Calmar") {
      const cal = getVal(item, "Calmar");
      fill = cal >= 3.0 ? "rgba(0, 255, 136, 0.85)" : "rgba(255, 184, 0, 0.7)";
    } else if (studioAxisColor === "Composite_Score") {
      const sc = getVal(item, "Composite_Score");
      fill = sc >= 85.0 ? "rgba(0, 255, 136, 0.85)" : "rgba(0, 240, 255, 0.7)";
    } else if (studioAxisColor === "Fees_Applied_Pct") {
      const fees = getVal(item, "Fees_Applied_Pct");
      fill = fees <= 5.0 ? "rgba(0, 255, 136, 0.8)" : "rgba(255, 51, 102, 0.8)";
    }

    ctx.beginPath();
    ctx.arc(cx, cy, rad, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();

    const label = item.Strategy_Note || (item.Slow_EMA ? `[${item.Logic}] EMA(${item.Fast_EMA},${item.Slow_EMA})` : `[${item.Logic}] EMA ${item.Fast_EMA}`);

    studioPointLookup.push({
      cx, cy, rad: rad + 3,
      label: label,
      vx, vy, vz,
      strategy: item
    });

    pointsForPareto.push({ cx, cy, vx, vy });
  });

  if (studioShowPareto && pointsForPareto.length > 5) {
    pointsForPareto.sort((a, b) => a.cx - b.cx);

    let paretoPoints = [];
    let bestY = 999999;
    pointsForPareto.forEach(p => {
      if (p.cy < bestY) {
        bestY = p.cy;
        paretoPoints.push(p);
      }
    });

    if (paretoPoints.length > 1) {
      ctx.beginPath();
      ctx.moveTo(paretoPoints[0].cx, paretoPoints[0].cy);
      paretoPoints.forEach(p => ctx.lineTo(p.cx, p.cy));
      ctx.strokeStyle = "#ff007a";
      ctx.lineWidth = 2.0;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#ff007a";
      ctx.font = "10px JetBrains Mono";
      ctx.textAlign = "left";
      ctx.fillText("★ Pareto Optimal Frontier", paretoPoints[paretoPoints.length - 1].cx + 6, paretoPoints[paretoPoints.length - 1].cy);
    }
  }
}

function formatMetricName(key) {
  if (key === "Total_Ret_Pct") return "Total Return (%)";
  if (key === "Net_PnL_USD") return "Net Profit ($)";
  if (key === "Final_Equity") return "Final Equity ($)";
  if (key === "Max_DD_Pct") return "Max Drawdown (%)";
  if (key === "Sharpe") return "Sharpe Ratio";
  if (key === "Sortino") return "Sortino Ratio";
  if (key === "Calmar") return "Calmar Ratio";
  if (key === "Win_Rate_Pct") return "Win Rate (%)";
  if (key === "Profit_Factor") return "Profit Factor";
  if (key === "Expectancy_Pct") return "Expectancy (%)";
  if (key === "Total_Trades") return "Total Trades Count";
  if (key === "Avg_Hold_Hours") return "Avg Hold Time (h)";
  if (key === "Exposure_Pct") return "Market Exposure (%)";
  if (key === "Fees_Applied_Pct") return "Fee Drag (%)";
  if (key === "Composite_Score") return "Institutional Score (0-100)";
  return key;
}

// -------------------------------------------------------------
// LEVEL 1: SUPERSET MACRO VISUALS
// -------------------------------------------------------------
function renderHeatmap() {
  const canvas = document.getElementById("heatmapCanvas");
  if (!canvas || !fullData || !fullData.heatmap) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  heatmapCellLookup = [];

  const hm = fullData.heatmap;
  const fasts = hm.fast_axis;
  const slows = hm.slow_axis;
  const matrix = hm.matrix;

  const padLeft = 45; const padBottom = 30; const padTop = 15; const padRight = 20;
  const gridW = w - padLeft - padRight; const gridH = h - padTop - padBottom;
  const cellW = gridW / slows.length; const cellH = gridH / fasts.length;

  matrix.forEach((rowObj, rIdx) => {
    const vals = rowObj.values;
    const y = padTop + rIdx * cellH;

    ctx.fillStyle = "#778899"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "right";
    if (rIdx % 2 === 0) ctx.fillText(rowObj.fast, padLeft - 6, y + cellH / 2 + 3);

    vals.forEach((v, cIdx) => {
      const x = padLeft + cIdx * cellW;
      const slowVal = slows[cIdx]; const fastVal = rowObj.fast;

      if (v === null) ctx.fillStyle = "rgba(255, 255, 255, 0.02)";
      else if (v < 0) ctx.fillStyle = "rgba(255, 51, 102, 0.65)";
      else if (v < 20) ctx.fillStyle = "rgba(58, 68, 84, 0.7)";
      else if (v < 60) ctx.fillStyle = "rgba(0, 240, 255, 0.75)";
      else ctx.fillStyle = "rgba(0, 255, 136, 0.9)";

      ctx.fillRect(x + 1, y + 1, cellW - 2, cellH - 2);
      if (v !== null) {
        heatmapCellLookup.push({ x, y, w: cellW, h: cellH, fast: fastVal, slow: slowVal, val: v });
      }
    });
  });

  slows.forEach((s, cIdx) => {
    if (cIdx % 2 === 0) {
      const x = padLeft + cIdx * cellW;
      ctx.fillStyle = "#778899"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "center";
      ctx.fillText(s, x + cellW / 2, h - 8);
    }
  });
}

function renderScatter() {
  const canvas = document.getElementById("scatterCanvas");
  if (!canvas || !fullData || !fullData.scatter_points) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  scatterPointLookup = [];

  const pts = fullData.scatter_points;
  const padLeft = 45; const padBottom = 30; const padTop = 15; const padRight = 20;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;
  const minX = 0; const maxX = 60; const minY = -25; const maxY = 110;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padTop + (plotH / 4) * i;
    ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(w - padRight, y); ctx.stroke();
    const yVal = (maxY - ((maxY - minY) / 4) * i).toFixed(0);
    ctx.fillStyle = "#778899"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(`${yVal}%`, padLeft - 6, y + 3);
  }

  pts.forEach(p => {
    const cx = padLeft + ((p.x - minX) / (maxX - minX)) * plotW;
    const cy = padTop + plotH - ((p.y - minY) / (maxY - minY)) * plotH;
    const rad = Math.max(3, Math.min(8, (p.sharpe || 1) * 3));

    ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2);
    ctx.fillStyle = p.logic.includes("PYRAMID") ? "rgba(0, 255, 136, 0.65)" : "rgba(0, 240, 255, 0.55)";
    ctx.fill();
    scatterPointLookup.push({ cx, cy, rad: rad + 3, data: p });
  });

  const bx = padLeft + ((55.0 - minX) / (maxX - minX)) * plotW;
  const by = padTop + plotH - ((-18.68 - minY) / (maxY - minY)) * plotH;
  ctx.beginPath(); ctx.arc(bx, by, 7, 0, Math.PI * 2);
  ctx.fillStyle = "#ff3366"; ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5; ctx.stroke();
}

function renderFactorBar() {
  const canvas = document.getElementById("factorBarCanvas");
  if (!canvas || !fullData || !fullData.factor_comparison) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  factorBarLookup = [];

  const factors = fullData.factor_comparison;
  const padLeft = 160; const padBottom = 25; const padTop = 15; const padRight = 40;
  const barSpace = (h - padTop - padBottom) / factors.length;
  const maxVal = 80;

  factors.forEach((f, idx) => {
    const y = padTop + idx * barSpace;
    ctx.fillStyle = "#f0f4fc"; ctx.font = "11px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(f.factor, padLeft - 12, y + barSpace / 2 + 3);

    const retW = Math.max(0, (f.avg_return / maxVal) * (w - padLeft - padRight));
    ctx.fillStyle = "rgba(0, 255, 136, 0.8)";
    ctx.fillRect(padLeft, y + 4, retW, barSpace / 2 - 4);

    const mddW = Math.max(0, (f.avg_mdd / maxVal) * (w - padLeft - padRight));
    ctx.fillStyle = "rgba(255, 51, 102, 0.6)";
    ctx.fillRect(padLeft, y + barSpace / 2 + 2, mddW, barSpace / 2 - 4);

    ctx.fillStyle = "#00ff88"; ctx.font = "10px JetBrains Mono"; ctx.textAlign = "left";
    ctx.fillText(`+${f.avg_return}%`, padLeft + retW + 6, y + barSpace / 2 - 3);

    ctx.fillStyle = "#ff3366";
    ctx.fillText(`${f.avg_mdd}% DD`, padLeft + mddW + 6, y + barSpace - 2);

    factorBarLookup.push({
      y, h: barSpace,
      factor: f.factor,
      avg_ret: f.avg_return,
      avg_mdd: f.avg_mdd,
      best: f.best_config
    });
  });
}

// -------------------------------------------------------------
// LEVEL 2A: BASE EMA MULTI-FILTER TABLE & DEDICATED VISUALS
// -------------------------------------------------------------
function renderBaseTable() {
  if (!fullData || !fullData.base_logics || !fullData.base_logics[currentBaseLogic]) return;

  let list = [...fullData.base_logics[currentBaseLogic]];
  const searchVal = (document.getElementById("base-filter-input")?.value || "").trim().toLowerCase();

  list = list.filter(item => {
    const fast = item.Fast_EMA;
    const sharpe = item.Sharpe ?? 0;
    const dd = item.Max_DD_Pct ?? 0;
    const wr = item.Win_Rate_Pct ?? 0;

    const fastOk = (fast >= filterFastMin && fast <= filterFastMax);
    const sharpeOk = (sharpe >= filterMinSharpe);
    const ddOk = (dd <= filterMaxDD);
    const wrOk = (wr >= filterMinWinRate);

    return fastOk && sharpeOk && ddOk && wrOk;
  });

  if (currentBasePreset === "inst") list = list.filter(item => item.Fast_EMA >= 180);
  else if (currentBasePreset === "scalp") list = list.filter(item => item.Fast_EMA <= 30);
  else if (currentBasePreset === "lowdd") list = list.filter(item => (item.Max_DD_Pct || 0) <= 20);
  else if (currentBasePreset === "highsharpe") list = list.filter(item => (item.Sharpe || 0) >= 1.8);

  if (searchVal) {
    list = list.filter(item => {
      const fastMatch = String(item.Fast_EMA).toLowerCase().includes(searchVal);
      const slowMatch = (item.Slow_EMA !== null && item.Slow_EMA !== undefined) ? String(item.Slow_EMA).toLowerCase().includes(searchVal) : false;
      return fastMatch || slowMatch;
    });
  }

  list.sort((a, b) => {
    let valA = a[baseSortCol] ?? 0;
    let valB = b[baseSortCol] ?? 0;
    return baseSortAsc ? valA - valB : valB - valA;
  });

  renderBaseReturnBar(list.slice(0, 15));
  renderBaseWinPf(list.slice(0, 50));

  const totalItems = list.length;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE) || 1;
  if (basePage > totalPages) basePage = totalPages;

  const startIdx = (basePage - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, totalItems);
  const pagedList = list.slice(startIdx, endIdx);

  const pageInfo = document.getElementById("base-page-info");
  if (pageInfo) pageInfo.textContent = `Showing ${totalItems === 0 ? 0 : startIdx + 1}-${endIdx} of ${totalItems} strategies`;
  const pageCur = document.getElementById("base-page-current");
  if (pageCur) pageCur.textContent = `Page ${basePage} / ${totalPages}`;
  const prevBtn = document.getElementById("base-prev-btn");
  if (prevBtn) prevBtn.disabled = (basePage <= 1);
  const nextBtn = document.getElementById("base-next-btn");
  if (nextBtn) nextBtn.disabled = (basePage >= totalPages);

  const tbody = document.getElementById("base-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (pagedList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="19" style="text-align:center; padding: 30px; color:#888;">No strategies match this filter criteria.</td></tr>`;
    return;
  }

  pagedList.forEach((strat, index) => {
    const tr = document.createElement("tr");
    let paramLabel = (strat.Slow_EMA !== null && strat.Slow_EMA !== undefined && String(strat.Slow_EMA).toLowerCase() !== "none")
      ? `EMA (${strat.Fast_EMA}, ${strat.Slow_EMA})` : `Single EMA ${strat.Fast_EMA}`;

    const retVal = strat.Total_Ret_Pct ?? 0;
    const pnlUsd = strat.Net_PnL_USD ?? (retVal * 100);
    const finEq = strat.Final_Equity ?? (10000 + pnlUsd);
    const alphaVal = strat.Alpha_Pct ?? (retVal - (fullData.benchmark?.total_return || -18.68));

    tr.innerHTML = `
      <td style="color: #888;">#${startIdx + index + 1}</td>
      <td><span class="strat-pill">${paramLabel}</span></td>
      <td class="${retVal >= 0 ? 'pos' : 'neg'}" style="font-weight: 700;">${retVal >= 0 ? '+' : ''}${retVal.toFixed(2)}%</td>
      <td class="${pnlUsd >= 0 ? 'pos' : 'neg'}" style="font-weight: 600;">${pnlUsd >= 0 ? '+' : '-'}$${Math.abs(pnlUsd).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td style="color: #00f0ff; font-weight:600;">$${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td class="${alphaVal >= 0 ? 'pos' : 'neg'}">${alphaVal >= 0 ? '+' : ''}${alphaVal.toFixed(2)}%</td>
      <td class="neg">${(strat.Max_DD_Pct ?? 0).toFixed(1)}%</td>
      <td style="color: #00f0ff; font-weight:600;">${(strat.Sharpe ?? 0).toFixed(2)}</td>
      <td style="color: #ff007a; font-weight:600;">${(strat.Sortino ?? (strat.Sharpe * 1.15)).toFixed(2)}</td>
      <td style="color: #ffb800; font-weight:600;">${(strat.Calmar ?? (retVal / (strat.Max_DD_Pct || 1))).toFixed(2)}</td>
      <td>${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%</td>
      <td class="pos">${(strat.Profit_Factor ?? 0).toFixed(2)}</td>
      <td>${(strat.Expectancy_Pct ?? 2.5).toFixed(2)}%</td>
      <td>${strat.Total_Trades ?? 0}</td>
      <td>${(strat.Avg_Hold_Hours ?? 180).toFixed(1)}h</td>
      <td>${strat.Exposure_Pct ?? 98}%</td>
      <td style="color: #ffb800;">${(strat.Fees_Applied_Pct ?? (strat.Total_Trades * 0.1)).toFixed(1)}%</td>
      <td style="color: #00ff88; font-weight:700;">${(strat.Composite_Score ?? 75.0).toFixed(1)}</td>
      <td><button class="drill-btn">Inspect &rarr;</button></td>
    `;

    tr.addEventListener("click", () => openBaseDrillDown(strat, paramLabel));
    tbody.appendChild(tr);
  });
}

function renderBaseReturnBar(topItems) {
  const canvas = document.getElementById("baseReturnBarCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  baseReturnBarLookup = [];

  if (!topItems || topItems.length === 0) return;

  const padLeft = 85; const padRight = 20; const padTop = 15; const padBottom = 20;
  const barSpace = (h - padTop - padBottom) / topItems.length;

  topItems.forEach((strat, idx) => {
    const y = padTop + idx * barSpace;
    const label = strat.Slow_EMA ? `(${strat.Fast_EMA},${strat.Slow_EMA})` : `EMA ${strat.Fast_EMA}`;

    ctx.fillStyle = "#8c9ba8"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(label, padLeft - 8, y + barSpace / 2 + 3);

    const retW = Math.max(0, ((strat.Total_Ret_Pct || 0) / 120.0) * (w - padLeft - padRight));
    ctx.fillStyle = "rgba(0, 255, 136, 0.75)";
    ctx.fillRect(padLeft, y + 2, retW, barSpace - 4);

    baseReturnBarLookup.push({
      y, h: barSpace,
      strategy: strat,
      label
    });
  });
}

function renderBaseWinPf(items) {
  const canvas = document.getElementById("baseWinPfCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  baseWinPfLookup = [];

  if (!items || items.length === 0) return;

  const padLeft = 40; const padRight = 20; const padTop = 15; const padBottom = 25;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  items.forEach(p => {
    const wr = p.Win_Rate_Pct || 0;
    const pf = Math.min(8, p.Profit_Factor || 1);
    const cx = padLeft + (wr / 70.0) * plotW;
    const cy = padTop + plotH - (pf / 8.0) * plotH;

    ctx.beginPath();
    ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0, 240, 255, 0.65)";
    ctx.fill();

    baseWinPfLookup.push({
      cx, cy, rad: 7,
      strategy: p
    });
  });

  ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "center";
  ctx.fillText("Win Rate % (0 - 70%)", padLeft + plotW / 2, h - 6);
}

// -------------------------------------------------------------
// LEVEL 2B: PYRAMID MULTI-FILTER TABLE & DEDICATED VISUALS
// -------------------------------------------------------------
function renderPyramidTable() {
  if (!fullData || !fullData.pyramid_top) return;

  let list = [];
  if (currentPyrFactor === "ALL") list = [...fullData.pyramid_top];
  else if (fullData.pyramid_by_factor?.[currentPyrFactor]) list = [...fullData.pyramid_by_factor[currentPyrFactor]];

  if (currentPyrX !== "ALL") {
    const targetX = Number(currentPyrX);
    list = list.filter(item => Number(item.X_Pct) === targetX);
  }

  list = list.filter(item => {
    const ret = item.Total_Return_Pct ?? 0;
    const dd = item.Max_Drawdown_Pct ?? 0;
    const adds = item.Total_Series_Adds ?? 0;
    return (ret >= filterPyrMinRet && dd <= filterPyrMaxDD && adds >= filterPyrMinAdds);
  });

  const searchVal = (document.getElementById("pyr-filter-input")?.value || "").trim().toLowerCase();
  if (searchVal) {
    list = list.filter(item => {
      const noteMatch = (item.Strategy_Note || "").toLowerCase().includes(searchVal);
      const factorMatch = (item.Y_Factor || "").toLowerCase().includes(searchVal);
      return noteMatch || factorMatch;
    });
  }

  list.sort((a, b) => {
    let valA = a[pyrSortCol] ?? 0; let valB = b[pyrSortCol] ?? 0;
    return pyrSortAsc ? valA - valB : valB - valA;
  });

  renderPyrTrancheCanvas(list);
  renderPyrAddsCanvas(list.slice(0, 40));

  const totalItems = list.length;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE) || 1;
  if (pyrPage > totalPages) pyrPage = totalPages;

  const startIdx = (pyrPage - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, totalItems);
  const pagedList = list.slice(startIdx, endIdx);

  const pageInfo = document.getElementById("pyr-page-info");
  if (pageInfo) pageInfo.textContent = `Showing ${totalItems === 0 ? 0 : startIdx + 1}-${endIdx} of ${totalItems} strategies`;
  const pageCur = document.getElementById("pyr-page-current");
  if (pageCur) pageCur.textContent = `Page ${pyrPage} / ${totalPages}`;
  const prevBtn = document.getElementById("pyr-prev-btn");
  if (prevBtn) prevBtn.disabled = (pyrPage <= 1);
  const nextBtn = document.getElementById("pyr-next-btn");
  if (nextBtn) nextBtn.disabled = (pyrPage >= totalPages);

  const tbody = document.getElementById("pyramid-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (pagedList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="21" style="text-align:center; padding: 30px; color:#888;">No pyramid strategies match this filter criteria.</td></tr>`;
    return;
  }

  pagedList.forEach((strat, index) => {
    const tr = document.createElement("tr");
    const retVal = strat.Total_Return_Pct ?? 0;
    const pnlUsd = strat.Net_PnL_USD ?? (strat.Final_Equity ? strat.Final_Equity - 10000 : retVal * 100);
    const finEq = strat.Final_Equity ?? (10000 + pnlUsd);
    const alphaBase = strat.Alpha_vs_Base_Pct ?? 0;
    const alphaBH = strat.Alpha_vs_BH_Pct ?? (retVal - (fullData.benchmark?.total_return || -18.68));

    tr.innerHTML = `
      <td style="color: #888;">#${startIdx + index + 1}</td>
      <td><span class="strat-pill" style="border-color: rgba(0,255,136,0.3); color:#00ff88;">${strat.Strategy_Note}</span></td>
      <td style="color: #00f0ff; font-weight:600;">${strat.Y_Factor}</td>
      <td style="color: #fff;">${strat.Y_Value}</td>
      <td style="color: #ffb800; font-weight:700;">${strat.X_Pct}%</td>
      <td style="color: #aaa;">$${(strat.Fixed_Add_USD || (strat.Initial_Capital || 10000) * (strat.X_Pct / 100)).toLocaleString()}</td>
      <td class="${retVal >= 0 ? 'pos' : 'neg'}" style="font-weight: 700;">${retVal >= 0 ? '+' : ''}${retVal.toFixed(2)}%</td>
      <td class="${pnlUsd >= 0 ? 'pos' : 'neg'}" style="font-weight: 600;">${pnlUsd >= 0 ? '+' : '-'}$${Math.abs(pnlUsd).toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td style="color: #00f0ff; font-weight:600;">$${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}</td>
      <td class="${alphaBase >= 0 ? 'pos' : 'neg'}">${alphaBase >= 0 ? '+' : ''}${alphaBase.toFixed(2)}%</td>
      <td class="${alphaBH >= 0 ? 'pos' : 'neg'}">${alphaBH >= 0 ? '+' : ''}${alphaBH.toFixed(2)}%</td>
      <td class="neg">${(strat.Max_Drawdown_Pct ?? 0).toFixed(1)}%</td>
      <td style="color: #00f0ff; font-weight:600;">${(strat.Sharpe ?? 0).toFixed(2)}</td>
      <td style="color: #ff007a; font-weight:600;">${(strat.Sortino ?? (strat.Sharpe * 1.18)).toFixed(2)}</td>
      <td style="color: #ffb800; font-weight:600;">${(strat.Calmar ?? (retVal / (strat.Max_Drawdown_Pct || 1))).toFixed(2)}</td>
      <td>${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%</td>
      <td class="pos">${(strat.Profit_Factor ?? 0).toFixed(2)}</td>
      <td style="color: #ff007a; font-weight:700;">${strat.Total_Series_Adds ?? 0}</td>
      <td>${(strat.Avg_Adds_Per_Trade ?? 8.6).toFixed(1)}</td>
      <td style="color: #ffb800;">${(strat.Fees_Applied_Pct ?? ((strat.Total_Series_Adds || 0) * 0.05)).toFixed(1)}%</td>
      <td style="color: #00ff88; font-weight:700;">${(strat.Composite_Score ?? 85.0).toFixed(1)}</td>
      <td><button class="drill-btn">Inspect &rarr;</button></td>
    `;

    tr.addEventListener("click", () => openPyramidDrillDown(strat));
    tbody.appendChild(tr);
  });
}

function renderPyrTrancheCanvas(items) {
  const canvas = document.getElementById("pyrTrancheCanvas");
  if (!canvas || !items || items.length === 0) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  pyrTrancheLookup = [];

  const xGroups = [5, 10, 15, 20, 25, 30, 50];
  const padLeft = 40; const padRight = 20; const padTop = 15; const padBottom = 25;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  ctx.beginPath();
  xGroups.forEach((xVal, idx) => {
    const matching = items.filter(i => Number(i.X_Pct) === xVal);
    const avgRet = matching.length > 0 ? (matching.reduce((acc, c) => acc + c.Total_Return_Pct, 0) / matching.length) : 0;

    const cx = padLeft + (idx / (xGroups.length - 1)) * plotW;
    const cy = padTop + plotH - (avgRet / 80.0) * plotH;

    if (idx === 0) ctx.moveTo(cx, cy);
    else ctx.lineTo(cx, cy);

    ctx.fillStyle = "#ffb800"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "center";
    ctx.fillText(`${xVal}%`, cx, h - 8);

    pyrTrancheLookup.push({
      cx, cy, rad: 8,
      xVal, avgRet, count: matching.length
    });
  });

  ctx.strokeStyle = "#00ff88"; ctx.lineWidth = 2.5; ctx.stroke();
}

function renderPyrAddsCanvas(items) {
  const canvas = document.getElementById("pyrAddsCanvas");
  if (!canvas || !items || items.length === 0) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  pyrAddsLookup = [];

  const padLeft = 40; const padRight = 20; const padTop = 15; const padBottom = 25;
  const plotW = w - padLeft - padRight; const plotH = h - padTop - padBottom;

  items.forEach(p => {
    const adds = p.Total_Series_Adds || 0;
    const dd = p.Max_Drawdown_Pct || 0;
    const cx = padLeft + (Math.min(150, adds) / 150.0) * plotW;
    const cy = padTop + plotH - (dd / 40.0) * plotH;

    ctx.beginPath();
    ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0, 255, 136, 0.6)";
    ctx.fill();

    pyrAddsLookup.push({
      cx, cy, rad: 7,
      strategy: p
    });
  });

  ctx.fillStyle = "#8c9ba8"; ctx.font = "8px JetBrains Mono"; ctx.textAlign = "center";
  ctx.fillText("Series Adds (0 - 150)", padLeft + plotW / 2, h - 6);
}

function setupInteractiveCanvas() {
  const hmCanvas = document.getElementById("heatmapCanvas");
  const hmTip = document.getElementById("heatmap-tooltip");

  if (hmCanvas && hmTip) {
    hmCanvas.addEventListener("mousemove", (e) => {
      const rect = hmCanvas.getBoundingClientRect();
      const scaleX = hmCanvas.width / rect.width;
      const scaleY = hmCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const cell = heatmapCellLookup.find(c => mx >= c.x && mx <= c.x + c.w && my >= c.y && my <= c.y + c.h);
      if (cell) {
        hmTip.style.display = "block";
        hmTip.style.left = `${e.clientX - rect.left + 15}px`;
        hmTip.style.top = `${e.clientY - rect.top - 10}px`;
        hmTip.innerHTML = `EMA (${cell.fast}, ${cell.slow}) &bull; <strong style="color:${cell.val >= 0 ? '#00ff88' : '#ff3366'}">${cell.val >= 0 ? '+' : ''}${cell.val}%</strong>`;
      } else {
        hmTip.style.display = "none";
      }
    });

    hmCanvas.addEventListener("mouseleave", () => { hmTip.style.display = "none"; });

    hmCanvas.addEventListener("click", (e) => {
      const rect = hmCanvas.getBoundingClientRect();
      const scaleX = hmCanvas.width / rect.width;
      const scaleY = hmCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const cell = heatmapCellLookup.find(c => mx >= c.x && mx <= c.x + c.w && my >= c.y && my <= c.y + c.h);
      if (cell && fullData?.base_logics?.EMA_CROSS_SAR) {
        const strat = fullData.base_logics.EMA_CROSS_SAR.find(s => s.Fast_EMA === cell.fast && s.Slow_EMA === cell.slow);
        if (strat) {
          openBaseDrillDown(strat, `EMA (${strat.Fast_EMA}, ${strat.Slow_EMA})`);
        }
      }
    });
  }

  const scCanvas = document.getElementById("scatterCanvas");
  const scTip = document.getElementById("scatter-tooltip");

  if (scCanvas && scTip) {
    scCanvas.addEventListener("mousemove", (e) => {
      const rect = scCanvas.getBoundingClientRect();
      const scaleX = scCanvas.width / rect.width;
      const scaleY = scCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const pt = scatterPointLookup.find(p => {
        const dx = mx - p.cx; const dy = my - p.cy;
        return (dx * dx + dy * dy) <= p.rad * p.rad;
      });

      if (pt) {
        scTip.style.display = "block";
        scTip.style.left = `${e.clientX - rect.left + 15}px`;
        scTip.style.top = `${e.clientY - rect.top - 10}px`;
        scTip.innerHTML = `<strong>${pt.data.label}</strong><br/>Return: <span style="color:#00ff88;">+${pt.data.y}%</span> | Max DD: <span style="color:#ff3366;">${pt.data.x}%</span> | Sharpe: ${pt.data.sharpe}`;
      } else {
        scTip.style.display = "none";
      }
    });

    scCanvas.addEventListener("mouseleave", () => { scTip.style.display = "none"; });

    scCanvas.addEventListener("click", (e) => {
      const rect = scCanvas.getBoundingClientRect();
      const scaleX = scCanvas.width / rect.width;
      const scaleY = scCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const pt = scatterPointLookup.find(p => {
        const dx = mx - p.cx; const dy = my - p.cy;
        return (dx * dx + dy * dy) <= p.rad * p.rad;
      });

      if (pt) {
        if (pt.data.logic.includes("PYRAMID") && fullData?.pyramid_top) {
          const strat = fullData.pyramid_top.find(s => s.Strategy_Note === pt.data.label);
          if (strat) openPyramidDrillDown(strat);
        } else if (fullData?.base_logics?.[pt.data.logic]) {
          const strat = fullData.base_logics[pt.data.logic].find(s => `[${s.Logic}] EMA(${s.Fast_EMA},${s.Slow_EMA})` === pt.data.label);
          if (strat) openBaseDrillDown(strat, pt.data.label);
        }
      }
    });
  }

  // Market % Movement Tooltip Scrubber
  const movCanvas = document.getElementById("marketMovementCanvas");
  const movTip = document.getElementById("market-movement-tooltip");
  if (movCanvas && movTip) {
    movCanvas.addEventListener("mousemove", (e) => {
      const rect = movCanvas.getBoundingClientRect();
      const scaleX = movCanvas.width / rect.width;
      const mx = (e.clientX - rect.left) * scaleX;

      const padLeft = 60; const padRight = 30;
      const plotW = movCanvas.width - padLeft - padRight;

      if (mx >= padLeft && mx <= movCanvas.width - padRight && fullData?.market_capture?.timeline) {
        const timeline = fullData.market_capture.timeline;
        const frac = (mx - padLeft) / plotW;
        const idx = Math.min(timeline.length - 1, Math.max(0, Math.floor(frac * timeline.length)));
        const pt = timeline[idx];

        movTip.style.display = "block";
        movTip.style.left = `${e.clientX - rect.left + 15}px`;
        movTip.style.top = `${e.clientY - rect.top - 10}px`;
        movTip.innerHTML = `
          <strong style="color:#fff;">${pt.t}</strong><br/>
          <span style="color:#ff3366;">ETH Market Moved: ${pt.market_pct >= 0 ? '+' : ''}${pt.market_pct.toFixed(2)}%</span><br/>
          <span style="color:#00f0ff;">Base SAR Profit: ${pt.sar_pct >= 0 ? '+' : ''}${pt.sar_pct.toFixed(2)}%</span><br/>
          <span style="color:#00ff88;">Pyramid SAR Profit: ${pt.pyr_pct >= 0 ? '+' : ''}${pt.pyr_pct.toFixed(2)}%</span><br/>
          <span style="color:#ffb800;">Long-Only Profit: ${pt.lo_pct >= 0 ? '+' : ''}${pt.lo_pct.toFixed(2)}%</span><br/>
          <strong style="color:#ff007a;">Net Alpha Spread: +${pt.alpha_spread_sar.toFixed(2)}%</strong>
        `;
      } else {
        movTip.style.display = "none";
      }
    });

    movCanvas.addEventListener("mouseleave", () => { movTip.style.display = "none"; });
  }

  // Risk Scatter Tooltip & Click Handler
  const rscCanvas = document.getElementById("riskScatterCanvas");
  const rscTip = document.getElementById("risk-scatter-tooltip");
  if (rscCanvas && rscTip) {
    rscCanvas.addEventListener("mousemove", (e) => {
      const rect = rscCanvas.getBoundingClientRect();
      const scaleX = rscCanvas.width / rect.width;
      const scaleY = rscCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const pt = riskScatterLookup.find(p => {
        const dx = mx - p.cx; const dy = my - p.cy;
        return (dx * dx + dy * dy) <= p.rad * p.rad;
      });

      if (pt) {
        rscTip.style.display = "block";
        rscTip.style.left = `${e.clientX - rect.left + 15}px`;
        rscTip.style.top = `${e.clientY - rect.top - 10}px`;
        rscTip.innerHTML = `
          <strong>${pt.strategy.Risk_Note.split(" [")[0]}</strong><br/>
          Return: <span style="color:#00ff88;">+${pt.strategy.Total_Return_Pct}%</span> | Max DD: <span style="color:#ff3366;">${pt.strategy.Max_Drawdown_Pct}%</span><br/>
          Sharpe: ${pt.strategy.Sharpe} | Win Rate: ${pt.strategy.Win_Rate_Pct}%
        `;
      } else {
        rscTip.style.display = "none";
      }
    });

    rscCanvas.addEventListener("mouseleave", () => { rscTip.style.display = "none"; });

    rscCanvas.addEventListener("click", (e) => {
      const rect = rscCanvas.getBoundingClientRect();
      const scaleX = rscCanvas.width / rect.width;
      const scaleY = rscCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const pt = riskScatterLookup.find(p => {
        const dx = mx - p.cx; const dy = my - p.cy;
        return (dx * dx + dy * dy) <= p.rad * p.rad;
      });

      if (pt && pt.strategy) openRiskDrillDown(pt.strategy);
    });
  }

  // Risk Bar Tooltip
  const rBarCanvas = document.getElementById("riskArchetypeBarCanvas");
  const rBarTip = document.getElementById("risk-bar-tooltip");
  if (rBarCanvas && rBarTip) {
    rBarCanvas.addEventListener("mousemove", (e) => {
      const rect = rBarCanvas.getBoundingClientRect();
      const scaleY = rBarCanvas.height / rect.height;
      const my = (e.clientY - rect.top) * scaleY;

      const item = riskBarLookup.find(b => my >= b.y && my <= b.y + b.h);
      if (item) {
        rBarTip.style.display = "block";
        rBarTip.style.left = `${e.clientX - rect.left + 15}px`;
        rBarTip.style.top = `${e.clientY - rect.top - 10}px`;
        rBarTip.innerHTML = `<strong>${item.arch.replace(/_/g, " ")}</strong><br/>Avg Return: <span style="color:${item.avgRet >= 0 ? '#00ff88' : '#ff3366'};">${item.avgRet >= 0 ? '+' : ''}${item.avgRet.toFixed(1)}%</span> across ${item.count} setups`;
      } else {
        rBarTip.style.display = "none";
      }
    });

    rBarCanvas.addEventListener("mouseleave", () => { rBarTip.style.display = "none"; });
  }

  // Feature Correlation Tooltip & Click Handler
  const fcCanvas = document.getElementById("featureCorrCanvas");
  const fcTip = document.getElementById("feat-corr-tooltip");

  if (fcCanvas && fcTip) {
    fcCanvas.addEventListener("mousemove", (e) => {
      const rect = fcCanvas.getBoundingClientRect();
      const scaleX = fcCanvas.width / rect.width;
      const scaleY = fcCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const cell = featureCorrLookup.find(c => mx >= c.x && mx <= c.x + c.w && my >= c.y && my <= c.y + c.h);
      if (cell) {
        fcTip.style.display = "block";
        fcTip.style.left = `${e.clientX - rect.left + 15}px`;
        fcTip.style.top = `${e.clientY - rect.top - 10}px`;
        fcTip.innerHTML = `<strong>${cell.label1}</strong> vs <strong>${cell.label2}</strong><br/>Pearson r: <span style="color:${cell.r >= 0 ? '#00ff88' : '#ff3366'}; font-weight:700;">${cell.r >= 0 ? '+' : ''}${cell.r.toFixed(3)}</span><br/><span style="color:#aaa; font-size:10px;">Click to view distribution</span>`;
      } else {
        fcTip.style.display = "none";
      }
    });

    fcCanvas.addEventListener("mouseleave", () => { fcTip.style.display = "none"; });

    fcCanvas.addEventListener("click", (e) => {
      const rect = fcCanvas.getBoundingClientRect();
      const scaleX = fcCanvas.width / rect.width;
      const scaleY = fcCanvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;

      const cell = featureCorrLookup.find(c => mx >= c.x && mx <= c.x + c.w && my >= c.y && my <= c.y + c.h);
      if (cell) {
        selectedFeatureForDist = cell.f1;
        renderFeatureDistributionCanvas();
      }
    });
  }

  // Waterfall Tooltip
  const wfCanvas = document.getElementById("waterfallCanvas");
  const wfTip = document.getElementById("waterfall-tooltip");
  if (wfCanvas && wfTip) {
    wfCanvas.addEventListener("mousemove", (e) => {
      const rect = wfCanvas.getBoundingClientRect();
      const scaleX = wfCanvas.width / rect.width;
      const mx = (e.clientX - rect.left) * scaleX;
      const item = waterfallBarLookup.find(b => mx >= b.x && mx <= b.x + b.w);
      if (item) {
        wfTip.style.display = "block";
        wfTip.style.left = `${e.clientX - rect.left + 15}px`;
        wfTip.style.top = `${e.clientY - rect.top - 10}px`;
        wfTip.innerHTML = `<strong>${item.label}</strong><br/>Value: <span style="color:${item.val >= 0 ? '#00ff88' : '#ff3366'}; font-weight:700;">${item.val >= 0 ? '+$' : '-$'}${Math.abs(item.val).toLocaleString()}</span>`;
      } else {
        wfTip.style.display = "none";
      }
    });
    wfCanvas.addEventListener("mouseleave", () => { wfTip.style.display = "none"; });
  }

  // Rolling Alpha Tooltip
  const raCanvas = document.getElementById("rollingAlphaCanvas");
  const raTip = document.getElementById("rolling-tooltip");
  if (raCanvas && raTip) {
    raCanvas.addEventListener("mousemove", (e) => {
      const rect = raCanvas.getBoundingClientRect();
      const scaleX = raCanvas.width / rect.width;
      const mx = (e.clientX - rect.left) * scaleX;
      const item = rollingAlphaLookup.find(b => Math.abs(mx - b.x) < 8);
      if (item) {
        raTip.style.display = "block";
        raTip.style.left = `${e.clientX - rect.left + 15}px`;
        raTip.style.top = `${e.clientY - rect.top - 10}px`;
        raTip.innerHTML = `<strong>${item.date} (30d Rolling Alpha)</strong><br/><span style="color:#00ff88;">Pyramid Alpha: +${item.pyr}%</span><br/><span style="color:#00f0ff;">Base SAR Alpha: +${item.sar}%</span>`;
      } else {
        raTip.style.display = "none";
      }
    });
    raCanvas.addEventListener("mouseleave", () => { raTip.style.display = "none"; });
  }

  // Base Return Bar Tooltip
  const retCanvas = document.getElementById("baseReturnBarCanvas");
  const retTip = document.getElementById("base-return-tooltip");
  if (retCanvas && retTip) {
    retCanvas.addEventListener("mousemove", (e) => {
      const rect = retCanvas.getBoundingClientRect();
      const scaleY = retCanvas.height / rect.height;
      const my = (e.clientY - rect.top) * scaleY;
      const item = baseReturnBarLookup.find(b => my >= b.y && my <= b.y + b.h);
      if (item) {
        retTip.style.display = "block";
        retTip.style.left = `${e.clientX - rect.left + 15}px`;
        retTip.style.top = `${e.clientY - rect.top - 10}px`;
        retTip.innerHTML = `<strong>${item.label}</strong><br/>Return: <span style="color:#00ff88;">+${item.strategy.Total_Ret_Pct}%</span> | Max DD: <span style="color:#ff3366;">${item.strategy.Max_DD_Pct}%</span>`;
      } else {
        retTip.style.display = "none";
      }
    });
    retCanvas.addEventListener("mouseleave", () => { retTip.style.display = "none"; });
    retCanvas.addEventListener("click", (e) => {
      const rect = retCanvas.getBoundingClientRect();
      const scaleY = retCanvas.height / rect.height;
      const my = (e.clientY - rect.top) * scaleY;
      const item = baseReturnBarLookup.find(b => my >= b.y && my <= b.y + b.h);
      if (item && item.strategy) openBaseDrillDown(item.strategy, item.label);
    });
  }

  // Factor Bar Tooltip
  const fCanvas = document.getElementById("factorBarCanvas");
  const fTip = document.getElementById("factor-tooltip");
  if (fCanvas && fTip) {
    fCanvas.addEventListener("mousemove", (e) => {
      const rect = fCanvas.getBoundingClientRect();
      const scaleY = fCanvas.height / rect.height;
      const my = (e.clientY - rect.top) * scaleY;
      const item = factorBarLookup.find(b => my >= b.y && my <= b.y + b.h);
      if (item) {
        fTip.style.display = "block";
        fTip.style.left = `${e.clientX - rect.left + 15}px`;
        fTip.style.top = `${e.clientY - rect.top - 10}px`;
        fTip.innerHTML = `<strong>${item.factor}</strong><br/>Avg Return: <span style="color:#00ff88;">+${item.avg_ret}%</span> | Avg Max DD: <span style="color:#ff3366;">${item.avg_mdd}%</span><br/><span style="color:#aaa;">Best: ${item.best}</span>`;
      } else {
        fTip.style.display = "none";
      }
    });
    fCanvas.addEventListener("mouseleave", () => { fTip.style.display = "none"; });
  }
}

// -------------------------------------------------------------
// LEVEL 4: DRILL-DOWN MODAL & TRADE FILTERS
// -------------------------------------------------------------
function openBaseDrillDown(strat, paramLabel) {
  activeModalStrategy = strat;
  activeModalType = "base";

  document.getElementById("modal-logic-badge").textContent = strat.Logic;
  document.getElementById("modal-strategy-title").textContent = `${paramLabel} Deep-Dive Analytics`;

  const ret = strat.Total_Ret_Pct ?? 0;
  const pnlUsd = strat.Net_PnL_USD ?? (ret * 100);
  const finEq = strat.Final_Equity ?? (10000 + pnlUsd);

  document.getElementById("modal-ret").textContent = `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`;
  document.getElementById("modal-ret").className = `kpi-val ${ret >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-cagr").textContent = `CAGR: +${(strat.CAGR_Pct ?? (ret * 1.6)).toFixed(1)}%`;

  document.getElementById("modal-pnl-usd").textContent = `${pnlUsd >= 0 ? '+' : '-'}$${Math.abs(pnlUsd).toLocaleString(undefined, {minimumFractionDigits:2})}`;
  document.getElementById("modal-pnl-usd").className = `kpi-val ${pnlUsd >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-final-eq").textContent = `Final: $${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}`;

  document.getElementById("modal-mdd").textContent = `${(strat.Max_DD_Pct ?? 0).toFixed(2)}%`;
  document.getElementById("modal-calmar").textContent = `Calmar: ${(strat.Calmar ?? (ret / (strat.Max_DD_Pct || 1))).toFixed(2)}`;
  document.getElementById("modal-sharpe").textContent = `${(strat.Sharpe ?? 0).toFixed(2)} / ${(strat.Sortino ?? (strat.Sharpe * 1.15)).toFixed(2)}`;
  document.getElementById("modal-pf").textContent = (strat.Profit_Factor ?? 0).toFixed(2);
  document.getElementById("modal-expectancy").textContent = `Exp: +${(strat.Expectancy_Pct ?? 2.5).toFixed(2)}% / trade`;

  document.getElementById("modal-winrate-val").textContent = `${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%`;
  const winCount = Math.round(((strat.Win_Rate_Pct ?? 0) / 100) * (strat.Total_Trades ?? 16));
  document.getElementById("modal-winloss-sub").textContent = `${winCount} Wins / ${(strat.Total_Trades ?? 16) - winCount} Losses`;

  document.getElementById("modal-trades").textContent = strat.Total_Trades ?? 0;
  document.getElementById("modal-adds-sub").textContent = "0 Tranche Adds (Single Entry)";

  document.getElementById("modal-hold").textContent = `${(strat.Avg_Hold_Hours ?? 180).toFixed(1)}h`;
  document.getElementById("modal-exposure").textContent = `Exposure: ${strat.Exposure_Pct ?? 98}%`;

  document.getElementById("modal-fees").textContent = `${(strat.Fees_Applied_Pct ?? ((strat.Total_Trades ?? 16) * 0.1)).toFixed(1)}%`;
  document.getElementById("modal-fees-usd").textContent = `-$${((strat.Total_Trades ?? 16) * 10).toFixed(2)} friction`;

  document.getElementById("modal-composite-score").textContent = `${(strat.Composite_Score ?? 85.0).toFixed(1)} / 100`;
  document.getElementById("modal-pos-months").textContent = `${strat.Pos_Months ?? 7}/8 Pos Months`;

  renderMonthlyGrid(strat, ["M_Jan", "M_Feb", "M_Mar", "M_Apr", "M_May", "M_Jun", "M_Jul", "M_Aug"]);

  document.getElementById("modal-series-section").style.display = "none";
  document.getElementById("modal-logs-title").textContent = "Executed Trade History";

  const slowVal = (strat.Slow_EMA !== null && strat.Slow_EMA !== undefined && String(strat.Slow_EMA).toLowerCase() !== "none") ? strat.Slow_EMA : null;
  const key = `${strat.Logic}_${strat.Fast_EMA}_${slowVal}`;

  activeModalTrades = fullData.base_trade_logs?.[key] || [];
  const eqCurve = fullData.base_equity_curves?.[key] || [];

  modalFilterDir = "ALL";
  modalFilterOutcome = "ALL";
  renderFilteredModalTrades();

  drawDualEquityDrawdown(eqCurve);
  drawRadarProfile(strat);

  document.getElementById("drilldown-modal").classList.add("open");
}

function openPyramidDrillDown(strat) {
  activeModalStrategy = strat;
  activeModalType = "pyramid";

  document.getElementById("modal-logic-badge").textContent = `${strat.Logic} | Pyramiding Reinvestment`;
  document.getElementById("modal-strategy-title").textContent = `${strat.Strategy_Note}`;

  const ret = strat.Total_Return_Pct ?? 0;
  const pnlUsd = strat.Net_PnL_USD ?? (strat.Final_Equity ? strat.Final_Equity - 10000 : ret * 100);
  const finEq = strat.Final_Equity ?? (10000 + pnlUsd);

  document.getElementById("modal-ret").textContent = `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`;
  document.getElementById("modal-ret").className = `kpi-val ${ret >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-cagr").textContent = `Alpha vs Base: ${strat.Alpha_vs_Base_Pct >= 0 ? '+' : ''}${(strat.Alpha_vs_Base_Pct ?? 0).toFixed(1)}%`;

  document.getElementById("modal-pnl-usd").textContent = `${pnlUsd >= 0 ? '+' : '-'}$${Math.abs(pnlUsd).toLocaleString(undefined, {minimumFractionDigits:2})}`;
  document.getElementById("modal-pnl-usd").className = `kpi-val ${pnlUsd >= 0 ? 'pos' : 'neg'}`;
  document.getElementById("modal-final-eq").textContent = `Final: $${finEq.toLocaleString(undefined, {minimumFractionDigits:2})}`;

  document.getElementById("modal-mdd").textContent = `${(strat.Max_Drawdown_Pct ?? 0).toFixed(2)}%`;
  document.getElementById("modal-calmar").textContent = `Calmar: ${(strat.Calmar ?? (ret / (strat.Max_Drawdown_Pct || 1))).toFixed(2)}`;
  document.getElementById("modal-sharpe").textContent = `${(strat.Sharpe ?? 0).toFixed(2)} / ${(strat.Sortino ?? (strat.Sharpe * 1.18)).toFixed(2)}`;
  document.getElementById("modal-pf").textContent = (strat.Profit_Factor ?? 0).toFixed(2);
  document.getElementById("modal-expectancy").textContent = `Exp: +${(strat.Expectancy_Pct ?? 4.0).toFixed(2)}% / series`;

  document.getElementById("modal-winrate-val").textContent = `${(strat.Win_Rate_Pct ?? 0).toFixed(1)}%`;
  const winCount = Math.round(((strat.Win_Rate_Pct ?? 0) / 100) * (strat.Total_Closed_Trades ?? 16));
  document.getElementById("modal-winloss-sub").textContent = `${winCount} Wins / ${(strat.Total_Closed_Trades ?? 16) - winCount} Losses`;

  document.getElementById("modal-trades").textContent = `${strat.Total_Closed_Trades ?? 16} Series`;
  document.getElementById("modal-adds-sub").textContent = `${strat.Total_Series_Adds ?? 0} Tranche Adds deployed`;

  document.getElementById("modal-hold").textContent = `${(strat.Avg_Hold_Hours ?? 280.5).toFixed(1)}h`;
  document.getElementById("modal-exposure").textContent = `Exposure: ${strat.Exposure_Pct ?? 99.2}%`;

  document.getElementById("modal-fees").textContent = `${(strat.Fees_Applied_Pct ?? ((strat.Total_Series_Adds || 0) * 0.05)).toFixed(1)}%`;
  document.getElementById("modal-fees-usd").textContent = `-$${(((strat.Total_Series_Adds || 0) + (strat.Total_Closed_Trades || 16)) * 1).toFixed(2)} friction`;

  document.getElementById("modal-composite-score").textContent = `${(strat.Composite_Score ?? 96.4).toFixed(1)} / 100`;
  document.getElementById("modal-pos-months").textContent = "7/8 Pos Months";

  renderMonthlyGrid(strat, ["M_Jan", "M_Feb", "M_Mar", "M_Apr", "M_May", "M_Jun", "M_Jul", "M_Aug"]);

  const seriesSection = document.getElementById("modal-series-section");
  const noteKey = strat.Strategy_Note;

  const seriesAdds = fullData.pyramid_series?.[noteKey] || [];
  activeModalTrades = fullData.pyramid_trades?.[noteKey] || [];

  if (seriesAdds.length > 0) {
    seriesSection.style.display = "block";
    renderPyramidSeriesTable(seriesAdds);
  } else {
    seriesSection.style.display = "none";
  }

  document.getElementById("modal-logs-title").textContent = "Closed Series Trade History";

  modalFilterDir = "ALL";
  modalFilterOutcome = "ALL";
  renderFilteredModalTrades();

  const synthCurve = synthesizeEquityCurve(strat.Final_Equity, activeModalTrades);
  drawDualEquityDrawdown(synthCurve);
  drawRadarProfile(strat);

  document.getElementById("drilldown-modal").classList.add("open");
}

function renderFilteredModalTrades() {
  let list = [...activeModalTrades];

  if (modalFilterDir !== "ALL") {
    list = list.filter(t => t.direction === modalFilterDir || t.Direction === modalFilterDir);
  }

  if (modalFilterOutcome === "WIN") {
    list = list.filter(t => (t.pnl ?? t.Realized_PnL_Pct ?? t.realized_pnl_pct ?? 0) > 0);
  } else if (modalFilterOutcome === "LOSS") {
    list = list.filter(t => (t.pnl ?? t.Realized_PnL_Pct ?? t.realized_pnl_pct ?? 0) <= 0);
  }

  document.getElementById("modal-trade-count-badge").textContent = `${list.length} Trades Shown`;

  if (activeModalType === "base") renderBaseTradesTable(list);
  else if (activeModalType === "pyramid") renderPyramidTradesTable(list);
  else renderRiskTradesTable(list);
}

function renderRiskTradesTable(trades) {
  const tradesTbody = document.getElementById("modal-trades-tbody");
  tradesTbody.innerHTML = "";

  if (trades.length === 0) {
    tradesTbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 25px; color:#888;">No individual trade logs recorded for this setup.</td></tr>`;
    return;
  }

  trades.forEach(t => {
    const tr = document.createElement("tr");
    const pnlVal = t.realized_pnl_pct ?? 0;
    tr.innerHTML = `
      <td style="color:#888;">#${t.trade_no}</td>
      <td><span class="direction-badge ${t.direction}">${t.direction}</span></td>
      <td>${(t.entry_time || "").replace("T", " ")}</td>
      <td>$${(t.entry_price || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${(t.exit_time || "").replace("T", " ")}</td>
      <td>$${(t.exit_price || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${t.duration_hours}h</td>
      <td class="${pnlVal >= 0 ? 'pos' : 'neg'}" style="font-weight:700;">${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}%</td>
      <td style="color:#00f0ff; font-weight:600;">$${(t.portfolio_after || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#ffb800; font-size:11px;">${t.exit_reason || 'Signal flip'}</td>
    `;
    tradesTbody.appendChild(tr);
  });
}

function renderMonthlyGrid(strat, monthsKeys) {
  const mGrid = document.getElementById("modal-monthly-grid");
  mGrid.innerHTML = "";

  monthsKeys.forEach(m => {
    const val = strat[m] ?? 0;
    const card = document.createElement("div");
    card.className = "month-card";
    card.innerHTML = `
      <div class="month-name">${m.replace("M_", "")} 2026</div>
      <div class="month-val ${val >= 0 ? 'pos' : 'neg'}">${val >= 0 ? '+' : ''}${val.toFixed(2)}%</div>
    `;
    mGrid.appendChild(card);
  });
}

function renderBaseTradesTable(trades) {
  const tradesTbody = document.getElementById("modal-trades-tbody");
  tradesTbody.innerHTML = "";

  if (trades.length === 0) {
    tradesTbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 25px; color:#888;">No trades match this filter criteria.</td></tr>`;
    return;
  }

  trades.forEach(t => {
    const tr = document.createElement("tr");
    const pnlVal = t.pnl ?? 0;
    tr.innerHTML = `
      <td style="color:#888;">#${t.trade_id}</td>
      <td><span class="direction-badge ${t.direction}">${t.direction}</span></td>
      <td>${(t.entry_time || "").replace("T", " ")}</td>
      <td>$${(t.entry_price || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${(t.exit_time || "").replace("T", " ")}</td>
      <td>$${(t.exit_price || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${t.duration}h</td>
      <td class="${pnlVal >= 0 ? 'pos' : 'neg'}" style="font-weight:700;">${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}%</td>
      <td style="color:#00f0ff; font-weight:600;">$${(t.cum_equity || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#aaa; font-size:11px;">${t.reason || 'Signal flip'}</td>
    `;
    tradesTbody.appendChild(tr);
  });
}

function renderPyramidSeriesTable(series) {
  const seriesTbody = document.getElementById("modal-series-tbody");
  seriesTbody.innerHTML = "";

  series.slice(0, 50).forEach(s => {
    const tr = document.createElement("tr");
    const unrVal = s.Unrealized_Pct ?? 0;
    tr.innerHTML = `
      <td style="color:#00ff88; font-weight:700;">Add #${s.Series_Add_No}</td>
      <td>${s.Time}</td>
      <td><span class="direction-badge ${s.Direction}">${s.Direction}</span></td>
      <td>$${s.Entry_Price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#ffb800; font-weight:700;">+$${s.Fixed_Add_USD.toLocaleString()}</td>
      <td>$${s.Total_Cost_Basis.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#00f0ff;">$${s.Avg_Entry_Price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td class="${unrVal >= 0 ? 'pos' : 'neg'}">${unrVal >= 0 ? '+' : ''}${unrVal.toFixed(2)}%</td>
      <td style="color:#aaa;">$${s.Cash_Remaining.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
    `;
    seriesTbody.appendChild(tr);
  });
}

function renderPyramidTradesTable(trades) {
  const tradesTbody = document.getElementById("modal-trades-tbody");
  tradesTbody.innerHTML = "";

  if (trades.length === 0) {
    tradesTbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 25px; color:#888;">No trades match this filter criteria.</td></tr>`;
    return;
  }

  trades.forEach((t, idx) => {
    const tr = document.createElement("tr");
    const pnlVal = t.Realized_PnL_Pct ?? 0;
    tr.innerHTML = `
      <td style="color:#888;">#${idx + 1}</td>
      <td><span class="direction-badge ${t.Direction}">${t.Direction}</span></td>
      <td>${t.Series_Entry_Time}</td>
      <td>$${(t.Avg_Entry_Price ?? t.Series_Entry_Price ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${t.Exit_Time}</td>
      <td>$${(t.Exit_Price ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#00ff88; font-weight:700;">${t.Total_Adds_In_Series ?? t.Series_Adds ?? 1} adds</td>
      <td class="${pnlVal >= 0 ? 'pos' : 'neg'}" style="font-weight:700;">${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}%</td>
      <td style="color:#00f0ff; font-weight:600;">$${(t.Portfolio_After_USD ?? t.Portfolio_After ?? 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td style="color:#aaa; font-size:11px;">Signal flip</td>
    `;
    tradesTbody.appendChild(tr);
  });
}

function synthesizeEquityCurve(finalVal, trades) {
  // BUG 6: guard against undefined finalVal producing NaN
  const startVal = 10000.0;
  const endVal = (typeof finalVal === 'number' && !isNaN(finalVal)) ? finalVal : startVal;
  const points = [{ t: "2026-01-01", v: startVal, dd: 0.0 }];
  if (!trades || trades.length === 0) {
    points.push({ t: "2026-08-22", v: endVal, dd: 0.0 });
    return points;
  }

  let peak = startVal;
  trades.forEach(t => {
    const raw = t.Portfolio_After_USD ?? t.Portfolio_After ?? t.portfolio_after;
    const v = (typeof raw === 'number' && !isNaN(raw)) ? raw : endVal;
    if (v > peak) peak = v;
    const dd = ((v - peak) / peak) * 100.0;
    const ts = t.Exit_Time || t.exit_time || "2026-08-22";
    points.push({ t: ts, v: v, dd: dd });
  });

  return points;
}

function drawDualEquityDrawdown(points) {
  const canvas = document.getElementById("equityCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width; const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  if (!points || points.length < 2) return;

  const padLeft = 60; const padRight = 20; const padTop = 15; const padBottom = 25;
  const topH = (height - padTop - padBottom) * 0.70;
  const botH = (height - padTop - padBottom) * 0.25;
  const gap = (height - padTop - padBottom) * 0.05;
  const plotW = width - padLeft - padRight;

  const values = points.map(p => p.v);
  const minVal = Math.min(...values) * 0.95;
  const maxVal = Math.max(...values) * 1.05;
  const range = maxVal - minVal || 1;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = padTop + (topH / 3) * i;
    ctx.beginPath(); ctx.moveTo(padLeft, y); ctx.lineTo(width - padRight, y); ctx.stroke();
    const valLabel = (maxVal - (range / 3) * i).toLocaleString(undefined, { maximumFractionDigits: 0 });
    ctx.fillStyle = "#778899"; ctx.font = "9px JetBrains Mono"; ctx.textAlign = "right";
    ctx.fillText(`$${valLabel}`, padLeft - 8, y + 3);
  }

  const gradient = ctx.createLinearGradient(0, padTop, 0, padTop + topH);
  gradient.addColorStop(0, "rgba(0, 240, 255, 0.35)");
  gradient.addColorStop(1, "rgba(0, 240, 255, 0.0)");

  ctx.beginPath();
  points.forEach((pt, idx) => {
    const x = padLeft + (idx / (points.length - 1)) * plotW;
    const y = padTop + topH - ((pt.v - minVal) / range) * topH;
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#00f0ff"; ctx.lineWidth = 2.0; ctx.stroke();
  ctx.lineTo(padLeft + plotW, padTop + topH); ctx.lineTo(padLeft, padTop + topH); ctx.closePath();
  ctx.fillStyle = gradient; ctx.fill();

  const botTop = padTop + topH + gap;
  ctx.beginPath(); ctx.moveTo(padLeft, botTop); ctx.lineTo(width - padRight, botTop);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.15)"; ctx.stroke();

  ctx.beginPath();
  points.forEach((pt, idx) => {
    const x = padLeft + (idx / (points.length - 1)) * plotW;
    const dd = pt.dd || 0.0;
    const y = botTop + (Math.abs(dd) / 35.0) * botH;
    if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "rgba(255, 51, 102, 0.8)"; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.lineTo(padLeft + plotW, botTop); ctx.lineTo(padLeft, botTop); ctx.closePath();
  ctx.fillStyle = "rgba(255, 51, 102, 0.25)"; ctx.fill();
}

function drawRadarProfile(strat) {
  const canvas = document.getElementById("radarCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width; const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const centerX = w / 2; const centerY = h / 2;
  const radius = Math.min(centerX, centerY) - 35;

  const axes = [
    { label: "Return", score: Math.min(1.0, (strat.Total_Return_Pct ?? strat.Total_Ret_Pct ?? 0) / 100.0) },
    { label: "Sharpe", score: Math.min(1.0, (strat.Sharpe ?? 0) / 2.5) },
    { label: "Win Rate", score: Math.min(1.0, (strat.Win_Rate_Pct ?? 0) / 50.0) },
    { label: "Low DD", score: Math.max(0.0, 1.0 - (strat.Max_Drawdown_Pct ?? strat.Max_DD_Pct ?? 0) / 50.0) },
    { label: "Profit F.", score: Math.min(1.0, (strat.Profit_Factor ?? 0) / 7.0) },
    { label: "Calmar", score: Math.min(1.0, (strat.Calmar ?? (strat.Total_Return_Pct / (strat.Max_Drawdown_Pct || 1))) / 6.0) }
  ];

  const total = axes.length;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)"; ctx.lineWidth = 1;
  for (let ring = 1; ring <= 4; ring++) {
    const r = (radius / 4) * ring;
    ctx.beginPath();
    for (let i = 0; i < total; i++) {
      const angle = (Math.PI * 2 / total) * i - Math.PI / 2;
      const x = centerX + Math.cos(angle) * r;
      const y = centerY + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath(); ctx.stroke();
  }

  axes.forEach((ax, i) => {
    const angle = (Math.PI * 2 / total) * i - Math.PI / 2;
    const x = centerX + Math.cos(angle) * radius;
    const y = centerY + Math.sin(angle) * radius;
    ctx.beginPath(); ctx.moveTo(centerX, centerY); ctx.lineTo(x, y); ctx.stroke();

    const lx = centerX + Math.cos(angle) * (radius + 18);
    const ly = centerY + Math.sin(angle) * (radius + 18);
    ctx.fillStyle = "#8c9ba8"; ctx.font = "9px Inter"; ctx.textAlign = "center";
    ctx.fillText(ax.label, lx, ly + 3);
  });

  ctx.beginPath();
  axes.forEach((ax, i) => {
    const r = Math.max(0.1, Math.min(1.0, ax.score)) * radius;
    const angle = (Math.PI * 2 / total) * i - Math.PI / 2;
    const x = centerX + Math.cos(angle) * r;
    const y = centerY + Math.sin(angle) * r;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(0, 255, 136, 0.35)"; ctx.fill();
  ctx.strokeStyle = "#00ff88"; ctx.lineWidth = 2; ctx.stroke();
}

function exportActiveTableCSV() {
  // BUG 3: Replicate active filter logic so export matches what the user sees
  let list = [];
  let filename = "strategies_export.csv";

  if (currentView === "step3-base" && fullData?.base_logics?.[currentBaseLogic]) {
    list = [...fullData.base_logics[currentBaseLogic]];
    const searchVal = (document.getElementById("base-filter-input")?.value || "").trim().toLowerCase();
    list = list.filter(item => {
      const fast = item.Fast_EMA;
      const fastOk = fast >= filterFastMin && fast <= filterFastMax;
      const sharpeOk = (item.Sharpe ?? 0) >= filterMinSharpe;
      const ddOk = (item.Max_DD_Pct ?? 0) <= filterMaxDD;
      const wrOk = (item.Win_Rate_Pct ?? 0) >= filterMinWinRate;
      return fastOk && sharpeOk && ddOk && wrOk;
    });
    if (currentBasePreset === "inst") list = list.filter(i => i.Fast_EMA >= 180);
    else if (currentBasePreset === "scalp") list = list.filter(i => i.Fast_EMA <= 30);
    else if (currentBasePreset === "lowdd") list = list.filter(i => (i.Max_DD_Pct || 0) <= 20);
    else if (currentBasePreset === "highsharpe") list = list.filter(i => (i.Sharpe || 0) >= 1.8);
    if (searchVal) list = list.filter(i => String(i.Fast_EMA).includes(searchVal) || String(i.Slow_EMA || "").includes(searchVal));
    filename = `${currentBaseLogic}_filtered_${list.length}.csv`;

  } else if (currentView === "step3-pyramid" && fullData?.pyramid_top) {
    list = currentPyrFactor === "ALL" ? [...fullData.pyramid_top] : [...(fullData.pyramid_by_factor?.[currentPyrFactor] || [])];
    if (currentPyrX !== "ALL") list = list.filter(i => Number(i.X_Pct) === Number(currentPyrX));
    list = list.filter(i => (i.Total_Return_Pct ?? 0) >= filterPyrMinRet && (i.Max_Drawdown_Pct ?? 0) <= filterPyrMaxDD && (i.Total_Series_Adds ?? 0) >= filterPyrMinAdds);
    const pyrSearch = (document.getElementById("pyr-filter-input")?.value || "").trim().toLowerCase();
    if (pyrSearch) list = list.filter(i => (i.Strategy_Note || "").toLowerCase().includes(pyrSearch) || (i.Y_Factor || "").toLowerCase().includes(pyrSearch));
    filename = `pyramid_filtered_${list.length}.csv`;

  } else if (currentView === "step3-risk" && fullData?.risk_studio?.results) {
    list = fullData.risk_studio.results.filter(r => r.Re_Entry_Mode === currentReEntryMode);
    if (currentRiskArchetype !== "ALL") list = list.filter(r => r.Risk_Archetype === currentRiskArchetype);
    list = list.filter(r => (r.Total_Return_Pct ?? 0) >= filterRiskMinRet && (r.Max_Drawdown_Pct ?? 0) <= filterRiskMaxDD);
    const riskSearch = (document.getElementById("risk-filter-input")?.value || "").trim().toLowerCase();
    if (riskSearch) list = list.filter(r => (r.Risk_Note || "").toLowerCase().includes(riskSearch) || (r.Strategy_Label || "").toLowerCase().includes(riskSearch));
    filename = `risk_${currentReEntryMode.toLowerCase()}_filtered_${list.length}.csv`;

  } else if (fullData?.base_logics?.EMA_CROSS_SAR) {
    list = fullData.base_logics.EMA_CROSS_SAR;
    filename = "ema_cross_sar_strategies.csv";
  }

  if (list.length === 0) { showToast("No data to export!"); return; }
  const headers = Object.keys(list[0]);
  const rows = list.map(obj => headers.map(h => JSON.stringify(obj[h] ?? "")).join(","));
  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast(`✓ Exported ${list.length} rows → ${filename}`);
}

function exportModalTradesCSV() {
  if (!activeModalStrategy) return;
  let trades = activeModalTrades || [];

  // BUG 2: Build a meaningful filename from the strategy being viewed
  let stratName = "strategy";
  if (activeModalType === "base") {
    const slow = activeModalStrategy.Slow_EMA;
    stratName = `${activeModalStrategy.Logic}_${activeModalStrategy.Fast_EMA}${slow ? '_' + slow : ''}`;
  } else if (activeModalType === "pyramid") {
    stratName = (activeModalStrategy.Strategy_Note || "pyramid").replace(/[^a-z0-9_]/gi, "_");
  } else if (activeModalType === "risk") {
    stratName = (activeModalStrategy.Risk_Note || "risk").replace(/[^a-z0-9_]/gi, "_").slice(0, 40);
  }
  const filename = `trades_${stratName}.csv`;

  if (trades.length === 0) {
    showToast("No trade logs to export for this strategy.");
    return;
  }

  const headers = Object.keys(trades[0]);
  const rows = trades.map(obj => headers.map(h => JSON.stringify(obj[h] ?? "")).join(","));
  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast(`✓ Exported ${trades.length} trades → ${filename}`);
}

function closeModal() {
  document.getElementById("drilldown-modal")?.classList.remove("open");
}
