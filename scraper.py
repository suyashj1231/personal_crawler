import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from tokenizer import compute_word_frequencies, tokenize
from collections import deque
import time
from simhash_basic import make_simhash, simhash_diff

# Global storage for tracking unique URLs, subdomains, and word frequency
visited_urls = set()
visited_hashes = set()
subdomains = {}
word_counts = {}
longest_page = (None, 0)  # (URL, word count)
url_queue = deque()
robots_parsers = {}
STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be because been before being below between both but by can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves""".split())
# Set time limit for execution
start_time = time.time()
TIME_LIMIT = 20  # Stop after 20 seconds




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
    """
       Extracts valid URLs from the response, processes text content,
       and tracks statistics for reporting.
       """
    global longest_page

    if time.time() - start_time > TIME_LIMIT:
        print("Time limit reached. Stopping crawler.")
        return []

    if resp.status != 200 or resp.raw_response is None:
        return []

    # Parse the page content
    soup = BeautifulSoup(resp.raw_response.content, "html.parser")
    text_content = soup.get_text()

    # Skip similar pages
    if is_similar(text_content):
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
            url_queue.append(link)

    return valid_links

def extract_next_links(url, soup):
    """Extracts and normalizes hyperlinks from the page."""
    links = []
    for tag in soup.find_all("a", href=True):
        absolute_url = urljoin(url, tag["href"])  # Convert to absolute URL
        links.append(absolute_url)
    return links

def is_valid(url):
    """Determines whether a URL should be crawled."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())
    except TypeError:
        print("TypeError for ", parsed)
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


