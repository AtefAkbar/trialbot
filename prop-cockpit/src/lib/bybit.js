// Bybit perps client. Uses the public v5 market API (no key required).
// The browser can call this directly — Bybit sends permissive CORS headers on
// public market endpoints.
//
// We list linear USDT *crypto* perpetuals only. Bybit's linear category also
// includes tokenized equities (symbolType "stock", e.g. AAPL/AMZN) and
// commodities (symbolType "commodity") — those are excluded so the scanner
// shows only crypto pairs this account trades.

import { getMarketCaps } from './coingecko.js'

const BASE = 'https://api.bybit.com'

// symbolType values that count as crypto:
//   ''           standard crypto perps
//   'innovation' Bybit Innovation Zone (newer / smaller crypto tokens)
// Excluded: 'stock' (tokenized equities), 'commodity' (tokenized commodities).
const CRYPTO_TYPES = new Set(['', 'innovation'])

async function fetchJson(url) {
  const res = await fetch(url, { headers: { accept: 'application/json' } })
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error('Bybit rate limit hit — wait a moment and refresh.')
    }
    throw new Error(`Bybit error ${res.status}`)
  }
  const json = await res.json()
  if (json.retCode !== 0) {
    throw new Error(json.retMsg || 'Bybit API error')
  }
  return json
}

// Set of tradeable USDT crypto perp symbols, from instruments-info (the only
// endpoint that carries symbolType).
async function fetchCryptoSymbols() {
  const json = await fetchJson(
    `${BASE}/v5/market/instruments-info?category=linear&limit=1000`,
  )
  const list = json.result?.list || []
  const allowed = new Set()
  for (const i of list) {
    if (
      i.quoteCoin === 'USDT' &&
      i.status === 'Trading' &&
      CRYPTO_TYPES.has(i.symbolType ?? '')
    ) {
      allowed.add(i.symbol)
    }
  }
  return allowed
}

// Returns the top `limit` Bybit crypto perps by market cap, plus a `degraded`
// flag. Market cap comes from CoinGecko (Bybit has no such field); a pair is
// only shown if CoinGecko tracks its coin in the top tiers — this drops obscure
// micro-caps and untracked tokens, leaving famous, liquid names.
//
// If CoinGecko is unavailable (rate-limited, offline) and we have no cache, the
// scanner degrades to Bybit-only, ranked by 24h turnover, with degraded=true so
// the UI can flag that the market-cap filter isn't applied.
export async function fetchMarkets({ limit = 300 } = {}) {
  const [crypto, tickers, caps] = await Promise.all([
    fetchCryptoSymbols(),
    fetchJson(`${BASE}/v5/market/tickers?category=linear`),
    getMarketCaps({ pages: 2 }).catch(() => null),
  ])

  const list = tickers.result?.list || []
  const mapped = list
    // Keep only tradeable USDT crypto perps (the allowed set already enforces
    // quoteCoin/status/symbolType).
    .filter((t) => crypto.has(t.symbol))
    .map((t) => {
      const base = t.symbol.replace(/USDT$/, '')
      const cap = caps?.get(base) // undefined if CoinGecko doesn't rank it
      const price = parseFloat(t.lastPrice)
      const high = parseFloat(t.highPrice24h)
      const low = parseFloat(t.lowPrice24h)
      // price24hPcnt is a decimal fraction ("-0.05414" = -5.414%).
      const change = parseFloat(t.price24hPcnt) * 100
      const rangePct = price ? ((high - low) / price) * 100 : 0
      return {
        id: t.symbol,
        symbol: base,
        name: cap?.name || t.symbol,
        image: cap?.image || null,
        price,
        high24h: high,
        low24h: low,
        change24hPct: change,
        rangePct,
        volume: parseFloat(t.turnover24h), // 24h quote turnover, USDT
        marketCap: cap?.marketCap ?? null,
        mcapRank: cap?.rank ?? null,
      }
    })
    .filter((r) => r.price > 0 && Number.isFinite(r.rangePct))

  if (caps) {
    // Legitimacy filter: only coins whose GLOBAL market-cap rank is within the
    // top `limit`. This literally enforces "top 300 by market cap" and drops
    // lower-cap / untracked coins — the ones most prone to manipulation.
    const rows = mapped
      .filter((r) => r.mcapRank != null && r.mcapRank <= limit)
      .sort((a, b) => b.marketCap - a.marketCap)
    return { rows, degraded: false }
  }

  // Degraded: no market-cap data — fall back to turnover ranking.
  const rows = mapped.sort((a, b) => b.volume - a.volume).slice(0, limit)
  return { rows, degraded: true }
}
