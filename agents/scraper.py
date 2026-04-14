"""
Regulatory Scraper — FIXED VERSION (March 31 2026)
OCC, NAIC, NYDFS URLs corrected. FinCEN nav-link filter added.
"""
import hashlib, requests
from datetime import date, timedelta
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "ComplianceAI/1.0 (regulatory-monitor)"}

def make_id(title, url):
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def safe_get(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠️  Failed: {url[:70]} → {e}")
        return None

# OCC — FIXED URL
def fetch_occ():
    results = []
    year = date.today().year
    for url in [
        f"https://www.occ.gov/news-events/newsroom/news-issuances-by-year/news-releases/{year}-news-releases.html",
        "https://www.occ.gov/news-events/newsroom/index-newsroom.html",
    ]:
        r = safe_get(url)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.select("td a, li a, h3 a, h2 a")[:15]:
            href = link.get("href",""); title = link.get_text(strip=True)
            if not title or len(title) < 15: continue
            if any(s in title.lower() for s in ["subscribe","rss","sitemap","home","about"]): continue
            full_url = f"https://www.occ.gov{href}" if href.startswith("/") else href
            results.append({"source":"OCC","title":title,"url":full_url,"type":"Bulletin","id":make_id(title,full_url)})
        if results: break
    print(f"  OCC: {len(results)} items")
    return results

# FinCEN — FIXED: filters nav links
def fetch_fincen():
    results = []
    r = safe_get("https://www.fincen.gov/news/press-releases")
    if not r: return results
    soup = BeautifulSoup(r.text, "html.parser")
    SKIP = ["subscribe","foia","contact","chapter x","manual","related government",
            "law enforcement case","history of","ffiec examination","federal register notices","press contacts"]
    for container in soup.select(".views-row, .news-item, article")[:15]:
        link = container.find("a")
        if not link: continue
        href = link.get("href",""); title = link.get_text(strip=True)
        if not title or len(title) < 20: continue
        if any(s in title.lower() for s in SKIP): continue
        full_url = f"https://www.fincen.gov{href}" if href.startswith("/") else href
        results.append({"source":"FinCEN","title":title,"url":full_url,"type":"Advisory","id":make_id(title,full_url)})
    if not results:
        for link in soup.select("h3 a, h2 a")[:15]:
            href = link.get("href",""); title = link.get_text(strip=True)
            if not title or len(title) < 20: continue
            if any(s in title.lower() for s in SKIP): continue
            full_url = f"https://www.fincen.gov{href}" if href.startswith("/") else href
            results.append({"source":"FinCEN","title":title,"url":full_url,"type":"Advisory","id":make_id(title,full_url)})
    print(f"  FinCEN: {len(results)} items")
    return results

# NAIC — FIXED URLs
def fetch_naic():
    results = []
    seen_urls = set()
    for url, pub_type in [
        ("https://content.naic.org/newsroom",       "Press Release"),
        ("https://content.naic.org/resource-center", "Publication / Model Law"),
    ]:
        r = safe_get(url)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.select("h3 a, h2 a, .views-row a, article a")[:12]:
            href = link.get("href",""); title = link.get_text(strip=True)
            if not title or len(title) < 15: continue
            if any(s in title.lower() for s in ["register","login","subscribe","contact","home"]): continue
            full_url = f"https://content.naic.org{href}" if href.startswith("/") else href
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                results.append({"source":"NAIC","title":title,"url":full_url,"type":pub_type,"id":make_id(title,full_url)})
    print(f"  NAIC: {len(results)} items")
    return results

# Federal Register — unchanged (works fine)
AGENCIES = [
    "federal-reserve-system","comptroller-of-the-currency",
    "federal-deposit-insurance-corporation","consumer-financial-protection-bureau",
    "financial-crimes-enforcement-network","securities-and-exchange-commission",
    "national-credit-union-administration",
]
def fetch_federal_register():
    results = []
    since = (date.today() - timedelta(days=7)).isoformat()
    for agency in AGENCIES:
        api_url = (
            f"https://www.federalregister.gov/api/v1/documents.json"
            f"?conditions[agencies][]={agency}&conditions[publication_date][gte]={since}"
            f"&conditions[type][]=RULE&conditions[type][]=PRORULE"
            f"&fields[]=title&fields[]=html_url&fields[]=abstract&per_page=5&order=newest"
        )
        r = safe_get(api_url)
        if not r: continue
        try:
            for doc in r.json().get("results",[]):
                title = doc.get("title",""); url = doc.get("html_url","")
                if not title: continue
                results.append({"source":"Federal Register","title":title,"url":url,
                                "type":"Proposed / Final Rule","abstract":(doc.get("abstract") or "")[:400],
                                "agency":agency.replace("-"," ").title(),"id":make_id(title,url)})
        except: pass
    print(f"  Federal Register: {len(results)} items")
    return results

# SEC — unchanged (works fine)
def fetch_sec():
    results = []
    seen_titles = set()
    for feed in [
        "https://www.sec.gov/rss/news/pressreleases.rss"
    ]:
        r = safe_get(feed)
        if not r: continue
        soup = BeautifulSoup(r.text, "lxml-xml")
        for item in soup.find_all(["item","entry"])[:8]:
            t = item.find("title"); l = item.find("link") or item.find("id")
            title = t.get_text(strip=True) if t else ""
            url = (l.get("href") or l.get_text(strip=True)) if l else ""
            if title and url and title not in seen_titles:
                seen_titles.add(title)
                results.append({"source":"SEC","title":title,"url":url,"type":"Rule / Press Release","id":make_id(title,url)})
    print(f"  SEC: {len(results)} items")
    return results

# CA DOI — FIXED selectors
def fetch_california_doi():
    results = []
    SKIP = ["home","about","contact","sitemap","search","accessibility","privacy","español","back to"]
    seen_urls = set()
    for url in [
        "https://www.insurance.ca.gov/0400-news/0100-press-releases/",
        "https://www.insurance.ca.gov/0250-insurers/0300-insurers/0200-bulletins/bulletin-notices-commiss-opinion/bulletins.cfm",
    ]:
        r = safe_get(url)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.select("h2 a, h3 a, td a, p a, li a")[:15]:
            href = link.get("href",""); title = link.get_text(strip=True)
            if not title or len(title) < 15: continue
            if any(s in title.lower() for s in SKIP): continue
            full_url = f"https://www.insurance.ca.gov{href}" if href.startswith("/") else href
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                results.append({"source":"CA DOI","title":title,"url":full_url,"type":"Bulletin / Press Release","id":make_id(title,full_url)})
    print(f"  CA DOI: {len(results)} items")
    return results

# NYDFS — FIXED URL
def fetch_nydfs():
    results = []
    SKIP = ["home","about","contact","search","login"]
    seen_urls = set()
    for url in [
        "https://www.dfs.ny.gov/industry_guidance/circular_letters",
        "https://www.dfs.ny.gov/reports_and_publications",
    ]:
        r = safe_get(url)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.select("table a, h3 a, h2 a, .views-row a, li a")[:12]:
            href = link.get("href",""); title = link.get_text(strip=True)
            if not title or len(title) < 10: continue
            if any(s in title.lower() for s in SKIP): continue
            full_url = f"https://www.dfs.ny.gov{href}" if href.startswith("/") else href
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                results.append({"source":"NYDFS","title":title,"url":full_url,"type":"Circular / Guidance","id":make_id(title,full_url)})
        if results: break
    print(f"  NYDFS: {len(results)} items")
    return results

# Run all sources
def fetch_all():
    print("\n📡 Fetching all regulatory sources...")
    all_pubs = []
    all_pubs += fetch_occ()
    all_pubs += fetch_fincen()
    all_pubs += fetch_naic()
    all_pubs += fetch_federal_register()
    all_pubs += fetch_sec()
    all_pubs += fetch_california_doi()
    all_pubs += fetch_nydfs()
    seen, unique = set(), []
    for pub in all_pubs:
        if pub["id"] not in seen and pub.get("title"):
            seen.add(pub["id"]); unique.append(pub)
    print(f"\n📥 Total: {len(unique)} unique publications")
    return unique

if __name__ == "__main__":
    print("Testing all sources...\n")
    for name, fn in [("OCC",fetch_occ),("FinCEN",fetch_fincen),("NAIC",fetch_naic),
                     ("Federal Register",fetch_federal_register),("SEC",fetch_sec),
                     ("CA DOI",fetch_california_doi),("NYDFS",fetch_nydfs)]:
        items = fn()
        print(f"{'✅' if items else '⚠️ '} {name}: {len(items)} items")
        if items: print(f"   Sample: {items[0]['title'][:65]}")
        print()
