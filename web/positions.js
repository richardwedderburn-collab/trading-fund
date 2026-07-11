const positionsList = document.getElementById('positions-list');
const refreshBtn = document.getElementById('refresh-btn');
const ledgerStatus = document.getElementById('ledger-status');
const ledgerMeta = document.getElementById('ledger-meta');
const ledgerTxCount = document.getElementById('ledger-tx-count');
const ledgerWallets = document.getElementById('ledger-wallets');
const ledgerVolume = document.getElementById('ledger-volume');
const ledgerBlockRange = document.getElementById('ledger-block-range');
const equityCard = document.getElementById('equity-card');
const openPositionsCard = document.getElementById('open-positions-card');
const buyingPowerCard = document.getElementById('buying-power-card');
const equityStatus = document.getElementById('equity-status');
const brokerAccountBadge = document.getElementById('broker-account-badge');
const brokerAccountMeta = document.getElementById('broker-account-meta');
const brokerEnvironmentLabel = document.getElementById('broker-environment-label');
const brokerEnvironmentSubtext = document.getElementById('broker-environment-subtext');
const liveUpdateStatus = document.getElementById('live-update-status');
const positionsLastUpdated = document.getElementById('positions-last-updated');

const POSITIONS_POLL_MS_ACTIVE = 2000;
const POSITIONS_POLL_MS_BACKGROUND = 8000;
let positionsPollTimer = null;
let lastPositionsSignature = '';

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(value);
}

function buildLineChart(series, width = 120, height = 44, padding = 4) {
  const clean = series.map((value) => Number(value) || 0);
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = Math.max(1, max - min);
  const step = clean.length > 1 ? (width - padding * 2) / (clean.length - 1) : 0;

  const points = clean.map((value, index) => {
    const x = padding + index * step;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
  });

  const pointsAttr = points.map((point) => `${point.x},${point.y}`).join(' ');
  const areaPath = `M ${points[0].x} ${height - padding} L ${points
    .map((point) => `${point.x} ${point.y}`)
    .join(' L ')} L ${points[points.length - 1].x} ${height - padding} Z`;
  const last = points[points.length - 1];

  return `
    <svg class="line-chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img">
      <path class="line-area" d="${areaPath}"></path>
      <polyline class="line-path" points="${pointsAttr}"></polyline>
      <circle class="line-dot" cx="${last.x}" cy="${last.y}" r="2.8"></circle>
    </svg>
  `;
}

function renderPositions(positions) {
  if (!Array.isArray(positions) || positions.length === 0) {
    positionsList.innerHTML = '<div class="position-meta">No open positions found.</div>';
    return;
  }

  positionsList.innerHTML = positions
    .map((position) => {
      const history = [36, 38, 41, 39, 44, 46].map((value) => {
        return Math.max(16, value + (position.pnl >= 0 ? 6 : -2));
      });

      return `
        <div class="position-row">
          <div>
            <strong>${position.symbol}</strong>
            <div class="position-meta">Qty ${position.qty}</div>
          </div>
          <div>
            <div class="position-meta">Entry</div>
            <div>${formatCurrency(position.entry_price)}</div>
          </div>
          <div>
            <div class="position-meta">Market</div>
            <div>${formatCurrency(position.market_price)}</div>
          </div>
          <div>
            <div class="position-meta">P/L</div>
            <div class="position-pnl">${formatCurrency(position.pnl)}</div>
            <div class="position-side ${position.side.toLowerCase()}">${position.side}</div>
          </div>
          <div class="history-cell">
            <div class="position-meta">History</div>
            <div class="mini-chart" aria-label="${position.symbol} history">
              ${buildLineChart(history)}
            </div>
          </div>
        </div>
      `;
    })
    .join('');
}

function setPositionsLastUpdated(prefix = 'Last update') {
  if (!positionsLastUpdated) {
    return;
  }
  const now = new Date();
  positionsLastUpdated.textContent = `${prefix}: ${now.toLocaleTimeString()}`;
}

function buildPositionsSignature(positions) {
  if (!Array.isArray(positions)) {
    return 'invalid';
  }

  return positions
    .map((position) => {
      return [
        position.symbol,
        Number(position.qty || 0).toFixed(6),
        Number(position.entry_price || 0).toFixed(4),
        Number(position.market_price || 0).toFixed(4),
        Number(position.pnl || 0).toFixed(4),
        String(position.side || ''),
      ].join('|');
    })
    .sort()
    .join(';');
}

function flashPositionUpdates() {
  if (!positionsList) {
    return;
  }
  positionsList.classList.remove('positions-flash');
  window.requestAnimationFrame(() => {
    positionsList.classList.add('positions-flash');
  });
}

function renderLedger(snapshot) {
  if (!ledgerStatus) {
    return;
  }

  if (!snapshot?.ok) {
    ledgerStatus.textContent = 'Unavailable';
    ledgerStatus.className = 'panel-badge error-pill';
    ledgerMeta.textContent = `Reason: ${snapshot?.reason || 'request_failed'}`;
    ledgerTxCount.textContent = '--';
    ledgerWallets.textContent = '--';
    ledgerVolume.textContent = '--';
    ledgerBlockRange.textContent = '--';
    return;
  }

  ledgerStatus.textContent = 'Live';
  ledgerStatus.className = 'panel-badge';
  ledgerMeta.textContent = `Snapshot from block ${formatNumber(snapshot.from_block)} to ${formatNumber(snapshot.to_block)}`;
  ledgerTxCount.textContent = formatNumber(snapshot.ledger_tx_count || 0);
  ledgerWallets.textContent = formatNumber(snapshot.ledger_unique_wallets || 0);
  ledgerVolume.textContent = formatCurrency(snapshot.ledger_volume_usd || 0);
  ledgerBlockRange.textContent = `${formatNumber(snapshot.from_block || 0)}-${formatNumber(snapshot.to_block || 0)}`;
}

async function loadPositions() {
  try {
    const response = await fetch('/api/positions');
    const positions = await response.json();
    const signature = buildPositionsSignature(positions);
    const changed = signature !== lastPositionsSignature;
    lastPositionsSignature = signature;

    renderPositions(positions);
    if (changed) {
      flashPositionUpdates();
    }
    setPositionsLastUpdated('Last update');
    if (liveUpdateStatus) {
      liveUpdateStatus.textContent = `Live updates every ${Math.round(POSITIONS_POLL_MS_ACTIVE / 1000)}s`;
      liveUpdateStatus.className = 'panel-badge live-pill';
    }
    if (openPositionsCard) {
      openPositionsCard.textContent = String(Array.isArray(positions) ? positions.length : 0);
    }
  } catch (error) {
    positionsList.innerHTML = '<div class="position-meta">Unable to load live positions.</div>';
    if (liveUpdateStatus) {
      liveUpdateStatus.textContent = 'Reconnecting...';
      liveUpdateStatus.className = 'panel-badge error-pill';
    }
  }
}

async function loadAccount() {
  try {
    const response = await fetch('/api/account');
    const account = await response.json();
    if (!account?.ok) {
      if (equityStatus) {
        equityStatus.textContent = 'Account unavailable';
      }
      if (brokerAccountBadge) {
        brokerAccountBadge.textContent = account?.environment_label || 'Account unavailable';
        brokerAccountBadge.className = 'panel-badge error-pill';
      }
      if (brokerAccountMeta) {
        brokerAccountMeta.textContent = account?.message || 'Unable to read account metadata.';
      }
      if (brokerEnvironmentLabel) {
        brokerEnvironmentLabel.textContent = `${account?.environment_label || 'Broker account'} environment`;
      }
      return;
    }
    if (equityCard) {
      equityCard.textContent = formatCurrency(account.equity || 0);
    }
    if (buyingPowerCard) {
      buyingPowerCard.textContent = formatCurrency(account.buying_power || 0);
    }
    if (equityStatus) {
      equityStatus.textContent = 'Live account';
    }
    if (brokerAccountBadge) {
      brokerAccountBadge.textContent = account.environment_label || 'Broker account';
      brokerAccountBadge.className = `panel-badge ${account.environment === 'live' ? 'live-pill' : 'paper-pill'}`;
    }
    if (brokerAccountMeta) {
      const status = account.status ? String(account.status).toUpperCase() : 'UNKNOWN';
      const suffix = account.account_number ? ` • ${account.account_number}` : '';
      brokerAccountMeta.textContent = `${status}${suffix} • ${account.base_url || 'broker endpoint'}`;
    }
    if (brokerEnvironmentLabel) {
      brokerEnvironmentLabel.textContent = `${account.environment_label || 'Broker account'} environment`;
    }
    if (brokerEnvironmentSubtext) {
      brokerEnvironmentSubtext.textContent = `Monitoring real-time positions and balances from your ${account.environment_label || 'broker'} endpoint.`;
    }
  } catch (error) {
    if (equityStatus) {
      equityStatus.textContent = 'Account unavailable';
    }
    if (brokerAccountBadge) {
      brokerAccountBadge.textContent = 'Account unavailable';
      brokerAccountBadge.className = 'panel-badge error-pill';
    }
    if (brokerAccountMeta) {
      brokerAccountMeta.textContent = 'Unable to read account metadata.';
    }
    if (brokerEnvironmentLabel) {
      brokerEnvironmentLabel.textContent = 'Broker environment';
    }
  }
}

async function loadLedger() {
  try {
    const response = await fetch('/api/polymarket-ledger');
    if (!response.ok) {
      renderLedger({ ok: false, reason: `http_${response.status}` });
      return;
    }
    const snapshot = await response.json();
    renderLedger(snapshot);
  } catch (error) {
    renderLedger({ ok: false, reason: 'request_failed' });
  }
}

async function refreshAll() {
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Refreshing...';
  }
  await Promise.all([loadPositions(), loadLedger(), loadAccount()]);
  setPositionsLastUpdated('Manual refresh');
  if (refreshBtn) {
    refreshBtn.disabled = false;
    refreshBtn.textContent = 'Refresh data';
  }
}

function schedulePositionsPolling() {
  if (positionsPollTimer) {
    clearTimeout(positionsPollTimer);
  }

  const interval = document.hidden ? POSITIONS_POLL_MS_BACKGROUND : POSITIONS_POLL_MS_ACTIVE;
  positionsPollTimer = setTimeout(async () => {
    await loadPositions();
    schedulePositionsPolling();
  }, interval);
}

refreshBtn?.addEventListener('click', refreshAll);
document.addEventListener('visibilitychange', schedulePositionsPolling);

refreshAll();
schedulePositionsPolling();
setInterval(loadLedger, 10000);
setInterval(loadAccount, 10000);
