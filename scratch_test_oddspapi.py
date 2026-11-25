import httpx
import json
import time
import datetime

key = 'ae96bff3-2736-4dc4-9606-c02cb3819bfc'
base = 'https://api.oddspapi.io'

def test_diag():
    with httpx.Client(timeout=15) as client:
        # 1. Sports
        r_sports = client.get(f"{base}/v4/sports", params={"apiKey": key})
        print(f"[1] /v4/sports: HTTP {r_sports.status_code}")
        sports = r_sports.json() if r_sports.status_code == 200 else []
        print(f"    Available sports: {len(sports)} ({[s['slug'] for s in sports[:5]]})")

        time.sleep(2)
        # 2. Upcoming fixtures with from & to
        now = datetime.datetime.now(datetime.timezone.utc)
        now_str = now.strftime("%Y-%m-%d")
        to_str = (now + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        r_fix = client.get(f"{base}/v4/fixtures", params={
            "apiKey": key,
            "sportId": 10,
            "from": now_str,
            "to": to_str
        })
        print(f"\n[2] /v4/fixtures ({now_str} to {to_str}): HTTP {r_fix.status_code}")
        fixtures = r_fix.json() if r_fix.status_code == 200 else []
        print(f"    Total fixtures: {len(fixtures)}")
        with_odds = [f for f in fixtures if f.get("hasOdds")]
        print(f"    Fixtures with hasOdds=True: {len(with_odds)}")

        time.sleep(2)
        # 3. Check participants
        r_part = client.get(f"{base}/v4/participants", params={"apiKey": key, "sportId": 10})
        print(f"\n[3] /v4/participants: HTTP {r_part.status_code}")
        participants = r_part.json() if r_part.status_code == 200 else {}
        print(f"    Total participants loaded: {len(participants)}")

        time.sleep(2)
        # 4. Check odds for an upcoming fixture with odds
        future_odds = [f for f in with_odds if f.get("startTime", "") > now.strftime("%Y-%m-%dT%H:%M:%SZ")]
        print(f"    Future fixtures with hasOdds=True: {len(future_odds)}")
        if future_odds:
            sample_fix = future_odds[0]
            fid = sample_fix["fixtureId"]
            p1_id = str(sample_fix.get("participant1Id"))
            p2_id = str(sample_fix.get("participant2Id"))
            p1_name = participants.get(p1_id, f"ID {p1_id}")
            p2_name = participants.get(p2_id, f"ID {p2_id}")
            start_time = sample_fix.get("startTime")
            print(f"\n[4] /v4/odds for future fixture {fid} ({p1_name} vs {p2_name}) at {start_time}:")
            time.sleep(2)
            r_odds = client.get(f"{base}/v4/odds", params={"apiKey": key, "fixtureId": fid})
            print(f"    HTTP Status: {r_odds.status_code}")
            if r_odds.status_code == 200:
                odds_data = r_odds.json()
                bks = odds_data.get("bookmakerOdds", {})
                print(f"    Bookmakers available ({len(bks)}): {list(bks.keys())[:10]}")
                for bname in list(bks.keys())[:3]:
                    mkts = bks[bname].get("markets", {})
                    print(f"    Bookmaker '{bname}' markets: {list(mkts.keys())}")
                    if "101" in mkts:
                        m101 = mkts["101"]
                        outcomes = m101.get("outcomes", {})
                        odd_1 = outcomes.get("101", {}).get("players", {}).get("0", {}).get("odds")
                        odd_x = outcomes.get("102", {}).get("players", {}).get("0", {}).get("odds")
                        odd_2 = outcomes.get("103", {}).get("players", {}).get("0", {}).get("odds")
                        print(f"      [1X2 Full Time] Casa (1): {odd_1} | Empate (X): {odd_x} | Fora (2): {odd_2}")

if __name__ == "__main__":
    test_diag()
