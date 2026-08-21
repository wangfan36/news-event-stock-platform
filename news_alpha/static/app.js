(function () {
  const bootstrap = window.__APP_BOOTSTRAP__ || {};
  const pageMode = bootstrap.pageMode || "workspace";
  const workspaceRoot = document.getElementById("workspace-root");
  const runtimeDatabasePath = document.getElementById("runtime-database-path");
  const runtimeStockAsOf = document.getElementById("runtime-stock-as-of");
  const runtimeStockNote = document.getElementById("runtime-stock-note");
  const runtimeNewsAsOf = document.getElementById("runtime-news-as-of");
  const runtimeNewsNote = document.getElementById("runtime-news-note");
  const runtimeLatestGenerated = document.getElementById("runtime-latest-generated");
  const runtimeHistoryCount = document.getElementById("runtime-history-count");
  const runtimeTopEvent = document.getElementById("runtime-top-event");
  const runtimeTopEventNote = document.getElementById("runtime-top-event-note");
  const runtimeTopRecommendation = document.getElementById("runtime-top-recommendation");
  const runtimeTopRecommendationNote = document.getElementById("runtime-top-recommendation-note");
  const runtimeHistorySummary = document.getElementById("runtime-history-summary");
  const runtimeHistorySummaryNote = document.getElementById("runtime-history-summary-note");
  const runtimeRssList = document.getElementById("runtime-rss-list");
  const historyList = document.getElementById("history-list");
  const historyCount = document.getElementById("history-count");
  const clearHistoryButton = document.getElementById("clear-history");
  const historyModeInput = document.getElementById("history-mode-input");
  const historySearchInput = document.getElementById("history-search-input");
  const historyDateFromInput = document.getElementById("history-date-from-input");
  const historyDateToInput = document.getElementById("history-date-to-input");
  const form = document.getElementById("research-form");
  const watchlistInput = document.getElementById("watchlist-input");
  const topicsInput = document.getElementById("topics-input");
  const singleLimitInput = document.getElementById("single-limit-input");
  const sectorLimitInput = document.getElementById("sector-limit-input");
  const negativeThresholdInput = document.getElementById("negative-threshold-input");
  const notesInput = document.getElementById("notes-input");
  const liveNewsInput = document.getElementById("live-news-input");
  const rssSourcesInput = document.getElementById("rss-sources-input");
  const technicalProviderInput = document.getElementById("technical-provider-input");
  const technicalEndpointInput = document.getElementById("technical-endpoint-input");
  const technicalProviderStatus = document.getElementById("technical-provider-status");
  const technicalProviderNote = document.getElementById("technical-provider-note");
  const modelBaseUrlInput = document.getElementById("model-base-url-input");
  const modelNameInput = document.getElementById("model-name-input");
  const modelProviderInput = document.getElementById("model-provider-input");
  const modelApiKeyInput = document.getElementById("model-api-key-input");
  const modelTimeoutInput = document.getElementById("model-timeout-input");
  const modelSystemPromptInput = document.getElementById("model-system-prompt-input");
  const modelEnabledInput = document.getElementById("model-enabled-input");
  const saveSettingsButton = document.getElementById("save-settings");
  const refreshHistoryButton = document.getElementById("refresh-history");
  const refreshDataButton = document.getElementById("refresh-data");
  const refreshDataInlineButton = document.getElementById("refresh-data-inline");
  const exportMarkdownButton = document.getElementById("export-markdown");
  const exportJsonButton = document.getElementById("export-json");
  const settingsStatus = document.getElementById("settings-status");
  const loadDemoButton = document.getElementById("load-demo");
  const generateDemoButton = document.getElementById("generate-demo");
  let currentWorkspace = bootstrap.demoWorkspace || null;
  let currentEventReplay = null;
  let currentPortfolioReplay = null;
  let executionFilter = "all";
  let historyMode = "run";
  let candidateFilters = {
    benefit: "all",
    aiRank: "all",
    linkage: "all",
    market: "all",
  };
  let historySearchTimer = null;

  populateForm(bootstrap.formDefaults || bootstrap.demoRequest || {});
  populateSettings(bootstrap.userSettings || {});
  checkCodexStatus();
  if (bootstrap.demoWorkspace) {
    renderWorkspace(bootstrap.demoWorkspace);
  }
  loadRuntimeStatus();
  loadHistoryRuns();

  loadDemoButton.addEventListener("click", function () {
    populateForm(bootstrap.demoRequest || {});
  });

  generateDemoButton.addEventListener("click", function () {
    populateForm(bootstrap.demoRequest || {});
    generateWorkspace();
  });

  saveSettingsButton.addEventListener("click", function () {
    saveSettings();
  });

  refreshHistoryButton.addEventListener("click", function () {
    loadHistoryRuns();
  });
  refreshDataButton.addEventListener("click", function () {
    refreshDataSources();
  });
  if (refreshDataInlineButton) {
    refreshDataInlineButton.addEventListener("click", function () {
      refreshDataSources();
    });
  }
  exportMarkdownButton.addEventListener("click", function () {
    exportCurrentWorkspace("markdown");
  });
  exportJsonButton.addEventListener("click", function () {
    exportCurrentWorkspace("json");
  });
  clearHistoryButton.addEventListener("click", function () {
    clearHistoryRuns();
  });

  historySearchInput.addEventListener("input", function () {
    debounceHistoryReload();
  });
  historyModeInput.addEventListener("change", function () {
    historyMode = historyModeInput.value;
    loadHistoryRuns();
  });
  historyDateFromInput.addEventListener("change", loadHistoryRuns);
  historyDateToInput.addEventListener("change", loadHistoryRuns);
  modelProviderInput.addEventListener("change", applyModelProviderHints);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    generateWorkspace();
  });

  function populateForm(payload) {
    watchlistInput.value = (payload.watchlist || []).map(function (item) {
      return [item.symbol, item.name, item.position_pct, item.thesis].filter(Boolean).join(" ");
    }).join("\n");
    topicsInput.value = (payload.focus_topics || []).join("，");
    singleLimitInput.value = payload.risk_thresholds ? payload.risk_thresholds.single_name_limit_pct : 15;
    sectorLimitInput.value = payload.risk_thresholds ? payload.risk_thresholds.sector_limit_pct : 22;
    negativeThresholdInput.value = payload.risk_thresholds ? payload.risk_thresholds.negative_event_score_threshold : 70;
    notesInput.value = payload.personal_notes || "";
    liveNewsInput.checked = Boolean(payload.use_live_news);
  }

  function populateSettings(settings) {
    const model = settings.model_settings || {};
    const technical = settings.technical_settings || {};
    rssSourcesInput.value = settings.rss_sources_text || "";
    technicalProviderInput.value = technical.provider || "mock";
    technicalEndpointInput.value = technical.endpoint || "";
    modelBaseUrlInput.value = model.base_url || "";
    modelNameInput.value = model.model_name || "";
    modelProviderInput.value = model.provider || "openai-compatible";
    modelTimeoutInput.value = model.timeout_seconds || (model.provider === "codex-cli" ? 90 : 20);
    modelSystemPromptInput.value = model.system_prompt || "";
    modelEnabledInput.checked = Boolean(model.enabled);
    modelApiKeyInput.value = "";
    modelApiKeyInput.placeholder = model.has_api_key
      ? ("已保存：" + (model.api_key_masked || "已配置"))
      : "留空则沿用已保存 key";
    modelApiKeyInput.title = model.has_api_key
      ? ("当前已保存模型 key：" + (model.api_key_masked || "已配置"))
      : "留空则沿用已保存 key";
    applyModelProviderHints();
    renderTechnicalProviderStatus({
      provider: technical.provider || "mock",
      provider_status: "idle",
      note: technical.endpoint ? "bridge endpoint 已填写" : "当前为已保存配置，未执行生成。",
    });
    settingsStatus.textContent = model.has_api_key
      ? "已保存模型 key：" + (model.api_key_masked || "已配置")
      : "先保存配置，再开始本地生成。";
  }

  function collectPayload() {
    return {
      watchlist: parseWatchlist(watchlistInput.value),
      focus_topics: splitTokens(topicsInput.value),
      risk_thresholds: {
        single_name_limit_pct: Number(singleLimitInput.value || 15),
        sector_limit_pct: Number(sectorLimitInput.value || 22),
        negative_event_score_threshold: Number(negativeThresholdInput.value || 70)
      },
      personal_notes: notesInput.value.trim(),
      use_live_news: liveNewsInput.checked,
      rss_sources_text: rssSourcesInput.value.trim(),
      technical_settings: collectTechnicalSettings(),
      model_settings: collectModelSettings()
    };
  }

  function collectTechnicalSettings() {
    return {
      provider: technicalProviderInput.value,
      endpoint: technicalEndpointInput.value.trim(),
      timeout_seconds: 8,
      fallback_to_mock: true
    };
  }

  function collectModelSettings() {
    const provider = modelProviderInput.value.trim() || "openai-compatible";
    return {
      enabled: modelEnabledInput.checked,
      provider: provider,
      base_url: provider === "codex-cli" ? "" : modelBaseUrlInput.value.trim(),
      model_name: modelNameInput.value.trim(),
      api_key: provider === "codex-cli" ? "" : modelApiKeyInput.value.trim(),
      system_prompt: modelSystemPromptInput.value.trim(),
      temperature: 0.2,
      timeout_seconds: Number(modelTimeoutInput.value || (provider === "codex-cli" ? 90 : 20))
    };
  }

  function applyModelProviderHints() {
    const provider = modelProviderInput.value.trim() || "openai-compatible";
    const isCodexCli = provider === "codex-cli";
    modelBaseUrlInput.readOnly = isCodexCli;
    modelApiKeyInput.readOnly = isCodexCli;
    modelBaseUrlInput.placeholder = isCodexCli
      ? "codex-cli 模式无需 Base URL"
      : "https://api.openai.com/v1";
    modelApiKeyInput.placeholder = isCodexCli
      ? "codex-cli 模式无需 API Key，改用 ChatGPT 登录"
      : (modelApiKeyInput.placeholder || "留空则沿用已保存 key");
    if (isCodexCli) {
      modelBaseUrlInput.value = "";
      modelApiKeyInput.value = "";
      if (!modelTimeoutInput.value || Number(modelTimeoutInput.value) < 90) {
        modelTimeoutInput.value = 90;
      }
      settingsStatus.textContent = "codex-cli 模式将使用本机 ChatGPT 登录态（codex login）。";
    }
  }

  function checkCodexStatus() {
    fetch("/api/model/codex-status")
      .then(ensureJson)
      .then(function (payload) {
        if (payload.available && payload.logged_in && modelProviderInput.value.trim() !== "codex-cli") {
          settingsStatus.textContent = "已检测到本机 ChatGPT/Codex 登录态，可切换 Provider 为 codex-cli。";
        }
      })
      .catch(function () {
        // ignore silently
      });
  }

  function parseWatchlist(raw) {
    return raw.split(/\r?\n/).map(function (line) {
      return line.trim();
    }).filter(Boolean).map(function (line) {
      const tokens = line.split(/\s+/);
      const symbol = tokens.shift() || "";
      const name = tokens.shift() || symbol;
      let position = 0;
      if (tokens.length && /^-?\d+(\.\d+)?$/.test(tokens[0])) {
        position = Number(tokens.shift());
      }
      return { symbol: symbol, name: name, position_pct: position, thesis: tokens.join(" ") };
    });
  }

  function splitTokens(raw) {
    return raw.split(/[\n,，]/).map(function (token) {
      return token.trim();
    }).filter(Boolean);
  }

  function saveSettings() {
    setStatus("正在保存设置...");
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        watchlist: parseWatchlist(watchlistInput.value),
        focus_topics: splitTokens(topicsInput.value),
        risk_thresholds: {
          single_name_limit_pct: Number(singleLimitInput.value || 15),
          sector_limit_pct: Number(sectorLimitInput.value || 22),
          negative_event_score_threshold: Number(negativeThresholdInput.value || 70)
        },
        personal_notes: notesInput.value.trim(),
        use_live_news: liveNewsInput.checked,
        rss_sources_text: rssSourcesInput.value.trim(),
        technical_settings: collectTechnicalSettings(),
        model_settings: collectModelSettings()
      })
    })
      .then(ensureJson)
      .then(function (settings) {
        try {
          populateSettings(settings);
        } catch (error) {
          console.error("populateSettings failed", error);
          setStatus("设置已保存，但前端刷新配置时出错。请刷新页面。");
          return;
        }
        setStatus("设置已保存。生成时会优先使用你的 RSS 和模型。");
      })
      .catch(function (error) {
        setStatus("保存失败：" + error.message);
      });
  }

  function generateWorkspace(overrides) {
    workspaceRoot.innerHTML = '<div class="empty-state"><p>正在生成本地研究工作台...</p></div>';
    setStatus("正在生成本地工作台...");
    const payload = Object.assign({}, collectPayload(), overrides || {});
    fetch("/api/research/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(ensureJson)
      .then(function (workspace) {
        currentWorkspace = workspace;
        renderWorkspace(workspace);
        setStatus("生成完成。已写入本地历史。");
        loadRuntimeStatus();
        loadHistoryRuns();
      })
      .catch(function (error) {
        workspaceRoot.innerHTML = '<div class="empty-state"><p>生成失败：' + escapeHtml(error.message) + "</p></div>";
        setStatus("生成失败：" + error.message);
      });
  }

  function loadHistoryRuns() {
    const params = new URLSearchParams();
    if (historySearchInput.value.trim()) {
      params.set("q", historySearchInput.value.trim());
    }
    params.set("mode", historyMode);
    if (historyDateFromInput.value) {
      params.set("date_from", historyDateFromInput.value);
    }
    if (historyDateToInput.value) {
      params.set("date_to", historyDateToInput.value);
    }
    const url = "/api/history/runs" + (params.toString() ? "?" + params.toString() : "");
    fetch(url)
      .then(ensureJson)
      .then(function (runs) {
        historyCount.textContent = String(runs.length) + " runs";
        if (!runs.length) {
          historyList.innerHTML = '<div class="history-empty">还没有本地运行记录。</div>';
          return;
        }
        historyList.innerHTML = runs.map(function (item) {
          const runId = item.run_id || item.sample_run_id || "";
          const title = item.group_label || item.top_event || item.sample_top_event || "未命名事件";
          const generatedAt = item.generated_at || item.latest_generated_at || "";
          const recommendation = item.top_recommendation || item.sample_top_recommendation || "无建议";
          const recommendationAction = item.top_recommendation_action || item.sample_top_recommendation_action || "";
          const recommendationScore = item.top_recommendation_score != null ? item.top_recommendation_score : item.sample_top_recommendation_score;
          const eventMasterId = item.top_event_master_id || item.sample_top_event_master_id || "";
          const meta = historyMode === "run"
            ? ((recommendation || "无建议") + (recommendationAction ? (" / " + recommendationAction) : "") + (recommendationScore != null ? (" / " + recommendationScore + "分") : ""))
            : ("共 " + String(item.count || 0) + " 条 / " + (item.sublabels || []).slice(0, 2).join("；"));
          return '<div class="history-item"><div class="history-item-row"><button class="history-item-main" data-run-id="' + escapeHtml(runId) + '">' +
            '<strong>' + escapeHtml(title) + '</strong>' +
            '<span>' + escapeHtml(generatedAt || "") + '</span>' +
            '<em>' + escapeHtml(meta) + '</em>' +
            '<span class="history-run-id">' + escapeHtml(historyMode === "run" ? ("Run " + String(runId).slice(0, 8)) : ((historyMode === "event" && eventMasterId) ? ("事件 " + eventMasterId) : ("视角 " + historyMode))) + '</span>' +
            '</button>' + (historyMode === "run" ? ('<button class="history-delete" data-run-id="' + escapeHtml(runId) + '">删</button>') : '') + '</div></div>';
        }).join("");
        Array.prototype.forEach.call(historyList.querySelectorAll(".history-item-main"), function (button) {
          button.addEventListener("click", function () {
            loadHistoryRun(button.getAttribute("data-run-id"));
          });
        });
        if (historyMode === "run") {
          Array.prototype.forEach.call(historyList.querySelectorAll(".history-delete"), function (button) {
            button.addEventListener("click", function () {
              deleteHistoryRun(button.getAttribute("data-run-id"));
            });
          });
        }
      })
      .catch(function () {
        historyList.innerHTML = '<div class="history-empty">历史列表读取失败。</div>';
      });
  }

  function loadHistoryRun(runId) {
    if (!runId) {
      return;
    }
    workspaceRoot.innerHTML = '<div class="empty-state"><p>正在载入历史运行...</p></div>';
    fetch("/api/history/runs/" + encodeURIComponent(runId))
      .then(ensureJson)
      .then(function (workspace) {
        currentWorkspace = workspace;
        renderWorkspace(workspace);
        setStatus("已载入历史运行 " + runId.slice(0, 8) + "。");
      })
      .catch(function (error) {
        workspaceRoot.innerHTML = '<div class="empty-state"><p>载入失败：' + escapeHtml(error.message) + "</p></div>";
      });
  }

  function renderWorkspace(workspace) {
    const snapshot = workspace.market_snapshot || {};
    updateStageSummary(workspace);
    renderTechnicalProviderStatus({
      provider: snapshot.provider || collectTechnicalSettings().provider,
      provider_status: snapshot.provider_status || "unknown",
      note: snapshot.breadth_note || "未生成市场快照。",
    });
    const portfolioTerminal = renderPortfolioTerminal(
      workspace.portfolio_plan || {},
      workspace.portfolio_comparison || {},
      workspace.portfolio_timeline || [],
      currentPortfolioReplay
    );
    const workspaceTopline = [
      '<div class="workspace-topline">',
      renderCoreFocusPanel(workspace),
      renderSummaryBand(workspace),
      renderComplianceCard(workspace.compliance || {}, workspace.generated_at, workspace.storage || {}, workspace.model_runtime || {}),
      '</div>',
    ].join("");
    const fullContent = [
      renderRunComparisonPanel(workspace.run_comparison || {}),
      renderAiParticipationPanel(workspace.ai_participation_status || {}, workspace.source_diagnostics || {}),
      renderManagerOverview(workspace.recommendation_views || []),
      portfolioTerminal,
      renderDailyDigest(workspace.daily_digest || {}),
      renderAiResearchPipeline(workspace.ai_research_pipeline || {}),
      renderMarketSnapshot(workspace.market_snapshot || {}),
      renderExecutionPanel(workspace.recommendation_views || []),
      renderNewsSection(workspace.news_stream || {}),
      renderEvents(workspace.hotspot_events || []),
      renderEventReplay(workspace.hotspot_events || []),
      renderEventReplayDetail(currentEventReplay),
      renderIndustries(workspace.industry_views || []),
      renderCandidates(workspace.candidate_stocks || []),
      renderRecommendations(workspace.recommendation_views || []),
      renderHistory(workspace.recommendation_history || []),
      renderRiskCards(workspace.risk_cards || []),
      renderAgentTrace(workspace.agent_trace || []),
    ].join("");
    const portfolioOnlyContent = [
      portfolioTerminal,
      renderPortfolioReplayDetail(currentPortfolioReplay),
    ].join("");
    workspaceRoot.innerHTML = [
      workspaceTopline,
      '<div class="output-stack">',
      pageMode === "portfolio" ? portfolioOnlyContent : fullContent,
      "</div>"
    ].join("");
    bindExecutionFilter();
    bindCandidateFilters();
    bindEventReplayButtons();
    bindPortfolioReplayButtons();
  }

  function renderCoreFocusPanel(workspace) {
    const topEvent = (workspace.hotspot_events || [])[0] || {};
    const topRec = (workspace.recommendation_views || [])[0] || {};
    const topRisk = (workspace.risk_cards || [])[0] || {};
    return '<section class="output-card core-focus-panel"><div class="execution-panel-head"><div><h3>今日核心面板</h3><p class="inline-note">打开即先看今天最重要的事件、标的和风险。</p></div></div><div class="core-focus-grid">' +
      renderFocusCard("今日核心事件", topEvent.title || "暂无事件", topEvent.event_summary || topEvent.stage || "等待生成工作台。", "事件") +
      renderFocusCard("今日核心标的", topRec.name ? (topRec.name + " / " + topRec.action) : "暂无标的", topRec.core_logic || "等待生成工作台。", "标的") +
      renderFocusCard("今日核心风险", topRisk.risk_type || "暂无核心风险", topRisk.reason || "等待生成工作台。", "风险") +
      '</div></section>';
  }

  function renderFocusCard(label, title, summary, tag) {
    return '<article class="focus-card"><span class="focus-label">' + escapeHtml(label) + '</span><strong>' + escapeHtml(title) + '</strong><p>' + escapeHtml(summary) + '</p><em>' + escapeHtml(tag) + '</em></article>';
  }

  function renderManagerOverview(recommendations) {
    const top = (recommendations || []).slice(0, 3);
    if (!top.length) {
      return '<section class="output-card"><h3>Manager 总览</h3><p class="brief-summary">当前没有可汇总的建议。</p></section>';
    }
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>Manager 总览</h3><p class="inline-note">先看最终动作和综合分，再进入单票细节。</p></div></div><div class="manager-overview-grid">' + top.map(function (item) {
      const analystSignals = item.analyst_signals || {};
      const summary = [
        analystSignals.event_analyst ? '事件 ' + analystSignals.event_analyst.score : null,
        analystSignals.market_analyst ? '市场 ' + analystSignals.market_analyst.score : null,
        analystSignals.fundamental_analyst ? '基本面 ' + analystSignals.fundamental_analyst.score : null,
        analystSignals.beneficiary_analyst ? '受益排序 ' + analystSignals.beneficiary_analyst.score : null,
        analystSignals.technical_analyst ? '技术 ' + analystSignals.technical_analyst.score : null,
        analystSignals.risk_analyst ? '风险 ' + analystSignals.risk_analyst.score : null
      ].filter(Boolean).join(' / ');
      return '<article class="manager-overview-card"><div class="score-head"><strong>' + escapeHtml(item.name) + ' [' + escapeHtml(item.market || '未知市场') + '] (' + escapeHtml(item.symbol) + ')</strong><span class="score-badge">' + escapeHtml(String(item.final_score || item.score || 'n/a')) + '/100</span></div><p>' + escapeHtml(item.manager_summary || '') + '</p><p>' + escapeHtml(summary || '暂无分析器摘要') + '</p></article>';
    }).join('') + '</div></section>';
  }

  function renderPortfolioPlan(plan) {
    if (!plan || !Object.keys(plan).length) {
      return "";
    }
    const targetPositions = plan.target_positions || [];
    const concentrationAlerts = plan.concentration_alerts || [];
    const industryExposure = plan.target_industry_exposure || [];
    const themeExposure = plan.theme_exposure || [];
    const replay = plan.portfolio_replay || {};
    const riskBudget = plan.risk_budget || {};
    const appliedConstraints = plan.applied_constraints || [];
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>组合建议</h3><p class="inline-note">先给最小可执行的仓位建议、现金缓冲和主题集中度提示。</p></div></div><div class="chip-row">' +
      '<div class="chip"><strong>建议总投入</strong><br>' + escapeHtml(String(plan.suggested_invested_pct || "0")) + '%</div>' +
      '<div class="chip"><strong>现金缓冲</strong><br>' + escapeHtml(String(plan.cash_buffer_pct || "0")) + '%</div>' +
      '<div class="chip"><strong>单票上限</strong><br>' + escapeHtml(String(plan.single_name_limit_pct || "0")) + '%</div>' +
      '<div class="chip"><strong>行业上限</strong><br>' + escapeHtml(String(plan.sector_limit_pct || "0")) + '%</div>' +
      '</div><p class="brief-summary">' + escapeHtml(plan.summary || "") + '</p><div class="scorecard-grid">' +
      targetPositions.slice(0, 6).map(function (item) {
        return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(String(item.priority_rank) + '. ' + (item.name || item.symbol || '')) + '</strong><span class="score-badge">' + escapeHtml(String(item.suggested_position_pct || 0)) + '%</span></div><p>' + escapeHtml(item.sizing_reason || "") + '</p><dl><dt>当前仓位</dt><dd>' + escapeHtml(String(item.current_position_pct || 0)) + '%</dd><dt>建议仓位</dt><dd>' + escapeHtml(String(item.suggested_position_pct || 0)) + '%</dd><dt>仓位变化</dt><dd>' + escapeHtml(String(item.position_delta_pct || 0)) + '%</dd><dt>分层</dt><dd>' + escapeHtml(item.sizing_bucket || "未生成") + '</dd><dt>行业</dt><dd>' + escapeHtml(item.industry_name || "未生成") + '</dd></dl></article>';
      }).join('') + '</div>' +
      renderRiskBudgetPanel(riskBudget, appliedConstraints) +
      '<div class="event-evidence-grid">' +
      '<div class="comparison-box"><strong>目标行业暴露</strong><p>' + escapeHtml(industryExposure.slice(0, 6).map(function (item) { return (item.industry_name || '') + ' ' + String(item.target_position_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>集中度提醒</strong><p>' + escapeHtml(concentrationAlerts.length ? concentrationAlerts.map(function (item) { return item.reason; }).join('；') : '当前未触发主题集中风险。') + '</p></div>' +
      '<div class="comparison-box"><strong>优先加仓</strong><p>' + escapeHtml((plan.add_order || []).map(function (item) { return (item.name || item.symbol || '') + ' +' + String(item.delta_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>优先降仓</strong><p>' + escapeHtml((plan.trim_order || []).map(function (item) { return (item.name || item.symbol || '') + ' ' + String(item.delta_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '</div>' +
      renderThemeExposurePlan(themeExposure) +
      renderPortfolioReplay(replay) +
      '</section>';
  }

  function renderPortfolioTerminal(plan, comparison, timeline, replayDetail) {
    if ((!plan || !Object.keys(plan).length) && (!comparison || !comparison.summary) && !(timeline || []).length && !replayDetail) {
      return "";
    }
    return '<section class="output-card portfolio-terminal"><div class="execution-panel-head"><div><h3>组合终端</h3><p class="inline-note">把仓位建议、风险预算、主题暴露、组合回放和版本对比集中在一处。</p></div></div>' +
      renderPortfolioPlan(plan) +
      renderPortfolioComparison(comparison) +
      renderPortfolioTimeline(timeline) +
      renderPortfolioReplayDetail(replayDetail) +
      '</section>';
  }

  function renderRiskBudgetPanel(riskBudget, appliedConstraints) {
    if (!riskBudget || !Object.keys(riskBudget).length) {
      return "";
    }
    const constraintsText = appliedConstraints.length
      ? appliedConstraints.map(function (item) { return item.reason; }).join('；')
      : '当前未触发额外压仓约束。';
    const driversText = (riskBudget.drivers || []).join('；') || '暂无驱动说明。';
    return '<div class="event-evidence-grid">' +
      '<div class="comparison-box"><strong>风险预算</strong><p>' + escapeHtml(riskBudget.summary || '') + '</p></div>' +
      '<div class="comparison-box"><strong>风格</strong><p>' + escapeHtml((riskBudget.regime || '未生成') + ' / 高确信 ' + String(riskBudget.high_conviction_count || 0) + ' / 平均置信度 ' + String(riskBudget.avg_confidence || 0)) + '</p><p>' + escapeHtml(riskBudget.regime_reason || '') + '</p></div>' +
      '<div class="comparison-box"><strong>目标总暴露</strong><p>' + escapeHtml(String(riskBudget.target_gross_exposure_pct || 0) + '% / 现金缓冲 ' + String(riskBudget.target_cash_buffer_pct || 0) + '%') + '</p><p>' + escapeHtml('原始目标 ' + String(riskBudget.pre_constraint_target_gross_pct || 0) + '% / ' + (riskBudget.requires_scaling ? '需要压缩' : '无需压缩')) + '</p></div>' +
      '<div class="comparison-box"><strong>预算驱动</strong><p>' + escapeHtml(driversText) + '</p></div>' +
      '<div class="comparison-box"><strong>已应用约束</strong><p>' + escapeHtml(constraintsText) + '</p></div>' +
      '</div>';
  }

  function renderThemeExposurePlan(themeExposure) {
    if (!themeExposure.length) {
      return "";
    }
    return '<div class="portfolio-exposure-grid">' + themeExposure.slice(0, 8).map(function (item) {
      return '<article class="comparison-box"><strong>' + escapeHtml(item.industry_name || '未知行业') + '</strong><div class="exposure-bar-shell"><div class="exposure-bar-current" style="width:' + escapeHtml(String(Math.max(0, Math.min(100, item.current_position_pct || 0)))) + '%"></div><div class="exposure-bar-target' + (item.over_limit ? ' exposure-over-limit' : '') + '" style="width:' + escapeHtml(String(Math.max(0, Math.min(100, item.target_position_pct || 0)))) + '%"></div></div><p>' + escapeHtml('当前 ' + String(item.current_position_pct || 0) + '% / 目标 ' + String(item.target_position_pct || 0) + '% / 变化 ' + String(item.delta_pct || 0) + '%') + '</p></article>';
    }).join('') + '</div>';
  }

  function renderPortfolioReplay(replay) {
    if (!replay || !Object.keys(replay).length) {
      return "";
    }
    return '<section class="output-card"><h3>组合回放 / 复盘</h3><p class="brief-summary">' + escapeHtml(replay.summary || '') + '</p><div class="event-evidence-grid">' +
      '<div class="comparison-box"><strong>新增仓位</strong><p>' + escapeHtml((replay.new_positions || []).map(function (item) { return (item.name || item.symbol || '') + ' -> ' + String(item.suggested_position_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>增加仓位</strong><p>' + escapeHtml((replay.increase_positions || []).map(function (item) { return (item.name || item.symbol || '') + ' +' + String(item.position_delta_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>降低仓位</strong><p>' + escapeHtml((replay.trim_positions || []).map(function (item) { return (item.name || item.symbol || '') + ' ' + String(item.position_delta_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>移除仓位</strong><p>' + escapeHtml((replay.remove_positions || []).map(function (item) { return (item.name || item.symbol || '') + ' / 当前 ' + String(item.current_position_pct || 0) + '%'; }).join('；') || '暂无') + '</p></div>' +
      '</div></section>';
  }

  function renderPortfolioComparison(comparison) {
    if (!comparison || !comparison.summary) {
      return "";
    }
    const currentThemes = (comparison.current_theme_exposure || []).slice(0, 4).map(function (item) {
      return (item.industry_name || '') + ' ' + String(item.target_position_pct || 0) + '%';
    }).join('；') || '暂无';
    const previousThemes = (comparison.previous_theme_exposure || []).slice(0, 4).map(function (item) {
      return (item.industry_name || '') + ' ' + String(item.target_position_pct || 0) + '%';
    }).join('；') || '暂无';
    return '<section class="output-card"><h3>组合版本对比</h3><div class="event-evidence-grid">' +
      '<div class="comparison-box"><strong>组合变化</strong><p>' + escapeHtml(comparison.summary || '') + '</p></div>' +
      '<div class="comparison-box"><strong>总暴露变化</strong><p>' + escapeHtml('当前 ' + String(comparison.current_suggested_invested_pct || 0) + '% / 上一版 ' + String(comparison.previous_suggested_invested_pct || 0) + '% / 变化 ' + String(comparison.exposure_delta_pct || 0) + '%') + '</p></div>' +
      '<div class="comparison-box"><strong>现金缓冲变化</strong><p>' + escapeHtml('当前 ' + String(comparison.current_cash_buffer_pct || 0) + '% / 上一版 ' + String(comparison.previous_cash_buffer_pct || 0) + '%') + '</p></div>' +
      '<div class="comparison-box"><strong>风险预算风格</strong><p>' + escapeHtml((comparison.current_regime || '未生成') + ' / 上一版 ' + (comparison.previous_regime || '未生成')) + '</p></div>' +
      '<div class="comparison-box"><strong>当前主题暴露</strong><p>' + escapeHtml(currentThemes) + '</p></div>' +
      '<div class="comparison-box"><strong>上一版主题暴露</strong><p>' + escapeHtml(previousThemes) + '</p></div>' +
      '<div class="comparison-box"><strong>当前约束</strong><p>' + escapeHtml((comparison.current_constraints || []).map(function (item) { return item.reason; }).join('；') || '暂无') + '</p></div>' +
      '<div class="comparison-box"><strong>当前回放摘要</strong><p>' + escapeHtml(comparison.current_replay_summary || '暂无') + '</p></div>' +
      '</div></section>';
  }

  function renderPortfolioTimeline(timeline) {
    if (!timeline || !timeline.length) {
      return "";
    }
    return '<section class="output-card"><h3>组合时间线</h3><p class="inline-note">按最近几版看组合暴露、现金缓冲和主仓位如何变化。</p><div class="scorecard-grid">' + timeline.map(function (item, index) {
      const topTargets = (item.top_targets || []).map(function (target) {
        return [target.name || target.symbol || '', target.suggested_position_pct != null ? (String(target.suggested_position_pct) + '%') : ''].filter(Boolean).join(' / ');
      }).join('；') || '暂无';
      const deltaText = item.delta_vs_newer_pct == null
        ? '最新一版'
        : ((item.delta_vs_newer_pct > 0 ? '+' : '') + String(item.delta_vs_newer_pct) + '%');
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml((index + 1) + '. ' + (item.generated_at || '')) + '</strong><span class="score-badge">' + escapeHtml(String(item.suggested_invested_pct || 0)) + '%</span></div><p>' + escapeHtml((item.regime || '未生成') + ' / 现金缓冲 ' + String(item.cash_buffer_pct || 0) + '% / 相对更新版 ' + deltaText) + '</p><dl><dt>主仓位</dt><dd>' + escapeHtml(topTargets) + '</dd><dt>回放摘要</dt><dd>' + escapeHtml(item.replay_summary || '暂无') + '</dd></dl><div class="event-history-actions"><button type="button" class="ghost portfolio-replay-button" data-run-id="' + escapeHtml(item.run_id || '') + '">查看该版组合</button></div></article>';
    }).join('') + '</div></section>';
  }

  function renderPortfolioReplayDetail(detail) {
    if (!detail || !detail.run_id) {
      return "";
    }
    const plan = detail.portfolio_plan || {};
    const comparison = detail.portfolio_comparison || {};
    const topPositions = (plan.target_positions || []).slice(0, 8).map(function (item) {
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml((item.name || item.symbol || '')) + '</strong><span class="score-badge">' + escapeHtml(String(item.suggested_position_pct || 0)) + '%</span></div><p>' + escapeHtml(item.sizing_reason || '') + '</p><dl><dt>当前仓位</dt><dd>' + escapeHtml(String(item.current_position_pct || 0)) + '%</dd><dt>变化</dt><dd>' + escapeHtml(String(item.position_delta_pct || 0) + '%') + '</dd><dt>约束</dt><dd>' + escapeHtml((item.applied_constraints || []).join('；') || '暂无') + '</dd></dl></article>';
    }).join('');
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>组合回放详情</h3><p class="inline-note">' + escapeHtml((detail.generated_at || '') + ' / Run ' + String(detail.run_id || '').slice(0, 8)) + '</p></div><button type="button" class="ghost" id="close-portfolio-replay-detail">关闭</button></div>' + renderPortfolioComparison(comparison) + '<div class="scorecard-grid">' + topPositions + '</div></section>';
  }

  function renderRunComparisonPanel(runComparison) {
    if (!runComparison || !runComparison.summary) {
      return "";
    }
    return '<section class="output-card"><h3>版本对比</h3><div class="comparison-box"><p>' + escapeHtml(runComparison.summary) + '</p><dl><dt>当前核心事件</dt><dd>' + escapeHtml((runComparison.current_top_event || "暂无") + (runComparison.current_top_event_master_id ? (" / " + runComparison.current_top_event_master_id) : "")) + '</dd><dt>上一版核心事件</dt><dd>' + escapeHtml((runComparison.previous_top_event || "暂无") + (runComparison.previous_top_event_master_id ? (" / " + runComparison.previous_top_event_master_id) : "")) + '</dd><dt>当前首条标的</dt><dd>' + escapeHtml((runComparison.current_top_name || runComparison.current_top_symbol || "暂无") + (runComparison.current_top_action ? (" / " + runComparison.current_top_action) : "")) + '</dd><dt>上一版首条标的</dt><dd>' + escapeHtml((runComparison.previous_top_name || runComparison.previous_top_symbol || "暂无") + (runComparison.previous_top_action ? (" / " + runComparison.previous_top_action) : "")) + '</dd></dl></div></section>';
  }

  function renderAiParticipationPanel(status, diagnostics) {
    const stages = status.stages || [];
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>AI 参与状态</h3><p class="inline-note">明确区分本次哪些步骤用了 AI，哪些步骤失败或回退。</p></div></div><div class="chip-row">' +
      '<div class="chip"><strong>AI 总状态</strong><br>' + escapeHtml(formatAiStatus(status.status || "disabled")) + '</div>' +
      '<div class="chip"><strong>成功步骤</strong><br>' + escapeHtml(String(status.success_count || 0)) + '</div>' +
      '<div class="chip"><strong>失败步骤</strong><br>' + escapeHtml(String(status.failed_count || 0)) + '</div>' +
      '<div class="chip"><strong>停用步骤</strong><br>' + escapeHtml(String(status.disabled_count || 0)) + '</div>' +
      '<div class="chip"><strong>来源层级</strong><br>' + escapeHtml(Object.keys(diagnostics.layer_counts || {}).join(" / ") || "未生成") + '</div>' +
      '</div><div class="scorecard-grid">' + stages.map(function (stage) {
        return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(stage.title || stage.key || "未知步骤") + '</strong><span class="score-badge">' + escapeHtml(formatAiStatus(stage.status || "unknown")) + '</span></div><p>' + escapeHtml(stage.message || "无附加说明") + '</p></article>';
      }).join('') + '</div></section>';
  }

  function renderSummaryBand(workspace) {
    const topEvent = (workspace.hotspot_events || [])[0] || {};
    const topRec = (workspace.recommendation_views || [])[0] || {};
    const modelRuntime = workspace.model_runtime || {};
    const marketSnapshot = workspace.market_snapshot || {};
    return '<section class="summary-band">' +
      renderMiniMetric("热点事件", topEvent.title || "暂无") +
      renderMiniMetric("领先建议", topRec.name ? (topRec.name + " " + topRec.action) : "暂无") +
      renderMiniMetric("模型状态", modelRuntime.status || "规则链路") +
      renderMiniMetric("市场状态", marketSnapshot.risk_regime || "未生成") +
      renderMiniMetric("历史回溯", String((workspace.recommendation_history || []).length) + " 条") +
      '</section>';
  }

  function renderComplianceCard(compliance, generatedAt, storage, modelRuntime) {
    const statusClass = compliance.is_compliant ? "status-ok" : "status-bad";
    const statusText = compliance.is_compliant ? "合规检查通过" : "发现禁用用语";
    const blocked = (compliance.blocked_terms || []).length ? "命中词：" + compliance.blocked_terms.map(escapeHtml).join("、") : "未命中禁用词。";
    return '<section class="output-card">' +
      '<h3>运行状态</h3>' +
      '<div class="chip-row">' +
      '<div class="chip"><strong class="' + statusClass + '">' + statusText + '</strong><br>' + escapeHtml(blocked) + '</div>' +
      '<div class="chip"><strong>生成时间</strong><br>' + escapeHtml(generatedAt || "") + '</div>' +
      '<div class="chip"><strong>Run ID</strong><br>' + escapeHtml((storage.run_id || "未持久化")) + '</div>' +
      '<div class="chip"><strong>模型</strong><br>' + escapeHtml((modelRuntime.model_name || modelRuntime.status || "未启用")) + '</div>' +
      '</div>' +
      '</section>';
  }

  function renderDailyDigest(digest) {
    return '<section class="output-card"><h3>' + escapeHtml(digest.headline || "新闻驱动选股日报") + '</h3><p class="brief-summary">' + escapeHtml(digest.summary || "") + '</p><div class="chip-row">' +
      '<div class="chip"><strong>来源多样性</strong><br>' + escapeHtml(String(digest.source_diversity_score || "n/a")) + '/100</div>' +
      '<div class="chip"><strong>覆盖概览</strong><br>' + escapeHtml(digest.coverage_overview || "未生成") + '</div>' +
      '</div>' +
      renderListBlock("今日先看", digest.must_watch || []) +
      renderListBlock("跟进问题", digest.follow_up_questions || []) +
      renderListBlock("建议靠前", digest.top_recommendations || []) +
      renderListBlock("覆盖缺口", digest.coverage_gaps || []) +
      renderListBlock("次日关注", digest.tomorrow_focus || []) + "</section>";
  }

  function renderAiResearchPipeline(pipeline) {
    const localizationStage = pipeline.news_localization || {};
    const eventStage = pipeline.event_understanding || {};
    const scenarioStage = pipeline.scenario_analysis || {};
    const chainStage = pipeline.supply_chain_expansion || {};
    const companyStage = pipeline.company_beneficiary_ranking || {};
    return '<section class="output-card"><h3>AI 研究链</h3><div class="chip-row">' +
      '<div class="chip"><strong>状态</strong><br>' + escapeHtml(pipeline.status || "未生成") + '</div>' +
      '<div class="chip"><strong>模型</strong><br>' + escapeHtml((pipeline.provider || "未启用") + (pipeline.model_name ? " / " + pipeline.model_name : "")) + '</div>' +
      '<div class="chip"><strong>说明</strong><br>' + escapeHtml(pipeline.note || "未生成") + '</div>' +
      '</div><div class="scorecard-grid">' +
      renderAiStageCard("AI 新闻中文化", localizationStage, ["items"]) +
      renderAiStageCard("AI 新闻理解", eventStage, ["events"]) +
      renderAiStageCard("AI 事态推演", scenarioStage, ["scenarios"]) +
      renderAiStageCard("AI 产业链展开", chainStage, ["industries", "chains", "supply_chains"]) +
      renderAiStageCard("AI 公司受益排序", companyStage, ["companies"]) +
      '</div></section>';
  }

  function renderAiStageCard(title, stage, preferredKeys) {
    const payload = stage.data || {};
    let preview = "未返回结构化结果。";
    for (let i = 0; i < preferredKeys.length; i += 1) {
      const key = preferredKeys[i];
      if (Array.isArray(payload[key]) && payload[key].length) {
        preview = payload[key].slice(0, 3).map(function (item) {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object") {
            return item.event_name || item.industry_name || item.chain_name || item.company_name || item.name || item.title || JSON.stringify(item);
          }
          return String(item);
        }).join("；");
        break;
      }
    }
    return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(title) + '</strong><span class="score-badge">' + escapeHtml(formatAiStatus(stage.status || "未运行")) + '</span></div><p><strong>当前目标：</strong>' + escapeHtml(stage.goal || "") + '</p><p><strong>下一步目标：</strong>' + escapeHtml(stage.next_stage_goal || "") + '</p><p>' + escapeHtml(stage.message || "") + '</p><p>' + escapeHtml(preview) + '</p></article>';
  }

  function renderMarketSnapshot(snapshot) {
    return '<section class="output-card"><h3>市场快照</h3><div class="chip-row">' +
      '<div class="chip"><strong>风险状态</strong><br>' + escapeHtml(snapshot.risk_regime || "未生成") + '</div>' +
      '<div class="chip"><strong>风格偏向</strong><br>' + escapeHtml(snapshot.index_bias || "未生成") + '</div>' +
      '<div class="chip"><strong>波动状态</strong><br>' + escapeHtml(snapshot.volatility_state || "未生成") + '</div>' +
      '<div class="chip"><strong>广度说明</strong><br>' + escapeHtml(snapshot.breadth_note || "未生成") + '</div>' +
      '<div class="chip"><strong>Provider</strong><br>' + escapeHtml((snapshot.provider || "unknown") + " / " + (snapshot.provider_status || "unknown")) + '</div>' +
      '</div></section>';
  }

  function renderExecutionPanel(recommendations) {
    const filtered = recommendations.filter(function (item) {
      return matchesExecutionFilter(item, executionFilter);
    });
    const cards = filtered.length ? filtered.map(function (item) {
      const technical = item.technical_overlay || {};
      const marketScore = item.market_score || {};
      const fundamentalScore = item.fundamental_score || {};
      const executionPlan = item.execution_plan || {};
      return [
        '<article class="scorecard execution-card">',
        '<div class="score-head">',
        '<strong>' + escapeHtml(item.name) + ' [' + escapeHtml(item.market || '未知市场') + '] (' + escapeHtml(item.symbol) + ')</strong>',
        '<span class="score-badge">' + escapeHtml(String(technical.technical_score || "n/a")) + '/100</span>',
        '</div>',
        '<p>' + escapeHtml((technical.trend_alignment || "未生成") + " / " + (technical.setup_quality || "未生成")) + '</p>',
        '<div class="execution-price-strip">',
        renderExecutionPriceChip("昨日收盘价", executionPlan.status === "ok" ? executionPlan.yesterday_close : (executionPlan.reason || "未生成")),
        renderExecutionPriceChip("建议买入价", executionPlan.status === "ok" && executionPlan.suggested_buy_price != null ? executionPlan.suggested_buy_price : "不适用"),
        renderExecutionPriceChip("建议卖出价", executionPlan.status === "ok" && executionPlan.suggested_sell_price != null ? executionPlan.suggested_sell_price : "不适用"),
        '</div>',
        '<dl>',
        '<dt>执行备注</dt><dd>' + escapeHtml(executionPlan.pricing_note || executionPlan.reason || "未生成") + '</dd>',
        '<dt>执行窗口</dt><dd>' + escapeHtml(technical.entry_window || "未生成") + '</dd>',
        '<dt>确认信号</dt><dd>' + escapeHtml((technical.confirmation_signals || []).join("、")) + '</dd>',
        '<dt>警告信号</dt><dd>' + escapeHtml((technical.warning_signals || []).join("、")) + '</dd>',
        '<dt>市场分 / 基本面分</dt><dd>' + escapeHtml(String(marketScore.score || "n/a") + " / " + String(fundamentalScore.score || "n/a")) + '</dd>',
        '<dt>Provider</dt><dd>' + escapeHtml((technical.provider || "unknown") + " / " + (technical.provider_status || "unknown")) + '</dd>',
        '<dt>标的历史</dt><dd><button type="button" class="ghost symbol-history-button" data-symbol="' + escapeHtml(item.symbol) + '">' + escapeHtml("查看 " + item.symbol + " 历史建议") + '</button></dd>',
        '</dl>',
        '</article>'
      ].join("");
    }).join("") : '<article class="risk-card"><p>当前筛选条件下没有可显示的执行确认标的。</p></article>';
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>执行确认面板</h3><p class="inline-note">把事件逻辑和技术确认拆开看，便于决定是否执行。</p></div><label class="field execution-filter"><span>筛选</span><select id="execution-filter-select"><option value="all">全部</option><option value="confirmed">技术确认强</option><option value="fallback">provider 已回退</option><option value="weak">技术确认偏弱</option></select></label></div><div class="scorecard-grid">' + cards + '</div></section>';
  }

  function renderNewsSection(stream) {
    const intraday = stream.intraday || [];
    const diagnostics = currentWorkspace && currentWorkspace.source_diagnostics ? currentWorkspace.source_diagnostics : {};
    return '<section class="output-card"><h3>热点事件流</h3><div class="chip-row">' +
      '<div class="chip"><strong>整体来源多样性</strong><br>' + escapeHtml(String(stream.source_diversity_score || "n/a")) + '/100 / ' + escapeHtml(stream.source_diversity_label || "未生成") + '</div>' +
      '<div class="chip"><strong>证据结构</strong><br>' + escapeHtml(stream.source_diversity_detail || "未生成") + '</div>' +
      '<div class="chip"><strong>覆盖提示</strong><br>' + escapeHtml(stream.coverage_gap_warning || "暂无明显覆盖缺口") + '</div>' +
      '<div class="chip"><strong>来源层级分布</strong><br>' + escapeHtml(formatLayerCounts(diagnostics.layer_counts || {})) + '</div>' +
      '</div><div class="scorecard-grid">' + intraday.map(function (item) {
      const title = item.translated_headline || item.headline;
      const summary = item.translated_summary || item.summary || "";
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(title) + '</strong><span class="score-badge">' + escapeHtml(String(item.hot_score)) + '/100</span></div><p>' + escapeHtml(summary) + '</p><dl><dt>来源</dt><dd>' + escapeHtml(item.source_name || "") + '</dd><dt>来源层级</dt><dd>' + escapeHtml(item.source_layer || "未标注") + ' / ' + escapeHtml(item.source_kind || "") + '</dd><dt>区域 / 市场</dt><dd>' + escapeHtml(item.region || "") + ' / ' + escapeHtml(item.market_scope || "") + '</dd><dt>标签</dt><dd>' + escapeHtml((item.tags || []).join("、")) + '</dd><dt>原始标题</dt><dd>' + escapeHtml(item.headline || "") + '</dd><dt>原始链接</dt><dd>' + renderSourceLinkButton(item.source_url, item.headline, item.source_name) + "</dd></dl></article>";
    }).join("") + "</div></section>";
  }

  function renderEvents(events) {
    return '<section class="output-card"><h3>事件详情与推演</h3><div class="scorecard-grid">' + events.map(function (event) {
      const supportingLinks = (event.supporting_news || []).slice(0, 3).map(function (item, index) {
        return '<div class="source-link-row"><span>' + escapeHtml((index + 1) + '. ' + (item.source_name || item.headline || '原文')) + '</span>' + renderSourceLinkButton(item.source_url, item.headline, item.source_name) + '</div>';
      }).join('');
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(event.title) + '</strong><div class="mini-meta"><span class="tone-badge tone-' + escapeHtml(event.direction) + '">' + escapeHtml(directionLabel(event.direction)) + '</span><span class="score-badge">' + escapeHtml(String(event.heat_score)) + '/100</span></div></div><p>' + escapeHtml(event.event_summary || "") + '</p>' + renderProfitPropagationBlock(event.profit_propagation || {}, "event") + '<dl><dt>事件主键</dt><dd>' + escapeHtml((event.event_master_id || "未生成") + " / " + (event.event_instance_id || "未生成")) + '</dd><dt>阶段</dt><dd>' + escapeHtml(event.stage || "") + '</dd><dt>时间窗口</dt><dd>' + escapeHtml(event.time_window || "") + '</dd><dt>来源多样性</dt><dd>' + escapeHtml(String(event.source_diversity_score || "n/a")) + '/100 / ' + escapeHtml(event.source_diversity_label || "未生成") + '</dd><dt>证据结构</dt><dd>' + escapeHtml(event.source_diversity_detail || "未生成") + '</dd><dt>覆盖提示</dt><dd>' + escapeHtml(event.coverage_gap_warning || "暂无明显覆盖缺口") + '</dd><dt>催化剂</dt><dd>' + escapeHtml((event.catalysts || []).join("、")) + '</dd><dt>失效条件</dt><dd>' + escapeHtml((event.invalidation_conditions || []).join("、")) + '</dd><dt>支持新闻原文</dt><dd>' + (supportingLinks || '暂无原始链接') + '</dd></dl><div class="event-history-actions"><button type="button" class="ghost event-history-button" data-event-master-id="' + escapeHtml(event.event_master_id || '') + '">查看该事件证据页</button></div></article>';
    }).join("") + "</div></section>";
  }

  function renderEventReplay(events) {
    const withHistory = (events || []).filter(function (event) {
      return Array.isArray(event.event_history) && event.event_history.length;
    });
    if (!withHistory.length) {
      return "";
    }
    return '<section class="output-card"><h3>事件版本回放</h3><div class="scorecard-grid">' + withHistory.map(function (event) {
      const rows = (event.event_history || []).map(function (item, index) {
        const profitFocus = (item.profit_focus || []).join("、") || "未生成";
        return '<div class="event-history-row"><strong>' + escapeHtml((index + 1) + '. ' + (item.generated_at || '')) + '</strong><span>' + escapeHtml((item.stage || '未标注') + ' / 热度 ' + String(item.heat_score || 'n/a')) + '</span><em>' + escapeHtml(item.change_summary || '') + '</em><p>' + escapeHtml('利润重心：' + profitFocus) + '</p></div>';
      }).join("");
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(event.title || '未命名事件') + '</strong><span class="score-badge">' + escapeHtml(String((event.event_history || []).length)) + ' 版</span></div><p>' + escapeHtml((event.event_master_id || '') + ' / ' + (event.event_instance_id || '')) + '</p><div class="event-history-list">' + rows + '</div><div class="event-history-actions"><button type="button" class="ghost event-history-button" data-event-master-id="' + escapeHtml(event.event_master_id || '') + '">查看该事件历史</button></div></article>';
    }).join("") + '</div></section>';
  }

  function renderEventReplayDetail(detail) {
    if (!detail || !detail.event_master_id) {
      return "";
    }
    const items = detail.history || [];
    const currentEvent = detail.current_event || {};
    const relatedIndustries = detail.related_industries || [];
    const relatedCandidates = detail.related_candidates || [];
    const relatedRecommendations = detail.related_recommendations || [];
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>事件证据页</h3><p class="inline-note">' + escapeHtml((detail.latest_title || '事件') + ' / ' + (detail.event_master_id || '')) + '</p></div><button type="button" class="ghost" id="close-event-replay-detail">关闭</button></div>' + renderEventEvidenceOverview(detail, currentEvent, relatedIndustries, relatedCandidates, relatedRecommendations) + '<div class="scorecard-grid">' + items.map(function (item, index) {
      const profitFocus = (item.profit_focus || []).join("、") || "未生成";
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml((index + 1) + '. ' + (item.generated_at || '')) + '</strong><span class="score-badge">' + escapeHtml(String(item.heat_score || 'n/a')) + '</span></div><p>' + escapeHtml(item.change_summary || '') + '</p><dl><dt>阶段</dt><dd>' + escapeHtml(item.stage || '未标注') + '</dd><dt>实例 ID</dt><dd>' + escapeHtml(item.event_instance_id || '未生成') + '</dd><dt>利润重心</dt><dd>' + escapeHtml(profitFocus) + '</dd><dt>事件摘要</dt><dd>' + escapeHtml(item.summary || '未生成') + '</dd></dl></article>';
    }).join("") + '</div></section>';
  }

  function renderEventEvidenceOverview(detail, currentEvent, relatedIndustries, relatedCandidates, relatedRecommendations) {
    const industriesText = relatedIndustries.map(function (item) {
      return (item.industry_name || '') + ((item.profit_focus || []).length ? (' / ' + item.profit_focus.join('、')) : '');
    }).join('；') || '暂无';
    const candidateText = relatedCandidates.slice(0, 6).map(function (item) {
      return [item.name || item.symbol || '', item.linkage_type || '', item.match_score != null ? (item.match_score + '分') : ''].filter(Boolean).join(' / ');
    }).join('；') || '暂无';
    const recommendationText = relatedRecommendations.slice(0, 6).map(function (item) {
      return [item.name || item.symbol || '', item.action || '', item.final_score != null ? (item.final_score + '分') : ''].filter(Boolean).join(' / ');
    }).join('；') || '暂无';
    return '<div class="event-evidence-grid">' +
      '<div class="comparison-box"><strong>当前事件判断</strong><p>' + escapeHtml(currentEvent.event_summary || detail.latest_title || '未生成') + '</p><dl><dt>阶段</dt><dd>' + escapeHtml(currentEvent.stage || detail.latest_stage || '未标注') + '</dd><dt>当前利润传导</dt><dd>' + escapeHtml(((currentEvent.profit_propagation || {}).profit_focus || []).join('、') || '未生成') + '</dd><dt>当前运行</dt><dd>' + escapeHtml(detail.latest_run_id || '未生成') + '</dd></dl></div>' +
      '<div class="comparison-box"><strong>相关产业链</strong><p>' + escapeHtml(industriesText) + '</p></div>' +
      '<div class="comparison-box"><strong>相关候选股</strong><p>' + escapeHtml(candidateText) + '</p></div>' +
      '<div class="comparison-box"><strong>当前建议</strong><p>' + escapeHtml(recommendationText) + '</p></div>' +
      '</div>';
  }

  function renderIndustries(industries) {
    return '<section class="output-card"><h3>产业链分析</h3><div class="scorecard-grid">' + industries.map(function (industry) {
      const impactedNodes = (industry.supply_chain || []).filter(function (node) { return node.is_impacted; }).map(function (node) { return node.name; });
      return '<article class="scorecard"><strong>' + escapeHtml(industry.industry_name) + '</strong><p>' + escapeHtml(industry.ai_summary || industry.description || "") + '</p>' + renderProfitPropagationBlock(industry.profit_propagation || {}, "industry") + '<dl><dt>当前状态</dt><dd>' + escapeHtml(industry.current_state || "") + '</dd><dt>受影响环节</dt><dd>' + escapeHtml(impactedNodes.join("、")) + '</dd><dt>结构要点</dt><dd>' + escapeHtml((industry.structural_notes || []).join("；")) + '</dd><dt>AI 新增环节</dt><dd>' + escapeHtml((industry.ai_chain_expansion || []).join("、") || "暂无") + '</dd></dl></article>';
    }).join("") + "</div></section>";
  }

  function renderCandidates(candidates) {
    const filtered = (candidates || []).filter(matchesCandidateFilters);
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>候选股票池</h3><p class="inline-note">按直接受益、AI 排名前列、龙头/弹性、A股/港股快速过滤。</p></div>' + renderCandidateFilterControls() + '</div><div class="scorecard-grid">' + filtered.slice(0, 24).map(function (item) {
      return '<article class="scorecard"><div class="score-head"><strong>' + escapeHtml(item.name) + " (" + escapeHtml(item.symbol) + ')</strong><span class="score-badge">' + escapeHtml(String(item.match_score)) + '/100</span></div><p>' + escapeHtml(item.rationale || "") + '</p><dl><dt>映射类型</dt><dd>' + escapeHtml(item.linkage_type || "") + '</dd><dt>AI 受益排序</dt><dd>' + escapeHtml(item.ai_beneficiary_rank ? ('第 ' + item.ai_beneficiary_rank + ' 位 / ' + (item.ai_beneficiary_level || '')) : '未进入 AI 排序前列') + '</dd><dt>产业位置</dt><dd>' + escapeHtml((item.direct_nodes || []).join("、")) + '</dd><dt>近期跟踪</dt><dd>' + escapeHtml((item.recent_vectors || []).join("、")) + "</dd></dl></article>";
    }).join("") + "</div></section>";
  }

  function renderRecommendations(recommendations) {
    const filtered = (recommendations || []).filter(matchesCandidateFilters);
    return '<section class="output-card"><div class="execution-panel-head"><div><h3>个股建议</h3><p class="inline-note">和候选池共享同一组强筛选，方便快速聚焦高质量标的。</p></div>' + renderCandidateFilterControls() + '</div><div class="scorecard-grid recommendation-grid">' + filtered.map(function (item) {
      const technical = item.technical_overlay || {};
      const price = item.price_snapshot || {};
      const valuation = item.valuation_snapshot || {};
      const fundamental = item.fundamental_snapshot || {};
      const marketScore = item.market_score || {};
      const fundamentalScore = item.fundamental_score || {};
      const riskScore = item.risk_score || {};
      const crowdingPenalty = item.crowding_penalty || {};
      const executionPlan = item.execution_plan || {};
      const confidenceGate = item.confidence_gate || {};
      const companyProfile = item.company_profile || {};
      const displayScore = item.final_score || item.score;
      const analystSignals = item.analyst_signals || {};
      const managerRationale = item.manager_rationale || [];
      const analystSummary = [
        analystSignals.event_analyst ? "事件 " + analystSignals.event_analyst.score : null,
        analystSignals.market_analyst ? "市场 " + analystSignals.market_analyst.score : null,
        analystSignals.fundamental_analyst ? "基本面 " + analystSignals.fundamental_analyst.score : null,
        analystSignals.beneficiary_analyst ? "受益排序 " + analystSignals.beneficiary_analyst.score : null,
        analystSignals.technical_analyst ? "技术 " + analystSignals.technical_analyst.score : null,
        analystSignals.risk_analyst ? "风险 " + analystSignals.risk_analyst.score : null
      ].filter(Boolean).join(" / ");
      return '<article class="scorecard execution-card"><div class="score-head"><strong>' + escapeHtml(item.name) + " [" + escapeHtml(item.market || "未知市场") + "] (" + escapeHtml(item.symbol) + ')</strong><div class="mini-meta"><span class="tone-badge tone-' + escapeHtml(actionTone(item.action)) + '">' + escapeHtml(item.action) + '</span><span class="score-badge">' + escapeHtml(String(displayScore)) + '/100</span></div></div><p>' + escapeHtml(item.core_logic || "") + '</p><div class="manager-box"><strong>Manager</strong><p>' + escapeHtml(item.manager_summary || "") + '</p><p>' + escapeHtml(analystSummary || "暂无分析器打分") + '</p><p>' + escapeHtml(riskScore.reason || "") + '</p>' + (managerRationale.length ? ('<details class=\"manager-rationale\"><summary>查看详细打分解释</summary><div class=\"manager-rationale-list\">' + managerRationale.map(function (line) { return '<p>' + escapeHtml(line) + '</p>'; }).join('') + '</div></details>') : '') + '</div>' + renderDecisionVerdictCard(item, confidenceGate) + renderThesisConditionsCard(item, confidenceGate) + renderCompanyProfileBlock(companyProfile) + '<dl><dt>催化剂</dt><dd>' + escapeHtml((item.catalysts || []).join("、")) + '</dd><dt>风险</dt><dd>' + escapeHtml((item.risks || []).join("、")) + '</dd><dt>利润重心</dt><dd>' + escapeHtml(item.profit_focus_summary || "未生成") + '</dd><dt>AI 受益排序</dt><dd>' + escapeHtml(item.ai_beneficiary_rank ? ('第 ' + item.ai_beneficiary_rank + ' 位 / ' + (item.ai_beneficiary_level || '') + ' / 加权 +' + String(item.ai_beneficiary_boost || 0) + ' / ' + (item.ai_ranking_rationale || '')) : '未进入 AI 排序前列') + '</dd><dt>新颖度 / 拥挤度</dt><dd>' + escapeHtml((crowdingPenalty.penalty ? ('惩罚 ' + String(crowdingPenalty.penalty) + ' 分') : '近期未见明显拥挤') + ' / ' + (crowdingPenalty.reason || '')) + '</dd><dt>来源多样性</dt><dd>' + escapeHtml(String(item.source_diversity_score || "n/a")) + '/100 / ' + escapeHtml(item.source_diversity_label || "未生成") + '</dd><dt>证据结构</dt><dd>' + escapeHtml(item.source_diversity_detail || "未生成") + '</dd><dt>覆盖提示</dt><dd>' + escapeHtml(item.coverage_gap_warning || "暂无明显覆盖缺口") + '</dd><dt>目标空间</dt><dd>' + escapeHtml(String(item.target_return_pct)) + '% / ' + escapeHtml(item.odds_label || "") + '</dd><dt>昨日收盘价</dt><dd>' + escapeHtml(executionPlan.status === 'ok' ? String(executionPlan.yesterday_close) : (executionPlan.reason || '未生成')) + '</dd><dt>建议买入价</dt><dd>' + escapeHtml(executionPlan.status === 'ok' && executionPlan.suggested_buy_price != null ? String(executionPlan.suggested_buy_price) : '不适用') + '</dd><dt>建议卖出价</dt><dd>' + escapeHtml(executionPlan.status === 'ok' && executionPlan.suggested_sell_price != null ? String(executionPlan.suggested_sell_price) : '不适用') + '</dd><dt>价格快照</dt><dd>' + escapeHtml(price.latest_price != null ? ("现价 " + price.latest_price + " / 日涨跌 " + price.day_change_pct + "% / 20日位置 " + price.position_20d_pct + "%") : (price.reason || "未生成")) + '</dd><dt>估值快照</dt><dd>' + escapeHtml(valuation.pe_ttm != null ? ("PE " + valuation.pe_ttm + " / PB " + valuation.pb + " / MV " + valuation.total_mv) : (valuation.reason || "未生成")) + '</dd><dt>财务快照</dt><dd>' + escapeHtml(fundamental.roe_dt != null ? ("ROE " + fundamental.roe_dt + " / 营收YoY " + fundamental.revenue_yoy + " / 利润YoY " + fundamental.netprofit_yoy) : (fundamental.reason || "未生成")) + '</dd><dt>市场分 / 基本面分 / 受益排序分 / 风险分</dt><dd>' + escapeHtml(String(marketScore.score || "n/a") + " / " + String(fundamentalScore.score || "n/a") + " / " + String((analystSignals.beneficiary_analyst || {}).score || "n/a") + " / " + String(riskScore.score || "n/a")) + '</dd><dt>失效条件</dt><dd>' + escapeHtml((item.invalidation_conditions || []).join("、")) + '</dd><dt>技术确认</dt><dd>' + escapeHtml("评分 " + String(technical.technical_score || "n/a") + " / " + (technical.trend_alignment || "未生成")) + '</dd><dt>执行窗口</dt><dd>' + escapeHtml((technical.entry_window || "未生成") + " / 止损参考：" + (technical.stop_reference || "未生成")) + '</dd><dt>确认信号</dt><dd>' + escapeHtml((technical.confirmation_signals || []).join("、")) + '</dd><dt>警告信号</dt><dd>' + escapeHtml((technical.warning_signals || []).join("、")) + '</dd><dt>技术 Provider</dt><dd>' + escapeHtml((technical.provider || "unknown") + " / " + (technical.provider_status || "unknown")) + "</dd></dl></article>";
    }).join("") + "</div></section>";
  }

  function renderProfitPropagationBlock(propagation, variant) {
    if (!propagation || !propagation.primary_profit_centers || !propagation.primary_profit_centers.length) {
      return "";
    }
    const centers = (propagation.primary_profit_centers || []).slice(0, 3).map(function (item) {
      return '<div class="propagation-chip"><span>' + escapeHtml(item.node_name || "") + '</span><strong>' + escapeHtml((item.profit_role || "利润传导") + " / " + String(item.propagation_score || "n/a")) + '</strong></div>';
    }).join("");
    const direct = (propagation.direct_beneficiaries || []).slice(0, 3).map(function (item) { return item.node_name; }).filter(Boolean).join("、");
    const indirect = (propagation.indirect_beneficiaries || []).slice(0, 3).map(function (item) { return item.node_name; }).filter(Boolean).join("、");
    const weak = (propagation.weak_links || []).slice(0, 3).map(function (item) { return item.node_name; }).filter(Boolean).join("、");
    return '<div class="propagation-box propagation-' + escapeHtml(variant || "industry") + '"><strong>利润传导</strong><p>' + escapeHtml(propagation.transmission_summary || "") + '</p><div class="propagation-chip-row">' + centers + '</div><dl><dt>集中度</dt><dd>' + escapeHtml(propagation.concentration_summary || "未生成") + '</dd><dt>直接受益</dt><dd>' + escapeHtml(direct || "暂无") + '</dd><dt>间接受益</dt><dd>' + escapeHtml(indirect || "暂无") + '</dd><dt>弱相关</dt><dd>' + escapeHtml(weak || "暂无") + '</dd></dl></div>';
  }

  function renderConfidenceGateBlock(gate) {
    if (!gate || !Object.keys(gate).length) {
      return "";
    }
    const isOpen = gate.high_confidence_eligible;
    const reasons = (gate.reasons || []).slice(0, 4).map(function (item) {
      return '<span class="chip gate-chip">' + escapeHtml(item) + '</span>';
    }).join("");
    return '<div class="confidence-gate-box tone-' + escapeHtml(isOpen ? "positive" : "negative") + '"><strong>高置信度门槛</strong><p>' + escapeHtml(gate.summary || (isOpen ? "满足高置信度门槛。" : "当前未满足高置信度门槛。")) + '</p><p>状态：' + escapeHtml(isOpen ? "已通过" : (gate.strict_block ? "严格拦截" : "软性降级")) + '</p>' + (reasons ? ('<div class="chip-row gate-chip-row">' + reasons + '</div>') : '') + '</div>';
  }

  function renderCompanyProfileBlock(profile) {
    if (!profile || !Object.keys(profile).length) {
      return "";
    }
    const businessSegments = (profile.business_segments || []).slice(0, 3).join("、") || "未生成";
    const profitSegments = (profile.profit_segments || []).slice(0, 3).join("、") || "未生成";
    const eventSensitivity = profile.historical_event_sensitivity || {};
    const ahPair = profile.ah_pair_symbol ? (profile.ah_pair_symbol + (profile.ah_pair_name ? (" / " + profile.ah_pair_name) : "")) : "暂无";
    return '<div class="company-profile-box"><strong>公司画像</strong><dl><dt>业务分部</dt><dd>' + escapeHtml(businessSegments) + '</dd><dt>利润分部</dt><dd>' + escapeHtml(profitSegments) + '</dd><dt>历史事件敏感度</dt><dd>' + escapeHtml((eventSensitivity.level || "待补充") + " / " + (eventSensitivity.summary || "未生成")) + '</dd><dt>A/H 联动</dt><dd>' + escapeHtml(ahPair) + '</dd><dt>画像完整度</dt><dd>' + escapeHtml(String(profile.profile_completeness != null ? profile.profile_completeness : "n/a")) + '/100</dd></dl></div>';
  }

  function renderThesisConditionsCard(item, confidenceGate) {
    const rankText = item.ai_beneficiary_rank
      ? ('第 ' + item.ai_beneficiary_rank + ' 位 / ' + (item.ai_beneficiary_level || ''))
      : '未进入 AI 排序前列';
    const gateText = confidenceGate && confidenceGate.high_confidence_eligible
      ? '已通过'
      : (confidenceGate && confidenceGate.strict_block ? '严格拦截' : '软性降级');
    const reasons = (confidenceGate && confidenceGate.reasons ? confidenceGate.reasons : []).slice(0, 3).join('、') || '暂无拦截原因';
    return '<div class="thesis-box"><strong>建议成立条件</strong><dl><dt>利润承接环节</dt><dd>' + escapeHtml(item.profit_focus_summary || '未生成') + '</dd><dt>AI 公司排序</dt><dd>' + escapeHtml(rankText) + '</dd><dt>高置信度门槛</dt><dd>' + escapeHtml(gateText + ' / ' + reasons) + '</dd></dl></div>';
  }

  function renderDecisionVerdictCard(item, confidenceGate) {
    const blocked = confidenceGate && !confidenceGate.high_confidence_eligible;
    let verdict = "结论待确认";
    if (item.action === "买入") {
      verdict = blocked ? "逻辑较强，但当前不满足高置信度买入条件" : "可以执行买入研究结论";
    } else if (item.action === "持有") {
      verdict = "逻辑仍成立，但更适合持有跟踪";
    } else if (item.action === "观察") {
      verdict = "暂时只能观察，等待证据继续强化";
    } else if (item.action === "卖出") {
      verdict = "当前应回避或降低暴露";
    }
    return '<div class="verdict-box"><strong>最终决策结论</strong><p>' + escapeHtml(verdict) + '</p><p>' + escapeHtml('利润重心：' + (item.profit_focus_summary || '未生成') + '；AI 排名：' + (item.ai_beneficiary_rank ? ('第 ' + item.ai_beneficiary_rank + ' 位') : '未进入前列') + '；门槛状态：' + (confidenceGate && confidenceGate.high_confidence_eligible ? '已通过' : '未通过')) + '</p></div>';
  }

  function renderCandidateFilterControls() {
    return '<div class="candidate-filter-bar">' +
      '<select id="filter-benefit"><option value="all">全部受益</option><option value="direct">直接受益</option></select>' +
      '<select id="filter-ai-rank"><option value="all">全部 AI 排名</option><option value="top">AI 前10</option></select>' +
      '<select id="filter-linkage"><option value="all">全部类型</option><option value="leader">龙头</option><option value="elastic">弹性</option></select>' +
      '<select id="filter-market"><option value="all">全部市场</option><option value="A股">A股</option><option value="港股">港股</option></select>' +
      '</div>';
  }

  function bindExecutionFilter() {
    const select = document.getElementById("execution-filter-select");
    if (!select) {
      return;
    }
    select.value = executionFilter;
    select.addEventListener("change", function () {
      executionFilter = select.value;
      if (currentWorkspace) {
        renderWorkspace(currentWorkspace);
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll(".symbol-history-button"), function (button) {
      button.addEventListener("click", function () {
        loadSymbolHistory(button.getAttribute("data-symbol"));
      });
    });
  }

  function renderHistory(history) {
    return '<section class="output-card"><h3>观点版本回溯</h3><div class="risk-grid">' + history.map(function (item) {
      const versions = (item.versions || []).map(function (version) {
        return version.timestamp + " " + version.version + " " + version.view_change;
      });
      return '<article class="risk-card"><strong>' + escapeHtml(item.name) + " (" + escapeHtml(item.symbol) + ') / 当前 ' + escapeHtml(item.current_action) + '</strong><p>当前分数：' + escapeHtml(String(item.current_score)) + '</p><p>' + escapeHtml(versions.join("；")) + "</p></article>";
    }).join("") + "</div></section>";
  }

  function renderRiskCards(riskCards) {
    const blocks = riskCards.length ? riskCards.map(function (card) {
      return '<article class="risk-card"><strong>' + escapeHtml(card.risk_type) + " / " + escapeHtml(card.target) + '</strong><p>' + escapeHtml(card.reason) + '</p><p><strong>行动问题：</strong>' + escapeHtml(card.action_question) + "</p></article>";
    }).join("") : '<article class="risk-card"><p>当前未触发超过阈值的风险卡。</p></article>';
    return '<section class="output-card"><h3>风险卡</h3><div class="risk-grid">' + blocks + "</div></section>";
  }

  function renderAgentTrace(agentTrace) {
    return '<section class="output-card"><h3>Agent 编排</h3><div class="agent-grid">' + agentTrace.map(function (item) {
      return '<article class="agent-card"><strong>' + escapeHtml(item.agent) + '</strong><p>' + escapeHtml(item.responsibility) + '</p><p>' + escapeHtml(item.output_summary) + "</p></article>";
    }).join("") + "</div></section>";
  }

  function renderListBlock(title, items) {
    const values = items.length ? items : ["暂无"];
    return '<div class="list-block"><strong>' + escapeHtml(title) + '</strong><div class="chip-row">' + values.map(function (item) {
      return '<div class="chip">' + escapeHtml(item) + "</div>";
    }).join("") + "</div></div>";
  }

  function renderMiniMetric(label, value) {
    return '<div class="mini-metric"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(value) + '</strong></div>';
  }

  function bindEventReplayButtons() {
    Array.prototype.forEach.call(document.querySelectorAll(".event-history-button"), function (button) {
      button.addEventListener("click", function () {
        loadEventHistoryDetail(button.getAttribute("data-event-master-id"));
      });
    });
    const closeButton = document.getElementById("close-event-replay-detail");
    if (closeButton) {
      closeButton.addEventListener("click", function () {
        currentEventReplay = null;
        if (currentWorkspace) {
          renderWorkspace(currentWorkspace);
        }
      });
    }
  }

  function bindPortfolioReplayButtons() {
    Array.prototype.forEach.call(document.querySelectorAll(".portfolio-replay-button"), function (button) {
      button.addEventListener("click", function () {
        loadPortfolioReplayDetail(button.getAttribute("data-run-id"));
      });
    });
    const closeButton = document.getElementById("close-portfolio-replay-detail");
    if (closeButton) {
      closeButton.addEventListener("click", function () {
        currentPortfolioReplay = null;
        if (currentWorkspace) {
          renderWorkspace(currentWorkspace);
        }
      });
    }
  }

  function loadPortfolioReplayDetail(runId) {
    if (!runId) {
      return;
    }
    fetch("/api/history/portfolio/" + encodeURIComponent(runId))
      .then(ensureJson)
      .then(function (detail) {
        currentPortfolioReplay = detail;
        if (currentWorkspace) {
          renderWorkspace(currentWorkspace);
        }
      })
      .catch(function (error) {
        setStatus("组合回放读取失败：" + error.message);
      });
  }

  function loadEventHistoryDetail(eventMasterId) {
    if (!eventMasterId) {
      return;
    }
    fetch("/api/history/events/" + encodeURIComponent(eventMasterId))
      .then(ensureJson)
      .then(function (detail) {
        currentEventReplay = detail;
        if (currentWorkspace) {
          renderWorkspace(currentWorkspace);
        }
      })
      .catch(function (error) {
        setStatus("事件历史读取失败：" + error.message);
      });
  }

  function renderExecutionPriceChip(label, value) {
    return '<div class="price-chip"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(String(value)) + '</strong></div>';
  }

  function renderSourceLinkButton(url, headline, sourceName) {
    if (!url) {
      const fallback = buildSourceSearchUrl(headline, sourceName);
      return '<a class="source-link-button source-link-fallback" href="' + escapeHtml(fallback) + '" target="_blank" rel="noopener noreferrer">搜索原文</a>';
    }
    return '<a class="source-link-button" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">查看原文</a>';
  }

  function buildSourceSearchUrl(headline, sourceName) {
    const query = [headline || "", sourceName || ""].filter(Boolean).join(" ");
    return "https://news.google.com/search?q=" + encodeURIComponent(query);
  }

  function renderTechnicalProviderStatus(payload) {
    technicalProviderStatus.textContent = (payload.provider || "unknown") + " / " + (payload.provider_status || "unknown");
    technicalProviderNote.textContent = payload.note || "未生成。";
  }

  function formatLayerCounts(layerCounts) {
    const labels = {
      media: "媒体",
      official: "官方",
      filing: "公告/财报",
      policy: "政策",
      industry_data: "行业数据"
    };
    const parts = Object.keys(layerCounts || {}).map(function (key) {
      return (labels[key] || key) + " " + layerCounts[key];
    });
    return parts.join(" / ") || "未生成";
  }

  function formatAiStatus(status) {
    const mapping = {
      ok: "正常",
      partial: "部分成功",
      error: "失败",
      invalid_response: "返回异常",
      disabled: "未启用",
      missing_credentials: "配置不完整",
      blocked: "已阻断",
      quota_exceeded: "配额不足",
      auth_error: "鉴权失败",
      rate_limited: "速率受限",
      provider_timeout: "请求超时",
      provider_unavailable: "服务不可用",
    };
    return mapping[status] || status || "未知";
  }

  function matchesCandidateFilters(item) {
    const relationTypes = item.relation_types || [];
    if (candidateFilters.benefit === "direct" && relationTypes.indexOf("直接受益") === -1 && item.ai_beneficiary_level !== "直接受益") {
      return false;
    }
    if (candidateFilters.aiRank === "top" && !(item.ai_beneficiary_rank && Number(item.ai_beneficiary_rank) <= 10)) {
      return false;
    }
    if (candidateFilters.linkage === "leader" && item.linkage_type !== "龙头") {
      return false;
    }
    if (candidateFilters.linkage === "elastic" && item.linkage_type !== "弹性标的") {
      return false;
    }
    if (candidateFilters.market !== "all" && item.market !== candidateFilters.market) {
      return false;
    }
    return true;
  }

  function bindCandidateFilters() {
    const benefit = document.getElementById("filter-benefit");
    const aiRank = document.getElementById("filter-ai-rank");
    const linkage = document.getElementById("filter-linkage");
    const market = document.getElementById("filter-market");
    [benefit, aiRank, linkage, market].forEach(function (node) {
      if (!node) {
        return;
      }
    });
    if (benefit) {
      benefit.value = candidateFilters.benefit;
      benefit.addEventListener("change", function () {
        candidateFilters.benefit = benefit.value;
        if (currentWorkspace) { renderWorkspace(currentWorkspace); }
      });
    }
    if (aiRank) {
      aiRank.value = candidateFilters.aiRank;
      aiRank.addEventListener("change", function () {
        candidateFilters.aiRank = aiRank.value;
        if (currentWorkspace) { renderWorkspace(currentWorkspace); }
      });
    }
    if (linkage) {
      linkage.value = candidateFilters.linkage;
      linkage.addEventListener("change", function () {
        candidateFilters.linkage = linkage.value;
        if (currentWorkspace) { renderWorkspace(currentWorkspace); }
      });
    }
    if (market) {
      market.value = candidateFilters.market;
      market.addEventListener("change", function () {
        candidateFilters.market = market.value;
        if (currentWorkspace) { renderWorkspace(currentWorkspace); }
      });
    }
  }

  function updateStageSummary(workspace) {
    const topEvent = (workspace.hotspot_events || [])[0] || {};
    const topRecommendation = (workspace.recommendation_views || [])[0] || {};
    const historyCount = (workspace.recommendation_history || []).length;
    runtimeTopEvent.textContent = topEvent.title || "暂无事件";
    runtimeTopEventNote.textContent = topEvent.event_summary || topEvent.stage || "当前工作台未生成事件摘要。";
    runtimeTopRecommendation.textContent = topRecommendation.name
      ? (topRecommendation.name + " " + topRecommendation.action)
      : "暂无建议";
    runtimeTopRecommendationNote.textContent = topRecommendation.symbol
      ? ([topRecommendation.market || "未知市场", topRecommendation.symbol, "综合分 " + String(topRecommendation.final_score || topRecommendation.score || "n/a")].join(" / "))
      : "当前工作台没有建议结果。";
    runtimeHistorySummary.textContent = historyCount
      ? (String(historyCount) + " 条观点回溯")
      : "暂无观点回溯";
    runtimeHistorySummaryNote.textContent = workspace.generated_at
      ? ("当前工作台生成于 " + workspace.generated_at)
      : "等待工作台或历史状态。";
  }

  function loadSymbolHistory(symbol) {
    if (!symbol) {
      return;
    }
    workspaceRoot.innerHTML = '<div class="empty-state"><p>正在载入 ' + escapeHtml(symbol) + ' 的历史建议...</p></div>';
    fetch("/api/history/recommendations/" + encodeURIComponent(symbol))
      .then(ensureJson)
      .then(function (items) {
        const cards = items.length ? items.map(function (item) {
          return '<article class="risk-card"><strong>' + escapeHtml(item.name) + " (" + escapeHtml(item.symbol) + ") / " + escapeHtml(item.action) + '</strong><p>分数：' + escapeHtml(String(item.score)) + ' / 置信度 ' + escapeHtml(String(item.confidence)) + '</p><p>窗口：' + escapeHtml(item.effective_window || "未生成") + '</p><p>' + escapeHtml(item.generated_logic || "") + "</p></article>";
        }).join("") : '<article class="risk-card"><p>暂无该标的历史建议。</p></article>';
        workspaceRoot.innerHTML = '<section class="output-card"><h3>' + escapeHtml(symbol) + ' 历史建议</h3><div class="risk-grid">' + cards + '</div></section>';
        setStatus("已载入 " + symbol + " 的历史建议。");
      })
      .catch(function (error) {
        workspaceRoot.innerHTML = '<div class="empty-state"><p>载入失败：' + escapeHtml(error.message) + "</p></div>";
      });
  }

  function deleteHistoryRun(runId) {
    if (!runId) {
      return;
    }
    fetch("/api/history/runs/" + encodeURIComponent(runId), {
      method: "DELETE"
    })
      .then(ensureJson)
      .then(function () {
        const item = historyList.querySelector('[data-run-id="' + CSS.escape(runId) + '"]');
        if (item) {
          const wrapper = item.closest(".history-item");
          if (wrapper) {
            wrapper.remove();
          }
        }
        const remaining = historyList.querySelectorAll(".history-item").length;
        historyCount.textContent = String(remaining) + " runs";
        if (!remaining) {
          historyList.innerHTML = '<div class="history-empty">还没有本地运行记录。</div>';
        }
        setStatus("已删除历史运行 " + runId.slice(0, 8) + "。");
        loadRuntimeStatus();
        loadHistoryRuns();
      })
      .catch(function (error) {
        setStatus("删除失败：" + error.message);
      });
  }

  function clearHistoryRuns() {
    fetch("/api/history/runs", {
      method: "DELETE"
    })
      .then(ensureJson)
      .then(function (payload) {
        setStatus("已清空本地历史，共删除 " + String(payload.deleted_count || 0) + " 条。");
        loadRuntimeStatus();
        loadHistoryRuns();
      })
      .catch(function (error) {
        setStatus("清空失败：" + error.message);
      });
  }

  function exportCurrentWorkspace(format) {
    if (!currentWorkspace) {
      setStatus("当前没有可导出的工作台。");
      return;
    }
    const generatedAt = String(currentWorkspace.generated_at || "workspace");
    const stem = generatedAt.replace(/[:T]/g, "-").replace(/\s+/g, "-");
    if (format === "json") {
      downloadFile(
        "workspace-" + stem + ".json",
        JSON.stringify(currentWorkspace, null, 2),
        "application/json"
      );
      setStatus("已导出 JSON。");
      return;
    }
    downloadFile(
      "workspace-" + stem + ".md",
      workspaceToMarkdown(currentWorkspace),
      "text/markdown"
    );
    setStatus("已导出 Markdown。");
  }

  function workspaceToMarkdown(workspace) {
    const lines = [];
    const digest = workspace.daily_digest || {};
    const market = workspace.market_snapshot || {};
    lines.push("# " + (digest.headline || "新闻驱动选股日报"));
    lines.push("");
    lines.push("生成时间: " + String(workspace.generated_at || ""));
    lines.push("");
    lines.push("## 摘要");
    lines.push("");
    lines.push(digest.summary || "暂无摘要");
    lines.push("");
    lines.push("## 市场快照");
    lines.push("");
    lines.push("- 风险状态: " + (market.risk_regime || "未生成"));
    lines.push("- 风格偏向: " + (market.index_bias || "未生成"));
    lines.push("- 波动状态: " + (market.volatility_state || "未生成"));
    lines.push("- Provider: " + (market.provider || "unknown") + " / " + (market.provider_status || "unknown"));
    lines.push("");
    lines.push("## 热点事件");
    lines.push("");
    (workspace.hotspot_events || []).forEach(function (event, index) {
      lines.push("### " + String(index + 1) + ". " + (event.title || "未命名事件"));
      lines.push("");
      lines.push("- 阶段: " + (event.stage || "未生成"));
      lines.push("- 热度: " + String(event.heat_score || "n/a"));
      lines.push("- 时间窗口: " + (event.time_window || "未生成"));
      lines.push("- 催化剂: " + (event.catalysts || []).join("、"));
      lines.push("- 失效条件: " + (event.invalidation_conditions || []).join("、"));
      lines.push("");
      lines.push(event.event_summary || "暂无摘要");
      lines.push("");
    });
    lines.push("## 个股建议");
    lines.push("");
    (workspace.recommendation_views || []).forEach(function (item, index) {
      const technical = item.technical_overlay || {};
      const price = item.price_snapshot || {};
      const fundamental = item.fundamental_snapshot || {};
      lines.push("### " + String(index + 1) + ". " + item.name + " (" + item.symbol + ") / " + item.action);
      lines.push("");
      lines.push("- 综合分: " + String(item.final_score || item.score) + " / 置信度 " + String(item.confidence));
      lines.push("- 目标空间: " + String(item.target_return_pct) + "% / " + (item.odds_label || "未生成"));
      lines.push("- 现价: " + (price.latest_price != null ? String(price.latest_price) : (price.reason || "未生成")));
      lines.push("- ROE: " + (fundamental.roe_dt != null ? String(fundamental.roe_dt) : (fundamental.reason || "未生成")));
      lines.push("- 催化剂: " + (item.catalysts || []).join("、"));
      lines.push("- 风险: " + (item.risks || []).join("、"));
      lines.push("- 技术确认: " + String(technical.technical_score || "n/a") + " / " + (technical.trend_alignment || "未生成"));
      lines.push("- 执行窗口: " + (technical.entry_window || "未生成"));
      lines.push("- 止损参考: " + (technical.stop_reference || "未生成"));
      lines.push("");
      lines.push(item.core_logic || "暂无逻辑");
      lines.push("");
    });
    lines.push("## 历史回溯");
    lines.push("");
    (workspace.recommendation_history || []).forEach(function (item) {
      lines.push("- " + item.name + " (" + item.symbol + ") / 当前 " + item.current_action + " / 分数 " + String(item.current_score));
    });
    lines.push("");
    return lines.join("\n");
  }

  function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function debounceHistoryReload() {
    if (historySearchTimer) {
      clearTimeout(historySearchTimer);
    }
    historySearchTimer = setTimeout(loadHistoryRuns, 250);
  }

  function loadRuntimeStatus() {
    fetch("/api/runtime/status")
      .then(ensureJson)
      .then(function (status) {
        runtimeDatabasePath.textContent = status.database_path || "未生成";
        runtimeStockAsOf.textContent = status.stock_data_as_of || "暂无";
        runtimeStockNote.textContent = status.stock_data_note || "未生成";
        runtimeNewsAsOf.textContent = status.news_data_as_of || "暂无";
        runtimeNewsNote.textContent = status.news_data_note || "未生成";
        runtimeLatestGenerated.textContent = status.latest_generated_at || "暂无";
        runtimeHistoryCount.textContent = "历史 " + String(status.history_count || 0) + " runs";
        runtimeTopEvent.textContent = status.latest_top_event || "暂无事件";
        runtimeTopEventNote.textContent = status.stock_data_as_of
          ? ("股价数据截至 " + status.stock_data_as_of)
          : "等待工作台或历史状态。";
        runtimeTopRecommendation.textContent = status.latest_top_recommendation || "暂无建议";
        runtimeTopRecommendationNote.textContent = status.news_data_as_of
          ? ("新闻数据截至 " + status.news_data_as_of)
          : "等待工作台或历史状态。";
        runtimeHistorySummary.textContent = status.latest_generated_at || "暂无生成";
        runtimeHistorySummaryNote.textContent = "累计 " + String(status.history_count || 0) + " 条本地运行";
        renderRuntimeRssPreview(status.news_preview_items || []);
      })
      .catch(function () {
        runtimeDatabasePath.textContent = "读取失败";
        runtimeStockAsOf.textContent = "读取失败";
        runtimeStockNote.textContent = "读取失败";
        runtimeNewsAsOf.textContent = "读取失败";
        runtimeNewsNote.textContent = "读取失败";
        runtimeLatestGenerated.textContent = "读取失败";
        runtimeHistoryCount.textContent = "读取失败";
        runtimeTopEvent.textContent = "读取失败";
        runtimeTopEventNote.textContent = "读取失败";
        runtimeTopRecommendation.textContent = "读取失败";
        runtimeTopRecommendationNote.textContent = "读取失败";
        runtimeHistorySummary.textContent = "读取失败";
        runtimeHistorySummaryNote.textContent = "读取失败";
        if (runtimeRssList) {
          runtimeRssList.innerHTML = '<div class="history-empty">RSS 列表读取失败。</div>';
        }
      });
  }

  function renderRuntimeRssPreview(items) {
    if (!runtimeRssList) {
      return;
    }
    if (!items || !items.length) {
      runtimeRssList.innerHTML = '<div class="history-empty">暂无 RSS 推送标题，请先刷新数据。</div>';
      return;
    }
    runtimeRssList.innerHTML = items.map(function (item, index) {
      const headline = item.headline || "未命名新闻";
      const source = item.source_name || "未知来源";
      const published = item.published_at ? String(item.published_at).slice(5, 16).replace("T", " ") : "";
      const layer = item.source_layer || "未标注";
      const link = item.source_url
        ? '<a class="source-link-button" href="' + escapeHtml(item.source_url) + '" target="_blank" rel="noopener noreferrer">查看原文</a>'
        : '<span class="source-link-disabled">无原文链接</span>';
      return '<div class="runtime-rss-item"><div class="runtime-rss-main"><strong>' + escapeHtml(String(index + 1) + ". " + headline) + '</strong><p>' + escapeHtml(source + (published ? " / " + published : "") + (layer ? " / " + layer : "")) + '</p></div><div class="runtime-rss-action">' + link + '</div></div>';
    }).join("");
  }

  function refreshDataSources() {
    setStatus("正在刷新股价数据和新闻数据...");
    fetch("/api/data/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rss_sources_text: rssSourcesInput.value.trim()
      })
    })
      .then(ensureJson)
      .then(function (payload) {
        setStatus("数据刷新完成。");
        if (payload && payload.news) {
          renderRuntimeRssPreview(payload.news.news_preview_items || []);
        }
        loadRuntimeStatus();
      })
      .catch(function (error) {
        setStatus("数据刷新失败：" + error.message);
      });
  }

  function matchesExecutionFilter(item, filterValue) {
    const technical = item.technical_overlay || {};
    const score = Number(technical.technical_score || 0);
    const providerStatus = String(technical.provider_status || "");
    if (filterValue === "confirmed") {
      return score >= 70 && providerStatus === "ok";
    }
    if (filterValue === "fallback") {
      return providerStatus.indexOf("fallback:") === 0 || providerStatus.indexOf("bridge_") === 0;
    }
    if (filterValue === "weak") {
      return score < 60;
    }
    return true;
  }

  function ensureJson(response) {
    if (!response.ok) {
      return response.json().then(function (data) {
        throw new Error(data.error || "请求失败");
      });
    }
    return response.json();
  }

  function setStatus(text) {
    settingsStatus.textContent = text;
  }

  function directionLabel(direction) {
    if (direction === "positive") { return "正向"; }
    if (direction === "negative") { return "负向"; }
    return "混合";
  }

  function actionTone(action) {
    if (action === "买入") { return "positive"; }
    if (action === "卖出") { return "negative"; }
    return "mixed";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();
