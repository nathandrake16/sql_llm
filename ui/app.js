(() => {
  const state = {
    schema: null,
    selectedTable: null,
    activeStage: null,
    trace: {
      schema: null,
      prompt: null,
      attempts: [],
      finalResult: null,
    },
    lastSql: "",
    currentResult: null,
    sortCol: null,
    sortAsc: true,
    history: [],
  };

  const HISTORY_KEY = "sql_llm_history_v1";
  const THEME_KEY   = "sql_llm_theme_v1";

  // ── DOM Refs ──────────────────────────────────────────────────────────────
  const dbPill           = document.getElementById("db-pill");
  const modelPill        = document.getElementById("model-pill");
  const themeToggle      = document.getElementById("theme-toggle");
  const themeIcon        = document.getElementById("theme-icon");
  const schemaFilter     = document.getElementById("schema-filter");
  const tablesList       = document.getElementById("tables-list");
  const erCanvas         = document.getElementById("er-canvas");
  const schemaTablesView = document.getElementById("schema-tables-view");
  const schemaErView     = document.getElementById("schema-er-view");
  const historyList      = document.getElementById("history-list");
  const clearHistoryBtn  = document.getElementById("clear-history");
  const queryForm        = document.getElementById("query-form");
  const questionInput    = document.getElementById("question-input");
  const runBtn           = document.getElementById("run-btn");
  const simulateToggle   = document.getElementById("simulate-error-toggle");
  const pipelineStatus   = document.getElementById("pipeline-status");
  const pipelineTiming   = document.getElementById("pipeline-timing");
  const stageInspector   = document.getElementById("stage-inspector");
  const inspectorTitle   = document.getElementById("inspector-title");
  const inspectorBody    = document.getElementById("inspector-body");
  const closeInspector   = document.getElementById("close-inspector");
  const errorBanner      = document.getElementById("error-banner");
  const sqlBadges        = document.getElementById("sql-badges");
  const sqlOutput        = document.getElementById("sql-output");
  const copySqlBtn       = document.getElementById("copy-sql-btn");
  const rowCountBadge    = document.getElementById("row-count-badge");
  const exportCsvBtn     = document.getElementById("export-csv-btn");
  const resultsTableView = document.getElementById("results-table-view");
  const resultsChartView = document.getElementById("results-chart-view");
  const chartTabBtn      = document.getElementById("chart-tab-btn");
  const chartToolbar     = document.getElementById("chart-toolbar");
  const chartMetricSel   = document.getElementById("chart-metric-select");
  const chartContainer   = document.getElementById("chart-container");
  const tableModal       = document.getElementById("table-modal");
  const modalTitle       = document.getElementById("modal-title");
  const modalBody        = document.getElementById("modal-body");
  const closeModal       = document.getElementById("close-modal");

  // ── Utilities ─────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function highlightSQL(sql) {
    const tokenRe = /(--[^\n]*|'(?:''|[^'])*'|\b\d+(?:\.\d+)?\b|\b(?:SELECT|FROM|WHERE|JOIN|INNER|LEFT|RIGHT|OUTER|ON|AS|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|DESC|ASC|AND|OR|NOT|IN|IS|NULL|DISTINCT|CASE|WHEN|THEN|ELSE|END|WITH|UNION|ALL|BETWEEN|LIKE|EXISTS)\b|\b(?:SUM|COUNT|AVG|MIN|MAX|ROUND|COALESCE|STRFTIME|DATE_TRUNC)\b)/gi;
    let out = "";
    let last = 0;
    let match;
    while ((match = tokenRe.exec(sql)) !== null) {
      out += escapeHtml(sql.slice(last, match.index));
      const tok = match[0];
      if (tok.startsWith("--")) {
        out += `<span class="tok-cmt">${escapeHtml(tok)}</span>`;
      } else if (tok.startsWith("'")) {
        out += `<span class="tok-str">${escapeHtml(tok)}</span>`;
      } else if (/^\d/.test(tok)) {
        out += `<span class="tok-num">${escapeHtml(tok)}</span>`;
      } else if (/^(SUM|COUNT|AVG|MIN|MAX|ROUND|COALESCE|STRFTIME|DATE_TRUNC)$/i.test(tok)) {
        out += `<span class="tok-fn">${escapeHtml(tok.toUpperCase())}</span>`;
      } else {
        out += `<span class="tok-kw">${escapeHtml(tok.toUpperCase())}</span>`;
      }
      last = tokenRe.lastIndex;
    }
    out += escapeHtml(sql.slice(last));
    return out;
  }

  function isNumeric(val) {
    return typeof val === "number" && Number.isFinite(val);
  }

  function formatCell(val) {
    if (val === null || val === undefined) return '<span class="empty-muted">NULL</span>';
    if (typeof val === "number") {
      return Number.isInteger(val) ? val.toLocaleString() : val.toLocaleString(undefined, { maximumFractionDigits: 4 });
    }
    return escapeHtml(val);
  }

  // ── Theme ─────────────────────────────────────────────────────────────────
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
    localStorage.setItem(THEME_KEY, theme);
  }
  applyTheme(localStorage.getItem(THEME_KEY) || "dark");
  themeToggle.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
  });

  // ── Schema Loading & Rendering ────────────────────────────────────────────
  async function loadSchema() {
    try {
      const res = await fetch("/api/schema");
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Failed to load schema");
      state.schema = data;
      dbPill.textContent = `${data.dialect} · ${data.db_name}`;
      modelPill.textContent = `${data.model} (${data.thinking_level})`;
      renderTables();
      renderERDiagram();
    } catch (err) {
      tablesList.innerHTML = `<div class="error-banner">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderTables() {
    if (!state.schema) return;
    const filter = schemaFilter.value.trim().toLowerCase();
    const tables = state.schema.tables.filter((t) => {
      if (!filter) return true;
      return (
        t.name.toLowerCase().includes(filter) ||
        t.columns.some((c) => c.name.toLowerCase().includes(filter))
      );
    });

    if (!tables.length) {
      tablesList.innerHTML = '<div class="empty-muted">No matching tables or columns.</div>';
      return;
    }

    tablesList.innerHTML = tables
      .map((t) => {
        const colsHtml = t.columns
          .map((c) => {
            const pkBadge = c.pk ? '<span class="badge-pk">PK</span>' : "";
            const fkBadge = c.fk
              ? `<span class="badge-fk">FK→${escapeHtml(c.fk.table)}</span>`
              : "";
            return `
              <div class="col-row">
                <span class="col-name">${escapeHtml(c.name)}</span>
                <span class="col-badges">
                  ${pkBadge}${fkBadge}
                  <span class="col-type">${escapeHtml(c.type)}</span>
                </span>
              </div>
            `;
          })
          .join("");

        return `
          <div class="table-card" data-table="${escapeHtml(t.name)}">
            <div class="table-card-head">
              <div class="table-name-wrap">
                <span>▦</span>
                <span>${escapeHtml(t.name)}</span>
              </div>
              <div class="table-actions">
                <span class="row-pill">${t.row_count} rows</span>
                <button type="button" class="preview-mini-btn" data-preview="${escapeHtml(t.name)}">Preview</button>
              </div>
            </div>
            <div class="table-cols">${colsHtml}</div>
          </div>
        `;
      })
      .join("");

    tablesList.querySelectorAll("[data-preview]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openTablePreview(btn.getAttribute("data-preview"));
      });
    });
  }

  function renderERDiagram() {
    if (!state.schema) return;
    const tables = state.schema.tables;
    const colsPerRow = 2;
    const cardW = 136;
    const padX = 16;
    const padY = 14;
    const gapX = 28;
    const gapY = 22;

    // Position table boxes
    const layout = {};
    const rowHeights = [];
    tables.forEach((t, idx) => {
      const row = Math.floor(idx / colsPerRow);
      const col = idx % colsPerRow;
      const h = 28 + t.columns.length * 18 + 8;
      rowHeights[row] = Math.max(rowHeights[row] || 0, h);
      layout[t.name] = { t, row, col, w: cardW, h };
    });

    const rowY = [];
    let accY = padY;
    rowHeights.forEach((rh, r) => {
      rowY[r] = accY;
      accY += rh + gapY;
    });

    Object.values(layout).forEach((node) => {
      node.x = padX + node.col * (cardW + gapX);
      node.y = rowY[node.row];
    });

    const svgW = padX * 2 + colsPerRow * cardW + gapX;
    const svgH = Math.max(240, accY);

    // Build FK connectors
    const edges = [];
    tables.forEach((t) => {
      t.columns.forEach((c, cIdx) => {
        if (!c.fk || !layout[c.fk.table]) return;
        const from = layout[t.name];
        const to   = layout[c.fk.table];
        const targetIdx = Math.max(0, to.t.columns.findIndex((tc) => tc.name === c.fk.column));
        const x1 = from.col <= to.col ? from.x + from.w : from.x;
        const y1 = from.y + 34 + cIdx * 18;
        const x2 = to.col >= from.col ? to.x : to.x + to.w;
        const y2 = to.y + 34 + targetIdx * 18;
        const cx = (x1 + x2) / 2;
        edges.push({ from: t.name, to: c.fk.table, path: `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`, x2, y2 });
      });
    });

    const selected = state.selectedTable;
    const edgeSvg = edges
      .map((e) => {
        const active = selected && (e.from === selected || e.to === selected);
        const stroke = active ? "var(--primary)" : "var(--border-strong)";
        const width  = active ? 2.2 : 1.3;
        const opacity = selected && !active ? 0.35 : 0.9;
        return `<path d="${e.path}" fill="none" stroke="${stroke}" stroke-width="${width}" opacity="${opacity}" />` +
               `<circle cx="${e.x2}" cy="${e.y2}" r="3" fill="${stroke}" opacity="${opacity}" />`;
      })
      .join("");

    const nodesSvg = Object.values(layout)
      .map((n) => {
        const isSel = selected === n.t.name;
        const border = isSel ? "var(--primary)" : "var(--border-strong)";
        const colsSvg = n.t.columns
          .map((c, idx) => {
            const y = n.y + 40 + idx * 18;
            const badge = c.pk ? "🔑 " : c.fk ? "🔗 " : "• ";
            return `<text x="${n.x + 8}" y="${y}" font-size="12" font-family="var(--font-mono)" fill="var(--text-muted)">${badge}${escapeHtml(c.name)}</text>`;
          })
          .join("");

        return `
          <g class="er-node" data-er-table="${escapeHtml(n.t.name)}" style="cursor:pointer;">
            <rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="8" fill="var(--bg-elevated)" stroke="${border}" stroke-width="${isSel ? 2 : 1.2}" />
            <rect x="${n.x}" y="${n.y}" width="${n.w}" height="24" rx="8" fill="var(--bg-subtle)" />
            <text x="${n.x + 8}" y="${n.y + 16}" font-size="12" font-weight="700" font-family="var(--font-mono)" fill="var(--text)">${escapeHtml(n.t.name)}</text>
            ${colsSvg}
          </g>
        `;
      })
      .join("");

    erCanvas.innerHTML = `<svg viewBox="0 0 ${svgW} ${svgH}" width="100%" height="${svgH}" xmlns="http://www.w3.org/2000/svg">${edgeSvg}${nodesSvg}</svg>`;

    erCanvas.querySelectorAll("[data-er-table]").forEach((g) => {
      g.addEventListener("click", () => {
        const name = g.getAttribute("data-er-table");
        state.selectedTable = state.selectedTable === name ? null : name;
        renderERDiagram();
      });
      g.addEventListener("dblclick", () => openTablePreview(g.getAttribute("data-er-table")));
    });
  }

  async function openTablePreview(tableName) {
    modalTitle.textContent = `${tableName} (first 8 rows)`;
    modalBody.innerHTML = '<div class="empty-muted">Loading rows…</div>';
    tableModal.classList.remove("hidden");
    try {
      const res = await fetch(`/api/table/${encodeURIComponent(tableName)}`);
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Failed to preview table");
      modalBody.innerHTML = buildTableHtml(data.columns, data.rows, false);
    } catch (err) {
      modalBody.innerHTML = `<div class="error-banner">${escapeHtml(err.message)}</div>`;
    }
  }

  closeModal.addEventListener("click", () => tableModal.classList.add("hidden"));
  tableModal.addEventListener("click", (e) => {
    if (e.target === tableModal) tableModal.classList.add("hidden");
  });

  // Schema view tabs
  document.querySelectorAll("[data-schema-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-schema-tab");
      document.querySelectorAll("[data-schema-tab]").forEach((b) => b.classList.toggle("active", b === btn));
      schemaTablesView.classList.toggle("hidden", tab !== "tables");
      schemaErView.classList.toggle("hidden", tab !== "er");
    });
  });

  schemaFilter.addEventListener("input", renderTables);

  // ── Pipeline Stepper & Inspector ──────────────────────────────────────────
  function setStageState(stage, stageState) {
    const el = document.querySelector(`.stage-node[data-stage="${stage}"]`);
    if (el) el.setAttribute("data-state", stageState);
  }

  function resetPipeline() {
    ["schema", "prompt", "llm", "execute", "retry"].forEach((s) => setStageState(s, "idle"));
    state.trace = { schema: null, prompt: null, attempts: [], finalResult: null };
    pipelineStatus.className = "status-badge status-idle";
    pipelineStatus.textContent = "Ready";
    pipelineTiming.textContent = "Click any stage to inspect";
  }

  function renderInspector(stage) {
    state.activeStage = stage;
    document.querySelectorAll(".stage-node").forEach((n) => {
      n.classList.toggle("selected", n.getAttribute("data-stage") === stage);
    });

    const t = state.trace;
    let title = "Stage Details";
    let html  = '<div class="empty-muted">Run a query to inspect this stage.</div>';

    if (stage === "schema" && t.schema) {
      title = `1. Schema Extraction (${t.schema.table_count} tables · ${t.schema.duration_ms} ms)`;
      html  = `<pre class="inspector-pre">${escapeHtml(t.schema.schema)}</pre>`;
    } else if (stage === "prompt" && t.prompt) {
      title = `2. Grounded Prompt (${t.prompt.model} · thinking=${t.prompt.thinking_level})`;
      html  = `
        <div style="margin-bottom:8px;"><strong>System Instruction</strong></div>
        <pre class="inspector-pre" style="margin-bottom:10px;">${escapeHtml(t.prompt.system_prompt)}</pre>
        <div style="margin-bottom:8px;"><strong>User Input (Dialect + Schema + Question)</strong></div>
        <pre class="inspector-pre">${escapeHtml(t.prompt.user_prompt)}</pre>
      `;
    } else if ((stage === "llm" || stage === "execute" || stage === "retry") && t.attempts.length) {
      const labels = {
        llm: "3. Gemini Interactions API Attempts",
        execute: "4. SQLite Validation & Execution",
        retry: "5. Agentic Self-Correction Trace",
      };
      title = labels[stage];
      html = t.attempts
        .map((a) => {
          const badgeCls = a.status === "success" ? "status-done" : a.status === "error" ? "status-error" : "status-running";
          const errHtml = a.error
            ? `<div class="error-banner" style="margin-top:8px;">${escapeHtml(a.error)}</div>`
            : "";
          const corrHtml = a.correction_prompt
            ? `<div style="margin-top:8px;font-size:12px;color:var(--warn);"><strong>Chained Correction Prompt (previous_interaction_id):</strong></div><pre class="inspector-pre" style="margin-top:4px;">${escapeHtml(a.correction_prompt)}</pre>`
            : "";
          return `
            <div class="attempt-card">
              <div class="attempt-head">
                <strong>Attempt #${a.attempt}</strong>
                <span class="meta-text">LLM: ${a.llm_ms ?? "…"} ms · SQL: ${a.sql_ms ?? "…"} ms</span>
                <span class="status-badge ${badgeCls}">${escapeHtml(a.status || "running")}</span>
              </div>
              ${a.interaction_id ? `<div class="meta-text" style="margin-bottom:6px;font-family:var(--font-mono);">interaction_id: ${escapeHtml(a.interaction_id)}</div>` : ""}
              ${a.sql ? `<pre class="inspector-pre">${escapeHtml(a.sql)}</pre>` : ""}
              ${errHtml}
              ${corrHtml}
            </div>
          `;
        })
        .join("");
    }

    inspectorTitle.textContent = title;
    inspectorBody.innerHTML  = html;
    stageInspector.classList.remove("hidden");
  }

  document.querySelectorAll(".stage-node").forEach((node) => {
    node.addEventListener("click", () => {
      const stage = node.getAttribute("data-stage");
      if (state.activeStage === stage && !stageInspector.classList.contains("hidden")) {
        stageInspector.classList.add("hidden");
        node.classList.remove("selected");
        state.activeStage = null;
      } else {
        renderInspector(stage);
      }
    });
  });

  closeInspector.addEventListener("click", () => {
    stageInspector.classList.add("hidden");
    document.querySelectorAll(".stage-node").forEach((n) => n.classList.remove("selected"));
    state.activeStage = null;
  });

  // ── Query Execution (NDJSON Stream) ───────────────────────────────────────
  async function runQuery(question) {
    resetPipeline();
    errorBanner.classList.add("hidden");
    runBtn.disabled = true;
    runBtn.querySelector(".btn-label").textContent = "Running…";
    runBtn.querySelector(".btn-spinner").classList.remove("hidden");

    pipelineStatus.className = "status-badge status-running";
    pipelineStatus.textContent = "Running…";
    setStageState("schema", "running");

    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          simulate_error: simulateToggle.checked,
        }),
      });

      if (!res.ok) {
        const errObj = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(errObj.error || `HTTP ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          const ev = JSON.parse(line);
          handlePipelineEvent(ev);
        }
      }
    } catch (err) {
      showError(err.message);
    } finally {
      runBtn.disabled = false;
      runBtn.querySelector(".btn-label").textContent = "Run Query";
      runBtn.querySelector(".btn-spinner").classList.add("hidden");
    }
  }

  function handlePipelineEvent(ev) {
    if (ev.type === "schema") {
      state.trace.schema = ev;
      setStageState("schema", "done");
      setStageState("prompt", "running");
    } else if (ev.type === "prompt") {
      state.trace.prompt = ev;
      setStageState("prompt", "done");
    } else if (ev.type === "llm_start") {
      setStageState("llm", "running");
      state.trace.attempts.push({ attempt: ev.attempt, status: "calling Gemini…" });
    } else if (ev.type === "llm_done") {
      const cur = state.trace.attempts[state.trace.attempts.length - 1];
      if (cur) {
        cur.sql = ev.sql;
        cur.interaction_id = ev.interaction_id;
        cur.llm_ms = ev.duration_ms;
      }
      setStageState("llm", "done");
      state.lastSql = ev.sql;
      sqlOutput.innerHTML = highlightSQL(ev.sql);
      copySqlBtn.disabled = false;
    } else if (ev.type === "sql_start") {
      setStageState("execute", "running");
    } else if (ev.type === "sql_done") {
      const cur = state.trace.attempts[state.trace.attempts.length - 1];
      if (cur) {
        cur.status = "success";
        cur.sql_ms = ev.duration_ms;
      }
      setStageState("execute", "done");
      if (state.trace.attempts.length > 1) {
        setStageState("retry", "done");
      }
    } else if (ev.type === "sql_error") {
      const cur = state.trace.attempts[state.trace.attempts.length - 1];
      if (cur) {
        cur.status = "error";
        cur.error = ev.error;
        cur.sql_ms = ev.duration_ms;
      }
      setStageState("execute", "error");
    } else if (ev.type === "retrying") {
      const cur = state.trace.attempts[state.trace.attempts.length - 1];
      if (cur) cur.correction_prompt = ev.correction_prompt;
      setStageState("retry", "retrying");
      pipelineStatus.className = "status-badge status-retrying";
      pipelineStatus.textContent = `Self-correcting (attempt ${ev.to_attempt})…`;
    } else if (ev.type === "complete") {
      const r = ev.result;
      state.trace.finalResult = r;
      state.trace.attempts = r.attempts;
      renderCompletedResult(r);
      saveHistory(r);
    } else if (ev.type === "error") {
      showError(ev.error);
    }

    if (state.activeStage) {
      renderInspector(state.activeStage);
    }
  }

  function showError(msg) {
    pipelineStatus.className = "status-badge status-error";
    pipelineStatus.textContent = "Failed";
    errorBanner.textContent = msg;
    errorBanner.classList.remove("hidden");
  }

  function renderCompletedResult(r) {
    state.currentResult = r;
    state.sortCol = null;
    state.sortAsc = true;

    const attemptsCount = r.attempts.length;
    const hadRetry = attemptsCount > 1;
    pipelineStatus.className = "status-badge status-done";
    pipelineStatus.textContent = hadRetry ? `Self-corrected (${attemptsCount} attempts)` : "Success";
    pipelineTiming.textContent = `Total ${(r.total_duration_ms / 1000).toFixed(2)}s`;

    setStageState("schema", "done");
    setStageState("prompt", "done");
    setStageState("llm", "done");
    setStageState("execute", "done");
    setStageState("retry", hadRetry ? "done" : "idle");

    sqlOutput.innerHTML = highlightSQL(r.sql);
    copySqlBtn.disabled = false;

    sqlBadges.innerHTML = [
      `<span class="pill">${attemptsCount} attempt${attemptsCount > 1 ? "s" : ""}</span>`,
      `<span class="pill">${(r.total_duration_ms / 1000).toFixed(2)}s</span>`,
    ].join("");

    rowCountBadge.textContent = `${r.rows.length} row${r.rows.length === 1 ? "" : "s"}`;
    exportCsvBtn.disabled = r.rows.length === 0;

    renderResultsTable();
    setupChartControls();

    // Auto-show stage inspector on self-correction so the user can see the retry!
    if (hadRetry) {
      renderInspector("retry");
    }
  }

  // ── Table & Sorting ───────────────────────────────────────────────────────
  function buildTableHtml(columns, rows, sortable = true) {
    if (!rows.length) {
      return '<div class="empty-state">Query executed cleanly, but returned 0 rows.</div>';
    }

    const numericCols = columns.map((_, cIdx) =>
      rows.some((r) => isNumeric(r[cIdx]))
    );

    const headCells = columns
      .map((col, idx) => {
        const indicator = sortable && state.sortCol === idx ? (state.sortAsc ? " ▲" : " ▼") : "";
        const attr = sortable ? `data-sort-col="${idx}"` : "";
        return `<th ${attr}>${escapeHtml(col)}${indicator}</th>`;
      })
      .join("");

    const bodyRows = rows
      .map((row) => {
        const cells = row
          .map((val, cIdx) => `<td class="${numericCols[cIdx] ? "num-cell" : ""}">${formatCell(val)}</td>`)
          .join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");

    return `
      <div class="table-scroll">
        <table class="data-table">
          <thead><tr>${headCells}</tr></thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    `;
  }

  function renderResultsTable() {
    const r = state.currentResult;
    if (!r) return;

    let rows = [...r.rows];
    if (state.sortCol !== null) {
      const idx = state.sortCol;
      const dir = state.sortAsc ? 1 : -1;
      rows.sort((a, b) => {
        const va = a[idx];
        const vb = b[idx];
        if (va === vb) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
        return String(va).localeCompare(String(vb)) * dir;
      });
    }

    resultsTableView.innerHTML = buildTableHtml(r.columns, rows, true);
    resultsTableView.querySelectorAll("[data-sort-col]").forEach((th) => {
      th.addEventListener("click", () => {
        const idx = Number(th.getAttribute("data-sort-col"));
        if (state.sortCol === idx) {
          state.sortAsc = !state.sortAsc;
        } else {
          state.sortCol = idx;
          state.sortAsc = false;
        }
        renderResultsTable();
      });
    });
  }

  // ── SVG Bar Chart ─────────────────────────────────────────────────────────
  function setupChartControls() {
    const r = state.currentResult;
    if (!r || !r.rows.length) {
      chartTabBtn.disabled = true;
      chartContainer.innerHTML = '<div class="empty-state">No rows to visualize.</div>';
      return;
    }

    const numericIdx = [];
    r.columns.forEach((col, i) => {
      if (r.rows.some((row) => isNumeric(row[i]))) numericIdx.push(i);
    });

    if (!numericIdx.length) {
      chartTabBtn.disabled = true;
      chartToolbar.classList.add("hidden");
      chartContainer.innerHTML = '<div class="empty-state">Chart view activates automatically when results include numeric columns.</div>';
      // Switch back to table if user was on chart
      setResultTab("table");
      return;
    }

    chartTabBtn.disabled = false;
    chartMetricSel.innerHTML = numericIdx
      .map((idx) => `<option value="${idx}">${escapeHtml(r.columns[idx])}</option>`)
      .join("");
    chartToolbar.classList.toggle("hidden", numericIdx.length <= 1);
    renderChart();
  }

  function renderChart() {
    const r = state.currentResult;
    if (!r || !r.rows.length) return;

    const metricIdx = Number(chartMetricSel.value || 0);
    // Pick first non-metric column as label (preferring string columns)
    let labelIdx = r.columns.findIndex((_, i) => i !== metricIdx && !isNumeric(r.rows[0][i]));
    if (labelIdx === -1) labelIdx = r.columns.findIndex((_, i) => i !== metricIdx);

    const items = r.rows.slice(0, 15).map((row, idx) => ({
      label: labelIdx !== -1 ? String(row[labelIdx] ?? `Row ${idx + 1}`) : `Row ${idx + 1}`,
      value: Number(row[metricIdx] ?? 0),
    }));

    const maxVal = Math.max(...items.map((d) => Math.abs(d.value)), 1);
    const barH   = 28;
    const gap    = 10;
    const labelW = 165;
    const valW   = 78;
    const width  = 700;
    const plotW  = width - labelW - valW - 20;
    const height = items.length * (barH + gap) + 20;

    const barsSvg = items
      .map((d, i) => {
        const y = 10 + i * (barH + gap);
        const w = Math.max(2, (Math.max(0, d.value) / maxVal) * plotW);
        const shortLabel = d.label.length > 22 ? d.label.slice(0, 21) + "…" : d.label;
        const formatted = Number.isInteger(d.value) ? d.value.toLocaleString() : d.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
        return `
          <g class="chart-bar-group">
            <title>${escapeHtml(d.label)}: ${formatted}</title>
            <text x="${labelW - 10}" y="${y + 18}" text-anchor="end" font-size="12" fill="var(--text-muted)">${escapeHtml(shortLabel)}</text>
            <rect x="${labelW}" y="${y}" width="${plotW}" height="${barH}" rx="6" fill="var(--bg-subtle)" />
            <rect x="${labelW}" y="${y}" width="${w}" height="${barH}" rx="6" fill="url(#barGrad)" />
            <text x="${labelW + w + 8}" y="${y + 18}" font-size="12" font-weight="600" font-family="var(--font-mono)" fill="var(--text)">${formatted}</text>
          </g>
        `;
      })
      .join("");

    chartContainer.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#38bdf8" />
            <stop offset="100%" stop-color="#818cf8" />
          </linearGradient>
        </defs>
        ${barsSvg}
      </svg>
    `;
  }

  chartMetricSel.addEventListener("change", renderChart);

  function setResultTab(tab) {
    document.querySelectorAll("[data-result-tab]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-result-tab") === tab);
    });
    resultsTableView.classList.toggle("hidden", tab !== "table");
    resultsChartView.classList.toggle("hidden", tab !== "chart");
  }

  document.querySelectorAll("[data-result-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      setResultTab(btn.getAttribute("data-result-tab"));
    });
  });

  // ── Copy SQL & Export CSV ─────────────────────────────────────────────────
  copySqlBtn.addEventListener("click", async () => {
    const sqlText = state.currentResult?.sql || state.lastSql;
    if (!sqlText) return;
    await navigator.clipboard.writeText(sqlText);
    copySqlBtn.textContent = "Copied!";
    setTimeout(() => (copySqlBtn.textContent = "Copy SQL"), 1400);
  });

  exportCsvBtn.addEventListener("click", () => {
    const r = state.currentResult;
    if (!r || !r.rows.length) return;
    const csvEscape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [r.columns.map(csvEscape).join(","), ...r.rows.map((row) => row.map(csvEscape).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "query_results.csv";
    a.click();
    URL.revokeObjectURL(url);
  });

  // ── History ───────────────────────────────────────────────────────────────
  function loadHistory() {
    try {
      state.history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    } catch {
      state.history = [];
    }
    renderHistory();
  }

  function saveHistory(result) {
    state.history = [result, ...state.history.filter((h) => h.question !== result.question)].slice(0, 12);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history));
    renderHistory();
  }

  function renderHistory() {
    if (!state.history.length) {
      historyList.innerHTML = '<div class="empty-muted">Run a question to build history.</div>';
      return;
    }
    historyList.innerHTML = state.history
      .map((item, i) => `
        <button type="button" class="history-item" data-history-idx="${i}">
          <span class="history-q">${escapeHtml(item.question)}</span>
          <span class="history-meta">
            <span>${item.rows.length} rows</span>
            <span>${item.attempts.length} attempt${item.attempts.length > 1 ? "s" : ""}</span>
          </span>
        </button>
      `)
      .join("");

    historyList.querySelectorAll("[data-history-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = state.history[Number(btn.getAttribute("data-history-idx"))];
        if (!item) return;
        questionInput.value = item.question;
        errorBanner.classList.add("hidden");
        state.trace = {
          schema: { table_count: state.schema?.tables?.length || 5, duration_ms: 0, schema: item.schema },
          prompt: { system_prompt: item.system_prompt, user_prompt: item.initial_user_prompt, model: item.model, thinking_level: "cached" },
          attempts: item.attempts,
          finalResult: item,
        };
        renderCompletedResult(item);
      });
    });
  }

  clearHistoryBtn.addEventListener("click", () => {
    state.history = [];
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  });

  // ── Form & Sample Chips ───────────────────────────────────────────────────
  queryForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = questionInput.value.trim();
    if (!q) return;
    runQuery(q);
  });

  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      queryForm.requestSubmit();
    }
  });

  document.querySelectorAll(".chip[data-q]").forEach((chip) => {
    chip.addEventListener("click", () => {
      questionInput.value = chip.getAttribute("data-q");
      runQuery(questionInput.value);
    });
  });

  // Init
  loadHistory();
  loadSchema();
})();
