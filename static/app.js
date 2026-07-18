/* SQL Genie — frontend controller */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  const state = {
    token: localStorage.getItem("sg_token") || null,
    username: localStorage.getItem("sg_user") || null,
    profile: null,
    connected: false,
    tables: [],
    history: [],
    lastResult: null,
    conversationId: null,
    chartInstance: null,
    messages: [],
  };

  (function loadHistory() {
    try { state.history = JSON.parse(localStorage.getItem("sg_history") || "[]").slice(0, 50); } catch (e) { state.history = []; }
  })();

  const authHeaders = () => (state.token ? { Authorization: "Bearer " + state.token } : {});

  async function api(path, opts) {
    opts = opts || {};
    const headers = Object.assign({}, opts.headers || {});
    if (opts.body && !(opts.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, Object.assign({}, opts, { headers, signal: opts.signal }));
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || ("Request failed: " + res.status);
      throw new Error(msg);
    }
    return data;
  }

  /* ─── Toast ─── */
  let toastTimer = null;
  function toast(msg, kind) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast show" + (kind ? " toast-" + kind : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; el.className = "toast"; }, 3200);
  }

  /* ─── Auth screen logic ─── */
  let authMode = "login";
  function setAuthMode(mode) {
    authMode = mode;
    const isSignup = mode === "signup";
    $("#tab-login").classList.toggle("active", !isSignup);
    $("#tab-signup").classList.toggle("active", isSignup);
    $("#tab-login").setAttribute("aria-selected", String(!isSignup));
    $("#tab-signup").setAttribute("aria-selected", String(isSignup));
    $$('[data-field="name"], [data-field="email"]').forEach((f) => { f.hidden = !isSignup; });
    $("#auth-submit").textContent = isSignup ? "Sign Up" : "Log In";
    $("#f-password").setAttribute("autocomplete", isSignup ? "new-password" : "current-password");
    hideAuthError();
  }

  function showAuthError(msg) {
    const el = $("#auth-error");
    el.textContent = msg;
    el.hidden = false;
  }
  function hideAuthError() { $("#auth-error").hidden = true; }

  async function handleAuthSubmit(e) {
    e.preventDefault();
    hideAuthError();
    const payload = {
      username: $("#f-username").value.trim(),
      password: $("#f-password").value,
    };
    if (authMode === "signup") {
      payload.name = $("#f-name").value.trim();
      payload.email = $("#f-email").value.trim();
    }
    const btn = $("#auth-submit");
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "Working…";
    try {
      const endpoint = authMode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const data = await api(endpoint, { method: "POST", body: payload });
      state.token = data.token;
      state.username = data.username;
      localStorage.setItem("sg_token", data.token);
      localStorage.setItem("sg_user", data.username);
      enterDashboard();
    } catch (err) {
      showAuthError(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  function logout() {
    state.token = null; state.username = null; state.profile = null; state.connected = false;
    localStorage.removeItem("sg_token");
    localStorage.removeItem("sg_user");
    document.body.classList.remove("dashboard-state");
    document.body.classList.add("auth-state");
    $(".auth-wrapper").hidden = false;
    $(".dashboard-wrapper").hidden = true;
    refreshNav();
  }

  function refreshNav() {
    const actions = $("#nav-actions");
    if (state.token) {
      actions.innerHTML =
        '<button class="icon-btn theme-toggle" type="button" id="theme-toggle" aria-label="Toggle dark mode" title="Toggle theme">' +
          '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>' +
          '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>' +
        '</button>' +
        '<button class="btn btn-secondary btn-sm" type="button" data-action="logout">Log Out</button>';
      bindThemeToggle();
    } else {
      actions.innerHTML =
        '<button class="icon-btn theme-toggle" type="button" id="theme-toggle" aria-label="Toggle dark mode" title="Toggle theme">' +
          '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>' +
          '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>' +
        '</button>' +
        '<button class="btn btn-secondary btn-sm" type="button" data-action="show-auth">Log In</button>' +
        '<button class="btn btn-primary btn-sm" type="button" data-action="show-auth">Sign Up</button>';
      bindThemeToggle();
    }
  }

  function enterDashboard() {
    document.body.classList.remove("auth-state");
    document.body.classList.add("dashboard-state");
    $(".auth-wrapper").hidden = true;
    $(".dashboard-wrapper").hidden = false;
    const uname = state.username || "Guest";
    $("#user-name").textContent = uname;
    $("#user-avatar").textContent = (uname[0] || "G").toUpperCase();
    refreshNav();
    loadConnection();
  }

  /* ─── Connection modal ─── */
  function openConnModal() {
    const m = $("#conn-modal");
    m.hidden = false;
    document.body.style.overflow = "hidden";
    $("#conn-error").hidden = true;
    if (state.profile) {
      $("#c-dbtype").value = state.profile.db_type || "sqlite";
      if (state.profile.db_type === "sqlite") {
        $("#c-database-file").value = state.profile.database || "";
      } else {
        $("#c-host").value = state.profile.host || "";
        $("#c-port").value = state.profile.port || "";
        $("#c-username").value = state.profile.username || "";
        $("#c-database").value = state.profile.database || "";
        $("#c-ssl").value = state.profile.ssl_mode || "disable";
      }
    }
    syncConnFields();
    setTimeout(() => $("#c-dbtype").focus(), 50);
  }
  function closeConnModal() {
    $("#conn-modal").hidden = true;
    document.body.style.overflow = "";
  }
  function syncConnFields() {
    const isSqlite = $("#c-dbtype").value === "sqlite";
    $$('[data-sqlite-only]').forEach((f) => { f.hidden = !isSqlite; });
    $$('[data-server-only]').forEach((f) => { f.hidden = isSqlite; });
  }

  async function handleConnSubmit(e) {
    e.preventDefault();
    const dbType = $("#c-dbtype").value;
    const body = { db_type: dbType, ssl_mode: "disable" };
    if (dbType === "sqlite") {
      body.database = $("#c-database-file").value.trim();
      if (!body.database) { showConnError("Enter a database file path."); return; }
    } else {
      body.host = $("#c-host").value.trim();
      body.port = $("#c-port").value ? parseInt($("#c-port").value, 10) : undefined;
      body.username = $("#c-username").value.trim();
      body.password = $("#c-password").value;
      body.database = $("#c-database").value.trim();
      body.ssl_mode = $("#c-ssl").value || "disable";
      if (!body.host || !body.database) { showConnError("Host and database name are required."); return; }
    }
    const btn = $("#conn-save");
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = "Verifying…";
    try {
      const data = await api("/api/auth/connection", {
        method: "POST",
        headers: authHeaders(),
        body,
      });
      state.profile = body;
      state.connected = true;
      updateConnUI(data.tables || []);
      closeConnModal();
      toast("Connection verified and saved.");
      loadSchema();
    } catch (err) {
      showConnError(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = label;
    }
  }
  function showConnError(msg) {
    const el = $("#conn-error");
    el.textContent = msg;
    el.hidden = false;
  }

  function updateConnUI(tables) {
    const dot = $("#conn-dot");
    const label = $("#conn-label");
    const summary = $("#conn-summary");
    if (state.connected && state.profile) {
      dot.className = "status-dot connected";
      label.textContent = "Connected · " + (state.profile.db_type || "db");
      summary.hidden = false;
      summary.textContent = state.profile.database;
      $("#schema-count").textContent = (tables.length || 0) + " tables";
    } else {
      dot.className = "status-dot disconnected";
      label.textContent = "Not connected";
      summary.hidden = true;
    }
  }

  async function loadConnection() {
    try {
      const data = await api("/api/auth/connection", { method: "GET", headers: authHeaders() });
      if (data.success && data.profile) {
        state.profile = data.profile;
        state.connected = true;
        updateConnUI([]);
        loadSchema();
      } else {
        // No saved profile: the backend falls back to the local sandbox.db,
        // so treat that as the active connection instead of forcing a reconnect.
        state.profile = { db_type: "sqlite", database: "sandbox.db" };
        state.connected = true;
        updateConnUI([]);
        loadSchema();
      }
    } catch (e) {
      state.profile = { db_type: "sqlite", database: "sandbox.db" };
      state.connected = true;
      updateConnUI([]);
    }
  }

  async function loadSchema() {
    try {
      const data = await api("/api/schema", { method: "GET", headers: authHeaders() });
      state.tables = data.tables || [];
      renderSchema(data.schema_context || "");
      $("#schema-count").textContent = state.tables.length + " tables";
    } catch (e) {
      renderSchemaError(e.message);
    }
  }

  function renderSchema(context) {
    const list = $("#schema-list");
    if (!state.tables.length) {
      list.innerHTML = '<div class="schema-empty"><span aria-hidden="true">⌗</span><span>No tables found.</span></div>';
      return;
    }
    list.innerHTML = "";
    state.tables.forEach((t) => {
      const node = document.createElement("div");
      node.className = "table-node";
      node.setAttribute("role", "treeitem");
      node.innerHTML =
        '<div class="table-header" tabindex="0" role="button" aria-expanded="false">' +
        '<span class="table-name"><span class="chev" aria-hidden="true">▶</span>' + escapeHtml(t) + '</span>' +
        '<span class="table-count"></span></div>' +
        '<div class="table-cols"></div>';
      const summary = $(".table-header", node);
      summary.addEventListener("click", () => toggleTable(node, summary, t));
      summary.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggleTable(node, summary, t); }
      });
      list.appendChild(node);
    });
  }

  function toggleTable(node, summary, tableName) {
    const open = node.classList.toggle("expanded");
    summary.setAttribute("aria-expanded", String(open));
    if (open) {
      const colList = $(".table-cols", node);
      if (!colList.dataset.loaded) {
        colList.innerHTML = '<div class="col-item"><span class="mono-label">Loading…</span></div>';
        api("/api/schema", { method: "GET", headers: authHeaders() })
          .then((d) => {
            const re = new RegExp("(?:CREATE TABLE|TABLE)\\s+[`'\"]?" + tableName + "[`'\"]?\\s*\\(([\\s\\S]*?)\\)", "i");
            const m = (d.schema_context || "").match(re);
            if (m) {
              const cols = m[1].split(",").map((c) => c.trim().split(/\s+/)[0]).filter(Boolean);
              colList.innerHTML = cols.length
                ? cols.map((c) => '<div class="col-item"><span>' + escapeHtml(c) + '</span></div>').join("")
                : '<div class="col-item"><span class="mono-label">No columns parsed</span></div>';
            } else {
              colList.innerHTML = '<div class="col-item"><span class="mono-label">Schema detail unavailable</span></div>';
            }
            colList.dataset.loaded = "1";
          })
          .catch(() => { colList.innerHTML = '<div class="col-item"><span class="mono-label">Failed</span></div>'; });
      }
    }
  }

  function renderSchemaError(msg) {
    $("#schema-list").innerHTML =
      '<div class="schema-empty"><span aria-hidden="true">⚠</span><span>Could not load schema.</span><span class="mono-label">' +
      escapeHtml(msg) + "</span></div>";
  }

  /* ─── Query execution ─── */
  function setPipelineVisible(show) {
    $("#pipeline-card").hidden = !show;
    if (show) { $("#pipeline-track").innerHTML = ""; }
  }

  // Registry of the genuine multi-agent system (mirrors multi_agent/orchestrator.py).
  // Each agent gets a distinct identity: emoji icon, friendly label, role, accent color,
  // a "working" subtitle shown while it runs, and a terminal subtitle for its result.
  const AGENTS = {
    guardrail: { icon: "◈", label: "Guardrail Agent",   role: "security",   accent: "#f03e3e",
      working: "Screening for destructive / write intent…",
      result:  { blocked: "Blocked — unsafe request rejected", passed: "Cleared — request is read-only" } },
    generator: { icon: "❖", label: "Generator Agent",    role: "sql-author", accent: "#7048e8",
      working: "Drafting SQL from your natural-language request…",
      result:  { done: "SQL draft produced", passed: "SQL draft produced", failed: "Could not generate SQL" } },
    explainer: { icon: "✦", label: "Explainer Agent",    role: "translator", accent: "#1098ad",
      working: "Translating SQL into plain English…",
      result:  { done: "Explanation ready", passed: "Explanation ready", failed: "Could not explain" } },
    critic:    { icon: "◇", label: "Critic Agent",       role: "auditor",    accent: "#1c7ed6",
      working: "Auditing semantics, schema fit & safety…",
      result:  { passed: "Audit passed — SQL is valid", failed: "Audit failed — issues found" } },
    fixer:     { icon: "⌬", label: "Fixer Agent",        role: "repair",     accent: "#f59f00",
      working: "Repairing the query from critic feedback…",
      result:  { done: "Query repaired", passed: "Query repaired", failed: "Repair failed" } },
    formatter: { icon: "❅", label: "Formatter Agent",    role: "presenter",  accent: "#0ca678",
      working: "Composing a plain-language answer…",
      result:  { done: "Answer composed", passed: "Answer composed", failed: "Formatting failed" } },
  };

  function agentKey(agent) {
    const a = (agent || "").toLowerCase();
    if (a.includes("guardrail")) return "guardrail";
    if (a.includes("generator") || a.includes("sql generator")) return "generator";
    if (a.includes("explainer") || a.includes("sql explain")) return "explainer";
    if (a.includes("critic")) return "critic";
    if (a.includes("fixer")) return "fixer";
    if (a.includes("formatter") || a.includes("result")) return "formatter";
    return null;
  }

  function tagClass(status) {
    const s = (status || "").toLowerCase();
    if (s.includes("in progress") || s.includes("generating") || s.includes("evaluating") || s.includes("fixing") || s.includes("running")) return "running";
    if (s === "passed") return "passed";
    if (s === "completed") return "done";
    if (s === "failed" || s === "blocked") return "failed";
    return "done";
  }

  // Render the pipeline as a horizontal deploy-style trace: each agent is a quiet card
  // with a status dot, index, name, working note, and a verdict tag. Cards reveal in
  // order, light up while "working", then resolve — while a thin rail fills left→right.
  function renderPipeline(logs) {
    const track = $("#pipeline-track");
    const rail = $("#pipe-rail-fill");
    track.innerHTML = "";
    const items = logs || [];

    // Collapse multiple log rows into one stage per agent (keep the terminal entry).
    const order = ["guardrail", "generator", "explainer", "critic", "fixer", "formatter"];
    const merged = {};
    items.forEach((l) => {
      const key = agentKey(l.agent);
      if (!key) return;
      const prev = merged[key];
      const terminal = /passed|completed|done|failed|blocked/i.test(l.status || "");
      if (!prev || terminal) merged[key] = Object.assign({ _key: key }, l);
    });
    const stages = Object.values(merged).sort((a, b) => {
      const ia = order.indexOf(a._key), ib = order.indexOf(b._key);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    const card = $("#pipeline-card");
    let resolved = 0;
    const setRail = () => { if (rail) rail.style.width = Math.round((resolved / stages.length) * 100) + "%"; };
    if (rail) rail.style.width = "0%";

    const STEP = 900;     // gap between stages starting
    const WORK = 750;     // how long a stage shows "working" before resolving

    stages.forEach((l, i) => {
      const meta = AGENTS[l._key];
      const finalTag = tagClass(l.status);
      const isBad = (finalTag === "failed" || finalTag === "blocked");
      const li = document.createElement("li");
      li.className = "pipe-stage";
      li.style.setProperty("--accent", meta.accent);
      li.style.animationDelay = (i * 0.12) + "s";
      li.innerHTML =
        '<div class="pipe-top">' +
          '<span class="pipe-dot" aria-hidden="true"></span>' +
          '<span class="pipe-index">' + String(i + 1).padStart(2, "0") + '</span>' +
          '<span class="pipe-name">' + escapeHtml(meta.label) + '</span>' +
        '</div>' +
        '<div class="pipe-sub">' + escapeHtml(meta.working) + '</div>' +
        '<span class="pipe-tag ' + finalTag + '">' + escapeHtml(l.status || "Done") + '</span>';
      track.appendChild(li);

      // 1) Stage enters + shows "working"
      setTimeout(() => {
        li.classList.add("active");
        const tag = li.querySelector(".pipe-tag");
        const sub = li.querySelector(".pipe-sub");
        if (isBad && finalTag === "blocked") {
          tag.className = "pipe-tag blocked"; tag.textContent = "blocked";
          sub.textContent = meta.result.blocked || "Request blocked";
          li.classList.remove("active"); li.classList.add("blocked");
          resolved++; setRail();
        } else {
          tag.className = "pipe-tag running"; tag.textContent = "running";
          sub.textContent = meta.working;
        }
      }, i * STEP);

      // 2) Resolve to terminal verdict
      const resolveAt = i * STEP + (i === 0 && isBad && finalTag === "blocked" ? 0 : WORK);
      setTimeout(() => {
        li.classList.remove("active");
        const tag = li.querySelector(".pipe-tag");
        const sub = li.querySelector(".pipe-sub");
        const map = meta.result || {};
        const verdict = finalTag;
        if (finalTag === "passed") li.classList.add("passed");
        else if (finalTag === "done") li.classList.add("done");
        else if (finalTag === "failed") li.classList.add("failed");
        else if (finalTag === "blocked") li.classList.add("blocked");
        tag.className = "pipe-tag " + verdict; tag.textContent = verdict;
        sub.textContent = map[verdict] || (isBad ? "Step failed" : "Step complete");
        resolved++; setRail();
      }, resolveAt);

      // 3) Final sweep
      setTimeout(() => { if (rail) rail.style.width = "100%"; }, stages.length * STEP + WORK + 150);
    });
  }

  async function runQuery() {
    const q = $("#prompt-input").value.trim();
    if (!q) { toast("Describe your query first.", "error"); $("#prompt-input").focus(); return; }
    if (!state.connected) { toast("Connect a database first.", "error"); openConnModal(); return; }

    const btn = $("#run-query-btn");
    btn.disabled = true;
    btn.textContent = "Generating…";
    $("#error-card").hidden = true;
    $("#results-card").hidden = true;
    setPipelineVisible(true);
    setLoading(true, "Running agents…");
    $("#pipeline-status").textContent = "running…";
    $("#pipeline-status").className = "pipe-status";

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);

    try {
      const payload = { query: q, provider: $("#provider-select").value };
      if (state.conversationId) payload.conversation_id = state.conversationId;
      const data = await api("/api/query", {
        method: "POST",
        headers: authHeaders(),
        body: payload,
        signal: controller.signal,
      });

      renderPipeline(data.logs || []);
      const blocked = data.logs && data.logs.some((l) => /blocked/i.test(l.status || ""));
      const notAnswerable = data.error_type === "not_answerable";
      setLoading(false);
      $("#pipeline-status").textContent = blocked ? "blocked" : (notAnswerable ? "not answerable" : "completed");
      $("#pipeline-status").className = "pipe-status done";

      if (data.conversation_id) state.conversationId = data.conversation_id;
      renderConversation("user", q);
      if (notAnswerable) {
        renderResults(data);
        renderConversation("assistant", data.answer || data.message || "");
        pushHistory(q, data.sql_query || "", data.answer || "", false);
        return;
      }
      if (!data.success) {
        showError(data);
        renderConversation("assistant", data.message || data.error_type || "Error");
        pushHistory(q, data.sql_query || "", data.message || data.error_type || "Error", false);
        return;
      }
      renderResults(data);
      renderConversation("assistant", data.answer || "");
      pushHistory(q, data.sql_query || "", data.answer || "", true);
    } catch (err) {
      setLoading(false);
      $("#pipeline-status").textContent = "failed";
      $("#pipeline-status").className = "pipe-status failed";
      const msg = (err.name === "AbortError")
        ? "The request took too long. Check that your LLM provider is online and try again."
        : (err.message || "Request failed.");
      showError({ error_type: "client", message: msg, logs: [] });
      pushHistory(q, "", msg, false);
    } finally {
      clearTimeout(timeout);
      btn.disabled = false;
      btn.textContent = "Run Query";
    }
  }

  function showError(data) {
    const card = $("#error-card");
    card.hidden = false;
    $("#error-title").textContent = data.error_type === "security_violation" ? "Query blocked by guardrail" : "Query failed";
    $("#error-desc").textContent = data.message || "Something went wrong.";
    const logs = $("#error-logs");
    if (data.logs && data.logs.length) {
      logs.hidden = false;
      logs.innerHTML = (data.logs || [])
        .map((l) => '<div class="log-row"><span class="log-agent">' + escapeHtml(l.agent || "Agent") +
          '</span><span class="log-status failed">' + escapeHtml(l.status || "Failed") + "</span></div>")
        .join("");
    } else {
      logs.hidden = true;
    }
  }

  function newConversation() {
    state.conversationId = null;
    state.messages = [];
    const thread = $("#conv-thread");
    const header = $("#conv-header");
    if (thread) thread.innerHTML = "";
    if (header) header.hidden = true;
    toast("Started a new conversation.");
  }

  function renderConversation(role, body) {
    const header = $("#conv-header");
    const thread = $("#conv-thread");
    if (!thread || !header) return;
    header.hidden = false;
    state.messages.push({ role, body });
    const div = document.createElement("div");
    div.className = "conv-msg " + role;
    div.innerHTML = '<span class="conv-role">' + (role === "user" ? "You" : "SQL") + '</span>' +
      '<span class="conv-body">' + escapeHtml(body || "") + '</span>';
    thread.appendChild(div);
    thread.scrollTop = thread.scrollHeight;
  }

  function renderResults(data) {
    const card = $("#results-card");
    card.hidden = false;

    const notAnswerable = data.error_type === "not_answerable";
    $("#answer-note").hidden = !notAnswerable;

    $("#answer-content").textContent = data.answer || "No answer returned.";

    $("#sql-code").textContent = data.sql_query || "-- no SQL generated";

    // Explanation
    const explCard = $("#explanation-card");
    const explBody = $("#explanation-body");
    if (data.explanation) {
      explCard.hidden = false;
      explBody.textContent = data.explanation;
    } else {
      explCard.hidden = true;
    }

    const res = data.execution_result || {};
    state.lastResult = res.columns && res.data ? res : null;
    const exportBar = $("#export-bar");
    exportBar.hidden = !state.lastResult;

    const tbody = $("#results-table tbody");
    const thead = $("#results-table thead");
    tbody.innerHTML = "";
    thead.innerHTML = "";
    const meta = $("#results-meta");

    const rowData = res.data != null ? res.data : res.rows;
    if (res.columns && rowData) {
      thead.innerHTML = "<tr>" + res.columns.map((c) => "<th>" + escapeHtml(c) + "</th>").join("") + "</tr>";
      if (rowData.length) {
        rowData.forEach((row) => {
          const tr = document.createElement("tr");
          const cells = res.columns.map((c, i) => {
            const v = Array.isArray(row) ? row[i] : row[c];
            return "<td>" + escapeHtml(formatCell(v)) + "</td>";
          });
          tr.innerHTML = cells.join("");
          tbody.appendChild(tr);
        });
        meta.hidden = false;
        meta.textContent = rowData.length + " rows · " + res.columns.length + " cols";
      } else {
        tbody.innerHTML = '<tr><td colspan="100%" class="mono-label">No rows returned.</td></tr>';
        meta.hidden = true;
      }
    } else if (res.message) {
      tbody.innerHTML = '<tr><td colspan="100%" class="mono-label">' + escapeHtml(res.message) + "</td></tr>";
      meta.hidden = true;
    } else {
      $("#results-table-section").hidden = true;
      return;
    }
    $("#results-table-section").hidden = false;
    renderChart(res);
  }

  function renderChart(res) {
    const card = $("#chart-card");
    if (!res.columns || !res.data || res.data.length < 2 || res.columns.length < 2) {
      card.hidden = true;
      return;
    }
    // Destroy previous chart instance
    if (state.chartInstance) { state.chartInstance.destroy(); state.chartInstance = null; }

    const cols = res.columns;
    const rows = res.data;
    const labelCol = cols[0];
    const valueCandidates = cols.slice(1).filter((c, i) => {
      const vals = rows.map((r) => (Array.isArray(r) ? r[i + 1] : r[c]));
      return vals.some((v) => typeof v === "number" || !isNaN(parseFloat(v)));
    });
    if (!valueCandidates.length) { card.hidden = true; return; }

    card.hidden = false;
    const ctx = document.getElementById("result-chart").getContext("2d");
    const labels = rows.map((r) => String(Array.isArray(r) ? r[0] : r[labelCol])).slice(0, 20);
    const isSmall = rows.length <= 5;

    const datasets = valueCandidates.slice(0, 3).map((col, di) => {
      const ci = cols.indexOf(col);
      const data = rows.map((r) => {
        const v = Array.isArray(r) ? r[ci] : r[col];
        return parseFloat(v) || 0;
      }).slice(0, 20);
      const palette = ["#0070f3", "#7928ca", "#ff0080"];
      return {
        label: col,
        data,
        backgroundColor: palette[di] + "33",
        borderColor: palette[di],
        borderWidth: 2,
        borderRadius: 3,
        tension: 0.2,
      };
    });

    state.chartInstance = new Chart(ctx, {
      type: isSmall ? "bar" : "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: datasets.length > 1, labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
        },
        scales: {
          x: { ticks: { font: { size: 10 } } },
          y: { beginAtZero: true, ticks: { font: { size: 10 } } },
        },
      },
    });
  }

  function formatCell(v) {
    if (v === null || v === undefined) return "NULL";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }

  async function copySql() {
    const sql = $("#sql-code").textContent;
    try {
      await navigator.clipboard.writeText(sql);
      toast("SQL copied to clipboard.");
    } catch (e) {
      toast("Copy failed.", "error");
    }
  }

  /* ─── Utils ─── */
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ─── Wiring ─── */
  function init() {
    // Nav + global actions
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-action]");
      if (!t) return;
      const action = t.dataset.action;
      if (action === "show-auth") { $(".auth-wrapper").hidden = false; $(".dashboard-wrapper").hidden = true; document.body.classList.add("auth-state"); document.body.classList.remove("dashboard-state"); }
      else if (action === "logout") { logout(); }
      else if (action === "go-home") { if (state.token) enterDashboard(); }
    });

    // Brand keyboard activation
    $(".nav-brand").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (state.token) enterDashboard(); }
    });

    // Auth tabs
    $$(".auth-tab-btn").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.authTab)));
    $("#auth-form").addEventListener("submit", handleAuthSubmit);

    // Connection modal
    $("#db-edit-btn").addEventListener("click", openConnModal);
    $("#conn-test-btn").addEventListener("click", openConnModal);
    $("#conn-modal-close").addEventListener("click", closeConnModal);
    $("#conn-cancel").addEventListener("click", closeConnModal);
    $("#conn-modal").addEventListener("click", (e) => { if (e.target === $("#conn-modal")) closeConnModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#conn-modal").hidden) closeConnModal(); });
    $("#c-dbtype").addEventListener("change", syncConnFields);
    $("#conn-form").addEventListener("submit", handleConnSubmit);

    // Logout button (delegated since nav re-renders)
    document.addEventListener("click", (e) => { if (e.target.closest("#logout-btn")) logout(); });

    // Query
    $("#run-query-btn").addEventListener("click", runQuery);
    $("#prompt-input").addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); runQuery(); }
    });
    $$(".suggest-btn").forEach((b) => b.addEventListener("click", () => {
      $("#prompt-input").value = b.dataset.suggest;
      $("#prompt-input").focus();
    }));
    $("#copy-sql-btn").addEventListener("click", copySql);

    // Conversation
    $("#new-conv-btn").addEventListener("click", newConversation);

    // History
    $("#history-list").addEventListener("click", (e) => {
      const item = e.target.closest(".history-item");
      if (item) {
        const idx = parseInt(item.dataset.hidx, 10);
        const h = state.history[idx];
        if (h) { $("#prompt-input").value = h.query; $("#prompt-input").focus(); toast("Query restored from history."); }
      }
    });
    $("#history-clear-btn").addEventListener("click", clearHistory);

    // Export
    $("#export-csv").addEventListener("click", exportCSV);
    $("#export-json").addEventListener("click", exportJSON);

    // Schema search
    $("#schema-search").addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      $$(".table-node").forEach((n) => {
        const name = $(".table-name", n).textContent.toLowerCase();
        n.hidden = !name.includes(q);
      });
    });

    initTheme();
    renderHistory();
    refreshNav();
    if (state.token) { enterDashboard(); }
  }

  /* ─── Theme ─── */
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const meta = $("#meta-theme");
    if (meta) meta.content = theme === "dark" ? "#0a0a0a" : "#fafafa";
  }
  function initTheme() {
    let theme = localStorage.getItem("sg_theme");
    if (!theme) {
      theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    applyTheme(theme);
    bindThemeToggle();
  }
  function bindThemeToggle() {
    const btn = $("#theme-toggle");
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        applyTheme(next);
        localStorage.setItem("sg_theme", next);
      });
    }
  }

  /* ─── Query History ─── */
  function saveHistory() {
    try { localStorage.setItem("sg_history", JSON.stringify(state.history.slice(0, 50))); } catch (e) { /* quota exceeded */ }
  }
  function pushHistory(query, sql, answer, success) {
    state.history.unshift({ query, sql, answer, success, ts: Date.now() });
    saveHistory();
    renderHistory();
  }
  function clearHistory() {
    state.history = [];
    saveHistory();
    renderHistory();
  }
  function renderHistory() {
    const list = $("#history-list");
    const clearBtn = $("#history-clear-btn");
    if (!state.history.length) {
      list.innerHTML = '<div class="history-empty"><span class="mono-label">No queries yet.</span></div>';
      clearBtn.hidden = true;
      return;
    }
    clearBtn.hidden = false;
    list.innerHTML = state.history.map((h, i) =>
      '<div class="history-item" data-hidx="' + i + '" tabindex="0" role="button">' +
        '<span class="history-query">' + escapeHtml(h.query) + '</span>' +
        '<span class="history-sql">' + escapeHtml(h.sql || "") + '</span>' +
        '<span class="history-meta">' +
          '<span>' + (h.success ? "" : "✗ ") + new Date(h.ts).toLocaleTimeString() + '</span>' +
          '<span>' + formatTimeAgo(h.ts) + '</span>' +
        '</span>' +
      '</div>'
    ).join("");
  }
  function formatTimeAgo(ts) {
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }

  /* ─── Loading Spinner ─── */
  function setLoading(show, label) {
    const bar = $("#loading-bar");
    const fill = $("#loading-bar-fill");
    const lbl = $("#loading-label");
    if (!show) { bar.hidden = true; return; }
    bar.hidden = false;
    if (lbl) lbl.textContent = label || "Generating…";
    if (fill) fill.style.animation = "none";
    void fill.offsetHeight;
    if (fill) fill.style.animation = "";
  }

  /* ─── CSV / JSON Export ─── */
  function exportCSV() {
    const res = state.lastResult;
    if (!res || !res.columns || !res.data) { toast("No results to export.", "error"); return; }
    const rows = res.data.map((row) =>
      res.columns.map((c, i) => {
        const v = Array.isArray(row) ? row[i] : row[c];
        const s = v === null || v === undefined ? "" : String(v);
        return '"' + s.replace(/"/g, '""') + '"';
      }).join(",")
    );
    const csv = res.columns.map((c) => '"' + c + '"').join(",") + "\n" + rows.join("\n");
    downloadFile(csv, "sql-genie-results.csv", "text/csv");
  }
  function exportJSON() {
    const res = state.lastResult;
    if (!res || !res.columns || !res.data) { toast("No results to export.", "error"); return; }
    const arr = res.data.map((row) => {
      const obj = {};
      res.columns.forEach((c, i) => { obj[c] = Array.isArray(row) ? row[i] : row[c]; });
      return obj;
    });
    downloadFile(JSON.stringify(arr, null, 2), "sql-genie-results.json", "application/json");
  }
  function downloadFile(content, filename, mime) {
    const blob = new Blob([content], { type: mime + ";charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 150);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
