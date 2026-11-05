import os
import csv
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from prompt_toolkit.shortcuts import prompt
from prompt_toolkit.shortcuts import confirm

# optional flags
INDEX_FROM_CSV = False  # if True, read URLs from CSV file "urls.csv"

# service account file
SERVICE_ACCOUNT_FILE = (
    "motorcycle-specs-513815-5161c346bc6b.json"  # replace with your JSON file name
)

# scopes
SCOPES = ["https://www.googleapis.com/auth/webmasters"]


def get_all_site_urls(service):
    """Get all accessible site URLs."""
    sites = service.sites().list().execute()
    return [site["siteUrl"] for site in sites.get("siteEntry", [])]


def get_sitemap_url(service, site_url):
    """Get sitemap URL from Google Search Console."""
    sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
    if sitemaps.get("sitemap"):  # check if sitemap exists
        return sitemaps["sitemap"][0]["path"]
    else:
        return None  # if no sitemap, return None


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def get_all_pages_from_sitemap(url):
    """Parse all page URLs from sitemap (handles sitemap indexes)."""
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with urlopen(request) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
        # Some servers return an HTML page (e.g. a SPA fallback) instead of XML
        # when a sitemap route is missing. Detect that and report it clearly.
        if "html" in content_type.lower() or data.lstrip().lower().startswith(
            b"<!doctype html"
        ):
            print(f"Warning: {url} returned HTML instead of XML; skipping.")
            return []
        root = ET.fromstring(data)
        namespaces = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        links = []
        sub_sitemaps = root.findall("ns:sitemap", namespaces)
        if sub_sitemaps:
            # this is a sitemap index; recurse into each child
            for sub in sub_sitemaps:
                loc = sub.find("ns:loc", namespaces)
                if loc is not None and loc.text:
                    links.extend(get_all_pages_from_sitemap(loc.text))
        else:
            for element in root.findall("ns:url", namespaces):
                loc = element.find("ns:loc", namespaces)
                if loc is not None and loc.text:
                    links.append(loc.text)
        return links
    except Exception as e:
        print(f"Error parsing sitemap: {e}")
        return []


def get_all_pages_from_csv(path):
    """Read all page URLs from CSV file (one URL per line)."""
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.reader(csvfile)
            pages = []
            for row in reader:
                if row and row[0].strip():
                    pages.append(row[0].strip())
            return pages
    except FileNotFoundError:
        print(f"CSV file not found: {path}")
        return []


def submit_index_request(service, site_url, page_url):
    """Submit index request to Google Search Console."""
    try:
        request = {"inspectionUrl": page_url, "siteUrl": site_url}
        response = service.urlInspection().index().inspect(body=request).execute()
        return response
    except Exception as e:
        print(f"Error submitting index request: {e}")
        return None


def main():
    """Main function."""

    # authentication
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("searchconsole", "v1", credentials=credentials)

    # select site
    all_site_urls = get_all_site_urls(service)
    if not all_site_urls:
        print("No accessible sites. Please check your service account permissions.")
        return

    print("\nAvailable sites:")
    for i, url in enumerate(all_site_urls, 1):
        print(f"{i}. {url}")
    selected_site_url = prompt("Select a site number: ")
    try:
        site_index = int(selected_site_url) - 1
        selected_site_url = all_site_urls[site_index]
    except (ValueError, IndexError):
        print("Invalid selection")
        return

    # determine pages to index
    pages_to_index = []
    if INDEX_FROM_CSV:
        pages_to_index = get_all_pages_from_csv("urls.csv")
        print(f"Found {len(pages_to_index)} pages in urls.csv:")
        print(pages_to_index)
    else:
        sitemap_url = get_sitemap_url(service, selected_site_url)
        if sitemap_url:
            pages_to_index = get_all_pages_from_sitemap(sitemap_url)
            print(
                f"Found {len(pages_to_index)} pages in sitemap of {selected_site_url}:"
            )
            print(pages_to_index)
        else:
            print(f"No sitemap found for {selected_site_url}.")
            return

    # submit index
    if pages_to_index:
        should_index = confirm("Submit all these pages for re-indexing?")
        if should_index:
            for page in pages_to_index:
                response = submit_index_request(service, selected_site_url, page)
                if response:
                    index_status = response.get("inspectionResult", {}).get(
                        "indexStatusResult", {}
                    )
                    current_status = index_status.get("coverageState", "unknown")
                    last_crawled = index_status.get("lastCrawlTime", "never")
                    print(
                        f"({page}) | current status: {current_status} | last crawled: {last_crawled}"
                    )
            print(f"Indexed {len(pages_to_index)} pages for {selected_site_url}.")

    print("Done.")


if __name__ == "__main__":
    main()
