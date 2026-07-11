const datasetsStatus = document.getElementById('datasets-status');
const datasetsTableBody = document.getElementById('datasets-table-body');
const refreshDatasetsBtn = document.getElementById('refresh-datasets-btn');
const regenerateDatasetsBtn = document.getElementById('regenerate-datasets-btn');
const layerDatasetSelect = document.getElementById('layer-dataset-select');
const openLayerBtn = document.getElementById('open-layer-btn');
const layerMeta = document.getElementById('layer-meta');
const layerLiveStatus = document.getElementById('layer-live-status');
const layerTableHead = document.getElementById('layer-table-head');
const layerTableBody = document.getElementById('layer-table-body');
const layerColumnCount = document.getElementById('layer-column-count');
const layerRowCount = document.getElementById('layer-row-count');
const layerLastUpdated = document.getElementById('layer-last-updated');

const heroRunTitle = document.getElementById('hero-run-title');
const heroRunChip = document.getElementById('hero-run-chip');
const heroInsightList = document.getElementById('hero-insight-list');
const heroRunNote = document.getElementById('hero-run-note');
const foldList = document.getElementById('fold-list');
const driftChip = document.getElementById('drift-chip');
const driftWindowList = document.getElementById('drift-window-list');
const packStatusChip = document.getElementById('pack-status-chip');
const trendPackShare = document.getElementById('trend-pack-share');
const reversionPackShare = document.getElementById('reversion-pack-share');
const avgSizeMultiplier = document.getElementById('avg-size-multiplier');
const packBreakdownBars = document.getElementById('pack-breakdown-bars');
const regimeBreakdownList = document.getElementById('regime-breakdown-list');
const riskSnapshotList = document.getElementById('risk-snapshot-list');
const tradeDiagnosticList = document.getElementById('trade-diagnostic-list');
const driftChart = document.getElementById('drift-chart');
const packChart = document.getElementById('pack-chart');

const EXPORT_FORMATS = [
  { key: 'csv', label: 'CSV' },
  { key: 'json', label: 'JSON' },
  { key: 'xlsx', label: 'XLSX' },
  { key: 'sql', label: 'SQL' },
  { key: 'sqlite', label: 'SQLite' },
];

let datasetsCache = [];
let activeLayerDataset = '';
let activeLayerUpdatedAt = '';
let layerPollTimer = null;

function toDisplayName(name) {
  return String(name || '')
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatTimestamp(value) {
  if (!value) {
    return '--';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatCurrency(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatPercent(value, digits = 1) {
  const amount = Number(value || 0) * 100;
  return `${amount.toFixed(digits)}%`;
}

function formatNumber(value, digits = 2) {
  const amount = Number(value || 0);
  return amount.toFixed(digits);
}

function renderLineChart(target, series) {
  if (!target || !Array.isArray(series) || series.length < 2) {
    return;
  }

  const width = 320;
  const height = 140;
  const padding = 14;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = Math.max(1, max - min);
  const step = (width - padding * 2) / (series.length - 1);

  const points = series.map((value, index) => {
    const x = padding + index * step;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
  });

  const pointsAttr = points.map((point) => `${point.x},${point.y}`).join(' ');
  const areaPath = `M ${points[0].x} ${height - padding} L ${points
    .map((point) => `${point.x} ${point.y}`)
    .join(' L ')} L ${points[points.length - 1].x} ${height - padding} Z`;
  const last = points[points.length - 1];

  target.innerHTML = `
    <svg class="line-chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img">
      <defs>
        <linearGradient id="lineGradientStatic" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#4cc9f0"></stop>
          <stop offset="100%" stop-color="#7b61ff"></stop>
        </linearGradient>
      </defs>
      <line class="line-grid" x1="0" y1="40" x2="${width}" y2="40"></line>
      <line class="line-grid" x1="0" y1="78" x2="${width}" y2="78"></line>
      <line class="line-grid" x1="0" y1="116" x2="${width}" y2="116"></line>
      <path class="line-area" d="${areaPath}"></path>
      <polyline class="line-path" points="${pointsAttr}" style="stroke:url(#lineGradientStatic)"></polyline>
      <circle class="line-dot" cx="${last.x}" cy="${last.y}" r="4"></circle>
    </svg>
  `;
}

function downloadDataset(dataset, format) {
  const url = `/api/backtest/export?dataset=${encodeURIComponent(dataset)}&format=${encodeURIComponent(format)}`;
  window.open(url, '_blank', 'noopener');
}

async function fetchPreview(dataset, limit = 500) {
  const response = await fetch(`/api/backtest/preview?dataset=${encodeURIComponent(dataset)}&limit=${limit}`);
  const payload = await response.json();
  if (!payload?.ok) {
    throw new Error(payload?.reason || 'preview_failed');
  }
  return payload;
}

function renderDatasetRows(datasets) {
  if (!datasetsTableBody) {
    return;
  }

  if (!Array.isArray(datasets) || datasets.length === 0) {
    datasetsTableBody.innerHTML = `
      <tr>
        <td colspan="4">No datasets found in outputs/backtest.</td>
      </tr>
    `;
    return;
  }

  datasetsTableBody.innerHTML = datasets
    .map((item) => {
      const disabled = item.exists ? '' : 'disabled';
      const buttons = EXPORT_FORMATS
        .map(
          (format) =>
            `<button class="download-btn" type="button" ${disabled} data-dataset="${item.dataset}" data-format="${format.key}">${format.label}</button>`,
        )
        .join('');

      return `
        <tr>
          <td>${toDisplayName(item.dataset)}</td>
          <td>${item.rows}</td>
          <td>${formatTimestamp(item.updated_at)}</td>
          <td class="download-cell">${buttons}</td>
        </tr>
      `;
    })
    .join('');

  datasetsTableBody.querySelectorAll('.download-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const dataset = button.getAttribute('data-dataset');
      const format = button.getAttribute('data-format');
      if (!dataset || !format) {
        return;
      }
      downloadDataset(dataset, format);
    });
  });
}

function refreshLayerDatasetSelect(datasets) {
  if (!layerDatasetSelect) {
    return;
  }

  const previous = layerDatasetSelect.value;
  layerDatasetSelect.innerHTML = datasets
    .filter((item) => item.exists)
    .map((item) => `<option value="${item.dataset}">${toDisplayName(item.dataset)}</option>`)
    .join('');

  if (!layerDatasetSelect.value && datasets.length > 0) {
    layerDatasetSelect.value = datasets.find((item) => item.exists)?.dataset || '';
  }

  if (previous && layerDatasetSelect.querySelector(`option[value="${previous}"]`)) {
    layerDatasetSelect.value = previous;
  }
}

function setChipState(element, label, tone = 'positive') {
  if (!element) {
    return;
  }
  element.textContent = label;
  element.className = tone === 'warning' ? 'chip chip-warning' : tone === 'neutral' ? 'chip chip-neutral' : 'chip';
}

function renderList(target, rows) {
  if (!target) {
    return;
  }
  target.innerHTML = rows.join('');
}

function summarizeTrades(trades) {
  const countsByPack = new Map();
  const countsByRegime = new Map();
  let sizeMultiplierTotal = 0;
  let pnlPositive = 0;
  let pnlNegative = 0;

  trades.forEach((row) => {
    const pack = row.strategy_pack || 'unknown';
    const regime = row.regime_label || 'unknown';
    countsByPack.set(pack, (countsByPack.get(pack) || 0) + 1);
    countsByRegime.set(regime, (countsByRegime.get(regime) || 0) + 1);
    sizeMultiplierTotal += Number(row.size_multiplier || 0);
    if (Number(row.pnl_usd || 0) >= 0) {
      pnlPositive += 1;
    } else {
      pnlNegative += 1;
    }
  });

  return {
    countsByPack,
    countsByRegime,
    avgSizeMultiplier: trades.length ? sizeMultiplierTotal / trades.length : 0,
    pnlPositive,
    pnlNegative,
  };
}

function renderHero(summaryRow) {
  if (!summaryRow) {
    if (heroRunTitle) {
      heroRunTitle.textContent = 'No summary dataset found';
    }
    if (heroRunNote) {
      heroRunNote.textContent = 'Run a backtest export to populate overview metrics.';
    }
    setChipState(heroRunChip, 'Missing', 'warning');
    return;
  }

  const walkForwardEnabled = String(summaryRow.walk_forward_enabled).toLowerCase() === 'true';
  const degradationWarning = String(summaryRow.degradation_warning).toLowerCase() === 'true';
  const driftWarning = String(summaryRow.drift_warning).toLowerCase() === 'true';

  if (heroRunTitle) {
    heroRunTitle.textContent = walkForwardEnabled ? 'Walk-forward monitoring active' : 'In-sample backtest snapshot';
  }
  setChipState(heroRunChip, degradationWarning || driftWarning ? 'Attention' : 'Healthy', degradationWarning || driftWarning ? 'warning' : 'positive');

  if (heroInsightList) {
    heroInsightList.innerHTML = `
      <li><strong>In-sample PnL</strong><span>${formatCurrency(summaryRow.in_sample_total_pnl_usd || summaryRow.total_pnl_usd)}</span></li>
      <li><strong>Walk-forward PnL</strong><span>${walkForwardEnabled ? formatCurrency(summaryRow.total_pnl_usd) : 'Disabled'}</span></li>
      <li><strong>OOS/IS ratio</strong><span>${walkForwardEnabled ? formatNumber(summaryRow.oos_vs_insample_pnl_ratio, 3) : '--'}</span></li>
      <li><strong>Drift score</strong><span>${formatNumber(summaryRow.drift_score, 2)}</span></li>
    `;
  }

  if (heroRunNote) {
    heroRunNote.textContent = driftWarning
      ? summaryRow.drift_message || 'Rolling drift monitor flagged instability.'
      : summaryRow.degradation_message || 'Walk-forward and drift checks are within tolerance.';
  }
}

function renderRiskSnapshot(summaryRow) {
  if (!summaryRow) {
    renderList(riskSnapshotList, ['<li><strong>Waiting</strong><span>No summary metrics available</span></li>']);
    return;
  }

  renderList(riskSnapshotList, [
    `<li><strong>Best gateway floor</strong><span>${Number(summaryRow.best_gateway_min_volume || 0).toLocaleString()}</span></li>`,
    `<li><strong>Sharpe ratio</strong><span>${formatNumber(summaryRow.sharpe_ratio, 3)}</span></li>`,
    `<li><strong>Max drawdown</strong><span>${formatCurrency(summaryRow.max_drawdown_usd)}</span></li>`,
    `<li><strong>Worst trade</strong><span>${formatCurrency(summaryRow.max_loss_trade_usd)}</span></li>`,
    `<li><strong>Degradation threshold</strong><span>${formatPercent(summaryRow.degradation_threshold, 1)}</span></li>`,
    `<li><strong>Win rate</strong><span>${formatPercent(summaryRow.win_rate, 2)}</span></li>`,
  ]);
}

function renderFolds(folds) {
  if (!Array.isArray(folds) || folds.length === 0) {
    renderList(foldList, ['<li><strong>Walk-forward disabled</strong><span>No fold data available</span></li>']);
    return;
  }

  renderList(
    foldList,
    folds.slice(0, 6).map(
      (fold) =>
        `<li><strong>Fold ${fold.fold_id}</strong><span>${formatPercent(fold.win_rate, 2)} win, ${formatCurrency(fold.total_pnl_usd)} pnl, gate ${Number(fold.selected_min_volume_gate).toLocaleString()}</span></li>`,
    ),
  );
}

function renderDriftWindows(driftRows, summaryRow) {
  const warning = String(summaryRow?.drift_warning).toLowerCase() === 'true';
  setChipState(driftChip, warning ? 'Drift warning' : 'Stable', warning ? 'warning' : 'positive');

  if (!Array.isArray(driftRows) || driftRows.length === 0) {
    renderList(driftWindowList, ['<li><strong>Waiting</strong><span>No rolling drift windows available</span></li>']);
    return;
  }

  const recent = driftRows.slice(-3).reverse();
  if (Array.isArray(driftRows) && driftRows.length > 1) {
    renderLineChart(driftChart, driftRows.map((row) => Number(row.window_total_pnl_usd || 0)));
  }
  renderList(
    driftWindowList,
    recent.map(
      (row) =>
        `<li><strong>${row.end_date || 'Window'}</strong><span>${formatCurrency(row.window_total_pnl_usd)} pnl, ${formatPercent(row.window_win_rate, 2)} win, ${formatCurrency(row.window_avg_pnl_per_trade)} avg/trade</span></li>`,
    ),
  );
}

function renderStrategyPackSummary(trades) {
  if (!Array.isArray(trades) || trades.length === 0) {
    setChipState(packStatusChip, 'Missing', 'warning');
    trendPackShare.textContent = '--';
    reversionPackShare.textContent = '--';
    avgSizeMultiplier.textContent = '--';
    packBreakdownBars.innerHTML = '<div class="bar-row"><span>No trade metadata available</span></div>';
    renderList(regimeBreakdownList, ['<li><strong>Waiting</strong><span>No regime distribution loaded yet</span></li>']);
    return;
  }

  const summary = summarizeTrades(trades);
  const trendCount = summary.countsByPack.get('trend_following') || 0;
  const meanReversionCount = summary.countsByPack.get('mean_reversion') || 0;
  const total = trades.length;

  trendPackShare.textContent = formatPercent(trendCount / total, 1);
  reversionPackShare.textContent = formatPercent(meanReversionCount / total, 1);
  avgSizeMultiplier.textContent = formatNumber(summary.avgSizeMultiplier, 2);
  setChipState(packStatusChip, 'Live mix', 'positive');

  const packRows = Array.from(summary.countsByPack.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([pack, count]) => {
      const pct = total ? (count / total) * 100 : 0;
      return `
        <div class="bar-row">
          <div class="bar-copy">
            <strong>${toDisplayName(pack)}</strong>
            <span>${count} trades</span>
          </div>
          <div class="bar-track"><span style="width:${pct.toFixed(1)}%"></span></div>
          <div class="bar-value">${pct.toFixed(1)}%</div>
        </div>
      `;
    })
    .join('');
  packBreakdownBars.innerHTML = packRows;

  if (Array.isArray(trades) && trades.length > 1) {
    const runningPackBalance = [];
    let accumulator = 0;
    trades.forEach((row) => {
      accumulator += row.strategy_pack === 'trend_following' ? 1 : -1;
      runningPackBalance.push(accumulator);
    });
    renderLineChart(packChart, runningPackBalance);
  }

  const regimeRows = Array.from(summary.countsByRegime.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([regime, count]) => `<li><strong>${toDisplayName(regime)}</strong><span>${count} tagged trades</span></li>`);
  renderList(regimeBreakdownList, regimeRows);
}

function renderTradeDiagnostics(trades) {
  if (!Array.isArray(trades) || trades.length === 0) {
    renderList(tradeDiagnosticList, ['<li><strong>Waiting</strong><span>No trade diagnostics loaded</span></li>']);
    return;
  }

  const recentTrades = trades.slice(-4).reverse();
  renderList(
    tradeDiagnosticList,
    recentTrades.map((row) => {
      const pnl = Number(row.pnl_usd || 0);
      const direction = pnl >= 0 ? 'positive' : 'negative';
      return `<li><strong>${row.symbol} · ${toDisplayName(row.strategy_pack || 'unknown')}</strong><span class="diag-${direction}">${formatCurrency(pnl)} pnl | size ${formatNumber(row.size_multiplier, 2)} | z ${formatNumber(row.zscore_20d, 2)}</span></li>`;
    }),
  );
}

async function loadInsights() {
  const datasetNames = new Set(datasetsCache.filter((item) => item.exists).map((item) => item.dataset));

  const summaryPromise = datasetNames.has('summary') ? fetchPreview('summary', 5) : Promise.resolve(null);
  const foldsPromise = datasetNames.has('walk_forward_folds') ? fetchPreview('walk_forward_folds', 50) : Promise.resolve(null);
  const driftPromise = datasetNames.has('drift_monitor') ? fetchPreview('drift_monitor', 100) : Promise.resolve(null);
  const tradesPromise = datasetNames.has('trades') ? fetchPreview('trades', 400) : Promise.resolve(null);

  try {
    const [summaryPayload, foldsPayload, driftPayload, tradesPayload] = await Promise.all([
      summaryPromise,
      foldsPromise,
      driftPromise,
      tradesPromise,
    ]);

    const summaryRow = summaryPayload?.rows?.[0] || null;
    renderHero(summaryRow);
    renderRiskSnapshot(summaryRow);
    renderFolds(foldsPayload?.rows || []);
    renderDriftWindows(driftPayload?.rows || [], summaryRow);
    renderStrategyPackSummary(tradesPayload?.rows || []);
    renderTradeDiagnostics(tradesPayload?.rows || []);
  } catch (error) {
    setChipState(heroRunChip, 'Error', 'warning');
    if (heroRunNote) {
      heroRunNote.textContent = 'Unable to derive backtest insight panels from the export datasets.';
    }
  }
}

async function loadDatasets() {
  try {
    const response = await fetch('/api/backtest/datasets');
    const payload = await response.json();
    datasetsCache = Array.isArray(payload?.datasets) ? payload.datasets : [];
    renderDatasetRows(datasetsCache);
    refreshLayerDatasetSelect(datasetsCache);
    if (datasetsStatus) {
      datasetsStatus.textContent = `Datasets loaded: ${datasetsCache.filter((item) => item.exists).length}`;
      datasetsStatus.className = 'status-pill connected';
    }
    await loadInsights();
  } catch (error) {
    if (datasetsStatus) {
      datasetsStatus.textContent = 'Unable to load datasets.';
      datasetsStatus.className = 'status-pill';
    }
    setChipState(heroRunChip, 'Offline', 'warning');
  }
}

function renderLayerTable(columns, rows) {
  if (!layerTableHead || !layerTableBody) {
    return;
  }

  if (!Array.isArray(columns) || columns.length === 0) {
    layerTableHead.innerHTML = '';
    layerTableBody.innerHTML = '<tr><td>No columns available.</td></tr>';
    return;
  }

  layerTableHead.innerHTML = `<tr>${columns.map((column) => `<th>${column}</th>`).join('')}</tr>`;
  layerTableBody.innerHTML = rows
    .map((row) => `<tr>${columns.map((column) => `<td>${row[column] ?? ''}</td>`).join('')}</tr>`)
    .join('');
}

async function loadLayerPreview(forceMeta = false) {
  if (!activeLayerDataset) {
    return;
  }

  try {
    const payload = await fetchPreview(activeLayerDataset, 40);

    renderLayerTable(payload.columns || [], payload.rows || []);

    const didChange = activeLayerUpdatedAt && payload.updated_at && payload.updated_at !== activeLayerUpdatedAt;
    activeLayerUpdatedAt = payload.updated_at || '';

    if (layerMeta) {
      const changeSuffix = didChange ? ' | change detected' : '';
      layerMeta.textContent = `${toDisplayName(activeLayerDataset)} | rows: ${payload.row_count} | updated: ${formatTimestamp(payload.updated_at)}${changeSuffix}`;
    }

    if (layerColumnCount) {
      layerColumnCount.textContent = String((payload.columns || []).length);
    }
    if (layerRowCount) {
      layerRowCount.textContent = String((payload.rows || []).length);
    }
    if (layerLastUpdated) {
      layerLastUpdated.textContent = formatTimestamp(payload.updated_at);
    }

    if (layerLiveStatus) {
      layerLiveStatus.textContent = didChange ? 'Updated' : forceMeta ? 'Opened' : 'Monitoring';
      layerLiveStatus.className = 'chip';
    }
  } catch (error) {
    if (layerLiveStatus) {
      layerLiveStatus.textContent = 'Error';
      layerLiveStatus.className = 'status-pill';
    }
    if (layerMeta) {
      layerMeta.textContent = 'Unable to load live dataset preview.';
    }
  }
}

function scheduleLayerPolling() {
  if (layerPollTimer) {
    clearTimeout(layerPollTimer);
  }

  if (!activeLayerDataset) {
    return;
  }

  layerPollTimer = setTimeout(async () => {
    await loadLayerPreview(false);
    scheduleLayerPolling();
  }, 2500);
}

openLayerBtn?.addEventListener('click', async () => {
  activeLayerDataset = layerDatasetSelect?.value || '';
  activeLayerUpdatedAt = '';
  await loadLayerPreview(true);
  scheduleLayerPolling();
});

refreshDatasetsBtn?.addEventListener('click', async () => {
  refreshDatasetsBtn.disabled = true;
  refreshDatasetsBtn.textContent = 'Refreshing...';
  await loadDatasets();
  refreshDatasetsBtn.disabled = false;
  refreshDatasetsBtn.textContent = 'Refresh datasets';
});

regenerateDatasetsBtn?.addEventListener('click', async () => {
  regenerateDatasetsBtn.disabled = true;
  regenerateDatasetsBtn.textContent = 'Regenerating...';
  if (datasetsStatus) {
    datasetsStatus.textContent = 'Running backtest regeneration...';
    datasetsStatus.className = 'status-pill';
  }

  try {
    const response = await fetch('/api/backtest/regenerate');
    const payload = await response.json();
    if (!payload?.ok) {
      throw new Error(payload?.message || payload?.reason || 'regeneration_failed');
    }
    await loadDatasets();
    if (datasetsStatus) {
      datasetsStatus.textContent = 'Backtest exports regenerated successfully.';
      datasetsStatus.className = 'status-pill connected';
    }
  } catch (error) {
    if (datasetsStatus) {
      datasetsStatus.textContent = `Regeneration failed: ${error.message}`;
      datasetsStatus.className = 'status-pill';
    }
  } finally {
    regenerateDatasetsBtn.disabled = false;
    regenerateDatasetsBtn.textContent = 'Regenerate exports';
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (layerPollTimer) {
      clearTimeout(layerPollTimer);
    }
    return;
  }
  scheduleLayerPolling();
});

loadDatasets();
