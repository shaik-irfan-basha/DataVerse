/**
 * frontend/js/api.js - DataVerse Vanilla ES Module API Client
 *
 * SECURITY INVARIANT:
 * Zero credentials/API keys in frontend.
 * Bearer tokens stored in memory with tab-scoped sessionStorage fallback (never localStorage).
 */

const API_BASE = '/api/v1';
const SESSION_STORAGE_KEY = 'dataverse_session';

class ApiClient {
  constructor() {
    this.sessionToken = null;
    this.sessionId = null;
    this._loadSession();
  }

  _loadSession() {
    try {
      const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.sessionToken = parsed.token;
        this.sessionId = parsed.id;
      }
    } catch (e) {
      console.warn("sessionStorage unavailable or blocked:", e);
    }
  }

  _saveSession(id, token) {
    this.sessionId = id;
    this.sessionToken = token;
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ id, token }));
    } catch (e) {
      console.warn("Could not save to sessionStorage:", e);
    }
  }

  _clearSession() {
    this.sessionId = null;
    this.sessionToken = null;
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch (e) {
      // ignore
    }
  }

  async ensureSession() {
    if (this.sessionToken && this.sessionId) {
      return { sessionId: this.sessionId, token: this.sessionToken };
    }
    return this.createSession();
  }

  async createSession() {
    try {
      const res = await fetch(`${API_BASE}/auth/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!res.ok) {
        throw new Error(`Failed to initialize session (${res.status})`);
      }
      const data = await res.json();
      this._saveSession(data.session_id, data.session_token);
      return { sessionId: data.session_id, token: data.session_token };
    } catch (err) {
      console.error("Session creation error:", err);
      throw err;
    }
  }

  async _request(endpoint, options = {}) {
    await this.ensureSession();

    const headers = {
      'Authorization': `Bearer ${this.sessionToken}`,
      'X-Session-Token': this.sessionToken,
      ...(options.headers || {})
    };

    let response;
    try {
      response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers
      });
    } catch (netErr) {
      throw new Error(`Network connection error: ${netErr.message}`);
    }

    // Handle session expiry
    if (response.status === 401) {
      this._clearSession();
      window.dispatchEvent(new CustomEvent('dataverse:session-expired'));
      throw new Error("Session expired. Please retry your request.");
    }

    if (!response.ok) {
      let errorDetail = `Request failed (${response.status})`;
      try {
        const errJson = await response.json();
        if (errJson && errJson.detail) {
          errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
        }
      } catch (_) {
        // Response not JSON
      }
      throw new Error(errorDetail);
    }

    // Check if binary / file response
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/csv') || contentType.includes('application/vnd.openxmlformats') || contentType.includes('application/octet-stream')) {
      return response.blob();
    }

    return response.json();
  }

  // =========================================================================
  // API Methods
  // =========================================================================

  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  }

  async uploadDataset(file) {
    await this.ensureSession();
    const formData = new FormData();
    formData.append('file', file);

    const headers = {
      'Authorization': `Bearer ${this.sessionToken}`,
      'X-Session-Token': this.sessionToken
    };

    const response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      headers,
      body: formData
    });

    if (response.status === 401) {
      this._clearSession();
      window.dispatchEvent(new CustomEvent('dataverse:session-expired'));
      throw new Error("Session expired. Please retry upload.");
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }

    return response.json();
  }

  async getSchema() {
    return this._request('/schema', { method: 'GET' });
  }

  async getSuggestions() {
    return this._request('/suggestions', { method: 'GET' });
  }

  async submitQuery(question, clarificationHistory = '') {
    return this._request('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        clarification_history: clarificationHistory
      })
    });
  }

  async executeManualSql(sql, question = '', datasetName = '') {
    const payload = { sql };
    if (question && typeof question === 'string' && question.trim()) {
      payload.question = question.trim();
    }
    if (datasetName && typeof datasetName === 'string' && datasetName.trim()) {
      payload.dataset_name = datasetName.trim();
    }
    return this._request('/sql/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  async submitClarification(originalQuestion, clarificationQuestion, userResponse, priorHistory = '') {
    const cleanOriginal = (originalQuestion || '').trim();
    const cleanClarification = (clarificationQuestion || '').trim();
    const cleanResponse = (userResponse || '').trim();
    const cleanHistory = typeof priorHistory === 'string' ? priorHistory : '';

    if (!cleanOriginal) {
      throw new Error("Clarification error: Missing required field 'original_question'.");
    }
    if (!cleanClarification) {
      throw new Error("Clarification error: Missing required field 'clarification_question'.");
    }
    if (!cleanResponse) {
      throw new Error("Clarification error: Missing required field 'user_response'.");
    }

    return this._request('/clarify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_question: cleanOriginal,
        clarification_question: cleanClarification,
        user_response: cleanResponse,
        prior_history: cleanHistory
      })
    });
  }

  async getTableProfile(tableName) {
    return this._request(`/profile/${encodeURIComponent(tableName)}`, { method: 'GET' });
  }

  async generateChart(columns, rows, chartType = 'auto', title = '') {
    return this._request('/chart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        columns,
        rows,
        chart_type: chartType,
        title
      })
    });
  }

  async getHistory(limit = 50, datasetName = null, search = null, statusFilter = null) {
    let url = `/history?limit=${limit}`;
    if (datasetName) url += `&dataset_name=${encodeURIComponent(datasetName)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (statusFilter && statusFilter !== 'all') url += `&status_filter=${encodeURIComponent(statusFilter)}`;
    return this._request(url, { method: 'GET' });
  }

  async clearHistory(datasetName = null) {
    let url = '/history';
    if (datasetName) url += `?dataset_name=${encodeURIComponent(datasetName)}`;
    return this._request(url, { method: 'DELETE' });
  }

  async deleteHistoryEntry(entryId) {
    return this._request(`/history/${entryId}`, { method: 'DELETE' });
  }

  async getSavedQueries(datasetName = null, search = null) {
    let url = '/saved-queries';
    const params = [];
    if (datasetName) params.push(`dataset_name=${encodeURIComponent(datasetName)}`);
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    if (params.length > 0) url += `?${params.join('&')}`;
    return this._request(url, { method: 'GET' });
  }

  async saveQuery({ title, sql_query, question = '', dataset_name = '', notes = '' }) {
    return this._request('/saved-queries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        sql_query,
        question,
        dataset_name,
        notes
      })
    });
  }

  async deleteSavedQuery(queryId) {
    return this._request(`/saved-queries/${queryId}`, { method: 'DELETE' });
  }

  async getPreferences() {
    return this._request('/preferences', { method: 'GET' });
  }

  async setPreference(key, value) {
    return this._request('/preferences', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value: String(value) })
    });
  }

  // =========================================================================
  // Conversational Data Cleaning API
  // =========================================================================

  async analyzeCleaning(tableName = null) {
    let url = '/clean/analyze';
    if (tableName) url += `?table_name=${encodeURIComponent(tableName)}`;
    return this._request(url, { method: 'POST' });
  }

  async previewCleaning(prompt, tableName = null) {
    return this._request('/clean/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, table_name: tableName })
    });
  }

  async directPreviewCleaning(operation, params = {}, tableName = null) {
    return this._request('/clean/direct-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation, params, table_name: tableName })
    });
  }

  async applyCleaning() {
    return this._request('/clean/apply', { method: 'POST' });
  }

  async cancelCleaning() {
    return this._request('/clean/cancel', { method: 'POST' });
  }

  async undoCleaning() {
    return this._request('/clean/undo', { method: 'POST' });
  }

  async revertOriginalCleaning(tableName = null) {
    let url = '/clean/revert-original';
    if (tableName) url += `?table_name=${encodeURIComponent(tableName)}`;
    return this._request(url, { method: 'POST' });
  }

  // =========================================================================
  // Relational Schema Visualizer API (Phase 4)
  // =========================================================================

  async getSchemaVisualization() {
    return this._request('/schema/visualize', { method: 'GET' });
  }

  async confirmRelationship(sourceTable, sourceColumn, targetTable, targetColumn, cardinality = 'one-to-many') {
    return this._request('/schema/relationships/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_table: sourceTable,
        source_column: sourceColumn,
        target_table: targetTable,
        target_column: targetColumn,
        cardinality
      })
    });
  }

  async rejectRelationship(sourceTable, sourceColumn, targetTable, targetColumn, cardinality = 'one-to-many') {
    return this._request('/schema/relationships/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_table: sourceTable,
        source_column: sourceColumn,
        target_table: targetTable,
        target_column: targetColumn,
        cardinality
      })
    });
  }

  async createCustomRelationship(sourceTable, sourceColumn, targetTable, targetColumn, cardinality = 'one-to-many') {
    return this._request('/schema/relationships/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_table: sourceTable,
        source_column: sourceColumn,
        target_table: targetTable,
        target_column: targetColumn,
        cardinality
      })
    });
  }

  async deleteRelationshipOverride(sourceTable, sourceColumn, targetTable, targetColumn) {
    const q = new URLSearchParams({
      source_table: sourceTable,
      source_column: sourceColumn,
      target_table: targetTable,
      target_column: targetColumn
    }).toString();
    return this._request(`/schema/relationships?${q}`, { method: 'DELETE' });
  }

  async generateJoinSql(tableA, tableB, joinType = 'INNER JOIN', sourceColumn = null, targetColumn = null) {
    const payload = {
      table_a: tableA,
      table_b: tableB,
      join_type: joinType
    };
    if (sourceColumn && targetColumn) {
      payload.source_column = sourceColumn;
      payload.target_column = targetColumn;
    }
    return this._request('/schema/generate-join', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  async exportResults(format, columns, rows, filename = null) {
    const blob = await this._request('/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        format,
        columns,
        rows,
        filename
      })
    });

    // Trigger browser download
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename || `dataverse_export.${format === 'excel' ? 'xlsx' : format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    return true;
  }

  // =========================================================================
  // AI Provider & BYOK Settings
  // =========================================================================

  async getProviderSettings() {
    return this._request('/settings/ai-provider', { method: 'GET' });
  }

  async saveProviderSettings(provider, model, apiKey = null, validateConnection = true) {
    const payload = { provider, model, validate_connection: validateConnection };
    if (apiKey) payload.api_key = apiKey;
    return this._request('/settings/ai-provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  async removeProviderSettings() {
    return this._request('/settings/ai-provider', { method: 'DELETE' });
  }

  async testProviderConnection(provider, model, apiKey = null) {
    const payload = { provider, model };
    if (apiKey) payload.api_key = apiKey;
    return this._request('/settings/ai-provider/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }
}

export const api = new ApiClient();
