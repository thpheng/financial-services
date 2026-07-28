const STORAGE_KEY = "stock-value-app.holdings";
const QUOTE_URL = (symbol) =>
  `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=1d`;

const els = {
  form: document.getElementById("add-form"),
  symbolInput: document.getElementById("symbol-input"),
  sharesInput: document.getElementById("shares-input"),
  refreshBtn: document.getElementById("refresh-btn"),
  autoRefreshToggle: document.getElementById("auto-refresh-toggle"),
  body: document.getElementById("holdings-body"),
  emptyRow: document.getElementById("empty-row"),
  totalValue: document.getElementById("total-value"),
  totalChange: document.getElementById("total-change"),
  lastUpdated: document.getElementById("last-updated"),
  errorBanner: document.getElementById("error-banner"),
};

let holdings = loadHoldings();
let autoRefreshTimer = null;

function loadHoldings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHoldings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(holdings));
}

function showError(message) {
  els.errorBanner.textContent = message;
  els.errorBanner.hidden = false;
}

function clearError() {
  els.errorBanner.hidden = true;
  els.errorBanner.textContent = "";
}

function formatMoney(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function formatSigned(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString(undefined, { style: "currency", currency: "USD" })}`;
}

async function fetchQuote(symbol) {
  const res = await fetch(QUOTE_URL(symbol));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const result = data?.chart?.result?.[0];
  if (!result) {
    const reason = data?.chart?.error?.description || "symbol not found";
    throw new Error(reason);
  }
  const meta = result.meta;
  return {
    price: meta.regularMarketPrice ?? null,
    previousClose: meta.chartPreviousClose ?? meta.previousClose ?? null,
    currency: meta.currency ?? "USD",
    name: meta.longName || meta.shortName || meta.symbol,
  };
}

function render() {
  els.body.innerHTML = "";

  if (holdings.length === 0) {
    els.body.appendChild(els.emptyRow);
    els.totalValue.textContent = formatMoney(0);
    els.totalChange.textContent = formatMoney(0);
    return;
  }

  let totalValue = 0;
  let totalChange = 0;
  let hasData = false;

  for (const h of holdings) {
    const tr = document.createElement("tr");

    const price = h.quote?.price ?? null;
    const prevClose = h.quote?.previousClose ?? null;
    const change = price !== null && prevClose !== null ? price - prevClose : null;
    const changePct = change !== null && prevClose ? (change / prevClose) * 100 : null;
    const value = price !== null ? price * h.shares : null;

    if (price !== null) {
      hasData = true;
      totalValue += value;
      if (change !== null) totalChange += change * h.shares;
    }

    const changeClass = change === null ? "" : change >= 0 ? "up" : "down";

    tr.innerHTML = `
      <td class="symbol-cell">${h.symbol}</td>
      <td>${h.shares}</td>
      <td>${h.loading ? '<span class="loading-cell">loading&hellip;</span>' : formatMoney(price)}</td>
      <td>${h.loading ? "" : formatMoney(prevClose)}</td>
      <td class="${changeClass}">${h.loading ? "" : change === null ? "—" : `${formatSigned(change)} (${changePct.toFixed(2)}%)`}</td>
      <td>${h.loading ? "" : formatMoney(value)}</td>
      <td><button class="remove-btn" data-symbol="${h.symbol}" title="Remove">&times;</button></td>
    `;
    els.body.appendChild(tr);
  }

  els.totalValue.textContent = formatMoney(hasData ? totalValue : null);
  els.totalChange.textContent = formatMoney(hasData ? totalChange : null);
  els.totalChange.className = "value " + (totalChange >= 0 ? "up" : "down");

  els.body.querySelectorAll(".remove-btn").forEach((btn) => {
    btn.addEventListener("click", () => removeHolding(btn.dataset.symbol));
  });
}

async function refreshAll() {
  if (holdings.length === 0) return;
  clearError();
  holdings.forEach((h) => (h.loading = true));
  render();

  const results = await Promise.allSettled(holdings.map((h) => fetchQuote(h.symbol)));

  let anyFailed = false;
  results.forEach((result, i) => {
    holdings[i].loading = false;
    if (result.status === "fulfilled") {
      holdings[i].quote = result.value;
    } else {
      anyFailed = true;
      holdings[i].quote = holdings[i].quote || null;
      console.error(`Failed to fetch ${holdings[i].symbol}:`, result.reason);
    }
  });

  if (anyFailed) {
    showError(
      "Couldn't fetch one or more quotes. Check the ticker symbols, your network connection, " +
      "or try again — the data provider occasionally rate-limits or blocks requests."
    );
  }

  saveHoldings();
  render();
  els.lastUpdated.textContent = new Date().toLocaleTimeString();
}

function addHolding(symbol, shares) {
  symbol = symbol.trim().toUpperCase();
  if (!symbol || !(shares > 0)) return;

  const existing = holdings.find((h) => h.symbol === symbol);
  if (existing) {
    existing.shares = shares;
  } else {
    holdings.push({ symbol, shares, quote: null, loading: false });
  }
  saveHoldings();
  render();
  refreshAll();
}

function removeHolding(symbol) {
  holdings = holdings.filter((h) => h.symbol !== symbol);
  saveHoldings();
  render();
}

function setAutoRefresh(enabled) {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
  if (enabled) {
    autoRefreshTimer = setInterval(refreshAll, 60_000);
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  addHolding(els.symbolInput.value, Number(els.sharesInput.value));
  els.symbolInput.value = "";
  els.sharesInput.value = "1";
  els.symbolInput.focus();
});

els.refreshBtn.addEventListener("click", refreshAll);
els.autoRefreshToggle.addEventListener("change", (e) => setAutoRefresh(e.target.checked));

render();
if (holdings.length > 0) refreshAll();
