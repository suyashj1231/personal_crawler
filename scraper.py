import re
import json
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup
from tokenizer import tokenize
from collections import deque
from simhash_basic import make_simhash, simhash_diff
import urllib.error
from urllib.parse import parse_qs


MIN_WORD_COUNT = 50
MAX_PAGE_SIZE = 1 * 1024 * 1024  # 1MB = 1 * 1024 * 1024 bytes
# Global storage for tracking unique URLs, subdomains, and word frequency
visited_urls = set()
visited_hashes = set()
LOG_FILE = "crawler_log.json"
subdomains = {}
word_counts = {}
longest_page = (None, 0)  # (URL, word count)
url_queue = deque()
robots_parsers = {}

STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be because been before being below between both but by can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves""".split())

TRAP_PATTERNS = [
    r'\?sort=', r'\?order=', r'\?page=\d+',  # Blocks paginated URLs
    r'\?date=', r'\?filter=', r'calendar', r'\?view=', r'\?session=',
    r'\?print=', r'\?lang=', r'\?mode=', r'\?year=\d{4}', r'\?month=\d{1,2}', r'\?day=\d{1,2}',
    r'\?tribe-bar-date=', r'outlook-ical=',  # Blocks infinite event/calendar URLs
    r'\.ical$', r'\.ics$',  # Blocks iCalendar/ICS downloads
    r'doku\.php',  # Blocks all doku.php pages (including media, edit, revisions)
    r'\?do=media', r'\?tab_details=', r'\?tab_files=',
    r'\?rev=\d+',  # Blocks revision history pages
    r'&do=diff',  # Blocks version difference pages
    r'&do=edit',  # Blocks edit mode pages
    r'&printable=yes',  # Blocks printable versions of pages
    r'\?share=',  # Blocks unnecessary share links
    r'\?replytocom=',  # Blocks duplicate comment links
    r'\?fbclid=', r'utm_',  # Blocks tracking parameters (FB, Google Analytics)
    r'\?redirect=',  # Blocks auto-redirects that could loop infinitely
    r'\?attachment_id=',  # Blocks media attachment pages
]



def is_trap(url):
    """Detects common crawler traps based on URL patterns."""
    parsed = urlparse(url)

    # 🚀 **Prevent ALL doku.php URLs, even if they don’t have `?` parameters**
    if "doku.php" in parsed.path:
        return True

    # Check trap patterns
    for pattern in TRAP_PATTERNS:
        if re.search(pattern, url):
            return True

    return False


def can_fetch(url):
    """Checks if the URL is allowed by robots.txt"""
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if domain not in robots_parsers:
        robots_parsers[domain] = urllib.robotparser.RobotFileParser()
        robots_parsers[domain].set_url(domain)
        try:
            robots_parsers[domain].read()  # 🚀 **This is where the timeout happens**
        except urllib.error.URLError as e:
            print(f"⚠️ Failed to fetch robots.txt for {domain}: {e}")
            return True  # **Allow crawling if robots.txt is unavailable**
        except Exception as e:
            print(f"⚠️ Unexpected error fetching robots.txt for {domain}: {e}")
            return True  # **Allow crawling to continue**

    return robots_parsers[domain].can_fetch("*", url)


def is_similar(text):
    """Checks if a page is too similar to previously crawled pages."""
    page_hash = make_simhash(text)
    for old_hash in visited_hashes:
        if simhash_diff(page_hash, old_hash) < 5:  # Adjust threshold as needed
            return True  # Too similar, skip
    visited_hashes.add(page_hash)
    return False

def scraper(url, resp):
    global longest_page

    # **1️⃣ Check robots.txt before crawling**
    if not can_fetch(url):
        print(f"Blocked by robots.txt: {url}")
        return []

    if 600 <= resp.status < 700:
        print(f"Skipping URL due to unknown 6XX error (status {resp.status}): {url}")
        return []

    # Handle redirects (300-series status codes)
    if 300 <= resp.status <= 399:
        new_url = resp.raw_response.headers.get("Location")
        if new_url:
            print(f"Redirecting {url} → {new_url}")
            return [new_url]  # Follow the redirect
        else:
            print(f"Skipping redirect without location: {url}")
            return []

    if resp.status != 200 or resp.raw_response is None:
        return []

    # **2️⃣ Skip large files (>1MB)**
    if len(resp.raw_response.content) > MAX_PAGE_SIZE:
        print(f"Skipping large file (>1MB): {url}")
        return []

    if is_trap(url):
        print(f"Skipping potential crawler trap: {url}")
        return []

    # **3️⃣ Parse the page content**
    soup = BeautifulSoup(resp.raw_response.content, "html.parser")
    text_content = soup.get_text()

    # **4️⃣ Check for duplicate content (SimHash)**
    if is_similar(text_content):
        print(f"Skipping duplicate page: {url}")
        return []

    # **5️⃣ Avoid low-content pages (<50 words)**
    word_count = len(text_content.split())
    if word_count < MIN_WORD_COUNT:
        print(f"Skipping low-content page (<50 words): {url}")
        return []

    # **6️⃣ Process valid content**
    tokens = tokenize(text_content)
    tokens = [word for word in tokens if word not in STOPWORDS]
    update_word_counts(tokens)

    # **7️⃣ Update longest page record**
    if word_count > longest_page[1]:
        longest_page = (url, word_count)

    # **8️⃣ Track unique pages and subdomains**
    track_unique_pages(url)

    # **9️⃣ Extract and validate links**
    links = extract_next_links(url, soup)
    valid_links = [link for link in links if is_valid(link)]

    # **🔟 Add new valid links to the queue**
    for link in valid_links:
        if link not in visited_urls:
            visited_urls.add(link)
            url_queue.append(link)

    # **📌 Save log after every processed page**
    save_log()
    return valid_links

def extract_next_links(url, soup):
    """Extracts and normalizes hyperlinks from the page."""
    links = []
    for tag in soup.find_all("a", href=True):
        absolute_url = urljoin(url, tag["href"])  # Convert to absolute URL
        absolute_url, _ = urldefrag(absolute_url) # no frag
        links.append(absolute_url)
    return links


def is_valid(url):
    """Determines whether a URL should be crawled.

    Only URLs that:
      - Use the http or https scheme,
      - Belong to one of the allowed domains **(including subdomains)**,
      - Do not point to files with disallowed extensions,
    are considered valid.
    """
    try:
        parsed = urlparse(url)

        # Only allow HTTP or HTTPS URLs
        if parsed.scheme not in {"http", "https"}:
            return False

        # Ensure the URL belongs to allowed domains **(including subdomains)**
        allowed_domains = [
            ".ics.uci.edu",
            ".cs.uci.edu",
            ".informatics.uci.edu",
            ".stat.uci.edu"
        ]
        if not any(parsed.netloc.endswith(domain) for domain in allowed_domains):
            return False

        # Exclude URLs with certain file extensions (non-crawlable resources)
        if re.match(
                r".*\.(css|js|bmp|gif|jpg|jpeg|png|pdf|ico"
                + r"|tiff?|mid|mp2|mp3|mp4|wav|avi|mov|mpeg|m4v|mkv|ogg|ogv"
                + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx"
                + r"|data|dat|exe|bz2|tar|msi|bin|7z|dmg|iso"
                + r"|epub|dll|cnf|tgz|sha1|thmx|mso|arff|rtf|jar|csv"
                + r"|rm|smil|wmv|swf|wma|zip|rar|gz|ical|ppsx|pps|mol)$",
                parsed.path.lower()):
            return False

        return True

    except TypeError:
        print("TypeError for", parsed)
        raise

def track_unique_pages(url):
    """Tracks unique visited pages and subdomains."""
    global visited_urls, subdomains

    parsed = urlparse(url)
    domain = parsed.netloc

    if url not in visited_urls:
        visited_urls.add(url)
        if domain in subdomains:
            subdomains[domain] += 1
        else:
            subdomains[domain] = 1


def update_word_counts(tokens):
    """Updates word frequency counts."""
    global word_counts
    for word in tokens:
        word_counts[word] = word_counts.get(word, 0) + 1


def save_log():
    """Saves the current state of the crawl to a log file."""
    log_data = {
        "visited_urls": list(visited_urls),
        "word_counts": word_counts,
        "subdomains": subdomains,
        "longest_page": longest_page
    }
    with open(LOG_FILE, "w") as file:
        json.dump(log_data, file)

def load_log():
    """Loads the previous crawl state from the log file if it exists."""
    global visited_urls, word_counts, subdomains, longest_page
    try:
        with open(LOG_FILE, "r") as file:
            log_data = json.load(file)
            visited_urls = set(log_data["visited_urls"])
            word_counts.update(log_data["word_counts"])
            subdomains.update(log_data["subdomains"])
            longest_page = tuple(log_data["longest_page"])
            print("Previous crawl state loaded.")
    except FileNotFoundError:
        print("No previous log file found. Starting fresh crawl.")
    except Exception as e:
        print(f"Error loading log file: {e}")

def get_report():
    """Generates final report for the crawler statistics and saves it to a file."""
    report_content = f"Total Unique Pages: {len(visited_urls)}\n"
    report_content += f"Longest Page: {longest_page[0]} with {longest_page[1]} words\n\n"

    report_content += "Top 50 Most Common Words:\n"
    report_content += "\n".join([f"{word}: {count}" for word, count in
                                 sorted(word_counts.items(), key=lambda item: item[1], reverse=True)[:50]])

    report_content += "\n\nSubdomains in ics.uci.edu:\n"
    report_content += "\n".join(
        [f"{domain}, {subdomains[domain]}" for domain in sorted(subdomains.keys()) if "ics.uci.edu" in domain])

    # Save the report to a file
    with open("crawler_report.txt", "w") as file:
        file.write(report_content)

    print("Report saved to crawler_report.txt")


