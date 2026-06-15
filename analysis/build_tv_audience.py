#!/usr/bin/env python3
"""Build a per-match / per-tournament / per-country TV+streaming audience proxy
for the four completed World Cups (2010, 2014, 2018, 2022) from free, published
sources. Every figure carries a source_url. NO fabricated numbers.

Output:
  data/matches/tv_audience.parquet
  data/matches/tv_audience.csv

Schema:
  tournament : int  (2010/2014/2018/2022)
  scope      : str  global | country | match
  match      : str  "Home v Away" if a specific match, else ""
  home, away : str  teams (match scope; for country/global left "")
  country    : str  territory the figure applies to ("" or "GLOBAL" for global)
  metric     : str  reach | avg_audience | peak_audience
  value      : float audience count, in PERSONS
  unit       : str  "persons"
  note       : str  methodology / qualifier
  source_url : str
"""
import pandas as pd

M = 1_000_000.0
B = 1_000_000_000.0

# Source URL shorthands
S = {
    "fifa2022_5b": "https://inside.fifa.com/news/one-month-on-5-billion-engaged-with-the-fifa-world-cup-qatar-2022-tm",
    "fifa2022_records": "https://inside.fifa.com/organisation/news/reports-detail-record-global-audience-figures-and-positive-sustainability-outcomes-fifa-world-cup-qatar",
    "sportcal2022": "https://www.sportcal.com/media/fifa-world-cup-engages-5-billion-final-reaches-1-5bn/",
    "fifa2018_release": "https://inside.fifa.com/tournaments/mens/worldcup/2018russia/media-releases/more-than-half-the-world-watched-record-breaking-2018-world-cup",
    "dailysabah2018": "https://www.dailysabah.com/football/2018/12/21/record-35-billion-audience-watched-2018-world-cup-fifa",
    "malaymail2018": "https://www.malaymail.com/news/sports/2018/12/21/world-cup-final-drew-global-audience-of-1.12-billion/1705290",
    "espn2014": "https://www.espn.com/soccer/story/_/id/37447282/fifa-reports-101-billion-viewers-2014-world-cup-final",
    "sportbusiness2014": "https://media.sportbusiness.com/news/fifa-reveals-viewing-figures-for-2014-world-cup/",
    "espn2010_billion": "https://www.espn.com/sports/soccer/news/_/id/6758280/least-1-billion-saw-part-2010-world-cup-final",
    "nielsen2010_final": "https://www.nielsen.com/insights/2010/2010-world-cup-final-becomes-most-watched-soccer-game-in-u-s-tv-history/",
    "nielsen2010_us": "https://www.nielsen.com/insights/2010/usa-ratings-up-big-in-2010-world-cup/",
    # USA
    "awful_usa_eng": "https://awfulannouncing.com/soccer/us-england-world-cup-match-averages-19-977-million-viewers-across-fox-telemundo-peacock.html",
    "smw_usa_final22": "https://www.sportsmediawatch.com/2022/12/world-cup-final-ratings-argentina-france-fox-telemundo-viewership/",
    "variety2014_final": "https://variety.com/2014/tv/ratings/world-cup-final-nets-26-5-million-viewers-in-the-u-s-1201262095/",
    "cnn2014_usa_por": "https://money.cnn.com/2014/06/23/media/world-cup-match-ratings/index.html",
    "smw2018_final": "https://www.sportsmediawatch.com/2018/07/world-cup-ratings-fox-telemundo-final/",
    "espn2022_final_us": "https://www.espn.com/soccer/story/_/id/37634970/world-cup-final-watched-more-25-million-viewers-united-states",
    # UK
    "bbc2018_eng_cro": "https://www.bbc.com/news/entertainment-arts-44804428",
    "campaign2018": "https://www.campaignlive.co.uk/article/itv-claims-highest-ever-football-audience-243m-watch-england-vs-croatia/1487605",
    "bbc2022_eng_out": "https://www.bbc.com/news/entertainment-arts-63933748",
    "bbc2022_final": "https://www.bbc.com/sport/football/64026863",
    # France
    "variety2018_fra": "https://variety.com/2018/tv/news/world-cup-france-record-ratings-1202873843/",
    "deadline2018_fra_bel": "https://deadline.com/2018/07/world-cup-france-v-belgium-ratings-tf1-record-1202424490/",
    "deadline2022_fra_mar": "https://deadline.com/2022/12/world-cup-ratings-france-morocco-tf1-record-1235199951/",
    # Germany
    "thr2014_ger_bra": "https://www.hollywoodreporter.com/tv/tv-news/world-cup-german-ratings-record-717374/",
    "guardianwc_final2014": "https://worldcuptheguide.wordpress.com/2014/07/14/world-cup-final-sets-tv-viewing-records/",
    "sportspro2022_ger_jpn": "https://www.sportspromedia.com/news/qatar-2022-germany-japan-viewership-ard-audience/",
    # Spain
    "thr2010_spain": "https://www.hollywoodreporter.com/business/business-news/world-cup-gives-telecinco-audience-24891/",
    # Brazil / per-country tournament reach 2022
    "worldsoccershop": "https://www.worldsoccershop.com/guide/how-many-people-watch-the-world-cup-viewership",
    # Japan
    "allfootball2022": "https://m.allfootballapp.com/news/All/FIFA-World-Cup-Qatar-2022-delivering-record-breaking-TV-audience-numbers/2974049",
    "dailystar2022_jpn": "https://www.thedailystar.net/sports/sports-special/fifa-world-cup-2022/news/germany-japan-big-draw-viewers-japan-less-so-germany-3178301",
    # in-numbers
    "broadbandtv2018_final": "https://www.broadbandtvnews.com/2018/07/16/world-cup-final-attracted-163m-viewers-in-20-territories/",
}

rows = []
def add(tournament, scope, metric, value, country="", match="", home="", away="", note="", src=""):
    rows.append(dict(tournament=tournament, scope=scope, match=match, home=home, away=away,
                     country=country, metric=metric, value=float(value), unit="persons",
                     note=note, source_url=S.get(src, src)))

# ============================ GLOBAL / TOURNAMENT-LEVEL ============================
# 2010
add(2010, "global", "reach", 3.2*B, country="GLOBAL",
    note="In-home, >=1 min live coverage during tournament (FIFA/KantarSport)", src="espn2010_billion")
add(2010, "global", "avg_audience", 188.4*M, country="GLOBAL",
    note="Average official rating per match across 64 matches (in-home)", src="espn2010_billion")
# 2014
add(2014, "global", "reach", 3.2*B, country="GLOBAL",
    note="In-home, >=1 min during tournament (FIFA/Kantar Media)", src="sportbusiness2014")
add(2014, "global", "avg_audience", 186.7*M, country="GLOBAL",
    note="Average in-home audience per live match; 57 of 64 matches topped 100M", src="sportbusiness2014")
# 2018
add(2018, "global", "reach", 3.572*B, country="GLOBAL",
    note="Combined (in-home 3.262B + 309.7M out-of-home/digital), >=1 min (FIFA/PMSE)", src="fifa2018_release")
# 2022
add(2022, "global", "reach", 5.0*B, country="GLOBAL",
    note="~5 billion engaged across all platforms/devices (FIFA one-month-on)", src="fifa2022_5b")
add(2022, "global", "avg_audience", 175.0*M, country="GLOBAL",
    note="Average global live audience per match (FIFA)", src="sportcal2022")

# ============================ FINALS (global avg + reach) ============================
# 2010 Final: Spain 1-0 Netherlands
add(2010, "match", "reach", 909.6*M, match="Netherlands v Spain", home="Netherlands", away="Spain",
    country="GLOBAL", note="In-home, >=1 min (final). Total ~1B+ incl. out-of-home", src="espn2010_billion")
add(2010, "match", "avg_audience", 530.9*M, match="Netherlands v Spain", home="Netherlands", away="Spain",
    country="GLOBAL", note="Average in-home global audience (final)", src="espn2010_billion")
# 2014 Final: Germany 1-0 Argentina
add(2014, "match", "reach", 1.013*B, match="Germany v Argentina", home="Germany", away="Argentina",
    country="GLOBAL", note="In+out-of-home, >=1 min (final, most-watched match)", src="espn2014")
add(2014, "match", "avg_audience", 570.1*M, match="Germany v Argentina", home="Germany", away="Argentina",
    country="GLOBAL", note="Average in-home global audience (final)", src="espn2014")
# 2018 Final: France 4-2 Croatia
add(2018, "match", "reach", 1.12*B, match="France v Croatia", home="France", away="Croatia",
    country="GLOBAL", note="Combined live audience, >=1 min (final, most-watched match)", src="malaymail2018")
add(2018, "match", "avg_audience", 517.0*M, match="France v Croatia", home="France", away="Croatia",
    country="GLOBAL", note="Average live worldwide audience (final)", src="malaymail2018")
# 2022 Final: Argentina 3-3 (pens) France
add(2022, "match", "reach", 1.42*B, match="Argentina v France", home="Argentina", away="France",
    country="GLOBAL", note="Combined live, >=1 min (final, most-watched final ever)", src="sportcal2022")
add(2022, "match", "avg_audience", 571.0*M, match="Argentina v France", home="Argentina", away="France",
    country="GLOBAL", note="Average live global audience (final)", src="worldsoccershop")

# ============================ OTHER MARQUEE MATCHES (global avg in-home) ============================
# 2014 Brazil 1-7 Germany semi-final
add(2014, "match", "avg_audience", 390.2*M, match="Brazil v Germany", home="Brazil", away="Germany",
    country="GLOBAL", note="In-home average global audience (semi-final)", src="sportbusiness2014")

# ============================ PER-COUNTRY: USA -> US markets ============================
# 2010
add(2010, "match", "avg_audience", 24.3*M, match="Netherlands v Spain", home="Netherlands", away="Spain",
    country="USA", note="ABC+Univision US audience, final (most-watched US soccer game at the time)", src="nielsen2010_final")
add(2010, "match", "avg_audience", 17.1*M, match="England v USA", home="England", away="USA",
    country="USA", note="ABC 13.0M + Univision 4.1M; most-watched opening-round WC broadcast (US)", src="nielsen2010_us")
add(2010, "match", "avg_audience", 14.863*M, match="USA v Ghana", home="USA", away="Ghana",
    country="USA", note="US round-of-16 USA-Ghana audience (Nielsen)", src="nielsen2010_us")
# 2014
add(2014, "match", "avg_audience", 26.5*M, match="Germany v Argentina", home="Germany", away="Argentina",
    country="USA", note="ABC 17.3M + Univision 9.2M; US record for a soccer game at the time (final)", src="variety2014_final")
add(2014, "match", "avg_audience", 24.7*M, match="USA v Portugal", home="USA", away="Portugal",
    country="USA", note="ESPN 18.2M + Univision; US record WC group-stage telecast", src="cnn2014_usa_por")
# 2018 (USA did not qualify)
add(2018, "match", "avg_audience", 17.8*M, match="France v Croatia", home="France", away="Croatia",
    country="USA", note="Fox + Telemundo US audience (final), USMNT absent", src="smw2018_final")
# 2022
add(2022, "match", "avg_audience", 25.78*M, match="Argentina v France", home="Argentina", away="France",
    country="USA", note="Fox+Telemundo+Peacock US audience (final); most-watched men's WC final in US history", src="espn2022_final_us")
add(2022, "match", "avg_audience", 19.977*M, match="England v USA", home="England", away="USA",
    country="USA", note="Fox+Telemundo+Peacock US audience; Fox 15.49M an English-lang US men's soccer record", src="awful_usa_eng")

# ============================ PER-COUNTRY: UK -> GBP markets (England matches) ============================
# 2018
add(2018, "match", "peak_audience", 26.5*M, match="Croatia v England", home="Croatia", away="England",
    country="UK", note="ITV peak (England semi-final loss to Croatia); avg 24.3M", src="bbc2018_eng_cro")
add(2018, "match", "avg_audience", 24.3*M, match="Croatia v England", home="Croatia", away="England",
    country="UK", note="ITV match average; highest-ever single-channel UK football audience", src="campaign2018")
# 2022
add(2022, "match", "peak_audience", 19.4*M, match="England v France", home="England", away="France",
    country="UK", note="UK peak as England knocked out by France (quarter-final)", src="bbc2022_eng_out")
add(2022, "match", "peak_audience", 14.9*M, match="Argentina v France", home="Argentina", away="France",
    country="UK", note="BBC One peak (final)", src="bbc2022_final")

# ============================ PER-COUNTRY: France -> EUR markets ============================
# 2018
add(2018, "match", "avg_audience", 19.3*M, match="France v Croatia", home="France", away="Croatia",
    country="France", note="TF1 average (final); peak 22.3M, 82% share, all-time French record", src="variety2018_fra")
add(2018, "match", "avg_audience", 19.1*M, match="France v Belgium", home="France", away="Belgium",
    country="France", note="TF1 (semi-final); record for TF1 at the time", src="deadline2018_fra_bel")
# 2022
add(2022, "match", "avg_audience", 24.0*M, match="Argentina v France", home="Argentina", away="France",
    country="France", note="French audience for final (~24M, FIFA/press)", src="worldsoccershop")
add(2022, "match", "avg_audience", 20.69*M, match="France v Morocco", home="France", away="Morocco",
    country="France", note="TF1 (semi-final); biggest TF1 audience since 2016", src="deadline2022_fra_mar")

# ============================ PER-COUNTRY: Germany -> EUR markets ============================
# 2014
add(2014, "match", "avg_audience", 34.65*M, match="Germany v Argentina", home="Germany", away="Argentina",
    country="Germany", note="ARD; all-time German TV audience record (final)", src="thr2014_ger_bra")
add(2014, "match", "avg_audience", 32.57*M, match="Brazil v Germany", home="Brazil", away="Germany",
    country="Germany", note="ZDF avg ~32.6M (semi-final), prior German record", src="thr2014_ger_bra")
# 2022
add(2022, "match", "avg_audience", 9.2*M, match="Germany v Japan", home="Germany", away="Japan",
    country="Germany", note="ARD; down ~64% on 2018 opener (Germany shock loss)", src="sportspro2022_ger_jpn")

# ============================ PER-COUNTRY: Spain -> EUR markets ============================
# 2010
add(2010, "match", "avg_audience", 15.6*M, match="Netherlands v Spain", home="Netherlands", away="Spain",
    country="Spain", note="Telecinco; Spain's highest-ever TV audience, 85.9% share (final)", src="thr2010_spain")

# ============================ PER-COUNTRY: Japan -> JPY markets ============================
# 2022
add(2022, "match", "avg_audience", 36.37*M, match="Japan v Costa Rica", home="Japan", away="Costa Rica",
    country="Japan", note="TV Asahi; 66.5% share, a 2022 record-high single-broadcast audience in Japan", src="allfootball2022")
add(2022, "match", "avg_audience", 25.92*M, match="Germany v Japan", home="Germany", away="Japan",
    country="Japan", note="Japan audience for opening comeback win (~10M below Costa Rica game)", src="dailystar2022_jpn")

# ============================ PER-COUNTRY: Brazil -> Brazil market (EWZ) ============================
# 2022 tournament reach in Brazil
add(2022, "global", "reach", 173.0*M, country="Brazil",
    note="~81% of Brazil watched the tournament (FIFA)", src="worldsoccershop")

df = pd.DataFrame(rows, columns=["tournament","scope","match","home","away","country",
                                 "metric","value","unit","note","source_url"])
# de-dup any accidental exact repeats
df = df.drop_duplicates().reset_index(drop=True)

out_pq = "data/matches/tv_audience.parquet"
out_csv = "data/matches/tv_audience.csv"
df.to_parquet(out_pq, index=False)
df.to_csv(out_csv, index=False)

print(f"rows: {len(df)}")
print(df.groupby(["scope","metric"]).size())
print("\nby tournament x country (counts):")
print(df.groupby(["tournament","country"]).size())
print(f"\nwrote {out_pq} and {out_csv}")
