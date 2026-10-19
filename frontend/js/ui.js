/**
 * frontend/js/ui.js - High-Fidelity DOM Rendering, Table Sorting, Profiler & Dialogs
 */

export class UIController {
  constructor() {
    this.toastContainer = null;
    this._initToastContainer();
  }

  _initToastContainer() {
    if (typeof document === 'undefined') return;
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    this.toastContainer = container;
  }

  showToast(message, type = 'info', duration = 3500) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = 'ℹ️';
    if (type === 'success') icon = '✓';
    if (type === 'error') icon = '✕';
    if (type === 'warning') icon = '⚠';

    toast.innerHTML = `
      <span style="font-weight: 500; font-size: 0.85rem; line-height: 1;">${icon}</span>
      <span style="flex: 1; font-weight: 400; line-height: 1.4;">${this.escapeHtml(message)}</span>
    `;
    this.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)';
      setTimeout(() => toast.remove(), 200);
    }, duration);
  }

  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // =========================================================================
  // Tables List & Schema
  // =========================================================================

  renderTableList(tables, activeTable, onSelect) {
    const container = document.getElementById('sidebar-tables');
    if (!container) return;

    if (!tables || tables.length === 0) {
      container.innerHTML = `
        <div class="empty-tables-hint">
          <span style="font-size: 1.1rem; opacity: 0.6;">📂</span>
          <span>No tables loaded yet.<br/>Upload a CSV, Excel, or SQLite file.</span>
        </div>
      `;
      return;
    }

    container.innerHTML = tables.map((t) => `
      <div class="table-item ${t === activeTable ? 'active' : ''}" data-table="${this.escapeHtml(t)}">
        <span style="display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <span style="font-size: 0.82rem; opacity: 0.75; font-family: var(--font-mono);">▦</span>
          <span style="overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(t)}</span>
        </span>
        <span class="badge badge-cyan" style="font-size: 0.625rem; padding: 1px 5px;">Table</span>
      </div>
    `).join('');

    container.querySelectorAll('.table-item').forEach((el) => {
      el.addEventListener('click', () => {
        const table = el.dataset.table;
        if (onSelect) onSelect(table);
      });
    });
  }

  renderSuggestions(suggestions, onSelect) {
    const container = document.getElementById('suggestions-bar');
    if (!container) return;

    if (!suggestions || suggestions.length === 0) {
      container.innerHTML = '';
      container.style.display = 'none';
      return;
    }

    container.style.display = 'flex';
    container.innerHTML = suggestions.map((s) => `
      <button type="button" class="suggestion-chip" data-question="${this.escapeHtml(s)}" title="${this.escapeHtml(s)}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="color: var(--accent-cyan); flex-shrink: 0;"><path d="M12 2l2.4 7.2L21.6 12l-7.2 2.8L12 22l-2.4-7.2L2.4 12l7.2-2.8L12 2z"/></svg>
        <span style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(s)}</span>
      </button>
    `).join('');

    container.querySelectorAll('.suggestion-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const q = btn.dataset.question;
        if (onSelect) onSelect(q);
      });
    });
  }

  // =========================================================================
  // Data Table with Sorting & Pagination
  // =========================================================================

  renderResultsTable(columns, rows, page = 1, rowsPerPage = 50, sortCol = null, sortDir = 'asc', onSort = null) {
    const wrapper = document.getElementById('table-wrapper');
    const paginationEl = document.getElementById('pagination-controls');
    if (!wrapper) return;

    if (!columns || columns.length === 0 || !rows || rows.length === 0) {
      wrapper.innerHTML = `
        <div class="empty-view-placeholder">
          <span class="placeholder-icon">📋</span>
          <strong>No query results yet</strong>
          <p>Enter a natural language question above or select an example prompt to query your data.</p>
        </div>
      `;
      if (paginationEl) paginationEl.style.display = 'none';
      return;
    }

    // Sort rows if column selected
    let processedRows = [...rows];
    if (sortCol !== null && sortCol >= 0 && sortCol < columns.length) {
      processedRows.sort((a, b) => {
        const valA = a[sortCol];
        const valB = b[sortCol];
        if (valA === valB) return 0;
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;
        if (typeof valA === 'number' && typeof valB === 'number') {
          return sortDir === 'asc' ? valA - valB : valB - valA;
        }
        return sortDir === 'asc'
          ? String(valA).localeCompare(String(valB))
          : String(valB).localeCompare(String(valA));
      });
    }

    // Pagination slice
    const totalRows = processedRows.length;
    const totalPages = Math.ceil(totalRows / rowsPerPage) || 1;
    const startIdx = (page - 1) * rowsPerPage;
    const endIdx = Math.min(startIdx + rowsPerPage, totalRows);
    const visibleRows = processedRows.slice(startIdx, endIdx);

    // Build Table HTML
    const headersHtml = columns.map((col, idx) => {
      let arrow = '';
      if (sortCol === idx) {
        arrow = sortDir === 'asc' ? ' <span style="color: var(--accent-cyan);">↑</span>' : ' <span style="color: var(--accent-cyan);">↓</span>';
      }
      return `<th data-col-idx="${idx}">${this.escapeHtml(col)}${arrow}</th>`;
    }).join('');

    const bodyHtml = visibleRows.map((row) => {
      const cells = row.map((cell) => `<td>${this.escapeHtml(cell)}</td>`).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    wrapper.innerHTML = `
      <table class="data-table">
        <thead><tr>${headersHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    `;

    // Bind sort click
    if (onSort) {
      wrapper.querySelectorAll('th').forEach((th) => {
        th.addEventListener('click', () => {
          const colIdx = parseInt(th.dataset.colIdx, 10);
          onSort(colIdx);
        });
      });
    }

    // Pagination UI
    if (paginationEl) {
      paginationEl.style.display = 'flex';
      paginationEl.innerHTML = `
        <span>Showing <strong style="color: var(--text-primary); font-variant-numeric: tabular-nums;">${startIdx + 1}–${endIdx}</strong> of <strong style="color: var(--text-primary); font-variant-numeric: tabular-nums;">${totalRows}</strong> rows</span>
        <div style="display: flex; align-items: center; gap: 6px;">
          <button type="button" class="btn btn-secondary btn-icon" id="btn-prev-page" ${page <= 1 ? 'disabled' : ''} title="Previous Page">←</button>
          <span style="font-family: var(--font-mono); font-size: 0.74rem; padding: 0 8px; color: var(--text-secondary);">Page ${page} of ${totalPages}</span>
          <button type="button" class="btn btn-secondary btn-icon" id="btn-next-page" ${page >= totalPages ? 'disabled' : ''} title="Next Page">→</button>
        </div>
      `;
    }
  }

  // =========================================================================
  // Chart Rendering
  // =========================================================================

  renderChart(chartData, options = {}) {
    const container = document.getElementById('chart-container');
    if (!container) return;

    const { onSelectType, onRefresh, activeType, isLoading, error } = options;

    if (isLoading || (chartData && chartData.isLoading)) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 14px; text-align: center;">
          <div class="neon-spinner" style="width: 36px; height: 36px; border: 3px solid rgba(0, 245, 255, 0.2); border-top-color: #00F5FF; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">Generating chart visualization...</span>
            <span style="font-size: 0.78rem; color: var(--text-muted);">Analyzing categorical and numeric distributions</span>
          </div>
        </div>
      `;
      return;
    }

    const err = error || (chartData && chartData.error);
    if (err) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 14px; text-align: center; max-width: 480px; margin: 0 auto; padding: 20px;">
          <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(244, 63, 94, 0.15); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; border: 1px solid rgba(244, 63, 94, 0.4); color: var(--accent-coral);">
            ⚠️
          </div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">Cannot generate chart</span>
            <span style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4;">${this.escapeHtml(err)}</span>
          </div>
          ${onRefresh ? `
            <button type="button" class="btn btn-secondary btn-sm" id="btn-chart-retry" style="margin-top: 6px;">
              ↻ Try Auto Detection
            </button>
          ` : ''}
        </div>
      `;
      const retryBtn = container.querySelector('#btn-chart-retry');
      if (retryBtn && onRefresh) {
        retryBtn.onclick = () => onRefresh();
      }
      return;
    }

    const b64 = chartData ? (chartData.base64_image || chartData.base64Image) : null;
    if (!chartData || !b64) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 12px; text-align: center;">
          <div style="width: 44px; height: 44px; border-radius: 50%; background: var(--bg-surface-elevated); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; border: 1px solid var(--border-subtle); color: var(--text-secondary);">
            📊
          </div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">No chart generated</span>
            <span style="font-size: 0.78rem; color: var(--text-muted);">Execute a query returning categorical or numeric series to auto-generate a visualization</span>
          </div>
        </div>
      `;
      return;
    }

    const effectiveType = activeType || chartData.chart_type || chartData.chartType || 'auto';
    const chartTitle = chartData.title || '';

    container.innerHTML = `
      <div style="display: flex; flex-direction: column; align-items: center; gap: 14px; width: 100%;">
        <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; max-width: 860px; padding: 8px 12px; background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); flex-wrap: wrap; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="badge badge-cyan" style="text-transform: uppercase; font-family: var(--font-mono); font-size: 0.75rem;">Type: ${this.escapeHtml(effectiveType)}</span>
            ${chartTitle ? `<span style="font-size: 0.8rem; color: var(--text-secondary); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(chartTitle)}</span>` : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <label for="chart-type-select" style="font-size: 0.75rem; color: var(--text-muted);">Style:</label>
            <select id="chart-type-select" class="form-select form-select-sm" style="background: var(--bg-input); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: var(--radius-sm); padding: 4px 8px; font-size: 0.78rem; outline: none; cursor: pointer;">
              <option value="auto" ${effectiveType === 'auto' ? 'selected' : ''}>Auto Detect</option>
              <option value="bar" ${effectiveType === 'bar' ? 'selected' : ''}>Bar Chart</option>
              <option value="grouped_bar" ${effectiveType === 'grouped_bar' ? 'selected' : ''}>Grouped Bar</option>
              <option value="horizontal_bar" ${effectiveType === 'horizontal_bar' ? 'selected' : ''}>Horizontal Bar</option>
              <option value="line" ${effectiveType === 'line' ? 'selected' : ''}>Line Chart</option>
              <option value="scatter" ${effectiveType === 'scatter' ? 'selected' : ''}>Scatter Plot</option>
              <option value="pie" ${effectiveType === 'pie' ? 'selected' : ''}>Pie Chart</option>
            </select>
            <button type="button" class="btn btn-secondary btn-sm" id="btn-chart-refresh" title="Regenerate Visualization" style="padding: 4px 10px; font-size: 0.78rem; display: flex; align-items: center; gap: 4px;">
              <span>↻</span> Refresh
            </button>
          </div>
        </div>
        <div style="width: 100%; max-width: 860px; display: flex; justify-content: center;">
          <img src="${b64}" alt="DataVerse Query Chart" class="chart-image" />
        </div>
      </div>
    `;

    const selectEl = container.querySelector('#chart-type-select');
    if (selectEl && onSelectType) {
      selectEl.onchange = (e) => onSelectType(e.target.value);
    }
    const refreshBtn = container.querySelector('#btn-chart-refresh');
    if (refreshBtn && onRefresh) {
      refreshBtn.onclick = () => onRefresh();
    }
  }

  // =========================================================================
  // Data Profiler Rendering
  // =========================================================================

  renderProfile(profileData, options = {}) {
    const container = document.getElementById('profile-container');
    if (!container) return;

    const { activeTable, availableTables = [], isLoading, error, onSelectTable, onRetry } = options;

    if (isLoading || (options && options.isLoading)) {
      const tblLabel = activeTable || (profileData ? profileData.table_name : 'table');
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 14px; text-align: center;">
          <div class="neon-spinner" style="width: 36px; height: 36px; border: 3px solid rgba(0, 245, 255, 0.2); border-top-color: #00F5FF; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">Analyzing diagnostics for ${this.escapeHtml(tblLabel)}...</span>
            <span style="font-size: 0.78rem; color: var(--text-muted);">Profiling column null rates, distinct counts, and distributions</span>
          </div>
        </div>
      `;
      return;
    }

    const err = error || (options && options.error);
    if (err) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 14px; text-align: center; max-width: 480px; margin: 0 auto; padding: 20px;">
          <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(244, 63, 94, 0.15); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; border: 1px solid rgba(244, 63, 94, 0.4); color: var(--accent-coral);">
            ⚠️
          </div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">Failed to load table diagnostics</span>
            <span style="font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4;">${this.escapeHtml(err)}</span>
          </div>
          ${onRetry ? `
            <button type="button" class="btn btn-secondary btn-sm" id="btn-profile-retry" style="margin-top: 6px;">
              ↻ Retry Diagnostics
            </button>
          ` : ''}
        </div>
      `;
      const retryBtn = container.querySelector('#btn-profile-retry');
      if (retryBtn && onRetry) {
        retryBtn.onclick = () => onRetry();
      }
      return;
    }

    if (!profileData || !profileData.columns) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 320px; color: var(--text-muted); gap: 12px; text-align: center;">
          <div style="width: 44px; height: 44px; border-radius: 50%; background: var(--bg-surface-elevated); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; border: 1px solid var(--border-subtle); color: var(--text-secondary);">
            📈
          </div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <span style="font-weight: 500; color: var(--text-primary); font-size: 0.9375rem;">Select a table to inspect data diagnostics</span>
            <span style="font-size: 0.78rem; color: var(--text-muted);">Click any table name in the left sidebar or select from the dropdown above to view column health, distributions, and null ratios</span>
          </div>
        </div>
      `;
      return;
    }

    const colList = Array.isArray(profileData.columns)
      ? profileData.columns
      : Object.values(profileData.columns || {});

    const cardsHtml = colList.map((c) => {
      const colName = c.name || c.column || 'Column';
      const nullPct = Number(c.null_percentage || 0).toFixed(1);
      const uniquePct = Number(c.unique_percentage || 0).toFixed(1);
      const validPct = (100 - parseFloat(nullPct)).toFixed(1);

      let statsSection = '';
      if (c.is_numeric && c.min_val !== null) {
        statsSection = `
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.74rem; background: var(--bg-input); padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); margin-top: 4px; font-variant-numeric: tabular-nums;">
            <span>Min: <strong style="color: var(--text-primary);">${c.min_val}</strong></span>
            <span>Max: <strong style="color: var(--text-primary);">${c.max_val}</strong></span>
            <span>Mean: <strong style="color: var(--text-primary);">${Number(c.mean_val || 0).toFixed(2)}</strong></span>
            <span>Std: <strong style="color: var(--text-primary);">${Number(c.std_val || 0).toFixed(2)}</strong></span>
          </div>
        `;
      } else if (c.top_values && c.top_values.length > 0) {
        const topChips = c.top_values.slice(0, 3).map(tv => {
          const valStr = String(tv.value !== null && tv.value !== undefined ? tv.value : 'NULL');
          return `<span style="background: var(--bg-input); border: 1px solid var(--border-subtle); border-radius: 3px; padding: 1px 5px; font-size: 0.7rem; color: var(--text-secondary); max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(valStr)}: ${tv.count}">${this.escapeHtml(valStr)} (${tv.count})</span>`;
        }).join('');
        statsSection = `
          <div style="display: flex; flex-direction: column; gap: 3px; margin-top: 4px;">
            <span style="font-size: 0.7rem; color: var(--text-muted);">Top Values:</span>
            <div style="display: flex; flex-wrap: wrap; gap: 4px;">${topChips}</div>
          </div>
        `;
      }

      return `
        <div class="stat-card">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
            <strong style="color: var(--text-primary); font-size: 0.82rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(colName)}">${this.escapeHtml(colName)}</strong>
            <span class="badge badge-cyan">${this.escapeHtml(c.data_type || 'TEXT')}</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 0.74rem; color: var(--text-secondary); margin-top: 2px;">
            <span>Nulls: <strong style="color: ${parseFloat(nullPct) > 0 ? 'var(--accent-coral)' : 'var(--text-secondary)'};">${c.null_count} (${nullPct}%)</strong></span>
            <span>Distinct: <strong style="color: var(--text-primary);">${c.unique_count}</strong></span>
          </div>
          <div style="width: 100%; height: 4px; background: rgba(244, 63, 94, 0.2); border-radius: var(--radius-full); overflow: hidden; margin: 4px 0;">
            <div style="width: ${validPct}%; height: 100%; background: var(--accent-green);"></div>
          </div>
          ${statsSection}
        </div>
      `;
    }).join('');

    const currentTbl = profileData.table_name || activeTable || '';
    const tableOptions = (availableTables && availableTables.length > 1) ? `
      <select id="profile-table-select" class="form-select form-select-sm" style="background: var(--bg-input); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: var(--radius-sm); padding: 3px 8px; font-size: 0.78rem; outline: none; cursor: pointer;">
        ${availableTables.map(t => `<option value="${this.escapeHtml(t)}" ${t === currentTbl ? 'selected' : ''}>${this.escapeHtml(t)}</option>`).join('')}
      </select>
    ` : '';

    const emptyNotice = profileData.total_rows === 0 ? `
      <div style="padding: 8px 12px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-sm); font-size: 0.78rem; color: #f59e0b; display: flex; align-items: center; gap: 8px;">
        <span>ℹ️</span> Table contains 0 rows. Showing column schema definitions.
      </div>
    ` : '';

    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 14px; width: 100%;">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle);">
          <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
            <h3 style="font-size: 1rem; font-weight: 500; color: var(--text-primary); display: flex; align-items: center; gap: 8px; margin: 0;">
              <span>Table Diagnostics:</span>
              <span style="color: var(--accent-cyan-text); font-family: var(--font-mono);">${this.escapeHtml(currentTbl)}</span>
            </h3>
            ${tableOptions}
          </div>
          <span class="badge ${profileData.total_rows > 0 ? 'badge-green' : 'badge-amber'}">${profileData.total_rows} Rows • ${profileData.total_columns} Columns</span>
        </div>
        ${emptyNotice}
        <div class="stat-grid">${cardsHtml}</div>
      </div>
    `;

    const tableSelectEl = container.querySelector('#profile-table-select');
    if (tableSelectEl && onSelectTable) {
      tableSelectEl.onchange = (e) => onSelectTable(e.target.value);
    }
  }

  // =========================================================================
  // Clarification Handling (In-Workspace Card & Modal)
  // =========================================================================

  renderInPageClarification(question, options, reasoning, onSelectOption, onEditQuestion, onDismiss) {
    const banner = document.getElementById('sql-clarification-banner');
    const bannerDesc = document.getElementById('sql-clarification-banner-desc');
    if (banner) {
      if (bannerDesc && question) {
        bannerDesc.textContent = `Ambiguity Detected: ${question}`;
      }
      banner.style.display = 'flex';
    }

    const card = document.getElementById('inpage-clarification-card');
    const qEl = document.getElementById('inpage-clarification-question');
    const rEl = document.getElementById('inpage-clarification-reasoning');
    const optsEl = document.getElementById('inpage-clarification-options');
    const customInput = document.getElementById('inpage-custom-clarification-input');
    const customBtn = document.getElementById('inpage-custom-clarification-btn');
    const editBtn = document.getElementById('inpage-clarification-edit-btn');
    const dismissBtn = document.getElementById('inpage-clarification-dismiss-btn');

    if (!card || !qEl || !optsEl) return;

    qEl.textContent = question;

    if (rEl) {
      if (reasoning) {
        rEl.style.display = 'block';
        rEl.textContent = `✦ Ambiguity: ${reasoning}`;
      } else {
        rEl.style.display = 'none';
      }
    }

    optsEl.innerHTML = (options || []).map((opt) => `
      <button type="button" class="inpage-option-chip" data-choice="${this.escapeHtml(opt)}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
        <span>${this.escapeHtml(opt)}</span>
      </button>
    `).join('');

    card.style.display = 'flex';
    setTimeout(() => {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);

    // Bind option click
    optsEl.querySelectorAll('.inpage-option-chip').forEach((btn) => {
      btn.onclick = () => {
        const choice = btn.dataset.choice;
        this.hideInPageClarification();
        this.hideClarificationModal();
        if (onSelectOption) onSelectOption(choice);
      };
    });

    // Custom input submit
    const submitCustom = () => {
      if (!customInput) return;
      const val = (customInput.value || '').trim();
      if (val) {
        customInput.value = '';
        this.hideInPageClarification();
        this.hideClarificationModal();
        if (onSelectOption) onSelectOption(val);
      }
    };
    if (customBtn) customBtn.onclick = submitCustom;
    if (customInput) {
      customInput.onkeydown = (e) => {
        if (e.key === 'Enter') submitCustom();
      };
    }

    // Back / Edit Question
    if (editBtn) {
      editBtn.onclick = () => {
        this.hideInPageClarification();
        this.hideClarificationModal();
        if (onEditQuestion) onEditQuestion();
      };
    }

    // Dismiss / Cancel
    if (dismissBtn) {
      dismissBtn.onclick = () => {
        this.hideInPageClarification();
        this.hideClarificationModal();
        if (onDismiss) onDismiss();
      };
    }
  }

  hideInPageClarification() {
    const banner = document.getElementById('sql-clarification-banner');
    if (banner) banner.style.display = 'none';
    const card = document.getElementById('inpage-clarification-card');
    if (card) card.style.display = 'none';
  }

  hideClarificationModal() {
    // Obsolete: Modal replaced by in-page clarification stage and dedicated Clarification Studio
  }

  // =========================================================================
  // Dedicated Clarification Engine UI & Studio Navigation
  // =========================================================================

  switchStudioTab(tabName) {
    document.querySelectorAll('.studio-nav-btn').forEach(btn => {
      if (btn.dataset.tab === tabName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    const views = {
      'sql-lab': document.getElementById('studio-view-sql-lab'),
      'schema': document.getElementById('studio-view-schema'),
      'clarification': document.getElementById('studio-view-clarification'),
      'insights': document.getElementById('studio-view-insights')
    };

    Object.entries(views).forEach(([name, el]) => {
      if (!el) return;
      if (name === tabName) {
        el.style.display = 'flex';
        el.classList.add('active');
      } else {
        el.style.display = 'none';
        el.classList.remove('active');
      }
    });

    if (tabName === 'clarification') {
      const stream = document.getElementById('ce-message-stream');
      if (stream) {
        setTimeout(() => { stream.scrollTop = stream.scrollHeight; }, 30);
      }
      const dot = document.getElementById('nav-clarification-dot');
      if (dot) dot.style.display = 'none';
    }
  }

  renderConversationStream(messages, { onSelectOption, onExecuteSql, onCopySql, onPromptClick, onApplyCleaning, onCancelCleaning, onUndoCleaning, onRevertOriginal } = {}) {
    const stream = document.getElementById('ce-message-stream');
    if (!stream) return;

    if (!messages || messages.length === 0) {
      stream.innerHTML = `
        <div class="ce-welcome-card">
          <div class="ce-welcome-header">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00F5FF" stroke-width="2.2"><path d="M12 2l2.4 7.2L21.6 12l-7.2 2.8L12 22l-2.4-7.2L2.4 12l7.2-2.8L12 2z"/></svg>
            <span>Clarification Engine</span>
          </div>
          <p class="ce-welcome-text">
            I am the <strong>Data Scientist assistant</strong> for DataVerse. I can answer complex analytical questions with verified SQL or perform <strong>conversational data cleaning</strong> (missing values, deduplication, type conversions, filtering, and text normalization) with interactive before-and-after previews.
          </p>
          <div class="ce-welcome-chips" id="ce-welcome-chips">
            <button type="button" class="ce-option-chip" data-prompt="Analyze missing values in dataset">
              <span style="color: #00F5FF;">🧹</span> Analyze missing values
            </button>
            <button type="button" class="ce-option-chip" data-prompt="Check for duplicate rows">
              <span style="color: #9D4DFF;">🔍</span> Check duplicate rows
            </button>
            <button type="button" class="ce-option-chip" data-prompt="Show the top 5 rows">
              <span style="color: #00F5FF;">→</span> Show the top 5 rows
            </button>
            <button type="button" class="ce-option-chip" data-prompt="Which products have the highest sales?">
              <span style="color: #9D4DFF;">→</span> Which products have the highest sales?
            </button>
          </div>
        </div>
      `;

      stream.querySelectorAll('.ce-welcome-chips .ce-option-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          if (onPromptClick) onPromptClick(btn.dataset.prompt);
        });
      });
      return;
    }

    let html = '';
    for (const msg of messages) {
      if (msg.sender === 'user') {
        html += `
          <div class="ce-msg ce-msg-user">
            <div class="ce-msg-user-header">
              <span>You</span>
              <span>${this.escapeHtml(msg.timestamp || '')}</span>
            </div>
            <div class="ce-msg-user-text">${this.escapeHtml(msg.text)}</div>
          </div>
        `;
      } else {
        html += `
          <div class="ce-msg ce-msg-assistant">
            <div class="ce-msg-assistant-header">
              <div class="ce-avatar" style="width: 18px; height: 18px; font-size: 10px;">✦</div>
              <span>Data Scientist</span>
              <span style="margin-left: auto; font-size: 10px; color: var(--text-muted); font-weight: 400;">${this.escapeHtml(msg.timestamp || '')}</span>
            </div>
        `;

        if (msg.reasoning && msg.type !== 'cleaning_preview') {
          html += `
            <div class="ce-reasoning-box">
              ✦ <strong>Ambiguity Rationale:</strong> ${this.escapeHtml(msg.reasoning)}
            </div>
          `;
        }

        if (msg.text && msg.type !== 'result' && msg.type !== 'error' && msg.type !== 'cleaning_preview' && msg.type !== 'cleaning_applied' && msg.type !== 'cleaning_undo' && msg.type !== 'cleaning_cancelled') {
          html += `<div class="ce-question-text">${this.escapeHtml(msg.text)}</div>`;
        }

        // Data Cleaning Proposal Preview Card
        if (msg.type === 'cleaning_preview' || msg.cleaning_preview) {
          const cp = msg.cleaning_preview || {};
          const isDestructive = cp.is_destructive || false;
          const rowsBefore = cp.rows_before ?? 0;
          const rowsAfter = cp.rows_after ?? 0;
          const rowsAffected = cp.rows_affected ?? 0;
          const cellsModified = cp.cells_modified ?? 0;
          const colsAffected = (cp.columns_affected && cp.columns_affected.length > 0)
            ? cp.columns_affected.join(', ')
            : 'All Columns';
          const warning = cp.warning || '';
          const beforeSample = cp.before_sample || [];
          const afterSample = cp.after_sample || [];
          const sampleCols = (beforeSample.length > 0 ? Object.keys(beforeSample[0]) : (afterSample.length > 0 ? Object.keys(afterSample[0]) : [])).slice(0, 6);

          html += `
            <div class="ce-cleaning-card ${isDestructive ? 'destructive' : ''}">
              <div class="ce-cleaning-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 14px;">🧹</span>
                  <span style="font-weight: 500; font-size: 13px; color: #FFFFFF;">Data Cleaning Proposal</span>
                </div>
                <div style="display: flex; gap: 6px; align-items: center;">
                  ${isDestructive ? '<span class="badge badge-error" style="font-size: 10px;">⚠️ Destructive</span>' : '<span class="badge badge-cyan" style="font-size: 10px;">Safe Reversible</span>'}
                  <span class="badge badge-purple" style="font-size: 10px;">Table: ${this.escapeHtml(cp.table_name || 'dataset')}</span>
                </div>
              </div>

              <div class="ce-cleaning-description">
                ${this.escapeHtml(cp.description || msg.text || 'Proposed transformation')}
              </div>

              ${warning ? `
                <div class="ce-cleaning-warning">
                  ⚠️ <strong>Warning:</strong> ${this.escapeHtml(warning)}
                </div>
              ` : ''}

              <div class="ce-cleaning-metrics">
                <div class="ce-cleaning-metric-item">
                  <span class="ce-metric-lbl">Rows Before → After</span>
                  <span class="ce-metric-val">${rowsBefore} → <strong style="color: ${isDestructive ? '#FF3CAC' : '#00F5FF'};">${rowsAfter}</strong> (${rowsAffected > 0 ? '-' + rowsAffected : '0'} rows)</span>
                </div>
                <div class="ce-cleaning-metric-item">
                  <span class="ce-metric-lbl">Target Columns</span>
                  <span class="ce-metric-val" title="${this.escapeHtml(colsAffected)}">${this.escapeHtml(colsAffected)}</span>
                </div>
                <div class="ce-cleaning-metric-item">
                  <span class="ce-metric-lbl">Cells Modified</span>
                  <span class="ce-metric-val">${cellsModified}</span>
                </div>
              </div>

              ${(beforeSample.length > 0 || afterSample.length > 0) && sampleCols.length > 0 ? `
                <div class="ce-cleaning-samples-container">
                  <div class="ce-sample-section">
                    <div class="ce-sample-title">Before Transformation (First ${beforeSample.length} rows)</div>
                    <div class="ce-mini-table-wrapper">
                      <table class="data-table" style="font-size: 10.5px;">
                        <thead>
                          <tr>${sampleCols.map(c => `<th>${this.escapeHtml(c)}</th>`).join('')}</tr>
                        </thead>
                        <tbody>
                          ${beforeSample.map(r => `
                            <tr>${sampleCols.map(c => `<td>${this.escapeHtml(r[c] !== null && r[c] !== undefined ? r[c] : 'NULL')}</td>`).join('')}</tr>
                          `).join('')}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div class="ce-sample-section">
                    <div class="ce-sample-title" style="color: #00F5FF;">After Transformation Preview (First ${afterSample.length} rows)</div>
                    <div class="ce-mini-table-wrapper">
                      <table class="data-table" style="font-size: 10.5px;">
                        <thead>
                          <tr>${sampleCols.map(c => `<th>${this.escapeHtml(c)}</th>`).join('')}</tr>
                        </thead>
                        <tbody>
                          ${afterSample.map(r => `
                            <tr>${sampleCols.map(c => `<td>${this.escapeHtml(r[c] !== null && r[c] !== undefined ? r[c] : 'NULL')}</td>`).join('')}</tr>
                          `).join('')}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ` : ''}

              <div class="ce-cleaning-actions">
                <button type="button" class="btn btn-primary btn-sm ce-btn-apply-clean">
                  ✓ Apply Transformation
                </button>
                <button type="button" class="btn btn-secondary btn-sm ce-btn-cancel-clean">
                  ✕ Cancel
                </button>
                <span style="margin-left: auto; font-size: 10.5px; color: var(--text-muted);">Original upload is permanently preserved in-memory</span>
              </div>
            </div>
          `;
        }

        // Data Cleaning Applied Confirmation Card
        if (msg.type === 'cleaning_applied') {
          html += `
            <div class="ce-cleaning-card applied" style="border-color: rgba(52, 211, 153, 0.4); background: rgba(16, 28, 24, 0.8);">
              <div class="ce-cleaning-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="color: #34d399; font-size: 14px;">✓</span>
                  <span style="font-weight: 500; font-size: 13px; color: #FFFFFF;">Dataset Updated</span>
                </div>
                <span class="badge badge-green" style="font-size: 10px;">Applied Successfully</span>
              </div>
              <div style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.4;">
                ${this.escapeHtml(msg.text)}
              </div>
              <div class="ce-cleaning-actions" style="margin-top: 6px;">
                <button type="button" class="btn btn-secondary btn-xs ce-btn-undo-clean" style="color: #fbbf24; border-color: rgba(245, 158, 11, 0.35);">
                  ↺ Undo This Transformation
                </button>
                <button type="button" class="btn btn-secondary btn-xs ce-btn-revert-original" style="font-size: 10px; color: var(--text-muted);">
                  Revert to Original Upload
                </button>
              </div>
            </div>
          `;
        }

        // Undo Notice
        if (msg.type === 'cleaning_undo') {
          html += `
            <div style="font-size: 12px; color: #fbbf24; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-xs); padding: 8px 12px;">
              ↺ ${this.escapeHtml(msg.text)}
            </div>
          `;
        }

        // Cancelled Notice
        if (msg.type === 'cleaning_cancelled') {
          html += `
            <div style="font-size: 12px; color: var(--text-muted); background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: var(--radius-xs); padding: 8px 12px;">
              ✕ ${this.escapeHtml(msg.text)}
            </div>
          `;
        }

        if (msg.type === 'error') {
          html += `
            <div class="ce-error-box" style="background: rgba(255, 60, 172, 0.08); border: 1px solid rgba(255, 60, 172, 0.35); border-radius: var(--radius-sm); padding: 10px 12px; margin-top: 6px; color: #ffb3d9; font-size: 12px; display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; align-items: center; gap: 6px; font-weight: 500; color: #FF3CAC;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                <span>Pipeline Error</span>
              </div>
              <div>${this.escapeHtml(msg.text)}</div>
            </div>
          `;
        }

        if (msg.options && msg.options.length > 0 && msg.type !== 'cleaning_preview') {
          html += `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 4px;">
              <span style="font-size: 11px; font-weight: 500; color: var(--neon-cyan); letter-spacing: normal;">
                ✦ Suggested Interpretations (Schema Grounded)
              </span>
              <span class="badge badge-cyan" style="font-size: 10px;">${msg.options.length} Options Available</span>
            </div>
            <div class="ce-options-grid">
              ${msg.options.map((opt, i) => `
                <button type="button" class="ce-option-chip" data-choice="${this.escapeHtml(opt)}">
                  <span style="display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: rgba(0, 245, 255, 0.15); border: 1px solid rgba(0, 245, 255, 0.4); color: #00F5FF; font-weight: 500; font-size: 11px;">0${i+1}</span>
                  <div style="display: flex; flex-direction: column; gap: 2px;">
                    <span style="font-weight: 500; color: #FFFFFF;">${this.escapeHtml(opt)}</span>
                    <span style="font-size: 10.5px; color: var(--text-muted);">Click to refine & execute query</span>
                  </div>
                  <span style="margin-left: auto; color: var(--neon-cyan); font-weight: 500; font-size: 14px;">→</span>
                </button>
              `).join('')}
            </div>
          `;
        }

        if (msg.sql) {
          html += `
            <div class="ce-sql-box">
              <div class="ce-sql-header">
                <span>Verified SQLite Query</span>
                <div style="display: flex; gap: 6px;">
                  <button type="button" class="btn btn-secondary btn-xs ce-btn-copy-sql" data-sql="${this.escapeHtml(msg.sql)}" title="Copy SQL">
                    Copy
                  </button>
                  <button type="button" class="btn btn-secondary btn-xs ce-btn-run-sql" data-sql="${this.escapeHtml(msg.sql)}" style="color: #34d399; border-color: rgba(52, 211, 153, 0.3);" title="Re-run SQL">
                    Run SQL
                  </button>
                  <button type="button" class="btn btn-primary btn-xs ce-btn-open-sql-lab" title="Open in SQL Lab">
                    Open in SQL Lab →
                  </button>
                </div>
              </div>
              <div class="ce-sql-code">${this.escapeHtml(msg.sql)}</div>
            </div>
          `;
        }

        if (msg.data && msg.data.rows && msg.data.rows.length > 0) {
          const cols = msg.data.columns || [];
          const rows = msg.data.rows.slice(0, 5);
          html += `
            <div class="ce-mini-table-wrapper">
              <table class="data-table" style="font-size: 11px;">
                <thead>
                  <tr>
                    ${cols.map(c => `<th>${this.escapeHtml(c)}</th>`).join('')}
                  </tr>
                </thead>
                <tbody>
                  ${rows.map(r => `
                    <tr>
                      ${r.map(val => `<td>${this.escapeHtml(val !== null ? val : 'NULL')}</td>`).join('')}
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `;
        }

        if (msg.rowCount !== undefined || msg.executionTime !== undefined) {
          html += `
            <div class="ce-meta-bar">
              <span>Executed in ${Number(msg.executionTime || 0).toFixed(3)}s • ${msg.rowCount || 0} rows</span>
              <div style="display: flex; gap: 6px; align-items: center;">
                <span class="badge badge-green">✓ Verified & Grounded</span>
                <button type="button" class="btn btn-secondary btn-xs ce-btn-open-sql-lab" style="font-size: 10px; color: #00F5FF;">
                  View Table & Chart in SQL Lab →
                </button>
              </div>
            </div>
          `;
        }

        html += `</div>`;
      }
    }

    stream.innerHTML = html;

    stream.querySelectorAll('.ce-options-grid .ce-option-chip').forEach(btn => {
      btn.onclick = () => {
        if (onSelectOption) onSelectOption(btn.dataset.choice);
      };
    });

    stream.querySelectorAll('.ce-btn-copy-sql').forEach(btn => {
      btn.onclick = () => {
        if (onCopySql) onCopySql(btn.dataset.sql);
      };
    });

    stream.querySelectorAll('.ce-btn-run-sql').forEach(btn => {
      btn.onclick = () => {
        if (onExecuteSql) onExecuteSql(btn.dataset.sql);
      };
    });

    stream.querySelectorAll('.ce-btn-open-sql-lab').forEach(btn => {
      btn.onclick = () => {
        const sql = btn.dataset.sql;
        if (window.dataverseApp && window.dataverseApp.goToSqlLab) {
          window.dataverseApp.goToSqlLab(sql);
        } else {
          const tabBtn = document.getElementById('nav-btn-sql-lab');
          if (tabBtn) tabBtn.click();
        }
      };
    });

    stream.querySelectorAll('.ce-btn-apply-clean').forEach(btn => {
      btn.onclick = () => {
        if (onApplyCleaning) onApplyCleaning();
      };
    });

    stream.querySelectorAll('.ce-btn-cancel-clean').forEach(btn => {
      btn.onclick = () => {
        if (onCancelCleaning) onCancelCleaning();
      };
    });

    stream.querySelectorAll('.ce-btn-undo-clean').forEach(btn => {
      btn.onclick = () => {
        if (onUndoCleaning) onUndoCleaning();
      };
    });

    stream.querySelectorAll('.ce-btn-revert-original').forEach(btn => {
      btn.onclick = () => {
        if (onRevertOriginal) onRevertOriginal();
      };
    });

    setTimeout(() => { stream.scrollTop = stream.scrollHeight; }, 40);
  }

  setConversationAnalyzing(isAnalyzing) {
    const stream = document.getElementById('ce-message-stream');
    const existing = document.getElementById('ce-typing-indicator');
    if (existing) existing.remove();

    const statusBadge = document.getElementById('ce-status-badge');
    const statusText = document.getElementById('ce-status-text');

    if (isAnalyzing) {
      if (statusText) statusText.textContent = 'Analyzing Intent...';
      if (statusBadge) statusBadge.className = 'ce-status-badge amber';

      if (stream) {
        const ind = document.createElement('div');
        ind.id = 'ce-typing-indicator';
        ind.className = 'ce-typing-indicator';
        ind.innerHTML = `
          <div class="ce-typing-dots">
            <span class="ce-dot"></span>
            <span class="ce-dot"></span>
            <span class="ce-dot"></span>
          </div>
          <span>Analyzing schema & evaluating ambiguity...</span>
        `;
        stream.appendChild(ind);
        stream.scrollTop = stream.scrollHeight;
      }
    } else {
      if (statusText) statusText.textContent = 'Online • Grounded in Schema';
      if (statusBadge) statusBadge.className = 'ce-status-badge';
    }
  }

  renderIntentSummary(intentSummary) {
    const originalEl = document.getElementById('ce-intent-original');
    const statusEl = document.getElementById('ce-intent-status');
    const goalEl = document.getElementById('ce-intent-goal');

    if (originalEl) {
      originalEl.textContent = intentSummary.originalQuestion || 'None active';
      originalEl.title = intentSummary.originalQuestion || '';
    }

    if (statusEl) {
      if (intentSummary.status === 'ambiguous') {
        statusEl.className = 'badge badge-amber';
        statusEl.textContent = 'Ambiguity Detected';
      } else if (intentSummary.status === 'resolved') {
        statusEl.className = 'badge badge-green';
        statusEl.textContent = 'Intent Resolved';
      } else if (intentSummary.status === 'analyzing') {
        statusEl.className = 'badge badge-cyan';
        statusEl.textContent = 'Analyzing...';
      } else if (intentSummary.status === 'error') {
        statusEl.className = 'badge badge-error';
        statusEl.textContent = 'Error';
      } else {
        statusEl.className = 'badge badge-cyan';
        statusEl.textContent = 'Ready';
      }
    }

    if (goalEl) {
      if (intentSummary.chosenInterpretation) {
        goalEl.textContent = intentSummary.chosenInterpretation;
      } else if (intentSummary.reasoning) {
        goalEl.textContent = intentSummary.reasoning;
      } else {
        goalEl.textContent = intentSummary.status === 'analyzing' ? 'Processing...' : 'Awaiting question';
      }
      goalEl.title = goalEl.textContent;
    }
  }

  renderSchemaHints(tables, schemaOverview, onTagClick) {
    const container = document.getElementById('ce-schema-tags');
    if (!container) return;

    if (!tables || tables.length === 0 || !schemaOverview) {
      container.innerHTML = `<span class="ce-schema-hint-tag">Upload dataset to view columns</span>`;
      return;
    }

    const tags = [];
    for (const table of tables) {
      const cols = schemaOverview[table] || [];
      for (const col of cols) {
        tags.push({ table, col: typeof col === 'string' ? col : col.column });
      }
    }

    container.innerHTML = tags.slice(0, 15).map(t => `
      <span class="ce-schema-hint-tag" data-tag="${this.escapeHtml(t.col)}" title="Table: ${this.escapeHtml(t.table)}">
        ${this.escapeHtml(t.col)}
      </span>
    `).join('');

    container.querySelectorAll('.ce-schema-hint-tag').forEach(tagEl => {
      tagEl.onclick = () => {
        if (onTagClick) onTagClick(tagEl.dataset.tag);
      };
    });
  }

  renderInsightsStudio({ dataset, profileData, chartData, results, onNavigateView } = {}) {
    const hubBody = document.getElementById('insights-hub-body');
    const badge = document.getElementById('insights-dataset-badge');
    if (!hubBody) return;

    const isLoaded = Boolean(dataset && (dataset.isLoaded || dataset.is_loaded));
    if (!isLoaded) {
      hubBody.innerHTML = `
        <div class="insights-placeholder" id="insights-placeholder" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; text-align: center; color: var(--text-muted); padding: 40px 20px;">
          <div style="width: 54px; height: 54px; border-radius: 50%; background: rgba(0, 245, 255, 0.1); border: 1px solid rgba(0, 245, 255, 0.35); display: flex; align-items: center; justify-content: center; color: #00F5FF; box-shadow: 0 0 20px rgba(0, 245, 255, 0.2);">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
          </div>
          <strong style="color: #FFFFFF; font-size: 15px; letter-spacing: -0.01em;">Awaiting Active Dataset Ingestion</strong>
          <p style="font-size: 12.5px; max-width: 460px; line-height: 1.5; color: var(--text-secondary);">
            Drop a CSV, Excel (.xlsx), or SQLite database into the Data Explorer on the left to unlock instant executive KPI metrics, automated distribution health diagnostics, and multi-series visual charts.
          </p>
        </div>
      `;
      if (badge) {
        badge.textContent = 'No Dataset Active';
        badge.className = 'badge badge-secondary';
      }
      return;
    }

    const tables = dataset.tables || [];
    if (badge) {
      badge.textContent = `${dataset.filename || 'Active Dataset'} (${tables.length} table${tables.length !== 1 ? 's' : ''})`;
      badge.className = 'badge badge-cyan';
    }

    const tableCount = tables.length;
    let totalRows = results && results.rowCount ? results.rowCount : (profileData && profileData.total_rows ? profileData.total_rows : 'Ready');
    let totalCols = 0;
    const colList = [];
    if (dataset.schemaOverview) {
      Object.entries(dataset.schemaOverview).forEach(([tName, cols]) => {
        totalCols += cols.length;
        cols.forEach(c => {
          colList.push({
            table: tName,
            name: typeof c === 'string' ? c : c.column,
            type: typeof c === 'string' ? 'INFERRED' : (c.type || 'TEXT')
          });
        });
      });
    }

    let html = `
      <!-- 1. Executive Telemetry KPI Grid -->
      <div class="insights-kpi-grid">
        <div class="insights-kpi-card">
          <span class="kpi-label">Indexed Records</span>
          <div class="kpi-value-row">
            <span class="kpi-value">${this.escapeHtml(String(totalRows))}</span>
            <span class="badge badge-green">✓ Active Rows</span>
          </div>
          <span class="kpi-subtext">Table: ${this.escapeHtml(dataset.tables[0] || 'Default')}</span>
        </div>

        <div class="insights-kpi-card violet">
          <span class="kpi-label">Schema Attributes</span>
          <div class="kpi-value-row">
            <span class="kpi-value">${totalCols}</span>
            <span class="badge badge-violet">Indexed</span>
          </div>
          <span class="kpi-subtext">Across ${tableCount} database table(s)</span>
        </div>

        <div class="insights-kpi-card emerald">
          <span class="kpi-label">Data Completeness</span>
          <div class="kpi-value-row">
            <span class="kpi-value">100%</span>
            <span class="badge badge-green">Zero-Loss</span>
          </div>
          <span class="kpi-subtext">High integrity schema detected</span>
        </div>

        <div class="insights-kpi-card magenta">
          <span class="kpi-label">Analytics Pipeline</span>
          <div class="kpi-value-row">
            <span class="kpi-value">SQLite 3</span>
            <span class="badge badge-magenta">In-Memory</span>
          </div>
          <span class="kpi-subtext">Strict session isolation active</span>
        </div>
      </div>

      <!-- 2. Column Diagnostics & Quality Matrix -->
      <div style="margin-top: 6px;">
        <div class="insights-section-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00F5FF" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          <span>Column Schema Telemetry & Diagnostics</span>
        </div>
        <table class="insights-diagnostics-table">
          <thead>
            <tr>
              <th>Column Name</th>
              <th>Origin Table</th>
              <th>Inferred Type</th>
              <th>Quality Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${colList.map(c => `
              <tr>
                <td style="font-weight: 500; color: #00F5FF; font-family: var(--font-mono);">${this.escapeHtml(c.name)}</td>
                <td>${this.escapeHtml(c.table)}</td>
                <td><span class="badge badge-violet" style="font-family: var(--font-mono); font-size: 10px;">${this.escapeHtml(c.type)}</span></td>
                <td><span class="badge badge-green" style="font-size: 10px;">✓ Validated</span></td>
                <td>
                  <button type="button" class="btn btn-secondary btn-xs insights-query-col-btn" data-col="${this.escapeHtml(c.name)}" style="font-size: 10px; color: #00F5FF;">
                    Ask Query →
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

    const chartImg = chartData && (chartData.base64Image || chartData.base64_image);
    if (chartImg) {
      html += `
        <!-- 3. Automated Visual Intelligence Chart -->
        <div style="margin-top: 8px;">
          <div class="insights-section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9D4DFF" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
            <span>Automated Visual Chart Analytics</span>
          </div>
          <div class="insights-chart-preview-box">
            <img class="insights-chart-preview-img" src="${chartImg.startsWith('data:') ? chartImg : `data:image/png;base64,${chartImg}`}" alt="Visual Chart Preview" />
          </div>
        </div>
      `;
    }

    hubBody.innerHTML = html;

    hubBody.querySelectorAll('.insights-query-col-btn').forEach(btn => {
      btn.onclick = () => {
        const col = btn.dataset.col;
        if (onNavigateView) onNavigateView('query', `Summarize distribution for ${col}`);
      };
    });
  }

  // =========================================================================
  // Relational Schema Visualizer Studio & ER Diagram Methods (Phase 4)
  // =========================================================================

  applySchemaTransform(zoom, panX, panY) {
    const canvas = document.getElementById('schema-canvas');
    const zoomText = document.getElementById('schema-zoom-level');
    if (canvas) {
      canvas.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
    }
    if (zoomText) {
      zoomText.textContent = `${Math.round(zoom * 100)}%`;
    }
  }

  formatRelationshipCount(conf = 0, inf = 0, rej = 0) {
    const parts = [
      `${conf || 0} Confirmed`,
      `${inf || 0} Inferred`
    ];
    if (rej > 0) {
      parts.push(`${rej} Rejected`);
    }
    return parts.join(' • ');
  }

  renderSchemaStudio(schemaData, callbacks = {}) {
    const tableBadge = document.getElementById('schema-table-count-badge');
    const relBadge = document.getElementById('schema-rel-count-badge');
    const emptyState = document.getElementById('schema-canvas-empty');
    const nodesLayer = document.getElementById('schema-nodes-layer');
    const svgGroup = document.getElementById('schema-svg-connections');

    if (tableBadge) {
      tableBadge.textContent = `${schemaData.tables ? schemaData.tables.length : 0} Tables`;
    }
    if (relBadge) {
      const rels = schemaData.relationships || [];
      const conf = schemaData.confirmedCount ?? schemaData.confirmed_count ?? rels.filter(r => r.status === 'confirmed').length;
      const inf = schemaData.inferredCount ?? schemaData.inferred_count ?? rels.filter(r => r.status === 'inferred' || (!r.status && !r.user_confirmed && !r.user_rejected)).length;
      const rej = schemaData.rejectedCount ?? schemaData.rejected_count ?? rels.filter(r => r.status === 'rejected').length;
      relBadge.textContent = this.formatRelationshipCount(conf, inf, rej);
    }

    if (!schemaData.tables || schemaData.tables.length === 0) {
      if (emptyState) emptyState.style.display = 'flex';
      if (nodesLayer) nodesLayer.innerHTML = '';
      if (svgGroup) svgGroup.innerHTML = '';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

    // 1. Assign auto-grid positions for any table not yet positioned
    const numCols = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(schemaData.tables.length))));
    schemaData.tables.forEach((t, i) => {
      if (!schemaData.tablePositions || !schemaData.tablePositions[t.table_name]) {
        const colIdx = i % numCols;
        const rowIdx = Math.floor(i / numCols);
        const x = 50 + colIdx * 340;
        const y = 50 + rowIdx * 300;
        if (callbacks.onSetTablePosition) {
          callbacks.onSetTablePosition(t.table_name, x, y);
        }
      }
    });

    // 2. Render Draggable Table Nodes
    if (nodesLayer) {
      nodesLayer.innerHTML = schemaData.tables.map(table => {
        const pos = (schemaData.tablePositions && schemaData.tablePositions[table.table_name]) || { x: 50, y: 50 };
        const isSelected = schemaData.selectedTable === table.table_name;

        return `
          <div class="schema-table-node ${isSelected ? 'selected' : ''}" id="schema-node-${this.escapeHtml(table.table_name)}" data-table="${this.escapeHtml(table.table_name)}" style="left: ${pos.x}px; top: ${pos.y}px;">
            <div class="table-node-header" data-drag-handle="true">
              <div class="table-node-title">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00F5FF" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18M9 21V9"></path></svg>
                <span class="table-node-name">${this.escapeHtml(table.table_name)}</span>
              </div>
              <span class="badge badge-cyan" style="font-size: 9.5px; padding: 1px 5px;">${table.row_count} rows</span>
            </div>
            <div class="table-node-columns">
              ${table.columns.map(c => {
                const isPk = c.is_pk;
                const isFk = c.is_fk;
                const isInferredFk = !isPk && !isFk && c.name.toLowerCase().endsWith('_id');
                const shortType = (c.data_type || 'TEXT').split('(')[0].toUpperCase();

                return `
                  <div class="table-col-row ${isPk ? 'is-pk' : ''} ${isFk ? 'is-fk' : ''}" data-col="${this.escapeHtml(c.name)}">
                    <span class="col-name">${this.escapeHtml(c.name)}</span>
                    <div class="col-meta-cluster">
                      ${isPk ? '<span class="badge-pk" title="Primary Key">PK</span>' : ''}
                      ${isFk ? '<span class="badge-fk" title="Foreign Key">FK</span>' : ''}
                      ${isInferredFk ? '<span class="badge-fk-inferred" title="Inferred Key Candidate">FK?</span>' : ''}
                      <span class="col-type-tag">${this.escapeHtml(shortType)}</span>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        `;
      }).join('');

      // Attach Node Drag & Click Listeners
      nodesLayer.querySelectorAll('.schema-table-node').forEach(nodeEl => {
        const tblName = nodeEl.dataset.table;

        // Click to select table
        nodeEl.addEventListener('click', (e) => {
          if (nodeEl._wasDragged) {
            nodeEl._wasDragged = false;
            return;
          }
          if (callbacks.onSelectTable) {
            callbacks.onSelectTable(tblName);
          }
        });

        // Pointer-based dragging
        const headerEl = nodeEl.querySelector('.table-node-header');
        if (headerEl) {
          headerEl.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            nodeEl._wasDragged = false;
            const startX = e.clientX;
            const startY = e.clientY;
            const initialLeft = parseFloat(nodeEl.style.left) || 0;
            const initialTop = parseFloat(nodeEl.style.top) || 0;
            const currentZoom = (schemaData.zoom || 1.0);

            const onPointerMove = (moveEvt) => {
              const dx = (moveEvt.clientX - startX) / currentZoom;
              const dy = (moveEvt.clientY - startY) / currentZoom;
              if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
                nodeEl._wasDragged = true;
              }
              const newLeft = Math.round(initialLeft + dx);
              const newTop = Math.round(initialTop + dy);
              nodeEl.style.left = `${newLeft}px`;
              nodeEl.style.top = `${newTop}px`;

              if (callbacks.onSetTablePosition) {
                callbacks.onSetTablePosition(tblName, newLeft, newTop);
              }
              // Dynamically re-render SVG paths during drag
              this._renderSvgConnectors(schemaData, callbacks);
            };

            const onPointerUp = () => {
              window.removeEventListener('pointermove', onPointerMove);
              window.removeEventListener('pointerup', onPointerUp);
            };

            window.addEventListener('pointermove', onPointerMove);
            window.addEventListener('pointerup', onPointerUp);
          });
        }
      });
    }

    // 3. Render SVG Connector Paths
    this._renderSvgConnectors(schemaData, callbacks);

    // 4. Update Inspector Selection Pane
    this.renderSchemaInspectorSelection(schemaData, callbacks);

    // 5. Update Relationships Manager Pane
    this.renderSchemaRelationshipManager(schemaData, callbacks);

    // 6. Update Join Builder Form Options
    this.renderSchemaJoinBuilder(schemaData, callbacks);
  }

  _renderSvgConnectors(schemaData, callbacks = {}) {
    const svgGroup = document.getElementById('schema-svg-connections');
    if (!svgGroup) return;

    if (!schemaData.relationships || schemaData.relationships.length === 0) {
      svgGroup.innerHTML = '';
      return;
    }

    const nodeWidth = 260;
    const headerHeight = 34;
    const rowHeight = 24;

    const pathsHtml = schemaData.relationships.map(rel => {
      if (rel.status === 'rejected' && schemaData.filter !== 'rejected' && schemaData.filter !== 'all') {
        return '';
      }

      const srcTbl = schemaData.tables.find(t => t.table_name === rel.source_table);
      const tgtTbl = schemaData.tables.find(t => t.table_name === rel.target_table);
      if (!srcTbl || !tgtTbl) return '';

      const srcPos = (schemaData.tablePositions && schemaData.tablePositions[rel.source_table]) || { x: 50, y: 50 };
      const tgtPos = (schemaData.tablePositions && schemaData.tablePositions[rel.target_table]) || { x: 390, y: 50 };

      // Calculate column vertical offsets
      const srcColIdx = Math.max(0, srcTbl.columns.findIndex(c => c.name === rel.source_column));
      const tgtColIdx = Math.max(0, tgtTbl.columns.findIndex(c => c.name === rel.target_column));

      const srcY = srcPos.y + headerHeight + (srcColIdx * rowHeight) + (rowHeight / 2);
      const tgtY = tgtPos.y + headerHeight + (tgtColIdx * rowHeight) + (rowHeight / 2);

      let x1, x2;
      if (srcPos.x < tgtPos.x) {
        x1 = srcPos.x + nodeWidth;
        x2 = tgtPos.x;
      } else {
        x1 = srcPos.x;
        x2 = tgtPos.x + nodeWidth;
      }

      const dx = Math.max(40, Math.abs(x2 - x1) * 0.45);
      const cx1 = srcPos.x < tgtPos.x ? x1 + dx : x1 - dx;
      const cx2 = srcPos.x < tgtPos.x ? x2 - dx : x2 + dx;

      const pathD = `M ${x1} ${srcY} C ${cx1} ${srcY}, ${cx2} ${tgtY}, ${x2} ${tgtY}`;

      const mx = (x1 + x2) / 2;
      const my = (srcY + tgtY) / 2;

      const isSelected = schemaData.selectedRelationship === rel.id;
      const isConfirmed = rel.status === 'confirmed';
      const isRejected = rel.status === 'rejected';

      const shortCard = rel.cardinality === 'one-to-one' ? '1:1' : (rel.cardinality === 'many-to-many' ? 'N:M' : '1:N');
      const markerId = isConfirmed ? 'marker-arrow-cyan' : 'marker-arrow-violet';

      return `
        <g class="schema-connector-group ${isSelected ? 'selected' : ''}" data-rel-id="${this.escapeHtml(rel.id)}">
          <!-- Invisible wide stroke for easy clicking/hovering -->
          <path class="connector-hit-area" d="${pathD}" />
          <!-- Visible stylized path -->
          <path
            class="schema-connector-line ${isConfirmed ? 'confirmed' : (isRejected ? 'rejected' : 'inferred')} ${isSelected ? 'selected' : ''}"
            d="${pathD}"
            marker-end="url(#${markerId})"
          />
          <!-- Cardinality Badge on Midpoint -->
          <g class="cardinality-badge" transform="translate(${mx}, ${my})">
            <rect class="cardinality-badge-bg ${isConfirmed ? 'confirmed' : 'inferred'}" x="-13" y="-8" width="26" height="16" rx="4" />
            <text class="cardinality-badge-text" text-anchor="middle" y="3.5">${shortCard}</text>
          </g>
        </g>
      `;
    }).join('');

    svgGroup.innerHTML = pathsHtml;

    // Attach click listener on connector groups
    svgGroup.querySelectorAll('.schema-connector-group').forEach(groupEl => {
      const relId = groupEl.dataset.relId;
      groupEl.addEventListener('click', (e) => {
        e.stopPropagation();
        if (callbacks.onSelectRelationship) {
          callbacks.onSelectRelationship(relId);
        }
      });
    });
  }

  renderSchemaInspectorSelection(schemaData, callbacks = {}) {
    const hintEl = document.getElementById('inspector-empty-hint');
    const contentEl = document.getElementById('inspector-selection-content');
    if (!hintEl || !contentEl) return;

    if (!schemaData.selectedTable && !schemaData.selectedRelationship) {
      hintEl.style.display = 'flex';
      contentEl.style.display = 'none';
      contentEl.innerHTML = '';
      return;
    }

    hintEl.style.display = 'none';
    contentEl.style.display = 'block';

    // 1. Table Selection Details
    if (schemaData.selectedTable) {
      const table = schemaData.tables.find(t => t.table_name === schemaData.selectedTable);
      if (!table) return;

      const pkCols = table.columns.filter(c => c.is_pk).map(c => c.name);
      const connectedRels = (schemaData.relationships || []).filter(
        r => r.source_table === table.table_name || r.target_table === table.table_name
      );

      contentEl.innerHTML = `
        <div class="inspector-card">
          <div class="inspector-card-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00F5FF" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18M9 21V9"></path></svg>
              <h4 style="font-size: 13.5px; font-weight: 500; color: var(--text-primary); margin: 0;">Table: ${this.escapeHtml(table.table_name)}</h4>
            </div>
            <span class="badge badge-cyan">${table.row_count} rows</span>
          </div>

          <div class="inspector-stats-grid">
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Columns</span>
              <span class="inspector-stat-val">${table.columns.length}</span>
            </div>
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Primary Key</span>
              <span class="inspector-stat-val" style="color: #f59e0b;">${pkCols.length > 0 ? this.escapeHtml(pkCols.join(', ')) : 'None'}</span>
            </div>
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Connections</span>
              <span class="inspector-stat-val" style="color: #9D4DFF;">${connectedRels.length} linked</span>
            </div>
          </div>

          <div class="inspector-section-label">Columns & Diagnostics:</div>
          <div class="inspector-columns-list">
            ${table.columns.map(c => `
              <div class="inspector-col-item">
                <div class="inspector-col-top">
                  <span class="inspector-col-name">${this.escapeHtml(c.name)}</span>
                  <div style="display: flex; gap: 4px;">
                    ${c.is_pk ? '<span class="badge-pk">PK</span>' : ''}
                    ${c.is_fk ? '<span class="badge-fk">FK</span>' : ''}
                    <span class="col-type-tag">${this.escapeHtml(c.data_type)}</span>
                  </div>
                </div>
                <div class="inspector-col-metrics">
                  <span>Nulls: ${(c.null_rate * 100).toFixed(0)}% (${c.null_count})</span>
                  <span>Unique: ${(c.unique_rate * 100).toFixed(0)}% (${c.unique_count})</span>
                </div>
                ${c.sample_values && c.sample_values.length > 0 ? `
                  <div class="inspector-col-samples">
                    Sample: <code>${c.sample_values.slice(0, 3).map(v => this.escapeHtml(String(v))).join(', ')}</code>
                  </div>
                ` : ''}
              </div>
            `).join('')}
          </div>

          <div style="display: flex; gap: 6px; margin-top: 12px;">
            <button type="button" class="btn btn-secondary btn-xs btn-block" id="btn-inspector-query-table">
              Query Table in SQL Lab →
            </button>
          </div>
        </div>
      `;

      const qBtn = contentEl.querySelector('#btn-inspector-query-table');
      if (qBtn) {
        qBtn.onclick = () => {
          if (callbacks.onQueryTable) {
            callbacks.onQueryTable(table.table_name);
          }
        };
      }
    }

    // 2. Relationship Selection Details
    else if (schemaData.selectedRelationship) {
      const rel = schemaData.relationships.find(r => r.id === schemaData.selectedRelationship);
      if (!rel) return;

      const isConfirmed = rel.status === 'confirmed';
      const isRejected = rel.status === 'rejected';
      const isAmbiguous = rel.is_ambiguous;

      contentEl.innerHTML = `
        <div class="inspector-card">
          <div class="inspector-card-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="${isConfirmed ? '#00F5FF' : '#9D4DFF'}" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
              <h4 style="font-size: 13px; font-weight: 500; color: var(--text-primary); margin: 0;">Relationship Details</h4>
            </div>
            <span class="badge ${isConfirmed ? 'badge-cyan' : (isRejected ? 'badge-magenta' : 'badge-violet')}">
              ${rel.status.toUpperCase()}
            </span>
          </div>

          <!-- Endpoints Card -->
          <div class="inspector-relation-endpoints">
            <div class="endpoint-box">
              <span class="endpoint-role">Source (Child / FK)</span>
              <strong class="endpoint-name">${this.escapeHtml(rel.source_table)}.${this.escapeHtml(rel.source_column)}</strong>
            </div>
            <div class="endpoint-arrow">→</div>
            <div class="endpoint-box">
              <span class="endpoint-role">Target (Parent / PK)</span>
              <strong class="endpoint-name">${this.escapeHtml(rel.target_table)}.${this.escapeHtml(rel.target_column)}</strong>
            </div>
          </div>

          <!-- Cardinality & Confidence Meter -->
          <div class="inspector-stats-grid" style="margin-top: 10px;">
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Cardinality</span>
              <span class="inspector-stat-val" style="color: #00F5FF;">${this.escapeHtml(rel.cardinality)}</span>
            </div>
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Confidence</span>
              <span class="inspector-stat-val">${(rel.confidence * 100).toFixed(0)}%</span>
            </div>
            <div class="inspector-stat-item">
              <span class="inspector-stat-label">Value Overlap</span>
              <span class="inspector-stat-val" style="color: #10b981;">${rel.overlap_percentage.toFixed(0)}%</span>
            </div>
          </div>

          ${isAmbiguous ? `
            <div class="inspector-alert-box alert-warning" style="margin-top: 8px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FF3CAC" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              <span>${this.escapeHtml(rel.ambiguity_note || 'Ambiguous relationship matches multiple potential candidate keys.')}</span>
            </div>
          ` : ''}

          <!-- Matching Sample Values -->
          ${rel.sample_matches && rel.sample_matches.length > 0 ? `
            <div style="margin-top: 10px;">
              <span class="inspector-section-label">Matching Key Samples:</span>
              <div class="sample-pills-row">
                ${rel.sample_matches.map(val => `<span class="sample-key-pill">${this.escapeHtml(String(val))}</span>`).join('')}
              </div>
            </div>
          ` : ''}

          <!-- Relationship Action Buttons -->
          <div class="inspector-action-buttons" style="margin-top: 14px; display: flex; flex-direction: column; gap: 6px;">
            ${!isConfirmed ? `
              <button type="button" class="btn btn-primary btn-sm btn-block" id="btn-inspector-confirm-rel">
                ✓ Confirm Relationship
              </button>
            ` : ''}
            ${!isRejected ? `
              <button type="button" class="btn btn-secondary btn-sm btn-block" id="btn-inspector-reject-rel" style="color: #ff3cac;">
                ✕ Reject Relationship
              </button>
            ` : `
              <button type="button" class="btn btn-secondary btn-sm btn-block" id="btn-inspector-restore-rel">
                ↺ Restore Candidate
              </button>
            `}
            <button type="button" class="btn btn-secondary btn-sm btn-block" id="btn-inspector-generate-join" style="color: #00F5FF;">
              ⚡ Generate JOIN Query
            </button>
          </div>
        </div>
      `;

      // Wire action buttons
      const confirmBtn = contentEl.querySelector('#btn-inspector-confirm-rel');
      if (confirmBtn) {
        confirmBtn.onclick = () => {
          if (callbacks.onConfirmRelationship) callbacks.onConfirmRelationship(rel);
        };
      }
      const rejectBtn = contentEl.querySelector('#btn-inspector-reject-rel');
      if (rejectBtn) {
        rejectBtn.onclick = () => {
          if (callbacks.onRejectRelationship) callbacks.onRejectRelationship(rel);
        };
      }
      const restoreBtn = contentEl.querySelector('#btn-inspector-restore-rel');
      if (restoreBtn) {
        restoreBtn.onclick = () => {
          if (callbacks.onConfirmRelationship) callbacks.onConfirmRelationship(rel);
        };
      }
      const joinBtn = contentEl.querySelector('#btn-inspector-generate-join');
      if (joinBtn) {
        joinBtn.onclick = () => {
          if (callbacks.onOpenJoinBuilder) callbacks.onOpenJoinBuilder(rel.source_table, rel.target_table, rel.source_column, rel.target_column);
        };
      }
    }
  }

  renderSchemaRelationshipManager(schemaData, callbacks = {}) {
    const listEl = document.getElementById('relationship-manager-list');
    if (!listEl) return;

    const rels = schemaData.relationships || [];
    if (rels.length === 0) {
      listEl.innerHTML = `
        <div class="empty-tables-hint" style="padding: 16px; text-align: center;">
          <span>No relationships detected yet. Upload tables or define a custom relationship.</span>
        </div>
      `;
      return;
    }

    listEl.innerHTML = rels.map(rel => {
      const isConfirmed = rel.status === 'confirmed';
      const isRejected = rel.status === 'rejected';

      return `
        <div class="rel-manager-row ${rel.status}" data-rel-id="${this.escapeHtml(rel.id)}">
          <div class="rel-row-info">
            <div class="rel-row-endpoints">
              <strong>${this.escapeHtml(rel.source_table)}.${this.escapeHtml(rel.source_column)}</strong>
              <span class="rel-arrow">→</span>
              <strong>${this.escapeHtml(rel.target_table)}.${this.escapeHtml(rel.target_column)}</strong>
            </div>
            <div class="rel-row-meta">
              <span class="badge ${isConfirmed ? 'badge-cyan' : (isRejected ? 'badge-magenta' : 'badge-violet')}" style="font-size: 9px; padding: 1px 4px;">
                ${rel.status}
              </span>
              <span>${rel.cardinality}</span>
              <span>${(rel.confidence * 100).toFixed(0)}% conf</span>
              <span>${rel.overlap_percentage.toFixed(0)}% overlap</span>
            </div>
          </div>
          <div class="rel-row-actions">
            ${!isConfirmed ? `
              <button type="button" class="btn btn-secondary btn-xs btn-rel-confirm" data-rel-id="${this.escapeHtml(rel.id)}" title="Confirm Relationship">
                ✓
              </button>
            ` : ''}
            ${!isRejected ? `
              <button type="button" class="btn btn-secondary btn-xs btn-rel-reject" data-rel-id="${this.escapeHtml(rel.id)}" title="Reject Relationship">
                ✕
              </button>
            ` : ''}
            <button type="button" class="btn btn-secondary btn-xs btn-rel-join" data-rel-id="${this.escapeHtml(rel.id)}" title="Generate JOIN">
              ⚡
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Wire Row Click and Quick Action Buttons
    listEl.querySelectorAll('.rel-manager-row').forEach(row => {
      const relId = row.dataset.relId;
      row.onclick = (e) => {
        if (e.target.closest('button')) return;
        if (callbacks.onSelectRelationship) callbacks.onSelectRelationship(relId);
      };
    });

    listEl.querySelectorAll('.btn-rel-confirm').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const relId = btn.dataset.relId;
        const rel = rels.find(r => r.id === relId);
        if (rel && callbacks.onConfirmRelationship) callbacks.onConfirmRelationship(rel);
      };
    });

    listEl.querySelectorAll('.btn-rel-reject').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const relId = btn.dataset.relId;
        const rel = rels.find(r => r.id === relId);
        if (rel && callbacks.onRejectRelationship) callbacks.onRejectRelationship(rel);
      };
    });

    listEl.querySelectorAll('.btn-rel-join').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const relId = btn.dataset.relId;
        const rel = rels.find(r => r.id === relId);
        if (rel && callbacks.onOpenJoinBuilder) {
          callbacks.onOpenJoinBuilder(rel.source_table, rel.target_table, rel.source_column, rel.target_column);
        }
      };
    });
  }

  renderSchemaJoinBuilder(schemaData, callbacks = {}) {
    const selA = document.getElementById('join-table-a-select');
    const selB = document.getElementById('join-table-b-select');
    const colSelA = document.getElementById('join-col-a-select');
    const colSelB = document.getElementById('join-col-b-select');
    if (!selA || !selB) return;

    const tables = schemaData.tables || [];
    const prevA = selA.value;
    const prevB = selB.value;

    const optionsHtml = tables.map(t => `<option value="${this.escapeHtml(t.table_name)}">${this.escapeHtml(t.table_name)}</option>`).join('');
    selA.innerHTML = optionsHtml;
    selB.innerHTML = optionsHtml;

    if (prevA && tables.some(t => t.table_name === prevA)) selA.value = prevA;
    if (prevB && tables.some(t => t.table_name === prevB) && (tables.length === 1 || prevB !== selA.value)) {
      selB.value = prevB;
    } else if (tables.length > 1) {
      const other = tables.find(t => t.table_name !== selA.value);
      if (other) selB.value = other.table_name;
    }

    const updateColSelects = () => {
      const tblA = tables.find(t => t.table_name === selA.value);
      const tblB = tables.find(t => t.table_name === selB.value);
      if (colSelA && tblA) {
        colSelA.innerHTML = tblA.columns.map(c => `<option value="${this.escapeHtml(c.name)}">${this.escapeHtml(c.name)}</option>`).join('');
      }
      if (colSelB && tblB) {
        colSelB.innerHTML = tblB.columns.map(c => `<option value="${this.escapeHtml(c.name)}">${this.escapeHtml(c.name)}</option>`).join('');
      }
    };

    updateColSelects();
    selA.onchange = updateColSelects;
    selB.onchange = updateColSelects;
  }
}

export const ui = new UIController();
