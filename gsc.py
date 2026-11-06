"""Automatically submit page URLs to Google Search Console for indexing."""

from __future__ import annotations

import argparse
import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from google.oauth2 import service_account
from googleapiclient.discovery import build
from prompt_toolkit.shortcuts import confirm, prompt

# scopes
SCOPES = ["https://www.googleapis.com/auth/webmasters"]

# default service account file (override with --service-account)
DEFAULT_SERVICE_ACCOUNT_FILE = "motorcycle-specs-513815-5161c346bc6b.json"

# default CSV file (used when --csv is passed without a value)
DEFAULT_CSV_FILE = "urls.csv"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class CliArgs:
    """Parsed command-line arguments."""

    service_account: str
    csv_file: str | None
    site_url: str
    yes: bool


def parse_args(argv: list[str] | None = None) -> CliArgs:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Submit page URLs to Google Search Console for indexing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-a",
        "--service-account",
        default=DEFAULT_SERVICE_ACCOUNT_FILE,
        help="Path to the Google Cloud service account JSON file.",
    )
    parser.add_argument(
        "-c",
        "--csv",
        dest="csv_file",
        nargs="?",
        const=DEFAULT_CSV_FILE,
        default=argparse.SUPPRESS,
        help=(
            "CSV file with one URL per row. Defaults to "
            f"{DEFAULT_CSV_FILE} when the flag is passed without a value; "
            "when omitted, the site's sitemap is used instead."
        ),
    )
    parser.add_argument(
        "-s",
        "--site",
        dest="site_url",
        default=argparse.SUPPRESS,
        help="Site URL to index (skips the interactive site picker).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and submit immediately.",
    )
    raw = parser.parse_args(argv)
    return CliArgs(
        service_account=raw.service_account,
        csv_file=getattr(raw, "csv_file", None),
        site_url=getattr(raw, "site_url", ""),
        yes=raw.yes,
    )


def get_service(service_account_file: str) -> Any:
    """Build the Search Console API service from a service account file."""
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=credentials)


def get_all_site_urls(service: Any) -> list[str]:
    """Get all accessible site URLs."""
    sites = service.sites().list().execute()
    return [site["siteUrl"] for site in sites.get("siteEntry", [])]


def get_sitemap_url(service: Any, site_url: str) -> str | None:
    """Get sitemap URL from Google Search Console."""
    sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
    if sitemaps.get("sitemap"):  # check if sitemap exists
        return sitemaps["sitemap"][0]["path"]
    return None


def get_all_pages_from_sitemap(url: str) -> list[str]:
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
        links: list[str] = []
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
    except Exception as e:  # noqa: BLE001 - report and continue with partial results
        print(f"Error parsing sitemap: {e}")
        return []


def get_all_pages_from_csv(path: str) -> list[str]:
    """Read all page URLs from CSV file (one URL per line)."""
    try:
        with open(path, newline="") as csvfile:
            reader = csv.reader(csvfile)
            return [row[0].strip() for row in reader if row and row[0].strip()]
    except FileNotFoundError:
        print(f"CSV file not found: {path}")
        return []


def submit_index_request(
    service: Any, site_url: str, page_url: str
) -> dict[str, Any] | None:
    """Submit index request to Google Search Console."""
    try:
        response = (
            service.urlInspection()
            .index()
            .inspect(body={"inspectionUrl": page_url, "siteUrl": site_url})
            .execute()
        )
        return response
    except Exception as e:  # noqa: BLE001 - report and continue with remaining pages
        print(f"Error submitting index request: {e}")
        return None


def select_site(all_site_urls: list[str], preset_site: str) -> str | None:
    """Return the chosen site URL, either from the preset argument or a prompt."""
    if preset_site:
        if preset_site in all_site_urls:
            print(f"Using site: {preset_site}")
            return preset_site
        print(f"Warning: {preset_site} is not in the accessible sites list:")
        print(all_site_urls)

    print("\nAvailable sites:")
    for i, url in enumerate(all_site_urls, 1):
        print(f"{i}. {url}")
    selected = prompt("Select a site number: ")
    try:
        site_index = int(selected) - 1
        return all_site_urls[site_index]
    except ValueError, IndexError:
        print("Invalid selection")
        return None


def index_pages(service: Any, site_url: str, pages: list[str]) -> None:
    """Submit each page for re-indexing and print its indexing status."""
    for page in pages:
        response = submit_index_request(service, site_url, page)
        if response:
            index_status = response.get("inspectionResult", {}).get(
                "indexStatusResult", {}
            )
            current_status = index_status.get("coverageState", "unknown")
            last_crawled = index_status.get("lastCrawlTime", "never")
            status_line = (
                f"({page}) | current status: {current_status} "
                f"| last crawled: {last_crawled}"
            )
            print(status_line)
    print(f"Indexed {len(pages)} pages for {site_url}.")


def main(argv: list[str] | None = None) -> None:
    """Main function."""
    args = parse_args(argv)

    # authentication
    try:
        service = get_service(args.service_account)
    except (OSError, ValueError) as e:
        print(f"Could not load service account file '{args.service_account}': {e}")
        return

    # select site
    all_site_urls = get_all_site_urls(service)
    if not all_site_urls:
        print("No accessible sites. Please check your service account permissions.")
        return
    selected_site_url = select_site(all_site_urls, args.site_url)
    if selected_site_url is None:
        return

    # determine pages to index
    if args.csv_file is not None:
        pages_to_index = get_all_pages_from_csv(args.csv_file)
        print(f"Found {len(pages_to_index)} pages in {args.csv_file}:")
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
        if args.yes or confirm("Submit all these pages for re-indexing?"):
            index_pages(service, selected_site_url, pages_to_index)
        else:
            print("Aborted.")

    print("Done.")


if __name__ == "__main__":
    main()
