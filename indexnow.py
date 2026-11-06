"""Automatically submit page URLs to search engines via the IndexNow API.

Docs: https://www.indexnow.org/documentation
Ownership is verified by hosting a text key file ({your-key}.txt) on your
host, or by passing a custom key file location with --key-location.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from prompt_toolkit.shortcuts import confirm, prompt

from gsc import DEFAULT_CSV_FILE, get_all_pages_from_csv, get_all_pages_from_sitemap

# default IndexNow API host (supports Bing, Yandex, Seznam, etc.)
DEFAULT_API_HOST = "api.indexnow.org"

# IndexNow accepts at most 10,000 URLs per POST request
MAX_URLS_PER_REQUEST = 10_000

KEY_PATTERN = re.compile(r"[A-Za-z0-9-]{8,128}")


@dataclass
class CliArgs:
    """Parsed command-line arguments."""

    host: str
    key: str
    key_location: str
    csv_file: str | None
    sitemap_url: str
    api_host: str
    dry_run: bool
    yes: bool


def parse_args(argv: list[str] | None = None) -> CliArgs:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Submit page URLs to search engines through the IndexNow API."),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-H",
        "--host",
        dest="host",
        default="",
        help="Your website host without scheme, e.g. www.example.com.",
    )
    key_group = parser.add_mutually_exclusive_group()
    key_group.add_argument(
        "-k",
        "--key",
        dest="key",
        default="",
        help="IndexNow key (8-128 chars, a-z A-Z 0-9 -).",
    )
    key_group.add_argument(
        "-l",
        "--key-location",
        dest="key_location",
        default="",
        help="URL of the hosted IndexNow key file (alternative to --key).",
    )
    parser.add_argument(
        "-c",
        "--csv",
        dest="csv_file",
        nargs="?",
        const=DEFAULT_CSV_FILE,
        default=None,
        help=(
            "CSV file with one URL per row. Defaults to "
            f"{DEFAULT_CSV_FILE} when the flag is passed without a value; "
            "use --sitemap to read URLs from a sitemap instead."
        ),
    )
    parser.add_argument(
        "-n",
        "--api-host",
        dest="api_host",
        default=DEFAULT_API_HOST,
        help="IndexNow API host to POST to.",
    )
    parser.add_argument(
        "-s",
        "--sitemap",
        dest="sitemap_url",
        default="",
        help="Sitemap URL to fetch page URLs from (instead of a CSV).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip the confirmation prompt."
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Show the request payload without submitting it.",
    )
    raw = parser.parse_args(argv)
    return CliArgs(
        host=raw.host,
        key=raw.key,
        key_location=raw.key_location,
        csv_file=raw.csv_file,
        sitemap_url=raw.sitemap_url,
        api_host=raw.api_host,
        dry_run=raw.dry_run,
        yes=raw.yes,
    )


def normalize_host(host: str) -> str:
    """Reduce a user-supplied site URL to a bare host name."""
    host = host.strip().strip("/")
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", host)
    host = host.split("/", 1)[0].split(":", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9.-]+(\.[A-Za-z0-9-]+)+", host):
        raise ValueError(f"Invalid host: {host!r} (expected e.g. www.example.com)")
    return host.lower()


def collect_urls(args: CliArgs) -> list[str]:
    """Gather page URLs from the chosen source (CSV or sitemap)."""
    if args.sitemap_url and args.csv_file is not None:
        print("Use either --csv or --sitemap, not both.")
        sys.exit(2)
    if args.sitemap_url:
        urls = get_all_pages_from_sitemap(args.sitemap_url)
        print(f"Found {len(urls)} pages in sitemap {args.sitemap_url}:")
    else:
        csv_path = args.csv_file if args.csv_file is not None else DEFAULT_CSV_FILE
        urls = get_all_pages_from_csv(csv_path)
        print(f"Found {len(urls)} pages in {csv_path}:")
    print(urls)
    return urls


def build_payload(host: str, args: CliArgs, urls: list[str]) -> dict:
    """Build the IndexNow JSON payload."""
    payload: dict = {"host": host, "urlList": urls}
    if args.key_location:
        payload["keyLocation"] = args.key_location
    else:
        if not args.key:
            print("No IndexNow key provided; aborting.")
            sys.exit(2)
        payload["key"] = args.key
    return payload


def submit_chunk(api_host: str, payload: dict) -> tuple[int, str]:
    """POST one batch of URLs and return (HTTP status, response body)."""
    endpoint = f"https://{normalize_api_host(api_host)}/indexnow"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except URLError as e:
        raise SystemExit(f"Could not reach {endpoint}: {e.reason}") from e


def normalize_api_host(api_host: str) -> str:
    """Normalize the API host (accepts a bare host name or full URL)."""
    return re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", api_host).strip("/")


def chunked(urls: list[str], size: int) -> list[list[str]]:
    """Split urls into batches of at most size entries."""
    return [urls[i : i + size] for i in range(0, len(urls), size)]


def main(argv: list[str] | None = None) -> None:
    """Main function."""
    args = parse_args(argv)

    # resolve host
    try:
        host = normalize_host(
            args.host or prompt("Website host (e.g. www.example.com): ")
        )
    except ValueError as e:
        print(str(e))
        return

    # resolve key / key location
    if args.key_location:
        print(f"Using key file location: {args.key_location}")
    else:
        if not args.key:
            key = prompt("IndexNow key: ").strip()
            while not key:
                print("A key is required (or use --key-location instead).")
                key = prompt("IndexNow key: ").strip()
            args.key = key
        if not KEY_PATTERN.fullmatch(args.key):
            print(
                "Note: the key does not look like a valid IndexNow key "
                "(8-128 characters, only a-z, A-Z, 0-9 and dashes)."
            )
        print(
            f"Note: your key file must be publicly reachable at "
            f"https://{host}/{args.key}.txt"
        )

    # collect urls
    urls = collect_urls(args)
    if not urls:
        print("No URLs to submit.")
        return

    if args.dry_run:
        batches = chunked(urls, MAX_URLS_PER_REQUEST)
        for i, batch in enumerate(batches, 1):
            print(f"\n[dry-run] request {i}/{len(batches)}:")
            print(json.dumps(build_payload(host, args, batch), indent=2))
        print(f"\nDry run complete: {len(urls)} URLs in {len(batches)} chunk(s).")
        return

    should_submit = confirm(f"Submit {len(urls)} URL(s) for {host} to {args.api_host}?")
    if not should_submit:
        print("Aborted.")
        return

    batches = chunked(urls, MAX_URLS_PER_REQUEST)
    failures = 0
    for i, batch in enumerate(batches, 1):
        status, body = submit_chunk(args.api_host, build_payload(host, args, batch))
        label = f"batch {i}/{len(batches)} ({len(batch)} URLs)"
        if status in (200, 202):
            print(f"OK: {label} accepted (HTTP {status}).")
        else:
            failures += 1
            print(f"FAILED: {label} (HTTP {status}): {body.strip() or 'no body'}")
            if status in (400, 403):
                print(
                    "Hint: check that your key / key location is valid and the "
                    f"key file is reachable at https://{host}/ (ownership check)."
                )

    if failures:
        print(f"Done with errors: {failures}/{len(batches)} batch(es) failed.")
    else:
        print(f"Done. {len(urls)} URL(s) submitted for {host}.")


if __name__ == "__main__":
    main()
