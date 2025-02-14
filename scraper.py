import re
import json
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup
from tokenizer import tokenize
from collections import deque
from simhash_basic import make_simhash, simhash_diff
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
    r'\?sort=', r'\?order=', r'\?page=', r'\?date=', r'\?filter=', r'calendar', r'\?view=',
    r'\?session=', r'\?print=', r'\?lang=', r'\?mode=', r'\?year=', r'\?month=', r'\?day=', r'\?.ical$'
]

def is_trap(url):
    """Detects common crawler traps based on URL patterns."""
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
        robots_parsers[domain].read()

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

    if resp.status != 200 or resp.raw_response is None:
        return []

    # Skip files larger than 1MB
    if len(resp.raw_response.content) > MAX_PAGE_SIZE:
        print(f"Skipping large file (>1MB): {url}")
        return[]

    if is_trap(url):
        print(f"Skipping potential crawler trap: {url}")
        return []

    # Parse the page content
    soup = BeautifulSoup(resp.raw_response.content, "html.parser")
    text_content = soup.get_text()

    # *Check for similar pages BEFORE processing*
    if is_similar(text_content):
        print(f"Skipping duplicate page: {url}")
        return []  # *Skip processing similar pages*

    word_count = len(text_content.split())
    if word_count < MIN_WORD_COUNT:
        print(f"Skipping low-content page (<50 words): {url}")
        return []

    tokens = tokenize(text_content)
    tokens = [word for word in tokens if word not in STOPWORDS]  # Remove stopwords
    update_word_counts(tokens)

    # Update longest page record
    word_count = len(tokens)
    if word_count > longest_page[1]:
        longest_page = (url, word_count)

    # Track unique pages and subdomains
    track_unique_pages(url)

    # Extract and validate links
    links = extract_next_links(url, soup)
    valid_links = [link for link in links if is_valid(link)]

    # Add new valid links to the queue
    for link in valid_links:
        if link not in visited_urls:
            visited_urls.add(link)
            url_queue.append(link)

    # Save progress to log file after every page processed
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
      - Belong to one of the allowed domains:
          *.ics.uci.edu, *.cs.uci.edu, *.informatics.uci.edu, *.stat.uci.edu,
      - Do not point to files with disallowed extensions,
    are considered valid.
    """
    try:
        parsed = urlparse(url)
        # Only accept http and https URLs
        if parsed.scheme not in {"http", "https"}:
            return False

        # Only accept URLs within the allowed domains.
        # This regex ensures that the netloc ends with one of the specified domains.
        if not re.search(r"(ics\.uci\.edu|cs\.uci\.edu|informatics\.uci\.edu|stat\.uci\.edu)$", parsed.netloc):
            return False

        # Exclude URLs with certain file extensions.
        if re.match(
                r".*\.(css|js|bmp|gif|jpe?g|ico"
                + r"|png|tiff?|mid|mp2|mp3|mp4"
                + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
                + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
                + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
                + r"|epub|dll|cnf|tgz|sha1"
                + r"|thmx|mso|arff|rtf|jar|csv"
                + r"|rm|smil|wmv|swf|wma|zip|rar|gz|ical|djvu|apk|bak|tmp|jpg|jpeg|svg|pps)$",
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


