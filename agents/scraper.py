"""
Regulatory Scraper — v2 FIXED
Uses RSS feeds where possible, strict date filtering,
aggressive navigation filtering
"""
import re
import hashlib, requests, feedparser
from datetime import date, datetime, timedelta
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

HEADERS = {"User-Agent": "ComplianceAI/2.0 (regulatory-monitor)"}
CUTOFF_DAYS = 7  # Only items from last 7 days

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

def is_recent(date_str, days=CUTOFF_DAYS):
    """Check if a date string is within the last N days."""
    if not date_str:
        return False
    cutoff = datetime.now() - timedelta(days=days)
    # Try common date formats
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
                "%m-%d-%Y", "%Y-%m-%dT%H:%M:%S"]:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            return parsed >= cutoff
        except ValueError:
            continue
    return False

# ── GLOBAL SKIP LIST ──────────────────────────────
NAV_SKIP = [
    # Generic website navigation
    "home", "about", "about us", "contact", "contact us", "search",
    "login", "log in", "sign in", "subscribe", "register", "sitemap",
    "rss", "privacy", "privacy policy", "accessibility", "español",
    "back to", "foia", "careers", "menu", "skip to main", "toggle menu",
    "share this", "print this", "email this page",
    
    # OCC navigation
    "banknet.gov", "helpwithmybank", "find resources for bankers",
    "join one of the best", "get answers to banking",
    "comptroller's handbook", "bank secrecy act (bsa)",
    "community reinvestment act (cra)", "corporate applications search",
    "financial institution lists", "enforcement action search",
    
    # CA DOI navigation  
    "file a complaint", "check license status", "types of insurance",
    "health insurance information", "company and agent",
    "laws & regulations", "virtual viewing room",
    "dealing with catastrophes", "administrative hearings",
    "cannabis and insurance", "rate filing systems",
    "low cost auto insurance", "earthquake insurance",
    
    # NYDFS navigation
    "consumer information", "auto insurance", "banking and sending",
    "credit and debt", "disaster and flood", "drug prices and pbms",
    "fraud and cyber", "small business resources", "student loan",
    "how to file a complaint", "regulated industries",
    
    # NAIC navigation
    "resource center", "about the naic", "state map",
    "government affairs", "capital markets", "cipr topics",
    
    # Generic regulatory site patterns
    "press contacts", "media inquiries", "follow us", "connect with us",
    "social media", "newsroom", "news room", "all press releases",
    "view all", "see all", "read more", "learn more", "click here",
    "download", "subscribe to updates", "email alerts",
]

def is_nav_link(title):
    """Return True if this looks like a navigation link, not real content."""
    if not title:
        return True
    t = title.lower().strip()
    if len(t) < 15:
        return True
    if any(skip in t for skip in NAV_SKIP):
        return True
    # Likely a nav link if it has no verbs/substance
    nav_patterns = [
        t.startswith("http"),
        t.count(" ") < 2 and len(t) < 30,  # "Auto Insurance" = 2 words
    ]
    return any(nav_patterns)

 # Add this at the TOP of scraper.py with other imports

def clean_title(raw_title):
    """
    Cleans scraped titles that have jammed-together text,
    weird whitespace, dates stuck to words, etc.
    
    BEFORE: "News Release209 Foreign Regulators to Participate in 2026 NAIC Spring"
    AFTER:  "209 Foreign Regulators to Participate in 2026 NAIC Spring"
    
    BEFORE: "Money Market Fund ListMoney Market Fund ListApr. 30, 2026"
    AFTER:  "Money Market Fund List"
    
    BEFORE: "National Meeting NewsState Insurance Regulators Look to the Future"
    AFTER:  "State Insurance Regulators Look to the Future"
    """
    if not raw_title:
        return ""
    
    t = raw_title.strip()
    
    # Fix non-breaking spaces and weird whitespace
    t = t.replace("\xa0", " ").replace("\u200b", "").replace("&nbsp;", " ")
    
    # Remove common NAIC prefixes that get jammed together
    prefixes_to_strip = [
        "News Release",
        "National Meeting News", 
        "Consumer Insight",
        "CIPR Newsletter",
        "NAIC News",
        "Press Release",
    ]
    for prefix in prefixes_to_strip:
        if t.startswith(prefix) and len(t) > len(prefix) + 5:
            t = t[len(prefix):]
            break
    
    # Remove duplicate title patterns: "Money Market Fund ListMoney Market Fund List..."
    # If the first half equals the second half, keep only one
    half = len(t) // 2
    if half > 10 and t[:half].strip() == t[half:half*2].strip():
        t = t[:half].strip()
    
    # Remove trailing dates stuck to text: "...RegulationMar. 25, 2026"
    t = re.sub(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\.]?\s*\d{1,2},?\s*\d{4}\s*$',
        '', t
    ).strip()
    
    # Insert space between lowercase→uppercase joins: "ActProposed" → "Act Proposed"
    t = re.sub(r'([a-z])([A-Z])', r'\1 \2', t)
    
    # Collapse multiple spaces
    t = re.sub(r'\s+', ' ', t).strip()
    
    # Remove leading/trailing punctuation junk
    t = t.strip('.,;:- ')
    
    return t

# ── SEC via RSS (BEST SOURCE — already working) ──
def fetch_sec():
    results = []
    seen_titles = set()
    feed = feedparser.parse("https://www.sec.gov/news/pressreleases.rss")
    
    cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
    
    for entry in feed.entries[:15]:
        title = clean_title(entry.get("title", "").strip())
        link = entry.get("link", "")
        
        # Date filter
        published = entry.get("published", "")
        try:
            pub_date = parsedate_to_datetime(published)
            if pub_date.replace(tzinfo=None) < cutoff:
                continue
        except:
            pass  # If can't parse date, include it (conservative)
        
        if title and link and title not in seen_titles:
            if is_nav_link(title):
                continue
            seen_titles.add(title)
            results.append({
                "source": "SEC",
                "title": title,
                "url": link,
                "type": "Press Release / Rule",
                "id": make_id(title, link),
                "date": published,
            })
    
    print(f"  SEC: {len(results)} items")
    return results


# ── Federal Register via API (BEST SOURCE — already working) ──
AGENCIES = [
    "comptroller-of-the-currency",
    "federal-reserve-system",
    "federal-deposit-insurance-corporation",
    "consumer-financial-protection-bureau",
    "financial-crimes-enforcement-network",
    "securities-and-exchange-commission",
    "national-credit-union-administration",
]

def fetch_federal_register():
    results = []
    since = (date.today() - timedelta(days=CUTOFF_DAYS)).isoformat()
    
    for agency in AGENCIES:
        api_url = (
            f"https://www.federalregister.gov/api/v1/documents.json"
            f"?conditions[agencies][]={agency}"
            f"&conditions[publication_date][gte]={since}"
            f"&conditions[type][]=RULE&conditions[type][]=PRORULE"
            f"&fields[]=title&fields[]=html_url&fields[]=abstract"
            f"&fields[]=publication_date"
            f"&per_page=5&order=newest"
        )
        r = safe_get(api_url)
        if not r:
            continue
        try:
            for doc in r.json().get("results", []):
                title = clean_title(doc.get("title", ""))
                url = doc.get("html_url", "")
                if not title:
                    continue
                results.append({
                    "source": "Federal Register",
                    "title": title,
                    "url": url,
                    "type": "Proposed / Final Rule",
                    "abstract": (doc.get("abstract") or "")[:500],
                    "agency": agency.replace("-", " ").title(),
                    "date": doc.get("publication_date", ""),
                    "id": make_id(title, url),
                })
        except:
            pass
    
    print(f"  Federal Register: {len(results)} items")
    return results


# ── OCC via RSS (FIXED — use their actual RSS feed) ──
def fetch_occ():
    results = []
    year = date.today().year
    
    # Try RSS first
    feed_urls = [
        "https://www.occ.gov/static/news-issuances/ots/feed.xml",
        "https://www.occ.gov/rss/occ-news.xml",
    ]
    
    for feed_url in feed_urls:
        feed = feedparser.parse(feed_url)
        if feed.entries:
            cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
            for entry in feed.entries[:10]:
                title = clean_title(entry.get("title", ""))
                link = entry.get("link", "")
                if not title or is_nav_link(title):
                    continue
                published = entry.get("published", "")
                try:
                    pub_date = parsedate_to_datetime(published)
                    if pub_date.replace(tzinfo=None) < cutoff:
                        continue
                except:
                    pass
                results.append({
                    "source": "OCC", "title": title, "url": link,
                    "type": "Bulletin / News Release", "date": published,
                    "id": make_id(title, link),
                })
            if results:
                print(f"  OCC: {len(results)} items (via RSS)")
                return results
    
    # Fallback: scrape with DATE FILTERING
    for url in [
        f"https://www.occ.gov/news-events/newsroom/news-issuances-by-year/news-releases/{year}-news-releases.html",
        "https://www.occ.gov/news-events/newsroom/index.html",
    ]:
        r = safe_get(url)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        
        main_content = soup.find("div", {"id": "content"}) or \
                       soup.find("main") or soup
        
        # Look for table rows or list items that contain BOTH a date and a link
        for row in main_content.select("tr, li, .views-row, article")[:30]:
            link = row.find("a")
            if not link:
                continue
            
            href = link.get("href", "")
            title = clean_title(link.get_text(strip=True))
            
            if is_nav_link(title):
                continue
            
            # ── Extract date from the row ──
            row_text = row.get_text(" ", strip=True)
            date_found = None
            
            # Pattern 1: "January 15, 2026" or "June 9, 2026"
            import re
            date_match = re.search(
                r'(January|February|March|April|May|June|July|August|'
                r'September|October|November|December)\s+\d{1,2},?\s+\d{4}',
                row_text
            )
            if date_match:
                date_found = date_match.group()
            
            # Pattern 2: "01/15/2026" or "06/09/2026"
            if not date_found:
                date_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', row_text)
                if date_match:
                    date_found = date_match.group()
            
            # ── CRITICAL: Skip if date is too old ──
            if date_found:
                if not is_recent(date_found, CUTOFF_DAYS):
                    continue  # OLD — skip it
            # If no date found at all, skip to be safe
            # (prevents grabbing undated static pages)
            else:
                continue
            
            full_url = f"https://www.occ.gov{href}" if href.startswith("/") else href
            results.append({
                "source": "OCC",
                "title": title,
                "url": full_url,
                "type": "Bulletin / News Release",
                "date": date_found or "",
                "id": make_id(title, full_url),
            })
        
        if results:
            break
    
    print(f"  OCC: {len(results)} items")
    return results

# ── FinCEN (FIXED — strict container targeting) ──
def fetch_fincen():
    results = []
    r = safe_get("https://www.fincen.gov/news/press-releases")
    if not r:
        return results
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # ONLY look in .views-row containers (actual press releases)
    for container in soup.select(".views-row")[:10]:
        link = container.find("a")
        if not link:
            continue
        
        href = link.get("href", "")
        title = clean_title(link.get_text(strip=True))
        
        if is_nav_link(title):
            continue
        
        # Try to extract date from the container
        date_el = container.find("span", class_="date-display-single") or \
                  container.find("time")
        date_str = date_el.get_text(strip=True) if date_el else ""
        
        if date_str and not is_recent(date_str, CUTOFF_DAYS + 4):
            continue
        
        full_url = f"https://www.fincen.gov{href}" if href.startswith("/") else href
        results.append({
            "source": "FinCEN",
            "title": title,
            "url": full_url,
            "type": "Advisory / Press Release",
            "date": date_str,
            "id": make_id(title, full_url),
        })
    
    print(f"  FinCEN: {len(results)} items")
    return results


# ── NAIC (FIXED — newsroom only, date filtered) ──
def fetch_naic():
    results = []
    r = safe_get("https://content.naic.org/newsroom")
    if not r:
        print(f"  NAIC: 0 items")
        return results
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Only grab items from the actual news listing
    for container in soup.select(".views-row, article")[:12]:
        link = container.find("a")
        if not link:
            continue
        
        href = link.get("href", "")
        title = clean_title(link.get_text(strip=True))
        
        if is_nav_link(title):
            continue
        
        # Look for date within the container
        date_el = container.find("time") or \
                  container.find("span", class_="date-display-single") or \
                  container.find(class_="field--name-field-date")
        date_str = date_el.get_text(strip=True) if date_el else ""
        
        # Skip old items
        if date_str and not is_recent(date_str, CUTOFF_DAYS + 7):
            continue
        
        full_url = f"https://content.naic.org{href}" if href.startswith("/") else href
        results.append({
            "source": "NAIC",
            "title": title,
            "url": full_url,
            "type": "Press Release / Publication",
            "date": date_str,
            "id": make_id(title, full_url),
        })
    
    print(f"  NAIC: {len(results)} items")
    return results


# ── CA DOI (FIXED — only press releases, not nav) ──
def fetch_california_doi():
    results = []
    
    # ONLY the press releases page — NOT the main site
    r = safe_get("https://www.insurance.ca.gov/0400-news/0100-press-releases/")
    if not r:
        print(f"  CA DOI: 0 items")
        return results
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Target ONLY the content area
    content = soup.find("div", {"id": "MainContent"}) or \
              soup.find("div", class_="field-items") or \
              soup.find("main") or soup
    
    seen_urls = set()
    for link in content.select("li a, td a")[:15]:
        href = link.get("href", "")
        title = clean_title(link.get_text(strip=True))
        
        if is_nav_link(title):
            continue
        
        # Press releases usually have year in the URL or title
        current_year = str(date.today().year)
        if current_year not in href and current_year not in title:
            continue  # Likely not from this year
        
        full_url = f"https://www.insurance.ca.gov{href}" if href.startswith("/") else href
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            results.append({
                "source": "CA DOI",
                "title": title,
                "url": full_url,
                "type": "Press Release / Bulletin",
                "id": make_id(title, full_url),
            })
    
    print(f"  CA DOI: {len(results)} items")
    return results


# ── NYDFS (FIXED — circular letters only, with dates) ──
def fetch_nydfs():
    results = []
    
    r = safe_get("https://www.dfs.ny.gov/industry_guidance/circular_letters")
    if not r:
        print(f"  NYDFS: 0 items")
        return results
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Target only table rows or views-row (actual circular letters)
    content = soup.find("div", class_="view-content") or \
              soup.find("table") or \
              soup.find("main")
    
    if not content:
        content = soup
    
    seen_urls = set()
    for container in content.select("tr, .views-row")[:12]:
        link = container.find("a")
        if not link:
            continue
        
        href = link.get("href", "")
        title = clean_title(link.get_text(strip=True))
        
        if is_nav_link(title):
            continue
        
        full_url = f"https://www.dfs.ny.gov{href}" if href.startswith("/") else href
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            results.append({
                "source": "NYDFS",
                "title": title,
                "url": full_url,
                "type": "Circular Letter / Guidance",
                "id": make_id(title, full_url),
            })
    
    print(f"  NYDFS: {len(results)} items")
    return results


# ── Run All Sources ──
def fetch_all():
    print("\n📡 Fetching all regulatory sources...")
    all_pubs = []
    all_pubs += fetch_federal_register()  # Best source — API with dates
    all_pubs += fetch_sec()               # Good source — RSS with dates
    all_pubs += fetch_occ()
    all_pubs += fetch_fincen()
    all_pubs += fetch_naic()
    all_pubs += fetch_california_doi()
    all_pubs += fetch_nydfs()
    
    # Deduplicate
    seen, unique = set(), []
    for pub in all_pubs:
        if pub["id"] not in seen and pub.get("title"):
            seen.add(pub["id"])
            unique.append(pub)
    
    print(f"\n📥 Total: {len(unique)} unique publications (filtered)")
    return unique


if __name__ == "__main__":
    print("Testing all sources...\n")
    all_items = fetch_all()
    for item in all_items:
        print(f"  ✅ [{item['source']}] {item['title'][:70]}")