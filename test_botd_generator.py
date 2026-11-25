import asyncio
from owlsinsight_service import owlsinsight_service

def convert_american(price: float) -> float:
    if price is None:
        return 1.30
    if price > 0:
        return round(1.0 + (price / 100.0), 2)
    elif price < 0:
        return round(1.0 + (100.0 / abs(price)), 2)
    return 1.30

async def main():
    dt = '2026-09-17'
    c = owlsinsight_service._get_client()
    odds_resp = c.get_odds(sport='soccer')
    data = odds_resp.data if hasattr(odds_resp, 'data') else {}

    print(f"Books in get_odds: {list(data.keys())}")
    all_odds_events = []
    for book_name, events in data.items():
        for ev in events:
            all_odds_events.append((book_name, ev))

    print(f"Total odds events collected across books: {len(all_odds_events)}")

    # Test matching with scheduled games
    res = await owlsinsight_service.buscar_partidas_futebol(dt, force_refresh=False)
    jogos = res.get('jogos', [])

    for j in jogos:
        m = j.get('mandante', {}).get('nome', '')
        v = j.get('visitante', {}).get('nome', '')
        # search in all_odds_events
        matched = []
        for book_name, ev in all_odds_events:
            h = getattr(ev, 'home_team', '')
            a = getattr(ev, 'away_team', '')
            if (m.split()[0].lower() in h.lower() or m.split()[0].lower() in a.lower()) and \
               (v.split()[0].lower() in h.lower() or v.split()[0].lower() in a.lower()):
                matched.append((book_name, ev))
        print(f"Jogo: {m} vs {v} -> Matched odds: {len(matched)}")
        if matched:
            bname, oev = matched[0]
            print(f"   Match: {oev.home_team} vs {oev.away_team} ({bname})")
            for bm in getattr(oev, 'bookmakers', []):
                for mk in getattr(bm, 'markets', []):
                    outcomes = [(o.name, o.price, convert_american(o.price)) for o in getattr(mk, 'outcomes', [])]
                    print(f"      {mk.key}: {outcomes[:4]}")

if __name__ == '__main__':
    asyncio.run(main())
