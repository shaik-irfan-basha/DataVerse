/**
 * frontend/js/app.js - Main Application Controller & Event Coordinator
 */

import { api } from './api.js';
import { state } from './state.js';
import { ui } from './ui.js';

// =============================================================================
// PWA Installation & Service Worker Setup
// =============================================================================

let deferredInstallPrompt = null;

function setupPWA() {
  if ('serviceWorker' in navigator) {
    const hadController = Boolean(navigator.serviceWorker.controller);
    let isRefreshing = false;

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (hadController && !isRefreshing) {
        isRefreshing = true;
        console.log('[PWA] Service Worker controller updated. Seamlessly reloading latest app shell...');
        window.location.reload();
      }
    });

    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
        .then((reg) => {
          console.log('[PWA] Service Worker registered:', reg.scope);

          // Actively check for service worker updates
          reg.update().catch(() => {});

          // Listen for true worker updates
          reg.addEventListener('updatefound', () => {
            const newWorker = reg.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  console.log('[PWA] New version installed and ready.');
                }
              });
            }
          });
        })
        .catch((err) => {
          console.warn('[PWA] Service Worker registration failed:', err);
        });
    });
  }

  const installBtn = document.getElementById('btn-install-pwa');
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    if (installBtn) {
      installBtn.style.display = 'inline-flex';
    }
  });

  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      if (!deferredInstallPrompt) return;
      deferredInstallPrompt.prompt();
      const choice = await deferredInstallPrompt.userChoice;
      if (choice.outcome === 'accepted') {
        ui.showToast('DataVerse installed successfully!', 'success');
      }
      deferredInstallPrompt = null;
      installBtn.style.display = 'none';
    });
  }

  window.addEventListener('appinstalled', () => {
    deferredInstallPrompt = null;
    if (installBtn) installBtn.style.display = 'none';
    ui.showToast('DataVerse app installed!', 'success');
  });
}

// =============================================================================
// DOM Selectors
// =============================================================================

const elements = {
  mobileMenuBtn: document.getElementById('btn-mobile-menu'),
  sidebar: document.getElementById('sidebar'),
  sidebarBackdrop: document.getElementById('sidebar-backdrop'),
  fileInput: document.getElementById('file-input'),
  uploadDropzone: document.getElementById('upload-dropzone'),
  btnBrowseFile: document.getElementById('btn-browse-file'),
  datasetInfo: document.getElementById('dataset-info'),
  loadedFilename: document.getElementById('loaded-filename'),
  loadedFiletype: document.getElementById('loaded-filetype'),
  loadedStats: document.getElementById('loaded-stats'),
  tablesCount: document.getElementById('tables-count'),
  sidebarTables: document.getElementById('sidebar-tables'),
  queryInput: document.getElementById('query-input'),
  queryCharCount: document.getElementById('query-char-count'),
  suggestionsBar: document.getElementById('suggestions-bar'),
  btnClearQuery: document.getElementById('btn-clear-query'),
  btnRunQuery: document.getElementById('btn-run-query'),
  btnRunSpinner: document.getElementById('btn-run-spinner'),
  btnRunIcon: document.getElementById('btn-run-icon'),
  btnRunText: document.getElementById('btn-run-text'),
  sqlEditor: document.getElementById('sql-editor'),
  sqlExecutionStatus: document.getElementById('sql-execution-status'),
  btnSaveSql: document.getElementById('btn-save-sql'),
  btnCopySql: document.getElementById('btn-copy-sql'),
  btnRunSql: document.getElementById('btn-run-sql'),
  sqlErrorBanner: document.getElementById('sql-error-banner'),
  resultsMeta: document.getElementById('results-meta'),
  btnExportCsv: document.getElementById('btn-export-csv'),
  btnExportExcel: document.getElementById('btn-export-excel'),
  btnExportJson: document.getElementById('btn-export-json'),
  tabTable: document.getElementById('tab-table'),
  tabChart: document.getElementById('tab-chart'),
  tabProfile: document.getElementById('tab-profile'),
  viewTable: document.getElementById('view-table'),
  viewChart: document.getElementById('view-chart'),
  viewProfile: document.getElementById('view-profile'),
  btnOpenHistory: document.getElementById('btn-open-history'),
  historyModal: document.getElementById('history-modal'),
  historyList: document.getElementById('history-list'),
  historyCountBadge: document.getElementById('history-count-badge'),
  historySearchInput: document.getElementById('history-search-input'),
  btnClearHistorySearch: document.getElementById('btn-clear-history-search'),
  btnCloseHistory: document.getElementById('btn-close-history'),
  btnCloseHistoryAction: document.getElementById('btn-close-history-action'),
  btnClearHistoryConfirm: document.getElementById('btn-clear-history-confirm'),
  inpageClarificationCard: document.getElementById('inpage-clarification-card'),
  sqlClarificationTag: document.getElementById('sql-clarification-tag'),
  // BYOK Settings Elements
  btnOpenSettings: document.getElementById('btn-open-settings'),
  settingsModal: document.getElementById('settings-modal'),
  btnCloseSettings: document.getElementById('btn-close-settings'),
  settingsProviderSelect: document.getElementById('settings-provider-select'),
  settingsModelSelect: document.getElementById('settings-model-select'),
  settingsApiKeyInput: document.getElementById('settings-api-key-input'),
  btnToggleKeyVisibility: document.getElementById('btn-toggle-key-visibility'),
  iconEyeShow: document.getElementById('icon-eye-show'),
  iconEyeHide: document.getElementById('icon-eye-hide'),
  settingsKeyStatus: document.getElementById('settings-key-status'),
  settingsTestResult: document.getElementById('settings-test-result'),
  btnTestConnection: document.getElementById('btn-test-connection'),
  btnTestSpinner: document.getElementById('btn-test-spinner'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  btnRemoveKey: document.getElementById('btn-remove-key'),
  navKeyBadge: document.getElementById('nav-key-badge'),

  // Documentation Modal Elements
  btnOpenDocs: document.getElementById('btn-open-docs'),
  docsModal: document.getElementById('docs-modal'),
  btnCloseDocs: document.getElementById('btn-close-docs'),
  btnDoneDocs: document.getElementById('btn-done-docs')
};

// =============================================================================
// Application State Subscription & UI Synchronization
// =============================================================================

function syncInsightsTab() {
  ui.renderInsightsStudio({
    dataset: state.dataset,
    profileData: state.profile.data,
    chartData: state.chart,
    results: state.results,
    onNavigateView: (action, param) => {
      if (action === 'query') {
        state.setStudioTab('sql-lab');
        if (elements.queryInput) {
          elements.queryInput.value = param;
          updateCharCount();
          executeNaturalLanguageQuery(param);
        }
      }
    }
  });
}

window.dataverseApp = {
  goToSqlLab: (sql) => {
    state.setStudioTab('sql-lab');
    if (sql && elements.sqlEditor) {
      elements.sqlEditor.value = sql;
    }
    state.setActiveView('table');
  }
};

function setupStateSubscriptions() {
  state.subscribe((event, data) => {
    switch (event) {
      case 'studio:tab-changed':
        ui.switchStudioTab(data);
        if (data === 'insights') {
          syncInsightsTab();
        } else if (data === 'schema') {
          loadAndSyncSchemaStudio();
        }
        break;

      case 'schema-visualizer:updated':
      case 'schema-visualizer:selection-changed':
      case 'schema-visualizer:relationship-updated':
        renderSchemaStudioUI();
        {
          const relPane = document.getElementById('pane-inspector-relationships');
          if (relPane && relPane.style.display !== 'none') {
            switchInspectorTab('relationships');
          }
        }
        break;

      case 'schema-visualizer:view-transformed':
        ui.applySchemaTransform(data.zoom, data.pan.x, data.pan.y);
        break;

      case 'conversation:updated':
        ui.renderConversationStream(data.messages, {
          onSelectOption: (choice) => submitClarificationResponse(choice),
          onExecuteSql: (sql) => executeSqlDirect(sql),
          onCopySql: (sql) => copySqlToClipboard(sql),
          onPromptClick: (prompt) => {
            elements.queryInput.value = prompt;
            updateCharCount();
            executeNaturalLanguageQuery(prompt);
          },
          onApplyCleaning: () => handleApplyCleaning(),
          onCancelCleaning: () => handleCancelCleaning(),
          onUndoCleaning: () => handleUndoCleaning(),
          onRevertOriginal: () => handleRevertOriginal()
        });
        break;

      case 'conversation:intent-updated':
        ui.renderIntentSummary(data);
        break;

      case 'conversation:cleared':
        ui.renderConversationStream([], {
          onPromptClick: (prompt) => {
            elements.queryInput.value = prompt;
            updateCharCount();
            executeNaturalLanguageQuery(prompt);
          }
        });
        ui.renderIntentSummary(state.conversation.intentSummary);
        break;

      case 'dataset:loaded':
        updateDatasetUI(data);
        syncInsightsTab();
        break;

      case 'schema:updated':
        updateSchemaUI(data);
        syncInsightsTab();
        break;

      case 'suggestions:updated':
        ui.renderSuggestions(data, (selectedQuestion) => {
          elements.queryInput.value = selectedQuestion;
          updateCharCount();
          executeNaturalLanguageQuery(selectedQuestion);
        });
        break;

      case 'query:success':
        updateQuerySuccessUI(data);
        syncInsightsTab();
        break;

      case 'query:error':
        updateQueryErrorUI(data);
        break;

      case 'query:clarification':
        handleClarificationRequired(data);
        break;

      case 'query:cleaning_preview':
        handleCleaningPreviewUI(data);
        break;

      case 'chart:updated':
        renderCurrentChart();
        syncInsightsTab();
        break;

      case 'chart:loading':
        ui.renderChart(null, { isLoading: true });
        break;

      case 'chart:error':
        ui.renderChart(null, {
          error: data.error,
          onRefresh: () => generateChartFromCurrentResults('auto')
        });
        break;

      case 'chart:cleared':
        ui.renderChart(null);
        break;

      case 'profile:updated':
        renderCurrentProfile();
        syncInsightsTab();
        break;

      case 'profile:loading':
        ui.renderProfile(null, { isLoading: true, activeTable: data.table });
        break;

      case 'profile:error':
        ui.renderProfile(null, {
          error: data.error,
          activeTable: data.table,
          onRetry: () => loadTableProfile(data.table)
        });
        break;

      case 'profile:cleared':
        ui.renderProfile(null);
        break;

      case 'view:changed':
        switchActiveView(data);
        break;
    }
  });
}

function updateDatasetUI(dataset) {
  if (elements.datasetInfo) {
    elements.datasetInfo.style.display = 'block';
    elements.loadedFilename.textContent = dataset.filename;
    elements.loadedFilename.title = dataset.filename;
    elements.loadedFiletype.textContent = dataset.fileType.toUpperCase();
    elements.loadedStats.textContent = `${dataset.tables.length} table(s) ready for querying`;
  }
  if (elements.tablesCount) {
    elements.tablesCount.style.display = 'inline-flex';
    elements.tablesCount.textContent = dataset.tables.length;
  }
  const headerDatasetPill = document.getElementById('header-dataset-pill');
  const headerDatasetName = document.getElementById('header-dataset-name');
  if (headerDatasetPill && headerDatasetName) {
    headerDatasetPill.classList.add('active');
    headerDatasetName.textContent = `${dataset.filename} (${dataset.tables.length} table${dataset.tables.length > 1 ? 's' : ''})`;
  }
  const ceContextPill = document.getElementById('ce-context-pill');
  const ceContextText = document.getElementById('ce-context-text');
  if (ceContextPill && ceContextText) {
    ceContextPill.classList.add('active');
    ceContextText.textContent = `${dataset.filename} (${dataset.tables.length} table${dataset.tables.length > 1 ? 's' : ''})`;
  }
  ui.renderTableList(dataset.tables, state.profile.table, (tableName) => {
    loadTableProfile(tableName);
  });
  ui.renderSuggestions(dataset.suggestions, (q) => {
    elements.queryInput.value = q;
    updateCharCount();
    executeNaturalLanguageQuery(q);
  });
  ui.renderSchemaHints(dataset.tables, dataset.schemaOverview, (colName) => {
    const ceInput = document.getElementById('ce-followup-input');
    if (ceInput) {
      const cur = ceInput.value.trim();
      ceInput.value = cur ? `${cur} ${colName}` : colName;
      ceInput.focus();
    }
  });
}

function updateSchemaUI(dataset) {
  if (elements.tablesCount) {
    elements.tablesCount.textContent = dataset.tables.length;
    elements.tablesCount.style.display = dataset.tables.length > 0 ? 'inline-flex' : 'none';
  }
  ui.renderTableList(dataset.tables, state.profile.table, (tableName) => {
    loadTableProfile(tableName);
  });
  ui.renderSchemaHints(dataset.tables, dataset.schemaOverview, (colName) => {
    const ceInput = document.getElementById('ce-followup-input');
    if (ceInput) {
      const cur = ceInput.value.trim();
      ceInput.value = cur ? `${cur} ${colName}` : colName;
      ceInput.focus();
    }
  });
  const headerDatasetPill = document.getElementById('header-dataset-pill');
  const headerDatasetName = document.getElementById('header-dataset-name');
  if (headerDatasetPill && headerDatasetName && dataset.is_loaded) {
    headerDatasetPill.classList.add('active');
    headerDatasetName.textContent = `${dataset.filename || 'Active Dataset'} (${dataset.tables.length} table${dataset.tables.length > 1 ? 's' : ''})`;
  }
  const ceContextPill = document.getElementById('ce-context-pill');
  const ceContextText = document.getElementById('ce-context-text');
  if (ceContextPill && ceContextText && dataset.is_loaded) {
    ceContextPill.classList.add('active');
    ceContextText.textContent = `${dataset.filename || 'Active Dataset'} (${dataset.tables.length} table${dataset.tables.length > 1 ? 's' : ''})`;
  }
  ui.renderTableList(dataset.tables, state.profile.table, (tableName) => {
    loadTableProfile(tableName);
  });
}

function updateQuerySuccessUI({ query, results }) {
  setQueryLoading(false);
  ui.hideInPageClarification();
  ui.hideClarificationModal();
  elements.sqlEditor.value = query.sql;
  elements.sqlExecutionStatus.textContent = 'Success';
  elements.sqlExecutionStatus.className = 'badge badge-green';
  elements.sqlErrorBanner.style.display = 'none';

  // Display clarification tag if query was resolved through clarification
  if (elements.sqlClarificationTag) {
    if (query.clarificationInterpretation) {
      elements.sqlClarificationTag.style.display = 'inline-flex';
      elements.sqlClarificationTag.textContent = `✦ Clarified: "${query.clarificationInterpretation}"`;
      elements.sqlClarificationTag.title = query.clarificationHistory || `Interpreted as: ${query.clarificationInterpretation}`;
    } else {
      elements.sqlClarificationTag.style.display = 'none';
    }
  }

  elements.resultsMeta.textContent = `${results.rowCount} rows • ${Number(results.executionTime).toFixed(3)}s`;

  ui.renderResultsTable(
    results.columns,
    results.rows,
    results.currentPage,
    results.rowsPerPage,
    results.sortColumn,
    results.sortDirection,
    (colIdx) => {
      // Toggle sort
      if (state.results.sortColumn === colIdx) {
        state.results.sortDirection = state.results.sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        state.results.sortColumn = colIdx;
        state.results.sortDirection = 'asc';
      }
      ui.renderResultsTable(
        state.results.columns,
        state.results.rows,
        state.results.currentPage,
        state.results.rowsPerPage,
        state.results.sortColumn,
        state.results.sortDirection,
        (idx) => handleTableSort(idx)
      );
      bindPaginationButtons();
    }
  );
  bindPaginationButtons();

  // If results exist, auto-request chart visualization in the background
  if (results.rows && results.rows.length > 0) {
    generateChartFromCurrentResults('auto');
  }

  ui.showToast(`Query completed in ${Number(results.executionTime).toFixed(3)}s (${results.rowCount} rows)`, 'success');
}

function handleTableSort(colIdx) {
  if (state.results.sortColumn === colIdx) {
    state.results.sortDirection = state.results.sortDirection === 'asc' ? 'desc' : 'asc';
  } else {
    state.results.sortColumn = colIdx;
    state.results.sortDirection = 'asc';
  }
  ui.renderResultsTable(
    state.results.columns,
    state.results.rows,
    state.results.currentPage,
    state.results.rowsPerPage,
    state.results.sortColumn,
    state.results.sortDirection,
    (idx) => handleTableSort(idx)
  );
  bindPaginationButtons();
}

function bindPaginationButtons() {
  const btnPrev = document.getElementById('btn-prev-page');
  const btnNext = document.getElementById('btn-next-page');

  if (btnPrev) {
    btnPrev.onclick = () => {
      if (state.results.currentPage > 1) {
        state.results.currentPage -= 1;
        ui.renderResultsTable(
          state.results.columns,
          state.results.rows,
          state.results.currentPage,
          state.results.rowsPerPage,
          state.results.sortColumn,
          state.results.sortDirection,
          (idx) => handleTableSort(idx)
        );
        bindPaginationButtons();
      }
    };
  }

  if (btnNext) {
    const totalPages = Math.ceil(state.results.rows.length / state.results.rowsPerPage) || 1;
    btnNext.onclick = () => {
      if (state.results.currentPage < totalPages) {
        state.results.currentPage += 1;
        ui.renderResultsTable(
          state.results.columns,
          state.results.rows,
          state.results.currentPage,
          state.results.rowsPerPage,
          state.results.sortColumn,
          state.results.sortDirection,
          (idx) => handleTableSort(idx)
        );
        bindPaginationButtons();
      }
    };
  }
}

function updateQueryErrorUI({ error, sql }) {
  setQueryLoading(false);
  if (sql) elements.sqlEditor.value = sql;
  elements.sqlExecutionStatus.textContent = 'Error';
  elements.sqlExecutionStatus.className = 'badge badge-error';
  elements.sqlErrorBanner.style.display = 'block';
  elements.sqlErrorBanner.textContent = error;
  ui.showToast(`Error: ${error}`, 'error', 5000);
}

function handleClarificationRequired(data) {
  setQueryLoading(false);
  ui.setConversationAnalyzing(false);

  // Surface notification pulse dot on Clarification Engine nav tab
  const dot = document.getElementById('nav-clarification-dot');
  if (dot) dot.style.display = 'block';

  const originalQuestion = (
    data.original_question ||
    state.query.question ||
    (elements.queryInput ? elements.queryInput.value : '') ||
    ''
  ).trim();
  const clarificationQuestion = data.clarification_question || data.question || '';
  const options = data.clarification_options || data.options || [];
  const priorHistory = data.prior_history || '';

  // Update status badge to indicate clarification is awaiting user response
  if (elements.sqlExecutionStatus) {
    elements.sqlExecutionStatus.textContent = 'Awaiting Clarification';
    elements.sqlExecutionStatus.className = 'badge badge-amber';
  }
  if (elements.sqlClarificationTag) {
    elements.sqlClarificationTag.style.display = 'none';
  }

  // Seamlessly transition user into the dedicated Clarification Engine workspace
  state.setStudioTab('clarification');

  const handleSelection = (chosenOption) => {
    submitClarificationResponse(chosenOption);
  };

  const reasoning = data.reasoning || '';

  const handleEditQuestion = () => {
    ui.hideInPageClarification();
    ui.hideClarificationModal();
    if (elements.queryInput) {
      elements.queryInput.focus();
      elements.queryInput.select();
      elements.queryInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (elements.sqlExecutionStatus) {
      elements.sqlExecutionStatus.textContent = 'Ready';
      elements.sqlExecutionStatus.className = 'badge badge-cyan';
    }
    ui.showToast('You can now edit your original question.', 'info');
  };

  const handleCancel = () => {
    ui.hideInPageClarification();
    ui.hideClarificationModal();
    if (dot) dot.style.display = 'none';
    if (elements.sqlExecutionStatus) {
      elements.sqlExecutionStatus.textContent = 'Ready';
      elements.sqlExecutionStatus.className = 'badge badge-cyan';
    }
    ui.showToast('Query clarification cancelled.', 'warning');
  };

  ui.renderInPageClarification(
    clarificationQuestion,
    options,
    reasoning,
    handleSelection,
    handleEditQuestion,
    handleCancel
  );
}

async function submitClarificationResponse(chosenOption) {
  const originalQuestion = (
    state.query.question ||
    state.conversation.intentSummary.originalQuestion ||
    (elements.queryInput ? elements.queryInput.value : '') ||
    ''
  ).trim();
  const clarificationQuestion = state.query.clarification ?
    (state.query.clarification.clarification_question || state.query.clarification.question || '') : '';
  const priorHistory = state.conversation.dialogueHistory ||
    (state.query.clarification ? state.query.clarification.prior_history : '') || '';

  ui.showToast(`Refining query with: "${chosenOption}"...`, 'info');
  setQueryLoading(true);
  ui.setConversationAnalyzing(true);
  ui.hideInPageClarification();
  ui.hideClarificationModal();

  const dot = document.getElementById('nav-clarification-dot');
  if (dot) dot.style.display = 'none';

  // Record user selection in persistent conversation
  state.addConversationMessage({
    sender: 'user',
    text: chosenOption,
    type: 'user_response'
  });

  try {
    const res = await api.submitClarification(
      originalQuestion,
      clarificationQuestion,
      chosenOption,
      priorHistory
    );
    ui.setConversationAnalyzing(false);
    const priorBlock = priorHistory ? `${priorHistory.trim()}\n\n` : '';
    const nextHistory = `${priorBlock}AI: ${clarificationQuestion}\nUser: ${chosenOption}\n\n`;
    handleQueryResponse(res, originalQuestion, nextHistory);
  } catch (err) {
    ui.setConversationAnalyzing(false);
    state.setQueryError(err.message);
  }
}

function handleCleaningPreviewUI(data) {
  setQueryLoading(false);
  ui.setConversationAnalyzing(false);
  const dot = document.getElementById('nav-clarification-dot');
  if (dot) dot.style.display = 'block';
  state.setStudioTab('clarification');
  ui.showToast('Data cleaning proposal ready for review.', 'info');
}

async function handleApplyCleaning() {
  ui.showToast('Applying dataset transformation...', 'info');
  setQueryLoading(true);
  ui.setConversationAnalyzing(true);
  try {
    const res = await api.applyCleaning();
    ui.setConversationAnalyzing(false);
    setQueryLoading(false);
    if (res.success) {
      ui.showToast(res.message || 'Transformation applied successfully.', 'success');
      state.addConversationMessage({
        sender: 'assistant',
        text: res.message || `Transformation applied successfully. Dataset now has ${res.rows_current} rows and ${res.columns_current} columns.`,
        type: 'cleaning_applied',
        appliedInfo: res
      });
      // Refresh schema & table list
      const schema = await api.getSchema();
      state.setSchema(schema);
      // Reload active table profile or data
      const activeTable = state.profile.table || (schema.tables && schema.tables[0]);
      if (activeTable) {
        loadTableProfile(activeTable);
        executeSqlDirect(`SELECT * FROM "${activeTable}" LIMIT 50`);
      }
    }
  } catch (err) {
    ui.setConversationAnalyzing(false);
    setQueryLoading(false);
    ui.showToast(`Failed to apply transformation: ${err.message}`, 'error');
  }
}

async function handleCancelCleaning() {
  try {
    const res = await api.cancelCleaning();
    ui.showToast(res.message || 'Transformation proposal cancelled. Dataset unchanged.', 'info');
    state.addConversationMessage({
      sender: 'assistant',
      text: res.message || 'Transformation proposal cancelled. No changes were made to your dataset.',
      type: 'cleaning_cancelled'
    });
  } catch (err) {
    ui.showToast(`Error cancelling: ${err.message}`, 'error');
  }
}

async function handleUndoCleaning() {
  ui.showToast('Undoing transformation...', 'info');
  try {
    const res = await api.undoCleaning();
    if (res.success) {
      ui.showToast(res.message || 'Transformation undone successfully.', 'success');
      state.addConversationMessage({
        sender: 'assistant',
        text: res.message || `Undid transformation. Dataset restored to ${res.rows_restored} rows.`,
        type: 'cleaning_undo'
      });
      const schema = await api.getSchema();
      state.setSchema(schema);
      const activeTable = state.profile.table || (schema.tables && schema.tables[0]);
      if (activeTable) {
        loadTableProfile(activeTable);
        executeSqlDirect(`SELECT * FROM "${activeTable}" LIMIT 50`);
      }
    }
  } catch (err) {
    ui.showToast(`Failed to undo transformation: ${err.message}`, 'error');
  }
}

async function handleRevertOriginal() {
  ui.showToast('Reverting dataset to original upload snapshot...', 'info');
  try {
    const res = await api.revertOriginalCleaning();
    if (res.success) {
      ui.showToast(res.message || 'Dataset reverted to original snapshot!', 'success');
      state.addConversationMessage({
        sender: 'assistant',
        text: res.message || 'Dataset successfully reverted to initial upload snapshot.',
        type: 'cleaning_undo'
      });
      const schema = await api.getSchema();
      state.setSchema(schema);
      const activeTable = state.profile.table || (schema.tables && schema.tables[0]);
      if (activeTable) {
        loadTableProfile(activeTable);
        executeSqlDirect(`SELECT * FROM "${activeTable}" LIMIT 50`);
      }
    }
  } catch (err) {
    ui.showToast(`Failed to revert: ${err.message}`, 'error');
  }
}


async function executeSqlDirect(sql) {
  if (!sql) return;
  ui.showToast('Executing SQL query...', 'info');
  elements.sqlEditor.value = sql;
  try {
    const res = await api.executeManualSql(sql);
    state.setManualSqlResult(res, sql);
    if (res.success) {
      ui.showToast(`Executed successfully (${res.row_count} rows in ${Number(res.execution_time).toFixed(3)}s)`, 'success');
      elements.resultsMeta.textContent = `${res.row_count} rows • ${Number(res.execution_time).toFixed(3)}s`;
      ui.renderResultsTable(
        res.columns,
        res.rows,
        1,
        state.results.rowsPerPage,
        null,
        'asc',
        (idx) => handleTableSort(idx)
      );
      bindPaginationButtons();
      if (res.rows && res.rows.length > 0) {
        generateChartFromCurrentResults('auto');
      }
    }
  } catch (err) {
    state.setQueryError(err.message, sql);
  }
}

function copySqlToClipboard(sql) {
  if (!sql) return;
  navigator.clipboard.writeText(sql)
    .then(() => ui.showToast('SQL copied to clipboard!', 'success'))
    .catch(() => ui.showToast('Could not copy SQL', 'error'));
}

function setQueryLoading(isLoading) {
  if (elements.btnRunSpinner) elements.btnRunSpinner.style.display = isLoading ? 'inline-block' : 'none';
  if (elements.btnRunIcon) elements.btnRunIcon.style.display = isLoading ? 'none' : 'inline-block';
  if (elements.btnRunText) elements.btnRunText.textContent = isLoading ? 'Processing...' : 'Generate & Run SQL';
  if (elements.btnRunQuery) elements.btnRunQuery.disabled = isLoading;
}

// =============================================================================
// View Tabs Management
// =============================================================================

function setupViewTabs() {
  const tabs = [
    { btn: elements.tabTable, view: 'table' },
    { btn: elements.tabChart, view: 'chart' },
    { btn: elements.tabProfile, view: 'profile' }
  ];

  tabs.forEach(({ btn, view }) => {
    if (!btn) return;
    btn.addEventListener('click', () => {
      state.setActiveView(view);
    });
  });
}

function renderCurrentChart() {
  ui.renderChart(state.chart, {
    activeType: state.chart.chart_type || state.chart.chartType || 'auto',
    isLoading: state.chart.isLoading,
    error: state.chart.error,
    onSelectType: (newType) => {
      generateChartFromCurrentResults(newType);
    },
    onRefresh: () => {
      generateChartFromCurrentResults(state.chart.chart_type || state.chart.chartType || 'auto');
    }
  });
}

let currentChartRequestId = 0;

async function generateChartFromCurrentResults(chartType = 'auto') {
  const { columns, rows } = state.results;
  if (!columns || columns.length === 0 || !rows || rows.length === 0) {
    ui.renderChart(null);
    return;
  }

  const reqId = ++currentChartRequestId;
  state.setChartLoading(chartType);
  try {
    const chartData = await api.generateChart(columns, rows, chartType, state.query.question || '');
    if (reqId !== currentChartRequestId) {
      console.warn(`[Chart] Stale chart response ignored (req ${reqId} vs ${currentChartRequestId})`);
      return;
    }
    state.setChart(chartData, state.query.sql || state.query.question || '');
  } catch (err) {
    if (reqId !== currentChartRequestId) return;
    console.error("Chart generation error:", err);
    state.setChartError(err.message || "Failed to generate chart visualization.");
  }
}

function renderCurrentProfile() {
  ui.renderProfile(state.profile.data, {
    activeTable: state.profile.table,
    availableTables: state.dataset.tables || [],
    isLoading: state.profile.isLoading,
    error: state.profile.error,
    onSelectTable: (tbl) => {
      loadTableProfile(tbl);
    },
    onRetry: () => {
      if (state.profile.table) loadTableProfile(state.profile.table);
    }
  });
}

function switchActiveView(viewName) {
  // Update Tab buttons
  [elements.tabTable, elements.tabChart, elements.tabProfile].forEach((btn) => {
    if (!btn) return;
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });

  // Toggle View Panels
  if (elements.viewTable) elements.viewTable.style.display = viewName === 'table' ? 'flex' : 'none';
  if (elements.viewChart) elements.viewChart.style.display = viewName === 'chart' ? 'flex' : 'none';
  if (elements.viewProfile) elements.viewProfile.style.display = viewName === 'profile' ? 'flex' : 'none';

  if (viewName === 'chart') {
    if (state.results.rows && state.results.rows.length > 0) {
      if (state.chart.base64_image || state.chart.base64Image) {
        renderCurrentChart();
      } else if (state.chart.isLoading) {
        ui.renderChart(null, { isLoading: true });
      } else if (state.chart.error) {
        ui.renderChart(null, { error: state.chart.error, onRefresh: () => generateChartFromCurrentResults('auto') });
      } else {
        generateChartFromCurrentResults('auto');
      }
    } else {
      ui.renderChart(null);
    }
  } else if (viewName === 'profile') {
    if (state.profile.data) {
      renderCurrentProfile();
    } else if (state.profile.isLoading) {
      ui.renderProfile(null, { isLoading: true, activeTable: state.profile.table });
    } else if (state.profile.error) {
      ui.renderProfile(null, { error: state.profile.error, activeTable: state.profile.table, onRetry: () => loadTableProfile(state.profile.table) });
    } else if (state.dataset.tables && state.dataset.tables.length > 0) {
      loadTableProfile(state.dataset.tables[0]);
    } else {
      ui.renderProfile(null);
    }
  }
}

// =============================================================================
// User Action Handlers
// =============================================================================

async function handleFileUpload(file) {
  if (!file) return;

  const validExts = ['.csv', '.xlsx', '.xls', '.sqlite', '.db'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    ui.showToast(`Unsupported file type: ${ext}. Please upload CSV, Excel, or SQLite.`, 'error');
    return;
  }

  ui.showToast(`Uploading and profiling ${file.name}...`, 'info', 4000);
  try {
    const uploadRes = await api.uploadDataset(file);
    state.setDataset(uploadRes);
    ui.showToast(`Successfully loaded ${uploadRes.filename} (${uploadRes.tables_created.length} table(s))`, 'success');
  } catch (err) {
    console.error("Upload error:", err);
    ui.showToast(`Upload failed: ${err.message}`, 'error', 5000);
  }
}

async function executeNaturalLanguageQuery(questionText, priorHistory = '') {
  const question = (questionText || (elements.queryInput ? elements.queryInput.value : '') || '').trim();
  if (!question) {
    ui.showToast('Please type a natural language question or select a suggestion.', 'warning');
    if (elements.queryInput) elements.queryInput.focus();
    return;
  }

  ui.hideInPageClarification();
  ui.hideClarificationModal();
  if (elements.sqlClarificationTag) elements.sqlClarificationTag.style.display = 'none';

  state.setQueryStarting(question);
  setQueryLoading(true);
  ui.setConversationAnalyzing(true);
  if (elements.sqlExecutionStatus) {
    elements.sqlExecutionStatus.textContent = 'Generating...';
    elements.sqlExecutionStatus.className = 'badge badge-cyan';
  }
  if (elements.sqlErrorBanner) elements.sqlErrorBanner.style.display = 'none';

  try {
    const historyToSend = priorHistory || state.conversation.dialogueHistory || '';
    const response = await api.submitQuery(question, historyToSend);
    ui.setConversationAnalyzing(false);
    handleQueryResponse(response, question, historyToSend);
  } catch (err) {
    console.error("Query submission error:", err);
    ui.setConversationAnalyzing(false);
    state.setQueryError(err.message);
  }
}

function handleClarificationEngineSend() {
  const inputEl = document.getElementById('ce-followup-input');
  if (!inputEl) return;
  const text = (inputEl.value || '').trim();
  if (!text) return;
  inputEl.value = '';

  if (state.query.clarification && state.query.status === 'clarification') {
    submitClarificationResponse(text);
  } else {
    executeNaturalLanguageQuery(text, state.conversation.dialogueHistory || '');
  }
}

function handleQueryResponse(response, originalQuestion = '', priorHistory = '') {
  const activeQuestion = (
    originalQuestion ||
    state.query.question ||
    response.original_question ||
    (elements.queryInput ? elements.queryInput.value : '') ||
    ''
  ).trim();

  if (response.status === 'SUCCESS') {
    state.setQuerySuccess(response, activeQuestion);
  } else if (response.status === 'CLARIFICATION_REQUIRED') {
    state.setQueryClarification(response, activeQuestion, priorHistory);
  } else if (response.status === 'CLEANING_PREVIEW') {
    state.setCleaningPreview(response, activeQuestion, priorHistory);
  } else if (response.status === 'ERROR') {
    state.setQueryError(response.error_message || response.error || 'Query processing failed.', response.sql);
  } else {
    state.setQueryError('Unexpected response status received.');
  }
}

async function executeManualSql() {
  const sql = (elements.sqlEditor.value || '').trim();
  if (!sql) {
    ui.showToast('Please enter a SQL statement to execute.', 'warning');
    return;
  }

  ui.showToast('Executing SQL query...', 'info');
  try {
    const res = await api.executeManualSql(sql);
    state.setManualSqlResult(res, sql);
    if (res.success) {
      ui.showToast(`Executed successfully (${res.row_count} rows in ${Number(res.execution_time).toFixed(3)}s)`, 'success');
      elements.resultsMeta.textContent = `${res.row_count} rows • ${Number(res.execution_time).toFixed(3)}s`;
      ui.renderResultsTable(
        res.columns,
        res.rows,
        1,
        state.results.rowsPerPage,
        null,
        'asc',
        (idx) => handleTableSort(idx)
      );
      bindPaginationButtons();
      if (res.rows && res.rows.length > 0) {
        generateChartFromCurrentResults('auto');
      }
    }
  } catch (err) {
    console.error("Manual SQL execution error:", err);
    state.setQueryError(err.message, sql);
  }
}

let currentProfileRequestId = 0;

async function loadTableProfile(tableName) {
  if (!tableName) return;
  const reqId = ++currentProfileRequestId;
  state.setProfileLoading(tableName);

  // Update active item highlighting in sidebar
  document.querySelectorAll('#sidebar-tables .table-item').forEach(el => {
    if (el.dataset.table === tableName) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  });

  try {
    const profileData = await api.getTableProfile(tableName);
    if (reqId !== currentProfileRequestId) {
      console.warn(`[Diagnostics] Stale diagnostics response ignored for ${tableName} (req ${reqId} vs ${currentProfileRequestId})`);
      return;
    }
    state.setProfile(tableName, profileData);
  } catch (err) {
    if (reqId !== currentProfileRequestId) return;
    console.error("Profile error:", err);
    state.setProfileError(tableName, err.message || `Could not load diagnostics for ${tableName}`);
    ui.showToast(`Could not load profile: ${err.message}`, 'error');
  }
}

// =============================================================================
// Exporting Results
// =============================================================================

async function exportResults(format) {
  const { columns, rows } = state.results;
  if (!columns || columns.length === 0 || !rows || rows.length === 0) {
    ui.showToast('No query results available to export.', 'warning');
    return;
  }

  ui.showToast(`Exporting ${rows.length} rows as ${format.toUpperCase()}...`, 'info');
  try {
    await api.exportResults(format, columns, rows);
    ui.showToast(`Exported to ${format.toUpperCase()} successfully!`, 'success');
  } catch (err) {
    console.error("Export error:", err);
    ui.showToast(`Export failed: ${err.message}`, 'error');
  }
}

// =============================================================================
// Query History & Saved Queries (Bookmarks) Modal Management
// =============================================================================

let cachedHistoryEntries = [];
let cachedSavedQueries = [];
let currentHistoryFilter = 'all'; // 'all' | 'success' | 'failed' | 'bookmarks'
let currentHistorySearch = '';

function renderHistoryList() {
  if (!elements.historyList) return;

  // 1. Saved Queries / Bookmarks Tab
  if (currentHistoryFilter === 'bookmarks') {
    let filteredBookmarks = [...cachedSavedQueries];
    if (currentHistorySearch) {
      const q = currentHistorySearch.toLowerCase();
      filteredBookmarks = filteredBookmarks.filter((b) => {
        const title = (b.title || '').toLowerCase();
        const question = (b.question || '').toLowerCase();
        const sql = (b.sql_query || '').toLowerCase();
        const dataset = (b.dataset_name || '').toLowerCase();
        const notes = (b.notes || '').toLowerCase();
        return title.includes(q) || question.includes(q) || sql.includes(q) || dataset.includes(q) || notes.includes(q);
      });
    }

    if (elements.historyCountBadge) {
      elements.historyCountBadge.textContent = cachedSavedQueries.length;
    }

    if (cachedSavedQueries.length === 0) {
      elements.historyList.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 36px 16px; font-size: 0.8125rem;">
          <div style="font-size: 24px; color: #00F5FF; margin-bottom: 6px;">★</div>
          <div>No saved queries yet.</div>
          <div style="font-size: 0.72rem; opacity: 0.7; margin-top: 4px;">Click "★ Save" in SQL Lab or history to bookmark your favorite queries.</div>
        </div>
      `;
      return;
    }

    if (filteredBookmarks.length === 0) {
      elements.historyList.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 36px 16px; font-size: 0.8125rem;">
          <div>No saved queries match your search.</div>
        </div>
      `;
      return;
    }

    elements.historyList.innerHTML = filteredBookmarks.map((item, index) => {
      const datasetText = item.dataset_name || 'All Datasets';
      const createdText = item.created_at || '';
      return `
        <div class="history-card" data-bookmark-index="${index}">
          <div class="history-card-header">
            <div class="history-card-title-group">
              <span class="history-card-question">★ ${ui.escapeHtml(item.title)}</span>
              ${item.question ? `<span style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">${ui.escapeHtml(item.question)}</span>` : ''}
              <span class="history-card-dataset">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"></path></svg>
                <span>${ui.escapeHtml(datasetText)}</span>
              </span>
            </div>
            <div class="history-card-status-badges">
              <span class="badge badge-cyan">SAVED</span>
            </div>
          </div>

          <pre class="history-card-sql">${ui.escapeHtml(item.sql_query)}</pre>

          <div class="history-card-footer">
            <div class="history-card-meta">
              ${createdText ? `
                <span class="history-card-meta-item" title="Saved at ${ui.escapeHtml(createdText)}">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                  <span>${ui.escapeHtml(createdText)}</span>
                </span>
              ` : ''}
            </div>

            <div class="history-card-actions">
              <button type="button" class="history-action-btn btn-open-bookmark" title="Load into SQL Lab">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                <span>Open in SQL Lab</span>
              </button>
              <button type="button" class="history-action-btn btn-copy-bookmark-sql" title="Copy SQL statement">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                <span>Copy SQL</span>
              </button>
              <button type="button" class="history-action-btn btn-rerun btn-rerun-bookmark" title="Rerun SQL query">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                <span>Rerun</span>
              </button>
              <button type="button" class="history-action-btn btn-delete-item btn-delete-bookmark" title="Delete Saved Query">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                <span>Delete</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Attach bookmark events
    elements.historyList.querySelectorAll('.history-card').forEach((card) => {
      const idx = parseInt(card.dataset.bookmarkIndex, 10);
      const item = filteredBookmarks[idx];
      if (!item) return;

      const btnOpen = card.querySelector('.btn-open-bookmark');
      if (btnOpen) {
        btnOpen.addEventListener('click', (e) => {
          e.stopPropagation();
          loadHistoryQuery({ question: item.question || item.title, sql_query: item.sql_query });
        });
      }

      const btnCopy = card.querySelector('.btn-copy-bookmark-sql');
      if (btnCopy) {
        btnCopy.addEventListener('click', (e) => {
          e.stopPropagation();
          copyHistorySql(item.sql_query, btnCopy);
        });
      }

      const btnRerun = card.querySelector('.btn-rerun-bookmark');
      if (btnRerun) {
        btnRerun.addEventListener('click', (e) => {
          e.stopPropagation();
          rerunHistoryQuery({ question: item.question, sql_query: item.sql_query, dataset_name: item.dataset_name });
        });
      }

      const btnDel = card.querySelector('.btn-delete-bookmark');
      if (btnDel) {
        btnDel.addEventListener('click', async (e) => {
          e.stopPropagation();
          await deleteBookmark(item.id, item.title);
        });
      }

      card.addEventListener('click', () => {
        loadHistoryQuery({ question: item.question || item.title, sql_query: item.sql_query });
      });
    });
    return;
  }

  // 2. Query History Entries
  let filtered = [...cachedHistoryEntries];

  if (currentHistoryFilter === 'success') {
    filtered = filtered.filter((e) => Boolean(e.success));
  } else if (currentHistoryFilter === 'failed') {
    filtered = filtered.filter((e) => !e.success);
  }

  if (currentHistorySearch) {
    const q = currentHistorySearch.toLowerCase();
    filtered = filtered.filter((e) => {
      const question = (e.question || '').toLowerCase();
      const sql = (e.sql_query || '').toLowerCase();
      const dataset = (e.dataset_name || '').toLowerCase();
      const err = (e.error_message || '').toLowerCase();
      return question.includes(q) || sql.includes(q) || dataset.includes(q) || err.includes(q);
    });
  }

  if (elements.historyCountBadge) {
    elements.historyCountBadge.textContent = cachedHistoryEntries.length;
  }

  if (cachedHistoryEntries.length === 0) {
    elements.historyList.innerHTML = `
      <div style="text-align: center; color: var(--text-muted); padding: 36px 16px; font-size: 0.8125rem;">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" style="margin-bottom: 8px; opacity: 0.5;">
          <circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline>
        </svg>
        <div>No query history recorded yet in this session.</div>
        <div style="font-size: 0.72rem; opacity: 0.7; margin-top: 4px;">Run queries in SQL Lab or converse with Clarification Engine to build history.</div>
      </div>
    `;
    return;
  }

  if (filtered.length === 0) {
    elements.historyList.innerHTML = `
      <div style="text-align: center; color: var(--text-muted); padding: 36px 16px; font-size: 0.8125rem;">
        <div>No queries match your search or filter.</div>
        <div style="font-size: 0.72rem; opacity: 0.7; margin-top: 4px;">Try searching for a different term or resetting the status filter.</div>
      </div>
    `;
    return;
  }

  elements.historyList.innerHTML = filtered.map((entry, index) => {
    const questionText = entry.question || 'Manual SQL Execution';
    const isSuccess = Boolean(entry.success);
    const badgeClass = isSuccess ? 'badge-green' : 'badge-magenta';
    const statusText = isSuccess ? 'SUCCESS' : 'FAILED';
    const rowCountText = entry.row_count != null ? `${entry.row_count} rows` : '0 rows';
    const timeText = Number(entry.execution_time || 0).toFixed(3) + 's';
    const timestampText = entry.timestamp || '';
    const datasetText = entry.dataset_name || 'Active Dataset';
    const hasSql = Boolean(entry.sql_query && entry.sql_query.trim());

    return `
      <div class="history-card" data-history-index="${index}">
        <div class="history-card-header">
          <div class="history-card-title-group">
            <span class="history-card-question">${ui.escapeHtml(questionText)}</span>
            <span class="history-card-dataset">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"></path></svg>
              <span>${ui.escapeHtml(datasetText)}</span>
            </span>
          </div>
          <div class="history-card-status-badges">
            <span class="badge ${badgeClass}">${statusText}</span>
          </div>
        </div>

        ${hasSql ? `<pre class="history-card-sql">${ui.escapeHtml(entry.sql_query)}</pre>` : ''}

        ${(!isSuccess && entry.error_message) ? `<div class="history-card-error">${ui.escapeHtml(entry.error_message)}</div>` : ''}

        <div class="history-card-footer">
          <div class="history-card-meta">
            <span class="history-card-meta-item" title="Returned row count">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
              <span>${rowCountText}</span>
            </span>
            <span class="history-card-meta-item" title="Execution latency">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
              <span>${timeText}</span>
            </span>
            ${timestampText ? `
              <span class="history-card-meta-item" title="${ui.escapeHtml(timestampText)}">
                <span>${ui.escapeHtml(timestampText)}</span>
              </span>
            ` : ''}
          </div>

          <div class="history-card-actions">
            <button type="button" class="history-action-btn btn-open-in-lab" title="Load into SQL Lab">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
              <span>Open in SQL Lab</span>
            </button>
            ${hasSql ? `
              <button type="button" class="history-action-btn btn-copy-history-sql" title="Copy SQL statement">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                <span>Copy SQL</span>
              </button>
              <button type="button" class="history-action-btn btn-rerun" title="Rerun SQL query">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                <span>Rerun</span>
              </button>
              <button type="button" class="history-action-btn btn-save-bookmark" title="Bookmark Query">
                <span style="color: #00F5FF;">★</span>
                <span>Save</span>
              </button>
            ` : ''}
            ${entry.id != null ? `
              <button type="button" class="history-action-btn btn-delete-item btn-delete-history" title="Delete from history">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                <span>Delete</span>
              </button>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Attach event handlers to card elements
  elements.historyList.querySelectorAll('.history-card').forEach((card) => {
    const idx = parseInt(card.dataset.historyIndex, 10);
    const entry = filtered[idx];
    if (!entry) return;

    // Open in SQL Lab
    const btnOpen = card.querySelector('.btn-open-in-lab');
    if (btnOpen) {
      btnOpen.addEventListener('click', (e) => {
        e.stopPropagation();
        loadHistoryQuery(entry);
      });
    }

    // Copy SQL
    const btnCopy = card.querySelector('.btn-copy-history-sql');
    if (btnCopy) {
      btnCopy.addEventListener('click', (e) => {
        e.stopPropagation();
        copyHistorySql(entry.sql_query, btnCopy);
      });
    }

    // Rerun
    const btnRerun = card.querySelector('.btn-rerun');
    if (btnRerun) {
      btnRerun.addEventListener('click', (e) => {
        e.stopPropagation();
        rerunHistoryQuery(entry, btnRerun);
      });
    }

    // Bookmark
    const btnSaveBm = card.querySelector('.btn-save-bookmark');
    if (btnSaveBm) {
      btnSaveBm.addEventListener('click', async (e) => {
        e.stopPropagation();
        await bookmarkHistoryEntry(entry);
      });
    }

    // Delete single history item
    const btnDelHistory = card.querySelector('.btn-delete-history');
    if (btnDelHistory) {
      btnDelHistory.addEventListener('click', async (e) => {
        e.stopPropagation();
        await deleteHistoryItem(entry.id);
      });
    }

    // Clicking card opens in SQL Lab
    card.addEventListener('click', () => {
      loadHistoryQuery(entry);
    });
  });
}

async function saveSqlToBookmarks() {
  const sql = (elements.sqlEditor ? elements.sqlEditor.value : '').trim();
  if (!sql) {
    ui.showToast('No SQL query in editor to save.', 'warning');
    return;
  }
  const defaultTitle = (elements.queryInput ? elements.queryInput.value.trim() : '') || 'Saved Query';
  const title = prompt('Enter a title for this saved query:', defaultTitle);
  if (title === null) return;
  const cleanTitle = title.trim() || defaultTitle;

  try {
    const res = await api.saveQuery({
      title: cleanTitle,
      sql_query: sql,
      question: elements.queryInput ? elements.queryInput.value.trim() : '',
      dataset_name: state.dataset.isLoaded ? (state.dataset.name || '') : '',
      notes: ''
    });
    if (res && res.id) {
      ui.showToast(`Saved query "${cleanTitle}" to bookmarks!`, 'success');
      try {
        const sq = await api.getSavedQueries();
        cachedSavedQueries = sq.saved_queries || sq.queries || [];
      } catch (e) {}
    }
  } catch (err) {
    console.error('Failed to save query:', err);
    ui.showToast(`Failed to save query: ${err.message}`, 'error');
  }
}

async function bookmarkHistoryEntry(entry) {
  if (!entry || !entry.sql_query) return;
  const defaultTitle = entry.question || 'Saved Query';
  const title = prompt('Enter a title for this bookmark:', defaultTitle);
  if (title === null) return;
  const cleanTitle = title.trim() || defaultTitle;

  try {
    const res = await api.saveQuery({
      title: cleanTitle,
      sql_query: entry.sql_query,
      question: entry.question || '',
      dataset_name: entry.dataset_name || (state.dataset.isLoaded ? state.dataset.name : ''),
      notes: ''
    });
    if (res && res.id) {
      ui.showToast(`Saved query "${cleanTitle}" to bookmarks!`, 'success');
      try {
        const sq = await api.getSavedQueries();
        cachedSavedQueries = sq.saved_queries || sq.queries || [];
      } catch (e) {}
    }
  } catch (err) {
    console.error('Failed to bookmark query:', err);
    ui.showToast(`Failed to bookmark query: ${err.message}`, 'error');
  }
}

async function deleteHistoryItem(entryId) {
  if (!entryId) return;
  try {
    await api.deleteHistoryEntry(entryId);
    cachedHistoryEntries = cachedHistoryEntries.filter((e) => e.id !== entryId);
    state.setHistory({ entries: cachedHistoryEntries, count: cachedHistoryEntries.length });
    renderHistoryList();
    ui.showToast('History entry deleted.', 'info');
  } catch (err) {
    console.error('Failed to delete history item:', err);
    ui.showToast(`Failed to delete history entry: ${err.message}`, 'error');
  }
}

async function deleteBookmark(bookmarkId, title) {
  if (!bookmarkId) return;
  try {
    await api.deleteSavedQuery(bookmarkId);
    cachedSavedQueries = cachedSavedQueries.filter((b) => b.id !== bookmarkId);
    renderHistoryList();
    ui.showToast(`Bookmark "${title || bookmarkId}" removed.`, 'info');
  } catch (err) {
    console.error('Failed to delete bookmark:', err);
    ui.showToast(`Failed to delete bookmark: ${err.message}`, 'error');
  }
}

function loadHistoryQuery(entry) {
  if (!entry) return;
  state.setStudioTab('sql-lab');
  state.setActiveView('table');

  if (elements.queryInput) {
    elements.queryInput.value = entry.question || '';
    updateCharCount();
  }
  if (elements.sqlEditor) {
    elements.sqlEditor.value = entry.sql_query || '';
  }

  closeHistoryModal();
  ui.showToast('Loaded query into SQL Lab.', 'info');
}

function copyHistorySql(sql, btn) {
  if (!sql) {
    ui.showToast('No SQL statement to copy.', 'warning');
    return;
  }
  navigator.clipboard.writeText(sql).then(() => {
    ui.showToast('SQL statement copied to clipboard!', 'success');
    if (btn) {
      const origHtml = btn.innerHTML;
      btn.innerHTML = `
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#00F5FF" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
        <span style="color: var(--accent-cyan);">Copied!</span>
      `;
      setTimeout(() => {
        btn.innerHTML = origHtml;
      }, 1500);
    }
  }).catch((err) => {
    console.error("Clipboard copy error:", err);
    ui.showToast('Failed to copy SQL to clipboard.', 'error');
  });
}

async function rerunHistoryQuery(entry, btn) {
  if (!entry) return;

  if (!state.dataset.isLoaded) {
    ui.showToast('No dataset loaded. Please upload a dataset before rerunning queries.', 'error');
    return;
  }

  // Dataset mismatch guard
  if (entry.dataset_name && state.dataset.name && entry.dataset_name !== state.dataset.name) {
    const proceed = confirm(
      `This query was originally executed against "${entry.dataset_name}", but the currently active dataset is "${state.dataset.name}".\n\nDo you want to attempt rerunning it on "${state.dataset.name}"?`
    );
    if (!proceed) return;
  }

  const sqlToRun = (entry.sql_query || '').trim();
  if (!sqlToRun) {
    if (entry.question) {
      closeHistoryModal();
      state.setStudioTab('sql-lab');
      if (elements.queryInput) {
        elements.queryInput.value = entry.question;
        updateCharCount();
      }
      executeNaturalLanguageQuery(entry.question);
      return;
    }
    ui.showToast('No SQL query available to rerun.', 'warning');
    return;
  }

  closeHistoryModal();
  state.setStudioTab('sql-lab');
  state.setActiveView('table');

  if (elements.queryInput) {
    elements.queryInput.value = entry.question || '';
    updateCharCount();
  }
  if (elements.sqlEditor) {
    elements.sqlEditor.value = sqlToRun;
  }

  ui.showToast(`Rerunning query: ${sqlToRun.substring(0, 40)}...`, 'info');
  try {
    const res = await api.executeManualSql(sqlToRun, entry.question || '', state.dataset.name || '');
    state.setManualSqlResult(res, sqlToRun);
    if (res.success) {
      ui.showToast(`Rerun succeeded (${res.row_count} rows in ${Number(res.execution_time).toFixed(3)}s)`, 'success');
      if (elements.resultsMeta) {
        elements.resultsMeta.textContent = `${res.row_count} rows • ${Number(res.execution_time).toFixed(3)}s`;
      }
      ui.renderResultsTable(
        res.columns,
        res.rows,
        1,
        state.results.rowsPerPage,
        null,
        'asc',
        (idx) => handleTableSort(idx)
      );
      bindPaginationButtons();
    } else {
      ui.showToast(`Rerun failed: ${res.error || 'Execution error'}`, 'error');
    }
  } catch (err) {
    console.error("Rerun history error:", err);
    state.setQueryError(err.message, sqlToRun);
    ui.showToast(`Rerun error: ${err.message}`, 'error');
  }
}

async function openHistoryModal() {
  if (!elements.historyModal) return;
  elements.historyModal.classList.add('active');

  // Reset toolbar controls
  currentHistoryFilter = 'all';
  currentHistorySearch = '';
  if (elements.historySearchInput) {
    elements.historySearchInput.value = '';
  }
  if (elements.btnClearHistorySearch) {
    elements.btnClearHistorySearch.style.display = 'none';
  }
  document.querySelectorAll('.history-filter-pill').forEach((pill) => {
    pill.classList.toggle('active', pill.dataset.statusFilter === 'all');
  });

  elements.historyList.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 28px 0; font-size: 0.8125rem;">Loading session query history...</div>`;

  try {
    const [historyData, savedData] = await Promise.all([
      api.getHistory(100),
      api.getSavedQueries().catch(() => ({ saved_queries: [], count: 0 }))
    ]);
    cachedHistoryEntries = historyData.entries || [];
    cachedSavedQueries = savedData.saved_queries || savedData.queries || [];
    state.setHistory(historyData);
    if (elements.historyCountBadge) {
      elements.historyCountBadge.textContent = cachedHistoryEntries.length;
    }
    renderHistoryList();
    if (elements.historySearchInput) {
      elements.historySearchInput.focus();
    }
  } catch (err) {
    console.error("Failed to load history:", err);
    elements.historyList.innerHTML = `<div style="text-align: center; color: var(--accent-coral); padding: 24px 0; font-size: 0.8125rem;">Failed to load history: ${ui.escapeHtml(err.message)}</div>`;
  }
}

function closeHistoryModal() {
  if (elements.historyModal) {
    elements.historyModal.classList.remove('active');
  }
}

function openDocsModal() {
  if (elements.docsModal) {
    elements.docsModal.classList.add('active');
  }
}

function closeDocsModal() {
  if (elements.docsModal) {
    elements.docsModal.classList.remove('active');
  }
}

async function clearHistory() {
  try {
    await api.clearHistory();
    cachedHistoryEntries = [];
    state.setHistory({ entries: [], count: 0 });
    if (elements.historyCountBadge) {
      elements.historyCountBadge.textContent = '0';
    }
    renderHistoryList();
    ui.showToast('Session query history cleared.', 'success');
  } catch (err) {
    console.error("Failed to clear history:", err);
    ui.showToast(`Failed to clear history: ${err.message}`, 'error');
  }
}

// =============================================================================
// AI Provider Settings (BYOK) Logic
// =============================================================================

async function openSettingsModal() {
  if (!elements.settingsModal) return;
  elements.settingsModal.classList.add('active');
  if (elements.settingsTestResult) {
    elements.settingsTestResult.style.display = 'none';
  }

  try {
    const config = await api.getProviderSettings();
    if (config.supported_providers && config.supported_providers.length > 0) {
      const groqProv = config.supported_providers.find((p) => p.id === 'groq') || config.supported_providers[0];
      if (elements.settingsModelSelect && groqProv.models) {
        elements.settingsModelSelect.innerHTML = groqProv.models.map((m) =>
          `<option value="${m.id}" ${m.id === config.model ? 'selected' : ''}>${m.name}</option>`
        ).join('');
      }
    }

    if (config.has_key) {
      if (elements.settingsKeyStatus) {
        elements.settingsKeyStatus.textContent = `Active (${config.masked_key})`;
        elements.settingsKeyStatus.className = 'key-status-tag active';
      }
      if (elements.btnRemoveKey) elements.btnRemoveKey.disabled = false;
      if (elements.settingsApiKeyInput) elements.settingsApiKeyInput.placeholder = 'Enter new key to replace existing';
      if (elements.navKeyBadge) elements.navKeyBadge.style.display = 'inline-block';
    } else {
      if (elements.settingsKeyStatus) {
        elements.settingsKeyStatus.textContent = config.server_key_available ? 'Server key active (Dev)' : 'No key saved';
        elements.settingsKeyStatus.className = 'key-status-tag';
      }
      if (elements.btnRemoveKey) elements.btnRemoveKey.disabled = true;
      if (elements.settingsApiKeyInput) elements.settingsApiKeyInput.placeholder = 'Enter gsk_...';
      if (elements.navKeyBadge) elements.navKeyBadge.style.display = config.server_key_available ? 'inline-block' : 'none';
    }
  } catch (err) {
    console.warn('[DataVerse] Error fetching provider settings:', err);
  }
}

function closeSettingsModal() {
  if (!elements.settingsModal) return;
  elements.settingsModal.classList.remove('active');
  if (elements.settingsTestResult) {
    elements.settingsTestResult.style.display = 'none';
  }
}

function toggleKeyVisibility() {
  if (!elements.settingsApiKeyInput) return;
  const isPassword = elements.settingsApiKeyInput.type === 'password';
  elements.settingsApiKeyInput.type = isPassword ? 'text' : 'password';
  if (elements.iconEyeShow && elements.iconEyeHide) {
    elements.iconEyeShow.style.display = isPassword ? 'none' : 'block';
    elements.iconEyeHide.style.display = isPassword ? 'block' : 'none';
  }
}

async function saveSettings() {
  const provider = elements.settingsProviderSelect ? elements.settingsProviderSelect.value : 'groq';
  const model = elements.settingsModelSelect ? elements.settingsModelSelect.value : 'openai/gpt-oss-20b';
  const apiKey = elements.settingsApiKeyInput ? elements.settingsApiKeyInput.value.trim() : '';

  if (!apiKey) {
    const curConfig = await api.getProviderSettings().catch(() => null);
    if (!curConfig || !curConfig.has_key) {
      ui.showToast('Please enter your Groq API key.', 'warning');
      if (elements.settingsApiKeyInput) elements.settingsApiKeyInput.focus();
      return;
    }
  }

  if (elements.btnSaveSettings) {
    elements.btnSaveSettings.disabled = true;
    elements.btnSaveSettings.textContent = 'Validating...';
  }
  if (elements.settingsTestResult) {
    elements.settingsTestResult.style.display = 'none';
  }

  try {
    // Pass apiKey if entered, or null to preserve existing session key. validateConnection = true
    await api.saveProviderSettings(provider, model, apiKey || null, true);
    // Clean up any legacy localStorage entry if present (Strict Session-Only Invariant)
    try {
      localStorage.removeItem('dataverse_user_key');
      localStorage.removeItem('dataverse_user_model');
    } catch (e) {}

    if (elements.settingsApiKeyInput) elements.settingsApiKeyInput.value = '';
    ui.showToast('AI Provider settings applied successfully for this session!', 'success');
    closeSettingsModal();
    syncProviderSettings();
  } catch (err) {
    if (elements.settingsTestResult) {
      elements.settingsTestResult.style.display = 'block';
      elements.settingsTestResult.className = 'settings-test-banner error';
      elements.settingsTestResult.textContent = err.message;
    }
    ui.showToast(`Validation error: ${err.message}`, 'error');
  } finally {
    if (elements.btnSaveSettings) {
      elements.btnSaveSettings.disabled = false;
      elements.btnSaveSettings.textContent = 'Save & Apply';
    }
  }
}

async function removeKey() {
  try {
    await api.removeProviderSettings();
    try {
      localStorage.removeItem('dataverse_user_key');
      localStorage.removeItem('dataverse_user_model');
    } catch (e) {}
    if (elements.settingsApiKeyInput) elements.settingsApiKeyInput.value = '';
    if (elements.settingsKeyStatus) {
      elements.settingsKeyStatus.textContent = 'No key saved';
      elements.settingsKeyStatus.className = 'key-status-tag';
    }
    if (elements.btnRemoveKey) elements.btnRemoveKey.disabled = true;
    if (elements.navKeyBadge) elements.navKeyBadge.style.display = 'none';
    ui.showToast('API key removed from session.', 'info');
  } catch (err) {
    ui.showToast(`Error removing key: ${err.message}`, 'error');
  }
}

async function testConnection() {
  const provider = elements.settingsProviderSelect ? elements.settingsProviderSelect.value : 'groq';
  const model = elements.settingsModelSelect ? elements.settingsModelSelect.value : 'openai/gpt-oss-20b';
  const apiKey = elements.settingsApiKeyInput ? elements.settingsApiKeyInput.value.trim() : null;

  if (elements.btnTestConnection) elements.btnTestConnection.disabled = true;
  if (elements.btnTestSpinner) elements.btnTestSpinner.style.display = 'inline';
  if (elements.settingsTestResult) elements.settingsTestResult.style.display = 'none';

  try {
    const res = await api.testProviderConnection(provider, model, apiKey || undefined);
    if (elements.settingsTestResult) {
      elements.settingsTestResult.style.display = 'block';
      elements.settingsTestResult.className = `settings-test-banner ${res.success ? 'success' : 'error'}`;
      elements.settingsTestResult.textContent = res.message;
    }
    if (res.success) {
      ui.showToast('Connection verified successfully!', 'success');
    } else {
      ui.showToast(res.message, 'error');
    }
  } catch (err) {
    if (elements.settingsTestResult) {
      elements.settingsTestResult.style.display = 'block';
      elements.settingsTestResult.className = 'settings-test-banner error';
      elements.settingsTestResult.textContent = `Test failed: ${err.message}`;
    }
    ui.showToast(`Test failed: ${err.message}`, 'error');
  } finally {
    if (elements.btnTestConnection) elements.btnTestConnection.disabled = false;
    if (elements.btnTestSpinner) elements.btnTestSpinner.style.display = 'none';
  }
}

async function syncProviderSettings() {
  try {
    // Purge any legacy localStorage keys to enforce strict session-only invariant
    try {
      localStorage.removeItem('dataverse_user_key');
      localStorage.removeItem('dataverse_user_model');
    } catch (e) {}

    const config = await api.getProviderSettings();

    if (elements.navKeyBadge) {
      elements.navKeyBadge.style.display = (config.has_key || config.server_key_available) ? 'inline-block' : 'none';
    }
  } catch (e) {
    console.warn('[DataVerse] syncProviderSettings note:', e.message);
  }
}

// =============================================================================
// Helper Functions & Event Binding
// =============================================================================

function updateCharCount() {
  if (elements.queryCharCount && elements.queryInput) {
    elements.queryCharCount.textContent = `${elements.queryInput.value.length} chars`;
  }
}

function bindEvents() {
  // Mobile drawer toggle
  if (elements.mobileMenuBtn && elements.sidebar && elements.sidebarBackdrop) {
    const toggleSidebar = (open) => {
      elements.sidebar.classList.toggle('open', open);
      elements.sidebarBackdrop.classList.toggle('active', open);
    };

    elements.mobileMenuBtn.addEventListener('click', () => {
      const isOpen = elements.sidebar.classList.contains('open');
      toggleSidebar(!isOpen);
    });

    elements.sidebarBackdrop.addEventListener('click', () => {
      toggleSidebar(false);
    });
  }

  // File browse click
  if (elements.btnBrowseFile && elements.fileInput) {
    elements.btnBrowseFile.addEventListener('click', (e) => {
      e.stopPropagation();
      elements.fileInput.click();
    });
  }

  // Dropzone click & keyboard trigger
  if (elements.uploadDropzone && elements.fileInput) {
    elements.uploadDropzone.addEventListener('click', () => {
      elements.fileInput.click();
    });

    elements.uploadDropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        elements.fileInput.click();
      }
    });

    // Drag and drop handlers
    elements.uploadDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      elements.uploadDropzone.classList.add('dragover');
    });

    elements.uploadDropzone.addEventListener('dragleave', () => {
      elements.uploadDropzone.classList.remove('dragover');
    });

    elements.uploadDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      elements.uploadDropzone.classList.remove('dragover');
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    elements.fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });
  }

  // Query input typing & shortcuts
  if (elements.queryInput) {
    elements.queryInput.addEventListener('input', updateCharCount);
    elements.queryInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        executeNaturalLanguageQuery();
      }
    });
  }

  if (elements.btnClearQuery) {
    elements.btnClearQuery.addEventListener('click', () => {
      elements.queryInput.value = '';
      updateCharCount();
      elements.queryInput.focus();
    });
  }

  if (elements.btnRunQuery) {
    elements.btnRunQuery.addEventListener('click', () => {
      executeNaturalLanguageQuery();
    });
  }

  // SQL preview actions
  if (elements.btnSaveSql) {
    elements.btnSaveSql.addEventListener('click', () => {
      saveSqlToBookmarks();
    });
  }

  if (elements.btnCopySql && elements.sqlEditor) {
    elements.btnCopySql.addEventListener('click', () => {
      const sql = elements.sqlEditor.value;
      if (!sql) {
        ui.showToast('No SQL query to copy.', 'warning');
        return;
      }
      navigator.clipboard.writeText(sql)
        .then(() => ui.showToast('SQL copied to clipboard!', 'success'))
        .catch(() => ui.showToast('Failed to copy to clipboard.', 'error'));
    });
  }

  if (elements.btnRunSql) {
    elements.btnRunSql.addEventListener('click', () => {
      executeManualSql();
    });
  }

  // Export buttons
  if (elements.btnExportCsv) elements.btnExportCsv.addEventListener('click', () => exportResults('csv'));
  if (elements.btnExportExcel) elements.btnExportExcel.addEventListener('click', () => exportResults('excel'));
  if (elements.btnExportJson) elements.btnExportJson.addEventListener('click', () => exportResults('json'));

  // History modal
  if (elements.btnOpenHistory) elements.btnOpenHistory.addEventListener('click', openHistoryModal);
  if (elements.btnCloseHistory) elements.btnCloseHistory.addEventListener('click', closeHistoryModal);
  if (elements.btnCloseHistoryAction) elements.btnCloseHistoryAction.addEventListener('click', closeHistoryModal);
  if (elements.btnClearHistoryConfirm) elements.btnClearHistoryConfirm.addEventListener('click', clearHistory);
  if (elements.historyModal) {
    elements.historyModal.addEventListener('click', (e) => {
      if (e.target === elements.historyModal) closeHistoryModal();
    });
  }

  // History search and filter controls
  if (elements.historySearchInput) {
    elements.historySearchInput.addEventListener('input', () => {
      currentHistorySearch = (elements.historySearchInput.value || '').trim();
      if (elements.btnClearHistorySearch) {
        elements.btnClearHistorySearch.style.display = currentHistorySearch ? 'flex' : 'none';
      }
      renderHistoryList();
    });
  }

  if (elements.btnClearHistorySearch) {
    elements.btnClearHistorySearch.addEventListener('click', () => {
      if (elements.historySearchInput) {
        elements.historySearchInput.value = '';
        elements.historySearchInput.focus();
      }
      currentHistorySearch = '';
      elements.btnClearHistorySearch.style.display = 'none';
      renderHistoryList();
    });
  }

  document.querySelectorAll('.history-filter-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.history-filter-pill').forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      currentHistoryFilter = pill.dataset.statusFilter || 'all';
      renderHistoryList();
    });
  });

  // AI Provider Settings modal
  if (elements.btnOpenSettings) elements.btnOpenSettings.addEventListener('click', openSettingsModal);
  if (elements.btnCloseSettings) elements.btnCloseSettings.addEventListener('click', closeSettingsModal);
  if (elements.btnToggleKeyVisibility) elements.btnToggleKeyVisibility.addEventListener('click', toggleKeyVisibility);
  if (elements.btnSaveSettings) elements.btnSaveSettings.addEventListener('click', saveSettings);
  if (elements.btnRemoveKey) elements.btnRemoveKey.addEventListener('click', removeKey);
  if (elements.btnTestConnection) elements.btnTestConnection.addEventListener('click', testConnection);
  if (elements.settingsModal) {
    elements.settingsModal.addEventListener('click', (e) => {
      if (e.target === elements.settingsModal) closeSettingsModal();
    });
  }

  // Documentation modal
  if (elements.btnOpenDocs) elements.btnOpenDocs.addEventListener('click', openDocsModal);
  if (elements.btnCloseDocs) elements.btnCloseDocs.addEventListener('click', closeDocsModal);
  if (elements.btnDoneDocs) elements.btnDoneDocs.addEventListener('click', closeDocsModal);
  if (elements.docsModal) {
    elements.docsModal.addEventListener('click', (e) => {
      if (e.target === elements.docsModal) closeDocsModal();
    });
  }

  // Studio Top Navigation
  document.querySelectorAll('.studio-nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      if (tab) {
        state.setStudioTab(tab);
        api.setPreference('active_studio_tab', tab).catch(() => {});
      }
    });
  });

  // Dedicated Clarification Engine Controls
  const btnClearChat = document.getElementById('ce-btn-clear-chat');
  if (btnClearChat) {
    btnClearChat.addEventListener('click', () => {
      state.clearConversation();
      ui.showToast('Clarification conversation cleared.', 'info');
    });
  }

  const btnGotoSql = document.getElementById('ce-btn-goto-sql');
  if (btnGotoSql) {
    btnGotoSql.addEventListener('click', () => {
      state.setStudioTab('sql-lab');
    });
  }

  const btnCeSend = document.getElementById('ce-btn-send');
  if (btnCeSend) {
    btnCeSend.addEventListener('click', handleClarificationEngineSend);
  }

  const ceFollowupInput = document.getElementById('ce-followup-input');
  if (ceFollowupInput) {
    ceFollowupInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleClarificationEngineSend();
      }
    });
  }

  const btnOpenClarifyPanel = document.getElementById('inpage-clarification-open-panel-btn');
  if (btnOpenClarifyPanel) {
    btnOpenClarifyPanel.addEventListener('click', () => {
      state.setStudioTab('clarification');
    });
  }

  const btnGotoClarifyWorkspace = document.getElementById('btn-goto-clarification-workspace');
  if (btnGotoClarifyWorkspace) {
    btnGotoClarifyWorkspace.addEventListener('click', () => {
      state.setStudioTab('clarification');
    });
  }

  const btnInsightsTable = document.getElementById('insights-btn-view-table');
  if (btnInsightsTable) {
    btnInsightsTable.addEventListener('click', () => {
      state.setStudioTab('sql-lab');
      state.setActiveView('table');
    });
  }

  const btnInsightsChart = document.getElementById('insights-btn-view-chart');
  if (btnInsightsChart) {
    btnInsightsChart.addEventListener('click', () => {
      state.setStudioTab('sql-lab');
      state.setActiveView('chart');
    });
  }

  const btnInsightsProfile = document.getElementById('insights-btn-view-profile');
  if (btnInsightsProfile) {
    btnInsightsProfile.addEventListener('click', () => {
      state.setStudioTab('sql-lab');
      state.setActiveView('profile');
    });
  }

  // Curated example prompt chips
  document.querySelectorAll('.prompt-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt && elements.queryInput) {
        elements.queryInput.value = prompt;
        updateCharCount();
        elements.queryInput.focus();
        if (state.schema.is_loaded) {
          executeNaturalLanguageQuery(prompt);
        }
      }
    });
  });

  // Keyboard global shortcuts
  window.addEventListener('keydown', (e) => {
    // Ctrl + O: Upload file
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') {
      e.preventDefault();
      elements.fileInput.click();
    }
    // Ctrl + L: Clear query input
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
      e.preventDefault();
      elements.queryInput.value = '';
      updateCharCount();
      elements.queryInput.focus();
    }
    // Ctrl + H: History modal
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'h') {
      e.preventDefault();
      if (elements.historyModal.classList.contains('active')) {
        closeHistoryModal();
      } else {
        openHistoryModal();
      }
    }
    // Ctrl + , : Settings modal
    if ((e.ctrlKey || e.metaKey) && e.key === ',') {
      e.preventDefault();
      if (elements.settingsModal && elements.settingsModal.classList.contains('active')) {
        closeSettingsModal();
      } else {
        openSettingsModal();
      }
    }
    // Ctrl + R: Run SQL (when not in a standard browser reload context)
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r' && e.altKey) {
      e.preventDefault();
      executeManualSql();
    }
    // Escape key closes modals
    if (e.key === 'Escape') {
      closeHistoryModal();
      closeSettingsModal();
      closeDocsModal();
      ui.hideClarificationModal();
    }
  });

  // Session expiry listener
  window.addEventListener('dataverse:session-expired', () => {
    ui.showToast('Your secure session has expired. Reconnecting...', 'warning');
    api.createSession()
      .then(() => ui.showToast('Session refreshed successfully.', 'success'))
      .catch((e) => ui.showToast(`Session refresh failed: ${e.message}`, 'error'));
  });
}

// =============================================================================
// Bootstrap Application
// =============================================================================

// =============================================================================
// Relational Schema Visualizer Studio Handlers (Phase 4)
// =============================================================================

async function loadAndSyncSchemaStudio() {
  try {
    const data = await api.getSchemaVisualization();
    state.setSchemaVisualizerData(data);
    renderSchemaStudioUI();
  } catch (err) {
    console.error('[DataVerse] Schema visualization load error:', err);
    ui.showToast(`Failed to load schema: ${err.message}`, 'error');
  }
}

function renderSchemaStudioUI() {
  ui.renderSchemaStudio(state.schemaVisualizer, {
    onSelectTable: (tableName) => {
      state.setSchemaSelectedTable(tableName);
      switchInspectorTab('details');
    },
    onSelectRelationship: (relId) => {
      state.setSchemaSelectedRelationship(relId);
      switchInspectorTab('details');
    },
    onSetTablePosition: (tableName, x, y) => {
      state.setSchemaTablePosition(tableName, x, y);
    },
    onConfirmRelationship: async (rel) => {
      try {
        const res = await api.confirmRelationship(
          rel.source_table,
          rel.source_column,
          rel.target_table,
          rel.target_column,
          rel.cardinality
        );
        state.updateRelationshipStatus(rel.id, 'confirmed');
        ui.showToast(res.message || 'Relationship confirmed!', 'success');
      } catch (err) {
        ui.showToast(`Failed to confirm relationship: ${err.message}`, 'error');
      }
    },
    onRejectRelationship: async (rel) => {
      try {
        const res = await api.rejectRelationship(
          rel.source_table,
          rel.source_column,
          rel.target_table,
          rel.target_column,
          rel.cardinality
        );
        state.updateRelationshipStatus(rel.id, 'rejected');
        ui.showToast(res.message || 'Relationship rejected.', 'info');
      } catch (err) {
        ui.showToast(`Failed to reject relationship: ${err.message}`, 'error');
      }
    },
    onOpenJoinBuilder: (srcTbl, tgtTbl, srcCol, tgtCol) => {
      switchInspectorTab('join');
      const selA = document.getElementById('join-table-a-select');
      const selB = document.getElementById('join-table-b-select');
      if (selA && srcTbl) selA.value = srcTbl;
      if (selB && tgtTbl) selB.value = tgtTbl;
      if (selA) selA.dispatchEvent(new Event('change'));
      proposeJoinQuery(srcTbl, tgtTbl, 'INNER JOIN', srcCol, tgtCol);
    },
    onQueryTable: (tableName) => {
      const sql = `SELECT * FROM "${tableName}" LIMIT 50;`;
      window.dataverseApp.goToSqlLab(sql);
      executeSqlDirect(sql);
    }
  });
}

function switchInspectorTab(subtabName) {
  document.querySelectorAll('.schema-tab-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.subtab === subtabName);
  });
  document.querySelectorAll('.inspector-subtab-pane').forEach((pane) => {
    const isTarget = pane.id === `pane-inspector-${subtabName}` || pane.id === `pane-inspector-${subtabName}-builder`;
    pane.style.display = isTarget ? 'block' : 'none';
    pane.classList.toggle('active', isTarget);
  });

  if (subtabName === 'relationships') {
    ui.renderSchemaRelationshipManager(state.schemaVisualizer, {
      onSelectRelationship: (relId) => {
        state.setSchemaSelectedRelationship(relId);
        switchInspectorTab('details');
      },
      onConfirmRelationship: async (rel) => {
        try {
          const res = await api.confirmRelationship(
            rel.source_table,
            rel.source_column,
            rel.target_table,
            rel.target_column,
            rel.cardinality
          );
          state.updateRelationshipStatus(rel.id, 'confirmed');
          ui.showToast(res.message || 'Relationship confirmed!', 'success');
        } catch (err) {
          ui.showToast(`Failed to confirm relationship: ${err.message}`, 'error');
        }
      },
      onRejectRelationship: async (rel) => {
        try {
          const res = await api.rejectRelationship(
            rel.source_table,
            rel.source_column,
            rel.target_table,
            rel.target_column,
            rel.cardinality
          );
          state.updateRelationshipStatus(rel.id, 'rejected');
          ui.showToast(res.message || 'Relationship rejected.', 'info');
        } catch (err) {
          ui.showToast(`Failed to reject relationship: ${err.message}`, 'error');
        }
      },
      onOpenJoinBuilder: (srcTbl, tgtTbl, srcCol, tgtCol) => {
        switchInspectorTab('join');
        const selA = document.getElementById('join-table-a-select');
        const selB = document.getElementById('join-table-b-select');
        if (selA && srcTbl) selA.value = srcTbl;
        if (selB && tgtTbl) selB.value = tgtTbl;
        proposeJoinQuery(srcTbl, tgtTbl, 'INNER JOIN', srcCol, tgtCol);
      }
    });
  } else if (subtabName === 'join') {
    ui.renderSchemaJoinBuilder(state.schemaVisualizer);
  }
}

function fitSchemaToScreen() {
  const viewport = document.getElementById('schema-viewport');
  const tables = state.schemaVisualizer.tables || [];
  if (!viewport || tables.length === 0) return;

  const positions = state.schemaVisualizer.tablePositions;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  tables.forEach((t) => {
    const pos = positions[t.table_name] || { x: 50, y: 50 };
    minX = Math.min(minX, pos.x);
    maxX = Math.max(maxX, pos.x + 260);
    minY = Math.min(minY, pos.y);
    maxY = Math.max(maxY, pos.y + 200);
  });

  if (!isFinite(minX)) {
    minX = 0; maxX = 600; minY = 0; maxY = 400;
  }

  const contentW = Math.max(300, maxX - minX + 80);
  const contentH = Math.max(200, maxY - minY + 80);
  const viewW = viewport.clientWidth || 800;
  const viewH = viewport.clientHeight || 500;

  const scale = Math.min(1.4, Math.max(0.45, Math.min(viewW / contentW, viewH / contentH) * 0.9));
  const panX = Math.round((viewW - contentW * scale) / 2 - minX * scale);
  const panY = Math.round((viewH - contentH * scale) / 2 - minY * scale);

  state.setSchemaZoom(scale);
  state.setSchemaPan(panX, panY);
}

function autoArrangeSchemaNodes() {
  state.schemaVisualizer.tablePositions = {};
  renderSchemaStudioUI();
  setTimeout(() => fitSchemaToScreen(), 60);
  ui.showToast('Diagram auto-arranged.', 'info');
}

async function proposeJoinQuery(tableA, tableB, joinType = 'INNER JOIN', sourceCol = null, targetCol = null) {
  if (!tableA || !tableB) {
    ui.showToast('Please select both Table A and Table B.', 'warning');
    return;
  }
  try {
    const res = await api.generateJoinSql(tableA, tableB, joinType, sourceCol, targetCol);
    const sqlCode = document.getElementById('join-sql-code');
    const explText = document.getElementById('join-explanation-text');
    const box = document.getElementById('join-preview-box');

    if (sqlCode) sqlCode.textContent = res.sql;
    if (explText) {
      explText.textContent = res.explanation + (res.is_ambiguous ? ' ⚠️ Multiple join paths exist.' : '');
    }
    if (box) box.style.display = 'block';
  } catch (err) {
    ui.showToast(`Join query proposal failed: ${err.message}`, 'error');
  }
}

function setupSchemaStudioEvents() {
  // 1. Inspector Subtabs
  document.querySelectorAll('.schema-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const subtab = btn.dataset.subtab;
      if (subtab) switchInspectorTab(subtab);
    });
  });

  // 2. Relationship Filter Buttons
  document.querySelectorAll('.rel-filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.rel-filter-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.schemaVisualizer.filter = btn.dataset.filter || 'all';
      renderSchemaStudioUI();
    });
  });

  // 3. Canvas Zoom & Pan Controls
  const btnZoomIn = document.getElementById('btn-schema-zoom-in');
  if (btnZoomIn) {
    btnZoomIn.addEventListener('click', () => state.setSchemaZoom(state.schemaVisualizer.zoom + 0.15));
  }
  const btnZoomOut = document.getElementById('btn-schema-zoom-out');
  if (btnZoomOut) {
    btnZoomOut.addEventListener('click', () => state.setSchemaZoom(state.schemaVisualizer.zoom - 0.15));
  }
  const btnReset = document.getElementById('btn-schema-reset-view');
  if (btnReset) {
    btnReset.addEventListener('click', () => {
      state.setSchemaZoom(1.0);
      state.setSchemaPan(0, 0);
    });
  }
  const btnFit = document.getElementById('btn-schema-fit-view');
  if (btnFit) {
    btnFit.addEventListener('click', fitSchemaToScreen);
  }
  const btnAutoArrange = document.getElementById('btn-schema-auto-arrange');
  if (btnAutoArrange) {
    btnAutoArrange.addEventListener('click', autoArrangeSchemaNodes);
  }

  // 4. Canvas Viewport Pan & Wheel Zoom
  const viewport = document.getElementById('schema-viewport');
  if (viewport) {
    let isPanning = false;
    let startX = 0, startY = 0;
    let initialPanX = 0, initialPanY = 0;

    viewport.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.schema-table-node') || e.target.closest('button') || e.target.closest('select')) {
        return;
      }
      isPanning = true;
      startX = e.clientX;
      startY = e.clientY;
      initialPanX = state.schemaVisualizer.pan.x;
      initialPanY = state.schemaVisualizer.pan.y;
      viewport.style.cursor = 'grabbing';
    });

    window.addEventListener('pointermove', (e) => {
      if (!isPanning) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      state.setSchemaPan(initialPanX + dx, initialPanY + dy);
    });

    window.addEventListener('pointerup', () => {
      if (isPanning) {
        isPanning = false;
        viewport.style.cursor = 'default';
      }
    });

    viewport.addEventListener('wheel', (e) => {
      // Allow natural vertical scrolling when scrolling over node columns or inspector panels
      if (e.target.closest('.table-node-columns') || e.target.closest('.schema-inspector') || e.target.closest('.schema-inspector-body')) {
        return;
      }
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      state.setSchemaZoom(state.schemaVisualizer.zoom * factor);
    }, { passive: false });
  }

  // 5. Join Builder Events
  const btnToggleCustomCols = document.getElementById('btn-toggle-custom-join-cols');
  const customColsRow = document.getElementById('join-custom-cols-row');
  if (btnToggleCustomCols && customColsRow) {
    btnToggleCustomCols.addEventListener('click', () => {
      const isHidden = customColsRow.style.display === 'none';
      customColsRow.style.display = isHidden ? 'block' : 'none';
      btnToggleCustomCols.textContent = isHidden ? 'Auto Match' : 'Custom Columns';
    });
  }

  const btnExecuteProposal = document.getElementById('btn-execute-join-proposal');
  if (btnExecuteProposal) {
    btnExecuteProposal.addEventListener('click', () => {
      const tblA = document.getElementById('join-table-a-select')?.value;
      const tblB = document.getElementById('join-table-b-select')?.value;
      const joinType = document.getElementById('join-type-select')?.value || 'INNER JOIN';
      const isCustom = customColsRow && customColsRow.style.display !== 'none';
      const colA = isCustom ? document.getElementById('join-col-a-select')?.value : null;
      const colB = isCustom ? document.getElementById('join-col-b-select')?.value : null;
      proposeJoinQuery(tblA, tblB, joinType, colA, colB);
    });
  }

  const btnSchemaGenJoin = document.getElementById('btn-schema-generate-join');
  if (btnSchemaGenJoin) {
    btnSchemaGenJoin.addEventListener('click', () => {
      switchInspectorTab('join');
      const tblA = document.getElementById('join-table-a-select')?.value;
      const tblB = document.getElementById('join-table-b-select')?.value;
      const joinType = document.getElementById('join-type-select')?.value || 'INNER JOIN';
      if (tblA && tblB) {
        proposeJoinQuery(tblA, tblB, joinType);
      }
    });
  }

  const btnCopyJoinSql = document.getElementById('btn-copy-join-sql');
  if (btnCopyJoinSql) {
    btnCopyJoinSql.addEventListener('click', () => {
      const code = document.getElementById('join-sql-code')?.textContent || '';
      if (code) {
        copySqlToClipboard(code);
      }
    });
  }

  const btnSendJoinSql = document.getElementById('btn-send-join-to-sql-lab');
  if (btnSendJoinSql) {
    btnSendJoinSql.addEventListener('click', () => {
      const code = document.getElementById('join-sql-code')?.textContent || '';
      if (code.trim()) {
        window.dataverseApp.goToSqlLab(code.trim());
        executeSqlDirect(code.trim());
        ui.showToast('JOIN query loaded and executing in SQL Lab!', 'success');
      }
    });
  }

  // 6. Custom Link Button
  const btnAddRel = document.getElementById('btn-schema-add-relation');
  if (btnAddRel) {
    btnAddRel.addEventListener('click', () => {
      switchInspectorTab('join');
      if (customColsRow) customColsRow.style.display = 'block';
      if (btnToggleCustomCols) btnToggleCustomCols.textContent = 'Auto Match';
      ui.showToast('Select tables and columns in the JOIN Builder to link them.', 'info');
    });
  }

  // Smooth wheel scrolling dispatcher for SQL Lab
  const sqlLab = document.getElementById('studio-view-sql-lab');
  if (sqlLab) {
    sqlLab.addEventListener('wheel', (e) => {
      let el = e.target;
      while (el && el !== sqlLab) {
        const style = window.getComputedStyle(el);
        const hasScroll = (style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
        if (hasScroll) {
          const atTop = el.scrollTop <= 0 && e.deltaY < 0;
          const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1 && e.deltaY > 0;
          if (!atTop && !atBottom) {
            return; // Allow inner scrollable container to consume event
          }
        }
        el = el.parentElement;
      }
      if (sqlLab.scrollHeight > sqlLab.clientHeight) {
        sqlLab.scrollTop += e.deltaY;
      }
    }, { passive: true });
  }
}

async function init() {
  console.log('[DataVerse] Initializing application client...');
  setupPWA();
  setupStateSubscriptions();
  setupViewTabs();
  bindEvents();
  setupSchemaStudioEvents();

  // Initial render of Clarification Studio and Insights Tab
  ui.renderConversationStream([], {
    onPromptClick: (prompt) => {
      if (elements.queryInput) {
        elements.queryInput.value = prompt;
        updateCharCount();
        executeNaturalLanguageQuery(prompt);
      }
    }
  });
  ui.renderIntentSummary(state.conversation.intentSummary);
  syncInsightsTab();

  try {
    const session = await api.ensureSession();
    console.log('[DataVerse] Secure session established:', session.sessionId);

    // Synchronize user BYOK settings
    await syncProviderSettings();

    // Synchronize user preferences from persistent store
    try {
      const prefsRes = await api.getPreferences();
      if (prefsRes && prefsRes.preferences) {
        if (prefsRes.preferences.active_studio_tab) {
          state.setStudioTab(prefsRes.preferences.active_studio_tab);
        }
        if (prefsRes.preferences.rows_per_page) {
          const rpp = parseInt(prefsRes.preferences.rows_per_page, 10);
          if (rpp > 0) state.results.rowsPerPage = rpp;
        }
      }
    } catch (e) {
      console.warn('[DataVerse] Preferences sync note:', e.message);
    }

    // Initial schema sync if already loaded
    const schema = await api.getSchema();
    if (schema.is_loaded) {
      state.setSchema(schema);
      const suggestions = await api.getSuggestions();
      state.setSuggestions(suggestions.suggestions);
    }
  } catch (err) {
    console.warn('[DataVerse] Backend initial handshake note:', err.message);
  }
}

// Start app on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
