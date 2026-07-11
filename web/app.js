const activityFeed = document.getElementById('activity-feed');
const walletState = document.getElementById('wallet-state');
const alpacaState = document.getElementById('alpaca-state');
const cryptoState = document.getElementById('crypto-state');
const accountForm = document.getElementById('account-form');
const loginForm = document.getElementById('login-form');
const loginStatus = document.getElementById('login-status');
const accountStatus = document.getElementById('account-status');
const heroBalance = document.getElementById('hero-balance');
const heroInflow = document.getElementById('hero-inflow');
const heroOutflow = document.getElementById('hero-outflow');
const balanceCard = document.getElementById('balance-card');
const positionsCard = document.getElementById('positions-card');
const riskCard = document.getElementById('risk-card');
const sharpeCard = document.getElementById('sharpe-card');
const yieldCard = document.getElementById('yield-card');
const hedgeCard = document.getElementById('hedge-card');
const bufferCard = document.getElementById('buffer-card');
const holdingsList = document.getElementById('holdings-list');
const portfolioCryptoBalances = document.getElementById('portfolio-crypto-balances');
const portfolioOpenPositions = document.getElementById('portfolio-open-positions');
const portfolioCryptoAssetCount = document.getElementById('portfolio-crypto-asset-count');
const portfolioCryptoEstimateUsd = document.getElementById('portfolio-crypto-estimate-usd');
const portfolioEquityGrossUsd = document.getElementById('portfolio-equity-gross-usd');
const portfolioAllocationChart = document.getElementById('portfolio-allocation-chart');
const portfolioAllocationNote = document.getElementById('portfolio-allocation-note');
const strategyAssumptions = document.getElementById('strategy-assumptions');
const consensusPolicy = document.getElementById('consensus-policy');
const walkforwardFolds = document.getElementById('walkforward-folds');
const scrollToSetup = document.getElementById('scrollToSetup');
const llmStatus = document.getElementById('llm-status');
const heroChart = document.getElementById('hero-chart');
const activityChart = document.getElementById('activity-chart');
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');
const gatedElements = document.querySelectorAll('[data-requires-auth="true"]');
const accountTabButton = document.querySelector('.tab-btn[data-tab="account"]');
const accountTabPanel = document.getElementById('account');
const refreshNetworkStatusButton = document.getElementById('refresh-network-status');
const egressIpv4 = document.getElementById('egress-ipv4');
const egressIpv6 = document.getElementById('egress-ipv6');
const egressWhitelist = document.getElementById('egress-whitelist');
const egressWarning = document.getElementById('egress-warning');
const cryptoBalancesList = document.getElementById('crypto-balances-list');
const executionPreviewChip = document.getElementById('execution-preview-chip');
const executionPreviewNote = document.getElementById('execution-preview-note');
const runExecutionPreview = document.getElementById('run-execution-preview');
const previewSymbols = document.getElementById('preview-symbols');
const previewRiskPct = document.getElementById('preview-risk-pct');
const previewCorrSoft = document.getElementById('preview-corr-soft');
const previewCorrHard = document.getElementById('preview-corr-hard');
const previewSoftMultiplier = document.getElementById('preview-soft-multiplier');
const previewSectorSoft = document.getElementById('preview-sector-soft');
const previewFactorSoft = document.getElementById('preview-factor-soft');
const previewGroupMultiplier = document.getElementById('preview-group-multiplier');
const previewCandidateCount = document.getElementById('preview-candidate-count');
const previewSelectedCount = document.getElementById('preview-selected-count');
const previewSpentUsd = document.getElementById('preview-spent-usd');
const previewSkippedCount = document.getElementById('preview-skipped-count');
const selectedOrdersList = document.getElementById('selected-orders-list');
const exposureAdjustmentsList = document.getElementById('exposure-adjustments-list');
const groupExposureList = document.getElementById('group-exposure-list');
const sectorExposureList = document.getElementById('sector-exposure-list');
const factorExposureList = document.getElementById('factor-exposure-list');
const packComparisonList = document.getElementById('pack-comparison-list');
const autoTradeToggleBtn = document.getElementById('autotrade-toggle-btn');
const autoTradeRunOnceBtn = document.getElementById('autotrade-run-once-btn');
const autoTradeRunLiveOnceBtn = document.getElementById('autotrade-run-live-once-btn');
const autoTradeRefreshBtn = document.getElementById('autotrade-refresh-btn');
const autoTradeSaveBtn = document.getElementById('autotrade-save-btn');
const autoTradeSaveOperatorBtn = document.getElementById('autotrade-save-operator-btn');
const autoTradeMode = document.getElementById('autotrade-mode');
const autoTradeInterval = document.getElementById('autotrade-interval');
const autoTradeSymbols = document.getElementById('autotrade-symbols');
const autoTradeOperatorName = document.getElementById('autotrade-operator-name');
const autoTradeOperatorRole = document.getElementById('autotrade-operator-role');
const autoTradeStatus = document.getElementById('autotrade-status');
const autoTradeEnabled = document.getElementById('autotrade-enabled');
const autoTradeLastRun = document.getElementById('autotrade-last-run');
const autoTradeLastMode = document.getElementById('autotrade-last-mode');
const autoTradeLastSelected = document.getElementById('autotrade-last-selected');
const autoTradeLastOrdersList = document.getElementById('autotrade-last-orders-list');

const equitySeries = [124580, 125020, 124760, 125310, 124990, 125420];
const activitySeries = [72, 68, 79, 75, 83, 81, 88];
const AUTH_KEY = 'fundflow.authenticated';
const CONNECTION_PREFS_KEY = 'fundflow.connectionPrefs';
const LIVE_RUN_COOLDOWN_SECONDS = 90;

const connectionStates = {
  alpaca: false,
  crypto: false,
  wallet: false,
};

const criticalFlags = {
  network: false,
  alpaca: false,
  crypto: false,
};

let safetyLockReason = '';
let liveRunCooldownUntilMs = 0;
let liveRunCooldownTimerId = null;

function getOperatorIdentity() {
  const savedName = String(window.localStorage.getItem('fundflow.operatorName') || '').trim();
  const savedRole = String(window.localStorage.getItem('fundflow.operatorRole') || '').trim().toLowerCase();
  return {
    name: savedName || 'dashboard-user',
    role: savedRole || 'trader',
  };
}

function loadOperatorProfileInputs() {
  const operator = getOperatorIdentity();
  if (autoTradeOperatorName) {
    autoTradeOperatorName.value = operator.name;
  }
  if (autoTradeOperatorRole) {
    autoTradeOperatorRole.value = operator.role;
  }
}

function saveOperatorProfile() {
  const name = String(autoTradeOperatorName?.value || '').trim() || 'dashboard-user';
  const role = String(autoTradeOperatorRole?.value || '').trim().toLowerCase() || 'trader';
  window.localStorage.setItem('fundflow.operatorName', name);
  window.localStorage.setItem('fundflow.operatorRole', role);
  setAutoTradeStatus(`Operator profile saved: ${name} (${role}).`, true);
}

function defaultConnectionPrefs() {
  return {
    alpaca: true,
    crypto: true,
    wallet: true,
  };
}

function loadConnectionPrefs() {
  try {
    const raw = window.localStorage.getItem(CONNECTION_PREFS_KEY);
    if (!raw) {
      return defaultConnectionPrefs();
    }
    const parsed = JSON.parse(raw);
    return {
      alpaca: parsed?.alpaca !== false,
      crypto: parsed?.crypto !== false,
      wallet: parsed?.wallet !== false,
    };
  } catch (error) {
    return defaultConnectionPrefs();
  }
}

let connectionPrefs = loadConnectionPrefs();

function saveConnectionPrefs() {
  window.localStorage.setItem(CONNECTION_PREFS_KEY, JSON.stringify(connectionPrefs));
}

function isSafetyLockActive() {
  return Object.values(criticalFlags).some(Boolean);
}

function updateSafetyLockState() {
  if (isSafetyLockActive()) {
    const reasons = [];
    if (criticalFlags.network) {
      reasons.push('network whitelist risk');
    }
    if (criticalFlags.alpaca) {
      reasons.push('alpaca trading protection');
    }
    if (criticalFlags.crypto) {
      reasons.push('crypto.com auth risk');
    }
    safetyLockReason = reasons.join(', ');
    if (accountStatus) {
      accountStatus.textContent = `Safety lock active: ${safetyLockReason}. Auto-reconnect paused.`;
    }
  } else {
    safetyLockReason = '';
  }
  renderConnectionButtons();
}

function setCriticalFlag(flag, value) {
  criticalFlags[flag] = Boolean(value);
  updateSafetyLockState();
}

function renderConnectionButtons() {
  const labels = {
    alpaca: 'Alpaca',
    crypto: 'Crypto.com',
    wallet: 'Wallet',
  };
  const buttons = document.querySelectorAll('[data-connection]');
  const locked = isSafetyLockActive();

  buttons.forEach((button) => {
    const target = button.getAttribute('data-connection');
    const desired = Boolean(connectionPrefs[target]);
    const connected = Boolean(connectionStates[target]);

    if (!desired) {
      button.textContent = `Enable ${labels[target]}`;
      button.disabled = false;
      return;
    }

    if (locked) {
      button.textContent = `Paused ${labels[target]} (safety lock)`;
      button.disabled = false;
      return;
    }

    button.textContent = connected ? `Disconnect ${labels[target]}` : `Connect ${labels[target]}`;
    button.disabled = false;
  });
}

function setConnectionDesired(target, desired) {
  connectionPrefs[target] = Boolean(desired);
  saveConnectionPrefs();
  renderConnectionButtons();
}

function isAuthenticated() {
  if (window.fundflowAuth?.isAuthenticated) {
    return window.fundflowAuth.isAuthenticated();
  }
  return window.localStorage.getItem(AUTH_KEY) === 'true';
}

function setAuthenticated(value) {
  if (window.fundflowAuth?.setAuthenticated) {
    window.fundflowAuth.setAuthenticated(value);
    return;
  }
  window.localStorage.setItem(AUTH_KEY, value ? 'true' : 'false');
}

function activateTab(tabName) {
  tabButtons.forEach((btn) => btn.classList.remove('active'));
  tabPanels.forEach((panel) => panel.classList.remove('active'));
  const activeBtn = Array.from(tabButtons).find((btn) => btn.getAttribute('data-tab') === tabName);
  if (activeBtn) {
    activeBtn.classList.add('active');
  }
  document.getElementById(tabName)?.classList.add('active');
}

function setAccessLock(locked) {
  document.body.classList.toggle('auth-locked', locked);

  gatedElements.forEach((el) => {
    if (locked) {
      el.classList.add('auth-disabled');
      if (el.tagName === 'BUTTON') {
        el.disabled = true;
      }
      if (el.tagName === 'A') {
        const anchor = el;
        if (!anchor.dataset.originalHref) {
          anchor.dataset.originalHref = anchor.getAttribute('href') || '#';
        }
        anchor.setAttribute('href', '#');
        anchor.setAttribute('aria-disabled', 'true');
        anchor.setAttribute('tabindex', '-1');
      }
    } else {
      el.classList.remove('auth-disabled');
      if (el.tagName === 'BUTTON') {
        el.disabled = false;
      }
      if (el.tagName === 'A') {
        const anchor = el;
        if (anchor.dataset.originalHref) {
          anchor.setAttribute('href', anchor.dataset.originalHref);
        }
        anchor.removeAttribute('aria-disabled');
        anchor.removeAttribute('tabindex');
      }
    }
  });

  if (accountTabButton) {
    accountTabButton.style.display = locked ? '' : 'none';
  }

  if (accountTabPanel) {
    accountTabPanel.style.display = locked ? '' : 'none';
  }

  if (locked) {
    activateTab('account');
    if (loginStatus) {
      loginStatus.textContent = 'Sign in to unlock trading functions';
    }
  } else {
    if (loginStatus) {
      loginStatus.textContent = 'Access unlocked';
    }
    const defaultTab = document.querySelector('.tab-btn[data-requires-auth="true"]');
    if (defaultTab) {
      const tabName = defaultTab.getAttribute('data-tab');
      if (tabName) {
        activateTab(tabName);
      }
    }
  }

  renderConnectionButtons();
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function setChipState(element, label, tone = 'positive') {
  if (!element) {
    return;
  }
  element.textContent = label;
  element.className = tone === 'warning' ? 'chip chip-warning' : tone === 'neutral' ? 'chip chip-neutral' : 'chip';
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
        <linearGradient id="lineGradient" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#4cc9f0"></stop>
          <stop offset="100%" stop-color="#7b61ff"></stop>
        </linearGradient>
      </defs>
      <line class="line-grid" x1="0" y1="40" x2="${width}" y2="40"></line>
      <line class="line-grid" x1="0" y1="78" x2="${width}" y2="78"></line>
      <line class="line-grid" x1="0" y1="116" x2="${width}" y2="116"></line>
      <path class="line-area" d="${areaPath}"></path>
      <polyline class="line-path" points="${pointsAttr}"></polyline>
      <circle class="line-dot" cx="${last.x}" cy="${last.y}" r="4"></circle>
    </svg>
  `;
}

function setAutoTradeStatus(message, connected = false) {
  if (!autoTradeStatus) {
    return;
  }
  autoTradeStatus.textContent = message;
  autoTradeStatus.className = connected ? 'status-pill connected' : 'status-pill';
}

function liveRunCooldownRemainingSeconds() {
  return Math.max(0, Math.ceil((liveRunCooldownUntilMs - Date.now()) / 1000));
}

function renderLiveRunButtonState() {
  if (!autoTradeRunLiveOnceBtn) {
    return;
  }
  const remaining = liveRunCooldownRemainingSeconds();
  if (remaining > 0) {
    autoTradeRunLiveOnceBtn.disabled = true;
    autoTradeRunLiveOnceBtn.textContent = `Live cooldown (${remaining}s)`;
    return;
  }
  autoTradeRunLiveOnceBtn.disabled = false;
  autoTradeRunLiveOnceBtn.textContent = 'Run live once (confirm)';
}

function startLiveRunCooldown(seconds = LIVE_RUN_COOLDOWN_SECONDS) {
  liveRunCooldownUntilMs = Date.now() + Math.max(1, Number(seconds || 0)) * 1000;
  if (liveRunCooldownTimerId) {
    window.clearInterval(liveRunCooldownTimerId);
  }
  renderLiveRunButtonState();
  liveRunCooldownTimerId = window.setInterval(() => {
    renderLiveRunButtonState();
    if (liveRunCooldownRemainingSeconds() <= 0) {
      window.clearInterval(liveRunCooldownTimerId);
      liveRunCooldownTimerId = null;
    }
  }, 1000);
}

function renderAutoTradeState(state) {
  if (!state) {
    return;
  }
  if (autoTradeMode) {
    autoTradeMode.value = String(state.mode || 'dry_run');
  }
  if (autoTradeInterval) {
    autoTradeInterval.value = String(state.interval_seconds || 300);
  }
  if (autoTradeSymbols) {
    autoTradeSymbols.value = Array.isArray(state.symbols) ? state.symbols.join(',') : '';
  }
  if (autoTradeEnabled) {
    autoTradeEnabled.textContent = state.enabled ? 'On' : 'Off';
    autoTradeEnabled.className = `state ${state.enabled ? 'connected' : 'disconnected'}`;
  }
  if (autoTradeLastRun) {
    autoTradeLastRun.textContent = state.last_run_at || '--';
  }
  if (autoTradeLastMode) {
    autoTradeLastMode.textContent = state.last_mode || '--';
  }
  if (autoTradeLastSelected) {
    autoTradeLastSelected.textContent = String(state?.last_result?.selected_orders ?? '--');
  }
  if (autoTradeLastOrdersList) {
    const details = Array.isArray(state?.last_result?.selected_order_details) ? state.last_result.selected_order_details : [];
    if (!details.length) {
      autoTradeLastOrdersList.innerHTML = '<li>Orders <span class="state">No selected orders in last cycle</span></li>';
    } else {
      autoTradeLastOrdersList.innerHTML = details
        .map((item) => {
          const symbol = String(item?.symbol || '').toUpperCase();
          const action = String(item?.action || '').toLowerCase();
          const notional = Number(item?.notional_usd || 0);
          const votes = Number(item?.votes || 0);
          return `<li>${symbol} ${action} (${votes} votes)<span class="state">${formatCurrency(notional)}</span></li>`;
        })
        .join('');
    }
  }
  if (autoTradeToggleBtn) {
    autoTradeToggleBtn.textContent = state.enabled ? 'Disable auto trade' : 'Enable auto trade';
  }
}

async function loadAutoTradeStatus() {
  if (!autoTradeStatus) {
    return;
  }
  try {
    const response = await fetch('/api/autotrade/status');
    const payload = await response.json();
    if (!payload?.ok) {
      throw new Error(payload?.reason || 'status_failed');
    }
    renderAutoTradeState(payload.state || {});
    const dueStatus = payload?.due_result?.skipped ? ` (${payload.due_result.skipped})` : '';
    setAutoTradeStatus(`Auto-trade profile loaded${dueStatus}.`, true);
  } catch (error) {
    setAutoTradeStatus(`Auto-trade status failed: ${error.message}`);
  }
}

async function toggleAutoTrade() {
  const currentlyEnabled = String(autoTradeEnabled?.textContent || '').toLowerCase() === 'on';
  const nextEnabled = !currentlyEnabled;
  try {
    const response = await fetch(`/api/autotrade/toggle?enabled=${nextEnabled ? 'true' : 'false'}`);
    const payload = await response.json();
    renderAutoTradeState(payload.state || {});
    setAutoTradeStatus(nextEnabled ? 'Auto-trade enabled.' : 'Auto-trade disabled.', true);
  } catch (error) {
    setAutoTradeStatus(`Toggle failed: ${error.message}`);
  }
}

async function saveAutoTradeConfig() {
  const params = new URLSearchParams({
    mode: autoTradeMode?.value || 'dry_run',
    interval_seconds: autoTradeInterval?.value || '300',
    symbols: autoTradeSymbols?.value || 'AAPL,MSFT,NVDA,TSLA,AMD,AMZN,META,GOOGL',
  });
  try {
    const response = await fetch(`/api/autotrade/config?${params.toString()}`);
    const payload = await response.json();
    renderAutoTradeState(payload.state || {});
    setAutoTradeStatus('Auto-trade settings saved.', true);
  } catch (error) {
    setAutoTradeStatus(`Save failed: ${error.message}`);
  }
}

async function runAutoTradeTestCycle() {
  try {
    const response = await fetch('/api/autotrade/run-once?execute=false');
    const payload = await response.json();
    renderAutoTradeState(payload.state || {});
    if (payload.ok) {
      setAutoTradeStatus('Alpaca test cycle completed (dry run).', true);
    } else {
      setAutoTradeStatus(`Test cycle failed: ${payload?.state?.last_error || 'unknown_error'}`);
    }
  } catch (error) {
    setAutoTradeStatus(`Test cycle failed: ${error.message}`);
  }
}

async function runAutoTradeLiveCycle() {
  const mode = String(autoTradeMode?.value || 'dry_run');
  if (mode !== 'live') {
    setAutoTradeStatus('Switch mode to Live execute before running a live cycle.');
    return false;
  }

  const acknowledgedRisk = window.confirm('Live mode will place real Alpaca orders. Continue?');
  if (!acknowledgedRisk) {
    setAutoTradeStatus('Live cycle cancelled.');
    return false;
  }

  const confirmation = window.prompt('Type LIVE to confirm one live Alpaca execution cycle.');
  if (confirmation !== 'LIVE') {
    setAutoTradeStatus('Live cycle cancelled (confirmation not matched).');
    return false;
  }

  try {
    const operator = getOperatorIdentity();
    const liveParams = new URLSearchParams({
      execute: 'true',
      operator_name: operator.name,
      operator_role: operator.role,
    });
    const response = await fetch(`/api/autotrade/run-once?${liveParams.toString()}`);
    const payload = await response.json();
    if (response.status === 429) {
      const remaining = Number(payload?.remaining_seconds || 0);
      if (remaining > 0) {
        startLiveRunCooldown(remaining);
      }
      setAutoTradeStatus(`Live run blocked by server cooldown (${remaining}s remaining).`);
      return false;
    }
    if (response.status === 403 || payload?.reason === 'live_approval_required') {
      const roles = Array.isArray(payload?.required_roles) ? payload.required_roles.join(', ') : 'owner, admin';
      setAutoTradeStatus(`Live run requires approver role. Allowed roles: ${roles}.`);
      return false;
    }
    renderAutoTradeState(payload.state || {});
    if (payload.ok) {
      setAutoTradeStatus('Live Alpaca cycle completed.', true);
      startLiveRunCooldown();
      return true;
    } else {
      setAutoTradeStatus(`Live cycle failed: ${payload?.state?.last_error || 'unknown_error'}`);
      return false;
    }
  } catch (error) {
    setAutoTradeStatus(`Live cycle failed: ${error.message}`);
    return false;
  }
}

const holdings = [
  { symbol: 'BTC', weight: 34, value: '$43,800', note: 'Core momentum' },
  { symbol: 'ETH', weight: 22, value: '$28,100', note: 'Layer-1 exposure' },
  { symbol: 'SOL', weight: 12, value: '$15,350', note: 'High beta growth' },
  { symbol: 'USDC', weight: 22, value: '$28,360', note: 'Liquidity reserve' },
  { symbol: 'AI Basket', weight: 10, value: '$12,930', note: 'Thematic sleeve' },
];

const strategyAssumptionRows = [
  { name: 'Crypto gate', detail: 'low TVL + smart wallet + fresh wallet age' },
  { name: 'Stock gate', detail: 'average volume above configurable floor' },
  { name: 'Polymarket gate', detail: 'ledger tx, unique wallets, and on-chain volume' },
  { name: 'Unknown markets', detail: 'rejected by default as safety guard' },
];

const consensusPolicyRows = [
  { name: 'Full execution', detail: 'meets configurable full-consensus threshold' },
  { name: 'Half execution', detail: 'meets half-consensus fallback threshold' },
  { name: 'No consensus', detail: 'capital stays at 0 and trade aborts' },
  { name: 'Gate failure', detail: 'signal rejected before heavy model usage' },
];

const foldRows = [
  { fold: 'Fold 1', detail: 'gate 250k, win 54.10%, pnl $476.19' },
  { fold: 'Fold 2', detail: 'gate 250k, win 51.08%, pnl $99.18' },
  { fold: 'Fold 3', detail: 'gate 250k, win 51.10%, pnl $288.00' },
  { fold: 'Fold 4', detail: 'gate 250k, win 52.77%, pnl $303.19' },
];

async function checkConnection(target) {
  try {
    const response = await fetch(`/api/connection?type=${target}`);
    const data = await response.json();
    return data;
  } catch (error) {
    return { ok: false, reason: 'request_failed', message: 'Unable to reach the connection service.' };
  }
}

async function loadLlmStatus() {
  try {
    const response = await fetch('/api/llm');
    const data = await response.json();
    if (data.ready) {
      llmStatus.textContent = `LLM ready via ${data.provider} (${data.model})`;
      llmStatus.className = 'status-pill connected';
    } else {
      llmStatus.textContent = 'LLM unavailable; add provider keys';
      llmStatus.className = 'status-pill';
    }
  } catch (error) {
    llmStatus.textContent = 'LLM check failed';
    llmStatus.className = 'status-pill';
  }
}

async function loadLivePortfolioSummary() {
  try {
    let equityGross = 0;
    const [positionsResp, accountResp, cryptoResp] = await Promise.all([
      fetch('/api/positions'),
      fetch('/api/account'),
      fetch('/api/crypto/balances'),
    ]);

    if (positionsResp.ok) {
      const positions = await positionsResp.json();
      const count = Array.isArray(positions) ? positions.length : 0;
      positionsCard.textContent = String(count);
      equityGross = (positions || []).reduce((sum, position) => {
        const qty = Number(position.qty || 0);
        const marketPrice = Number(position.market_price || 0);
        return sum + Math.abs(qty * marketPrice);
      }, 0);

      if (portfolioEquityGrossUsd) {
        portfolioEquityGrossUsd.textContent = formatCurrency(equityGross);
      }

      renderList(
        portfolioOpenPositions,
        count
          ? positions.slice(0, 10).map(
              (position) =>
                `<li><strong>${position.symbol}</strong><span>${position.side || 'LONG'} | qty ${Number(position.qty || 0).toFixed(4)} | pnl ${formatCurrency(Number(position.pnl || 0))}</span></li>`,
            )
          : ['<li><strong>Positions</strong><span>No open positions.</span></li>'],
      );

      activitySeries.push(65 + count * 4);
      if (activitySeries.length > 16) {
        activitySeries.shift();
      }
      renderLineChart(activityChart, activitySeries);
    }

    if (accountResp.ok) {
      const account = await accountResp.json();
      if (account?.ok) {
        const equity = Number(account.equity || 0);
        const buyingPower = Number(account.buying_power || 0);
        setCriticalFlag('alpaca', Boolean(account.trading_blocked));
        heroBalance.textContent = formatCurrency(equity);
        balanceCard.textContent = formatCurrency(equity);
        heroOutflow.textContent = formatCurrency(Math.max(0, buyingPower));
        equitySeries.push(equity);
        if (equitySeries.length > 16) {
          equitySeries.shift();
        }
        renderLineChart(heroChart, equitySeries);
      }
    }

    if (cryptoResp.ok) {
      const crypto = await cryptoResp.json();
      if (crypto?.ok && Array.isArray(crypto.balances)) {
        const quoteSymbols = crypto.balances
          .map((row) => String(row.currency || '').toUpperCase())
          .filter((symbol) => Boolean(symbol));
        let quoteMap = {};
        if (quoteSymbols.length > 0) {
          try {
            const quotesResp = await fetch(`/api/crypto/quotes?symbols=${encodeURIComponent(quoteSymbols.join(','))}`);
            const quotes = await quotesResp.json();
            quoteMap = quotes?.quotes || {};
          } catch (error) {
            quoteMap = {};
          }
        }

        if (portfolioCryptoAssetCount) {
          portfolioCryptoAssetCount.textContent = String(crypto.balances.length);
        }

        const estimate = estimateCryptoUsdFromBalances(crypto.balances, quoteMap);
        if (portfolioCryptoEstimateUsd) {
          portfolioCryptoEstimateUsd.textContent = formatCurrency(estimate.usdEstimate);
        }
        renderAllocationChart(portfolioAllocationChart, estimate.usdEstimate, equityGross);
        if (portfolioAllocationNote) {
          portfolioAllocationNote.textContent = estimate.excludedAssets > 0
            ? `Estimate excludes ${estimate.excludedAssets} non-USD-priced crypto assets.`
            : 'Allocation estimate uses full available balances and positions snapshots.';
        }

        renderList(
          portfolioCryptoBalances,
          crypto.balances.length
            ? crypto.balances.slice(0, 10).map(
                (row) =>
                  `<li><strong>${row.currency}</strong><span>balance ${Number(row.balance || 0).toFixed(6)} | available ${Number(row.available || 0).toFixed(6)}</span></li>`,
              )
            : ['<li><strong>Balances</strong><span>No non-zero balances returned.</span></li>'],
        );
      } else {
        if (portfolioCryptoAssetCount) {
          portfolioCryptoAssetCount.textContent = '0';
        }
        if (portfolioCryptoEstimateUsd) {
          portfolioCryptoEstimateUsd.textContent = formatCurrency(0);
        }
        renderAllocationChart(portfolioAllocationChart, 0, equityGross);
        renderList(
          portfolioCryptoBalances,
          ['<li><strong>Balances unavailable</strong><span>Crypto.com is not connected or returned an error.</span></li>'],
        );
      }
    }
  } catch (error) {
    // Keep last known values in place when snapshot refresh fails.
  }
}

const activityItems = [
  { label: 'BTC buy', amount: '+$4,200', time: '10m ago' },
  { label: 'ETH withdrawal', amount: '-$1,120', time: '1h ago' },
  { label: 'USDC deposit', amount: '+$3,500', time: '3h ago' },
  { label: 'SOL trade close', amount: '+$860', time: '5h ago' },
];

function renderActivity() {
  activityFeed.innerHTML = activityItems
    .map(
      (item) => `
        <li>
          <span>${item.label}</span>
          <div>
            <strong>${item.amount}</strong>
            <div class="muted-label">${item.time}</div>
          </div>
        </li>
      `,
    )
    .join('');
}

function renderHoldings() {
  if (!holdingsList) {
    return;
  }

  holdingsList.innerHTML = holdings
    .map(
      (holding) => `
        <li class="holding-item">
          <div class="holding-top">
            <strong>${holding.symbol} · ${holding.value}</strong>
            <span>${holding.weight}%</span>
          </div>
          <div class="holding-track" aria-label="${holding.symbol} allocation ${holding.weight}%">
            <div class="holding-fill" style="width:${holding.weight}%"></div>
          </div>
          <span>${holding.note}</span>
        </li>
      `,
    )
    .join('');
}

function renderInsightList(targetEl, rows, keyName) {
  if (!targetEl) {
    return;
  }

  targetEl.innerHTML = rows
    .map((row) => `<li><strong>${row[keyName]}</strong><span>${row.detail}</span></li>`)
    .join('');
}

function renderList(targetEl, items) {
  if (!targetEl) {
    return;
  }
  targetEl.innerHTML = items.join('');
}

function estimateCryptoUsdFromBalances(balances, quoteMap = {}) {
  const stableCurrencies = new Set(['USD', 'USDT', 'USDC']);
  let usdEstimate = 0;
  let excludedAssets = 0;

  (balances || []).forEach((row) => {
    const currency = String(row.currency || '').toUpperCase();
    const balance = Number(row.balance || 0);
    if (stableCurrencies.has(currency)) {
      usdEstimate += balance;
    } else if (Number(quoteMap[currency] || 0) > 0) {
      usdEstimate += balance * Number(quoteMap[currency] || 0);
    } else {
      excludedAssets += 1;
    }
  });

  return { usdEstimate, excludedAssets };
}

function renderAllocationChart(target, cryptoUsd, equityUsd) {
  if (!target) {
    return;
  }

  const total = Math.max(cryptoUsd + equityUsd, 0);
  const cryptoPct = total > 0 ? (cryptoUsd / total) * 100 : 0;
  const equityPct = total > 0 ? (equityUsd / total) * 100 : 0;

  target.innerHTML = `
    <div class="bar-stack" style="padding:14px;">
      <div class="bar-row">
        <div class="bar-copy">
          <strong>Crypto (fiat-est.)</strong>
          <span>${formatCurrency(cryptoUsd)}</span>
        </div>
        <div class="bar-track"><span style="width:${Math.max(cryptoPct, 2)}%"></span></div>
        <strong class="bar-value">${cryptoPct.toFixed(1)}%</strong>
      </div>
      <div class="bar-row">
        <div class="bar-copy">
          <strong>Equities</strong>
          <span>${formatCurrency(equityUsd)}</span>
        </div>
        <div class="bar-track"><span style="width:${Math.max(equityPct, 2)}%"></span></div>
        <strong class="bar-value">${equityPct.toFixed(1)}%</strong>
      </div>
    </div>
  `;
}

async function loadExecutionPreview() {
  if (!runExecutionPreview) {
    return;
  }

  const params = new URLSearchParams({
    symbols: previewSymbols?.value || '',
    max_risk_pct: previewRiskPct?.value || '0.05',
    corr_soft_limit: previewCorrSoft?.value || '0.75',
    corr_hard_limit: previewCorrHard?.value || '0.9',
    exposure_soft_multiplier: previewSoftMultiplier?.value || '0.5',
    sector_soft_limit: previewSectorSoft?.value || '1.0',
    factor_soft_limit: previewFactorSoft?.value || '1.0',
    group_soft_multiplier: previewGroupMultiplier?.value || '0.65',
  });

  runExecutionPreview.disabled = true;
  runExecutionPreview.textContent = 'Running...';
  setChipState(executionPreviewChip, 'Syncing', 'neutral');

  try {
    const response = await fetch(`/api/strategy/execution-preview?${params.toString()}`);
    const payload = await response.json();
    if (!payload?.ok) {
      throw new Error(payload?.message || payload?.reason || 'preview_failed');
    }

    previewCandidateCount.textContent = String(payload.candidate_count ?? 0);
    previewSelectedCount.textContent = String((payload.selected_orders || []).length);
    previewSpentUsd.textContent = formatCurrency(payload.spent_usd || 0);
    previewSkippedCount.textContent = String((payload.skipped_by_exposure || []).length);

    renderList(
      selectedOrdersList,
      (payload.selected_orders || []).length
        ? payload.selected_orders.map(
            (order) =>
              `<li><strong>${order.symbol}</strong><span>${formatCurrency(order.notional_usd)} | ${order.action} | size ${Number(order.size_multiplier || 1).toFixed(2)} | votes ${String(order.votes || []).replaceAll(',', '/')}</span></li>`,
          )
        : ['<li><strong>No orders selected</strong><span>The current constraints filtered out all candidates.</span></li>'],
    );

    const exposureItems = [];
    (payload.exposure_adjustments || []).forEach((row) => {
      exposureItems.push(
        `<li><strong>${row.symbol} resized</strong><span>Peer ${row.peer_symbol} | corr ${Number(row.correlation || 0).toFixed(2)} | multiplier ${Number(row.size_multiplier || 0).toFixed(2)}</span></li>`,
      );
    });
    (payload.skipped_by_exposure || []).forEach((row) => {
      exposureItems.push(
        `<li><strong>${row.symbol} skipped</strong><span>Peer ${row.peer_symbol} | corr ${Number(row.correlation || 0).toFixed(2)} | ${row.reason}</span></li>`,
      );
    });
    renderList(
      exposureAdjustmentsList,
      exposureItems.length
        ? exposureItems
        : ['<li><strong>Exposure controls</strong><span>No correlation-based adjustments were needed in this dry run.</span></li>'],
    );

    renderList(
      groupExposureList,
      (payload.group_exposure_adjustments || []).length
        ? (payload.group_exposure_adjustments || []).map(
            (row) =>
              `<li><strong>${row.symbol} ${row.group_type} resize</strong><span>${row.group_name} | projected ${(Number(row.projected_ratio || 0) * 100).toFixed(1)}% > limit ${(Number(row.limit || 0) * 100).toFixed(1)}% | size x${Number(row.size_multiplier || 1).toFixed(2)}</span></li>`,
          )
        : ['<li><strong>Group controls</strong><span>No sector/factor group adjustments were required.</span></li>'],
    );

    renderList(
      sectorExposureList,
      (payload.sector_exposure_snapshot || []).length
        ? (payload.sector_exposure_snapshot || []).map(
            (row) =>
              `<li><strong>${row.group}</strong><span>${formatCurrency(row.notional_usd || 0)} | ${(Number(row.risk_budget_ratio || 0) * 100).toFixed(1)}% of risk budget</span></li>`,
          )
        : ['<li><strong>Sector exposure</strong><span>No sector allocation snapshot is available.</span></li>'],
    );

    renderList(
      factorExposureList,
      (payload.factor_exposure_snapshot || []).length
        ? (payload.factor_exposure_snapshot || []).map(
            (row) =>
              `<li><strong>${row.group}</strong><span>${formatCurrency(row.notional_usd || 0)} | ${(Number(row.risk_budget_ratio || 0) * 100).toFixed(1)}% of risk budget</span></li>`,
          )
        : ['<li><strong>Factor exposure</strong><span>No factor allocation snapshot is available.</span></li>'],
    );

    renderList(
      packComparisonList,
      (payload.per_symbol_pack_comparison || []).length
        ? (payload.per_symbol_pack_comparison || []).map((row) => {
            const trend = row.trend_following || {};
            const mean = row.mean_reversion || {};
            const trendAlloc = formatCurrency(Number(trend.allocated_capital || 0));
            const meanAlloc = formatCurrency(Number(mean.allocated_capital || 0));
            return `<li><strong>${row.symbol} | ${row.regime_label || 'unknown'} | recommended ${row.recommended_pack || 'n/a'}</strong><span>Trend ${trendAlloc} (score ${Number(trend.consensus_score || 0)}) vs Mean ${meanAlloc} (score ${Number(mean.consensus_score || 0)})</span></li>`;
          })
        : ['<li><strong>Per symbol compare</strong><span>No pack comparison is available for the current symbol set.</span></li>'],
    );

    setChipState(executionPreviewChip, 'Preview ready', 'positive');
    if (executionPreviewNote) {
      executionPreviewNote.textContent = `Risk budget ${formatCurrency(payload.risk_budget_usd || 0)} | auto slots ${payload.effective_new_position_slots || 0} | remaining ${formatCurrency(payload.remaining_budget_usd || 0)}.`;
    }
  } catch (error) {
    setChipState(executionPreviewChip, 'Error', 'warning');
    if (executionPreviewNote) {
      executionPreviewNote.textContent = `Preview failed: ${error.message}`;
    }
  } finally {
    runExecutionPreview.disabled = false;
    runExecutionPreview.textContent = 'Run dry run';
  }
}

function updateConnection(target, connected) {
  connectionStates[target] = Boolean(connected);
  const stateMap = {
    wallet: walletState,
    alpaca: alpacaState,
    crypto: cryptoState,
  };
  const stateEl = stateMap[target] || walletState;
  stateEl.textContent = connected ? 'Connected' : 'Disconnected';
  stateEl.className = `state ${connected ? 'connected' : 'disconnected'}`;
  renderConnectionButtons();
}

function summarizeBalances(balances) {
  if (!Array.isArray(balances) || balances.length === 0) {
    return 'No non-zero balances returned';
  }

  return balances
    .slice(0, 5)
    .map((row) => `${Number(row.balance).toFixed(6)} ${row.currency}`)
    .join(' | ');
}

function renderCryptoBalances(balances) {
  if (!cryptoBalancesList) {
    return;
  }

  if (!Array.isArray(balances) || balances.length === 0) {
    cryptoBalancesList.innerHTML = `
      <li>
        Balances
        <span class="state">No non-zero balances</span>
      </li>
    `;
    return;
  }

  cryptoBalancesList.innerHTML = balances
    .slice(0, 8)
    .map(
      (row) => `
        <li>
          ${row.currency}
          <span class="state">${Number(row.balance).toFixed(6)}</span>
        </li>
      `,
    )
    .join('');
}

async function loadNetworkStatus() {
  if (!egressIpv4 || !egressIpv6 || !egressWhitelist || !egressWarning) {
    return;
  }

  try {
    const response = await fetch('/api/network/egress-ip');
    const data = await response.json();
    const ipv4 = data?.current?.ipv4 || 'Unavailable';
    const ipv6 = data?.current?.ipv6 || 'Unavailable';
    const whitelistEntries = Array.isArray(data?.whitelist_entries) ? data.whitelist_entries : [];

    egressIpv4.textContent = ipv4;
    egressIpv6.textContent = ipv6;
    egressWhitelist.textContent = whitelistEntries.length ? whitelistEntries.join(' | ') : 'None';
    egressWarning.textContent = data?.warning || 'Network status up to date.';
    egressWarning.className = data?.warning ? 'status-pill' : 'status-pill connected';
    setCriticalFlag('network', Boolean(data?.warning));
  } catch (error) {
    egressIpv4.textContent = 'Unavailable';
    egressIpv6.textContent = 'Unavailable';
    egressWhitelist.textContent = 'Unavailable';
    egressWarning.textContent = 'Unable to load network diagnostics.';
    egressWarning.className = 'status-pill';
    setCriticalFlag('network', true);
  }
}

async function attemptConnection(target, source = 'manual') {
  if (target === 'crypto') {
    try {
      const response = await fetch('/api/crypto/balances');
      const data = await response.json();
      if (data.ok) {
        setCriticalFlag('crypto', false);
        updateConnection(target, true);
        renderCryptoBalances(data.balances);
        accountStatus.textContent = `Crypto.com connected. Balances: ${summarizeBalances(data.balances)}`;
        return true;
      }

      updateConnection(target, false);
      const detail = data.message || data.reason || 'Balance request failed';
      const isCritical = /ip_illegal|authentication failure|unauthorized|401/i.test(detail);
      setCriticalFlag('crypto', isCritical);
      if (source === 'manual') {
        accountStatus.textContent = `Crypto.com connection failed: ${detail}`;
      }
      return false;
    } catch (error) {
      updateConnection(target, false);
      if (source === 'manual') {
        accountStatus.textContent = 'Crypto.com connection failed: Unable to reach the balance endpoint.';
      }
      return false;
    }
  }

  const result = await checkConnection(target);
  const ok = Boolean(result?.ok);
  updateConnection(target, ok);

  if (source === 'manual') {
    const name = target === 'wallet' ? 'Wallet' : target === 'alpaca' ? 'Alpaca' : 'Platform';
    if (ok) {
      accountStatus.textContent = `${name} connected successfully`;
    } else {
      const detail = result?.missing_keys?.length
        ? `Missing keys: ${result.missing_keys.join(', ')}`
        : result?.message || 'Connection failed';
      accountStatus.textContent = `${name} connection failed: ${detail}`;
    }
  }
  return ok;
}

async function reconcileConnections() {
  if (!isAuthenticated()) {
    return;
  }

  await loadNetworkStatus();
  if (isSafetyLockActive()) {
    return;
  }

  if (connectionPrefs.alpaca) {
    await attemptConnection('alpaca', 'auto');
  }
  if (connectionPrefs.crypto) {
    await attemptConnection('crypto', 'auto');
  }
  if (connectionPrefs.wallet) {
    await attemptConnection('wallet', 'auto');
  }
}

document.querySelectorAll('[data-connection]').forEach((button) => {
  button.addEventListener('click', async () => {
    const target = button.getAttribute('data-connection');
    const desired = Boolean(connectionPrefs[target]);
    const connected = Boolean(connectionStates[target]);

    if (desired && connected) {
      setConnectionDesired(target, false);
      updateConnection(target, false);
      if (target === 'crypto') {
        renderCryptoBalances([]);
      }
      accountStatus.textContent = `${target === 'wallet' ? 'Wallet' : target === 'alpaca' ? 'Alpaca' : 'Crypto.com'} auto-connect disabled manually.`;
      return;
    }

    setConnectionDesired(target, true);
    await attemptConnection(target, 'manual');
  });
});

refreshNetworkStatusButton?.addEventListener('click', async () => {
  refreshNetworkStatusButton.disabled = true;
  refreshNetworkStatusButton.textContent = 'Refreshing...';
  await loadNetworkStatus();
  refreshNetworkStatusButton.disabled = false;
  refreshNetworkStatusButton.textContent = 'Refresh network';
});

autoTradeRefreshBtn?.addEventListener('click', async () => {
  autoTradeRefreshBtn.disabled = true;
  autoTradeRefreshBtn.textContent = 'Refreshing...';
  await loadAutoTradeStatus();
  autoTradeRefreshBtn.disabled = false;
  autoTradeRefreshBtn.textContent = 'Refresh auto-trade status';
});

autoTradeToggleBtn?.addEventListener('click', async () => {
  autoTradeToggleBtn.disabled = true;
  await toggleAutoTrade();
  autoTradeToggleBtn.disabled = false;
});

autoTradeSaveBtn?.addEventListener('click', async () => {
  autoTradeSaveBtn.disabled = true;
  await saveAutoTradeConfig();
  autoTradeSaveBtn.disabled = false;
});

autoTradeSaveOperatorBtn?.addEventListener('click', () => {
  autoTradeSaveOperatorBtn.disabled = true;
  saveOperatorProfile();
  autoTradeSaveOperatorBtn.disabled = false;
});

autoTradeRunOnceBtn?.addEventListener('click', async () => {
  autoTradeRunOnceBtn.disabled = true;
  autoTradeRunOnceBtn.textContent = 'Running test...';
  await runAutoTradeTestCycle();
  autoTradeRunOnceBtn.disabled = false;
  autoTradeRunOnceBtn.textContent = 'Run Alpaca test cycle';
});

autoTradeRunLiveOnceBtn?.addEventListener('click', async () => {
  if (liveRunCooldownRemainingSeconds() > 0) {
    renderLiveRunButtonState();
    return;
  }
  autoTradeRunLiveOnceBtn.disabled = true;
  autoTradeRunLiveOnceBtn.textContent = 'Running live...';
  await runAutoTradeLiveCycle();
  renderLiveRunButtonState();
});

accountForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = document.getElementById('fullName').value.trim();
  const email = document.getElementById('email').value.trim();
  if (!name || !email) {
    accountStatus.textContent = 'Please complete your profile details';
    return;
  }
  accountStatus.textContent = `Welcome aboard, ${name.split(' ')[0]}! Your workspace is ready.`;
  riskCard.textContent = '19%';
  sharpeCard.textContent = '1.57';
  yieldCard.textContent = '$1,420';
  hedgeCard.textContent = '72%';
  bufferCard.textContent = '25%';
});

loginForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  const email = document.getElementById('loginEmail')?.value.trim() || '';
  const password = document.getElementById('loginPassword')?.value.trim() || '';
  if (!email || !password) {
    if (loginStatus) {
      loginStatus.textContent = 'Email and password are required';
    }
    return;
  }
  setAuthenticated(true);
  setAccessLock(false);
  accountStatus.textContent = `Signed in as ${email}`;
  loadLivePortfolioSummary();
  reconcileConnections();
  loadExecutionPreview();
});

runExecutionPreview?.addEventListener('click', () => {
  loadExecutionPreview();
});

scrollToSetup?.addEventListener('click', () => {
  document.getElementById('workspace').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

tabButtons.forEach((button) => {
  button.addEventListener('click', () => {
    if (button.hasAttribute('data-requires-auth') && !isAuthenticated()) {
      activateTab('account');
      if (loginStatus) {
        loginStatus.textContent = 'Please sign in to access this section';
      }
      return;
    }
    tabButtons.forEach((btn) => btn.classList.remove('active'));
    tabPanels.forEach((panel) => panel.classList.remove('active'));
    button.classList.add('active');
    const target = button.getAttribute('data-tab');
    document.getElementById(target)?.classList.add('active');
  });
});

renderActivity();
renderHoldings();
renderInsightList(strategyAssumptions, strategyAssumptionRows, 'name');
renderInsightList(consensusPolicy, consensusPolicyRows, 'name');
renderInsightList(walkforwardFolds, foldRows, 'fold');
renderLineChart(heroChart, equitySeries);
renderLineChart(activityChart, activitySeries);
renderLiveRunButtonState();
loadOperatorProfileInputs();
loadLlmStatus();
const requiresAuth = new URLSearchParams(window.location.search).get('auth') === 'required';
if (requiresAuth && loginStatus) {
  loginStatus.textContent = 'Sign in required before accessing other pages';
}
setAccessLock(!isAuthenticated());
if (isAuthenticated()) {
  loadLivePortfolioSummary();
  reconcileConnections();
  loadExecutionPreview();
  loadAutoTradeStatus();
}
setInterval(() => {
  if (isAuthenticated()) {
    loadLivePortfolioSummary();
    reconcileConnections();
    loadAutoTradeStatus();
  }
}, 30000);

renderConnectionButtons();
