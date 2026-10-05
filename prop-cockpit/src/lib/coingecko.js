// CoinGecko market-cap source. Bybit's API has no market-cap field, so we use
// CoinGecko purely to RANK and legitimacy-filter the Bybit pairs: only coins
// CoinGecko tracks in the top tiers by market cap are shown, which excludes
// obscure / untracked micro-caps.
//
// Free public API, no key. Browser CORS is permitted.

import { load, save } from './storage.js'

const BASE = 'https://api.coingecko.com/api/v3'
const CACHE_KEY = 'capsCache'
const TTL_MS = 60 * 60 * 1000 // market caps barely move minute-to-minute; 1h is plenty

// Cached accessor. Returns a fresh cached Map if we have one under the TTL,
// otherwise fetches from the network and caches it. If the network fails but
// we have *any* cached copy (even stale), we return that rather than breaking
// the scanner — CoinGecko's free tier rate-limits, so this matters.
export async function getMarketCaps({ pages = 2 } = {}) {
  const cached = load(CACHE_KEY, null)
  if (cached && Date.now() - cached.at < TTL_MS) {
    return new Map(cached.entries)
  }
  try {
    const map = await fetchMarketCaps({ pages })
    save(CACHE_KEY, { at: Date.now(), entries: [...map] })
    return map
  } catch (e) {
    if (cached) return new Map(cached.entries) // stale, but usable
    throw e
  }
}

// Returns a Map: uppercase base symbol -> { marketCap, rank, image, name }.
// Covers the top `pages`×250 coins by market cap (default 500). If a symbol
// appears twice (ticker collision), the higher-cap / more-famous coin wins
// because we iterate in descending market-cap order and keep the first.
export async function fetchMarketCaps({ pages = 2 } = {}) {
  const reqs = []
  for (let page = 1; page <= pages; page++) {
    const url =
      `${BASE}/coins/markets?vs_currency=usd&order=market_cap_desc` +
      `&per_page=250&page=${page}&sparkline=false`
    reqs.push(
      fetch(url, { headers: { accept: 'application/json' } }).then((res) => {
        if (!res.ok) {
          if (res.status === 429) {
            throw new Error('CoinGecko rate limit hit — wait a minute and refresh.')
          }
          throw new Error(`CoinGecko error ${res.status}`)
        }
        return res.json()
      }),
    )
  }

  const pagesData = await Promise.all(reqs)
  const map = new Map()
  for (const list of pagesData) {
    for (const c of list) {
      const sym = (c.symbol || '').toUpperCase()
      if (!sym || map.has(sym)) continue // keep first = highest cap for this ticker
      map.set(sym, {
        marketCap: c.market_cap ?? null,
        rank: c.market_cap_rank ?? null,
        image: c.image ?? null,
        name: c.name ?? sym,
      })
    }
  }
  return map
}
