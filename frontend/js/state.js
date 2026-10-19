/**
 * frontend/js/state.js - Reactive In-Memory Application State Container
 */

export class AppState {
  constructor() {
    this.session = {
      id: null,
      isConnected: false,
    };
    this.dataset = {
      isLoaded: false,
      filename: '',
      fileType: '',
      tables: [],
      schemaOverview: {},
      suggestions: []
    };
    this.query = {
      question: '',
      sql: '',
      status: 'idle', // 'idle' | 'loading' | 'success' | 'clarification' | 'error'
      error: '',
      executionTime: 0,
      clarification: null // { question, options, originalQuestion, history }
    };
    this.results = {
      columns: [],
      rows: [],
      rowCount: 0,
      executionTime: 0,
      currentPage: 1,
      rowsPerPage: 50,
      sortColumn: null,
      sortDirection: 'asc'
    };
    this.chart = {
      base64Image: '',
      base64_image: '',
      seriesData: null,
      series_data: null,
      chartType: 'auto',
      chart_type: 'auto',
      title: '',
      error: null,
      sourceQuery: '',
      isLoading: false
    };
    this.profile = {
      table: null,
      data: null,
      isLoading: false,
      error: null
    };
    this.history = {
      entries: [],
      count: 0,
      isLoading: false
    };
    this.activeView = 'table'; // 'table' | 'chart' | 'profile'
    this.activeStudioTab = 'sql-lab'; // 'sql-lab' | 'clarification' | 'insights'

    // Dedicated Clarification Engine Conversational State
    this.conversation = {
      messages: [], // Array of { id, sender: 'user'|'assistant', text, type: 'query'|'clarification'|'result'|'error', options, reasoning, sql, data, executionTime, timestamp }
      intentSummary: {
        originalQuestion: '',
        status: 'idle', // 'idle' | 'analyzing' | 'ambiguous' | 'resolved' | 'error'
        reasoning: '',
        chosenInterpretation: ''
      },
      dialogueHistory: ''
    };

    // Relational Schema Visualizer State (Phase 4)
    this.schemaVisualizer = {
      isLoaded: false,
      datasetName: '',
      tables: [],
      relationships: [],
      confirmedCount: 0,
      inferredCount: 0,
      rejectedCount: 0,
      confirmed_count: 0,
      inferred_count: 0,
      rejected_count: 0,
      selectedTable: null,
      selectedRelationship: null,
      zoom: 1.0,
      pan: { x: 0, y: 0 },
      tablePositions: {},
      filter: 'all', // 'all' | 'confirmed' | 'inferred' | 'rejected'
      isLoading: false
    };

    this._listeners = new Set();
  }

  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  notify(event, data) {
    for (const listener of this._listeners) {
      try {
        listener(event, data, this);
      } catch (e) {
        console.error("State listener error:", e);
      }
    }
  }

  setDataset(uploadData) {
    this.dataset.isLoaded = true;
    this.dataset.filename = uploadData.filename;
    this.dataset.fileType = uploadData.file_type;
    this.dataset.tables = uploadData.tables_created || [];
    this.dataset.schemaOverview = uploadData.schema_overview || {};
    this.dataset.suggestions = uploadData.suggested_questions || [];
    this.clearProfile();
    this.clearChart();
    this.notify('dataset:loaded', this.dataset);
  }

  setSchema(schemaData) {
    this.dataset.isLoaded = schemaData.is_loaded;
    this.dataset.tables = schemaData.tables || [];
    this.dataset.schemaOverview = schemaData.schema_overview || {};
    this.notify('schema:updated', this.dataset);
  }

  setSuggestions(suggestions) {
    this.dataset.suggestions = suggestions || [];
    this.notify('suggestions:updated', this.dataset.suggestions);
  }

  setQueryStarting(question, isClarificationTurn = false) {
    const cleanQ = (question || '').trim();
    this.query.question = cleanQ;
    this.query.status = 'loading';
    this.query.error = '';
    this.query.clarification = null;
    this.clearChart();
    if (!isClarificationTurn) {
      this.query.clarificationHistory = '';
      this.query.clarificationInterpretation = '';
      this.conversation.dialogueHistory = '';

      // Record user query into conversational stream
      if (cleanQ) {
        this.addConversationMessage({
          sender: 'user',
          text: cleanQ,
          type: 'query'
        });
        this.updateIntentSummary({
          originalQuestion: cleanQ,
          status: 'analyzing',
          reasoning: '',
          chosenInterpretation: ''
        });
      }
    }
    this.notify('query:starting', { question: this.query.question });
  }

  setQuerySuccess(data, question = '') {
    this.query.status = 'success';
    this.query.sql = data.sql || '';
    this.query.error = '';
    this.query.clarification = null;

    if (data.clarification_history) {
      this.query.clarificationHistory = data.clarification_history;
      this.conversation.dialogueHistory = data.clarification_history;
      const matches = data.clarification_history.match(/User:\s*([^\n]+)/g);
      if (matches && matches.length > 0) {
        const lastUser = matches[matches.length - 1].replace(/^User:\s*/, '').trim();
        this.query.clarificationInterpretation = lastUser;
      } else {
        this.query.clarificationInterpretation = '';
      }
    } else {
      this.query.clarificationHistory = '';
      this.query.clarificationInterpretation = '';
      this.conversation.dialogueHistory = '';
    }

    if (question && question.trim()) {
      this.query.question = question.trim();
    } else if (data.original_question) {
      this.query.question = data.original_question;
    }

    const execData = data.data || {};
    this.results.columns = execData.columns || [];
    this.results.rows = execData.rows || [];
    this.results.rowCount = execData.row_count || 0;
    this.results.executionTime = execData.execution_time || data.execution_time || 0;
    this.results.currentPage = 1;
    this.results.sortColumn = null;
    this.results.sortDirection = 'asc';

    // Record verified assistant response in conversation stream
    this.addConversationMessage({
      sender: 'assistant',
      text: 'Verified SQL generated and executed through secure pipeline.',
      type: 'result',
      sql: this.query.sql,
      data: execData,
      rowCount: this.results.rowCount,
      executionTime: this.results.executionTime
    });

    this.updateIntentSummary({
      status: 'resolved',
      chosenInterpretation: this.query.clarificationInterpretation || 'Direct Execution'
    });

    this.notify('query:success', { query: this.query, results: this.results });
  }

  setQueryClarification(clarificationData, originalQuestion = '', priorHistory = '') {
    this.query.status = 'clarification';
    const original = (
      originalQuestion ||
      clarificationData.original_question ||
      this.query.question ||
      ''
    ).trim();
    this.query.question = original;

    const question = clarificationData.clarification_question || clarificationData.question || '';
    const options = clarificationData.clarification_options || clarificationData.options || [];
    const history = priorHistory || clarificationData.clarification_history || clarificationData.prior_history || '';
    this.conversation.dialogueHistory = history;

    const payload = {
      ...clarificationData,
      original_question: original,
      clarification_question: question,
      clarification_options: options,
      options: options,
      prior_history: history
    };

    this.query.clarification = payload;

    // Record assistant clarification question in conversational stream
    this.addConversationMessage({
      sender: 'assistant',
      text: question,
      type: 'clarification',
      options: options,
      reasoning: clarificationData.reasoning || '',
      originalQuestion: original,
      priorHistory: history
    });

    this.updateIntentSummary({
      originalQuestion: original,
      status: 'ambiguous',
      reasoning: clarificationData.reasoning || 'Multiple valid metric interpretations detected in schema.',
      chosenInterpretation: 'Awaiting User Selection'
    });

    this.notify('query:clarification', payload);
  }

  setCleaningPreview(previewData, originalQuestion = '', priorHistory = '') {
    this.query.status = 'cleaning_preview';
    const original = (
      originalQuestion ||
      previewData.original_question ||
      this.query.question ||
      ''
    ).trim();
    this.query.question = original;

    const question = previewData.clarification_question || previewData.question || 'Data Cleaning Proposal';
    const preview = previewData.cleaning_preview || previewData;
    const history = priorHistory || previewData.clarification_history || '';
    this.conversation.dialogueHistory = history;

    const payload = {
      ...previewData,
      original_question: original,
      clarification_question: question,
      cleaning_preview: preview,
      prior_history: history
    };

    this.query.clarification = payload;

    // Record cleaning proposal in conversational stream
    this.addConversationMessage({
      sender: 'assistant',
      text: question,
      type: 'cleaning_preview',
      cleaning_preview: preview,
      options: previewData.clarification_options || ["Apply Transformation", "Cancel"],
      reasoning: preview.description || '',
      originalQuestion: original,
      priorHistory: history
    });

    this.updateIntentSummary({
      originalQuestion: original,
      status: 'ambiguous',
      reasoning: preview.description || 'Data transformation proposal ready for preview.',
      chosenInterpretation: 'Awaiting User Confirmation'
    });

    this.notify('query:cleaning_preview', payload);
  }

  setQueryError(errorMsg, sql = '') {
    this.query.status = 'error';
    this.query.error = errorMsg;
    this.query.sql = sql;

    // Record assistant error response in conversation stream
    this.addConversationMessage({
      sender: 'assistant',
      text: errorMsg,
      type: 'error',
      sql: sql
    });

    this.updateIntentSummary({
      status: 'error',
      reasoning: errorMsg
    });

    this.notify('query:error', { error: errorMsg, sql });
  }

  setManualSqlResult(result, executedSql = null) {
    if (executedSql) {
      this.query.sql = executedSql;
    }
    if (result.success) {
      this.clearChart();
      this.query.status = 'success';
      this.query.error = '';
      this.results.columns = result.columns || [];
      this.results.rows = result.rows || [];
      this.results.rowCount = result.row_count || 0;
      this.results.executionTime = result.execution_time || 0;
      this.results.currentPage = 1;

      this.addConversationMessage({
        sender: 'assistant',
        text: 'Manual SQL executed successfully.',
        type: 'result',
        sql: this.query.sql,
        data: result,
        rowCount: this.results.rowCount,
        executionTime: this.results.executionTime
      });

      this.notify('query:success', { query: this.query, results: this.results });
    } else {
      this.clearChart();
      this.query.status = 'error';
      this.query.error = result.error || 'SQL execution failed.';

      this.addConversationMessage({
        sender: 'assistant',
        text: this.query.error,
        type: 'error',
        sql: this.query.sql
      });

      this.notify('query:error', { error: this.query.error, sql: this.query.sql });
    }
  }

  setChartLoading(chartType = 'auto') {
    this.chart.isLoading = true;
    this.chart.error = null;
    this.chart.chartType = chartType;
    this.chart.chart_type = chartType;
    this.notify('chart:loading', { chartType });
  }

  setChart(chartData, sourceQuery = '') {
    const b64 = chartData ? (chartData.base64_image || chartData.base64Image || '') : '';
    const sData = chartData ? (chartData.series_data || chartData.seriesData || null) : null;
    const cType = chartData ? (chartData.chart_type || chartData.chartType || 'auto') : 'auto';
    this.chart.base64Image = b64;
    this.chart.base64_image = b64;
    this.chart.seriesData = sData;
    this.chart.series_data = sData;
    this.chart.chartType = cType;
    this.chart.chart_type = cType;
    this.chart.title = chartData ? (chartData.title || '') : '';
    this.chart.error = null;
    this.chart.sourceQuery = sourceQuery;
    this.chart.isLoading = false;
    this.notify('chart:updated', this.chart);
  }

  setChartError(errorMessage) {
    this.chart.base64Image = '';
    this.chart.base64_image = '';
    this.chart.error = errorMessage;
    this.chart.isLoading = false;
    this.notify('chart:error', { error: errorMessage });
  }

  clearChart() {
    this.chart.base64Image = '';
    this.chart.base64_image = '';
    this.chart.seriesData = null;
    this.chart.series_data = null;
    this.chart.chartType = 'auto';
    this.chart.chart_type = 'auto';
    this.chart.title = '';
    this.chart.error = null;
    this.chart.sourceQuery = '';
    this.chart.isLoading = false;
    this.notify('chart:cleared', null);
  }

  setProfile(table, profileData) {
    this.profile.table = table;
    this.profile.data = profileData;
    this.profile.isLoading = false;
    this.profile.error = null;
    this.notify('profile:updated', this.profile);
  }

  setProfileLoading(table) {
    this.profile.table = table;
    this.profile.isLoading = true;
    this.profile.error = null;
    this.notify('profile:loading', { table });
  }

  setProfileError(table, errorMessage) {
    this.profile.table = table;
    this.profile.data = null;
    this.profile.isLoading = false;
    this.profile.error = errorMessage;
    this.notify('profile:error', { table, error: errorMessage });
  }

  clearProfile() {
    this.profile.table = null;
    this.profile.data = null;
    this.profile.isLoading = false;
    this.profile.error = null;
    this.notify('profile:cleared', null);
  }

  setHistory(historyData) {
    this.history.entries = historyData.entries || [];
    this.history.count = historyData.count || 0;
    this.history.isLoading = false;
    this.notify('history:updated', this.history);
  }

  setActiveView(view) {
    this.activeView = view;
    this.notify('view:changed', view);
  }

  // =========================================================================
  // Studio Navigation & Conversational Methods
  // =========================================================================

  setStudioTab(tab) {
    this.activeStudioTab = tab;
    this.notify('studio:tab-changed', tab);
  }

  addConversationMessage(msg) {
    const message = {
      id: Date.now() + Math.random(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      ...msg
    };
    this.conversation.messages.push(message);
    this.notify('conversation:updated', { messages: this.conversation.messages, lastMessage: message });
    return message;
  }

  updateIntentSummary(intent) {
    this.conversation.intentSummary = {
      ...this.conversation.intentSummary,
      ...intent
    };
    this.notify('conversation:intent-updated', this.conversation.intentSummary);
  }

  clearConversation() {
    this.conversation.messages = [];
    this.conversation.dialogueHistory = '';
    this.conversation.intentSummary = {
      originalQuestion: '',
      status: 'idle',
      reasoning: '',
      chosenInterpretation: ''
    };
    this.notify('conversation:cleared', this.conversation);
  }

  // =========================================================================
  // Relational Schema Visualizer State Methods (Phase 4)
  // =========================================================================

  recalculateRelationshipCounts() {
    const rels = this.schemaVisualizer.relationships || [];
    let conf = 0;
    let inf = 0;
    let rej = 0;
    for (const r of rels) {
      if (r.status === 'confirmed') {
        conf++;
      } else if (r.status === 'rejected') {
        rej++;
      } else {
        inf++;
      }
    }
    this.schemaVisualizer.confirmedCount = conf;
    this.schemaVisualizer.inferredCount = inf;
    this.schemaVisualizer.rejectedCount = rej;
    this.schemaVisualizer.confirmed_count = conf;
    this.schemaVisualizer.inferred_count = inf;
    this.schemaVisualizer.rejected_count = rej;
    return {
      confirmedCount: conf,
      inferredCount: inf,
      rejectedCount: rej,
      confirmed_count: conf,
      inferred_count: inf,
      rejected_count: rej
    };
  }

  setSchemaVisualizerData(data) {
    this.schemaVisualizer.isLoaded = !!data.is_loaded;
    this.schemaVisualizer.datasetName = data.dataset_name || '';
    this.schemaVisualizer.tables = data.tables || [];
    this.schemaVisualizer.relationships = data.relationships || [];
    this.recalculateRelationshipCounts();
    if (this.schemaVisualizer.relationships.length === 0 && (data.confirmed_count !== undefined || data.confirmedCount !== undefined)) {
      const conf = data.confirmed_count ?? data.confirmedCount ?? 0;
      const inf = data.inferred_count ?? data.inferredCount ?? 0;
      const rej = data.rejected_count ?? data.rejectedCount ?? 0;
      this.schemaVisualizer.confirmedCount = conf;
      this.schemaVisualizer.inferredCount = inf;
      this.schemaVisualizer.rejectedCount = rej;
      this.schemaVisualizer.confirmed_count = conf;
      this.schemaVisualizer.inferred_count = inf;
      this.schemaVisualizer.rejected_count = rej;
    }
    this.schemaVisualizer.isLoading = false;
    this.notify('schema-visualizer:updated', this.schemaVisualizer);
  }

  setSchemaSelectedTable(tableName) {
    this.schemaVisualizer.selectedTable = tableName;
    this.schemaVisualizer.selectedRelationship = null;
    this.notify('schema-visualizer:selection-changed', {
      selectedTable: tableName,
      selectedRelationship: null
    });
  }

  setSchemaSelectedRelationship(relId) {
    this.schemaVisualizer.selectedRelationship = relId;
    this.schemaVisualizer.selectedTable = null;
    this.notify('schema-visualizer:selection-changed', {
      selectedTable: null,
      selectedRelationship: relId
    });
  }

  setSchemaZoom(zoom) {
    this.schemaVisualizer.zoom = Math.max(0.4, Math.min(2.5, zoom));
    this.notify('schema-visualizer:view-transformed', {
      zoom: this.schemaVisualizer.zoom,
      pan: this.schemaVisualizer.pan
    });
  }

  setSchemaPan(x, y) {
    this.schemaVisualizer.pan = { x, y };
    this.notify('schema-visualizer:view-transformed', {
      zoom: this.schemaVisualizer.zoom,
      pan: this.schemaVisualizer.pan
    });
  }

  setSchemaTablePosition(tableName, x, y) {
    this.schemaVisualizer.tablePositions[tableName] = { x, y };
  }

  updateRelationshipStatus(relId, status) {
    const rel = this.schemaVisualizer.relationships.find(r => r.id === relId);
    if (rel) {
      rel.status = status;
      if (status === 'confirmed') {
        rel.user_confirmed = true;
        rel.user_rejected = false;
        rel.confidence = 1.0;
      } else if (status === 'rejected') {
        rel.user_rejected = true;
        rel.user_confirmed = false;
      } else {
        rel.user_confirmed = false;
        rel.user_rejected = false;
      }
      this.recalculateRelationshipCounts();
      this.notify('schema-visualizer:relationship-updated', {
        relationship: rel,
        visualizer: this.schemaVisualizer
      });
    }
  }
}

export const state = new AppState();
