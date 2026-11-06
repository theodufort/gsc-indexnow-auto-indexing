# GSC + IndexNow Auto-Indexing

Collection of Python scripts that submit URLs from your website to search engines for indexing or re-indexing. It offers a free alternative to paid SEO tools for managing your website's search engine visibility.

* **[`gsc.py`](gsc.py)** — submits pages to Google Search Console.
  * Connects to your Google Search Console using a Google Cloud Service Account.
  * Parses your website's sitemap to identify all URLs.
  * Submits each URL for indexing in Google Search Console.
* **[`indexnow.py`](indexnow.py)** — submits pages through the [IndexNow API](https://www.indexnow.org/documentation), which reaches Bing, Yandex, Seznam, Ask.com and others.
  * Requires no API token other than a self-owned IndexNow key file.
  * Accepts URLs from a sitemap or a CSV file.
  * Batches up to 10,000 URLs per request as allowed by IndexNow.

**Getting Started**

Setting up this script is straightforward:

1. **Install Dependencies:**
   Ensure you have Python 3 and [uv](https://docs.astral.sh/uv/) installed. Run the following command in your terminal to install the required libraries:

   ```bash
   uv sync
   ```

2. **Clone the Repository:**
   Clone this script's repository using Git:

   ```bash
   git clone https://github.com/oslook/gsc-auto-indexer.git  # Replace 'username' with your GitHub username
   cd gsc-auto-indexer
   ```

3. **Create a Google Cloud Service Account:**
   - Visit the Google Cloud Console ([https://console.cloud.google.com/](https://console.cloud.google.com/)) and navigate to the IAM & Admin section.
   - Create a new service account and download the JSON key file. Move this file to the script's directory.

4. **Provide the Service Account File:**
   - Keep your downloaded JSON key file in the script's directory, or pass its path with `--service-account` when running (see below). The `motorcycle-specs-513815-5161c346bc6b.json` file is used by default.

5. **Grant Permissions in Google Search Console:**
   - Access your Google Search Console dashboard.
   - Navigate to "Settings" > "Users and Permissions" > "Add User."
   - Enter the email address associated with your service account (found in the key file) and grant it "Owner" permissions.

**Running the GSC Script:**

Execute the script using uv:

```bash
uv run gsc.py
```

The script will:

* List all websites associated with your service account in Google Search Console.
* Prompt you to choose a website for indexing.
* Parse the website's sitemap (fetched from Search Console) and extract URLs (or read them from a CSV file if you pass `--csv`).
* Ask for confirmation before submitting URLs for indexing.
* Submit each URL to Google Search Console and display indexing status information.

**Command-Line Options**

```bash
uv run gsc.py [-h] [-a SERVICE_ACCOUNT] [-c [CSV_FILE]] [-s SITE_URL] [-y]
```

| Option | Description |
| --- | --- |
| `-a, --service-account FILE` | Path to the Google Cloud service account JSON file (default: `motorcycle-specs-513815-5161c346bc6b.json`). |
| `-c, --csv [FILE]` | Read URLs from a CSV file (one URL per row) instead of the sitemap. Defaults to `urls.csv` when the flag is passed without a value. |
| `-s, --site URL` | Site URL to index, skipping the interactive site picker. |
| `-y, --yes` | Skip the confirmation prompt and submit immediately. |

Example:

```bash
uv run gsc.py --service-account my-key.json --csv my-urls.csv --site https://www.my-site.com --yes
```

## IndexNow Submitter (`indexnow.py`)

[IndexNow](https://www.indexnow.org/documentation) is an open protocol adopted by Bing, Yandex, Seznam and others. You prove site ownership by hosting a small key file, then POST updated URLs in JSON to the IndexNow endpoint.

**Setup**

1. Generate a key (8–128 characters, only `a-z`, `A-Z`, `0-9` and dashes), e.g. `a1b2c3d4e5f60718`.
2. Host a plain text file containing exactly that key at `https://your-site.com/<key>.txt` (e.g. `https://your-site.com/a1b2c3d4e5f60718.txt`).

**Running the Script:**

```bash
uv run indexnow.py --host www.my-site.com --key a1b2c3d4e5f60718
```

The script will:

* Read page URLs from `urls.csv` (default) or a sitemap.
* Batch the URLs (max 10,000 per request, as allowed by IndexNow).
* Ask for confirmation, then POST the JSON payload to the IndexNow API.
* Report acceptance (`200`/`202`) or failure (often `400`/`403`, usually a key/ownership problem) for each batch.

**Command-Line Options**

```bash
uv run indexnow.py [-h] [-H HOST] [-k KEY | -l KEY_LOCATION] [-c [CSV_FILE]] [-n API_HOST] [-s SITEMAP_URL] [-y] [-d]
```

| Option | Description |
| --- | --- |
| `-H, --host HOST` | Your website host without scheme, e.g. `www.my-site.com`. |
| `-k, --key KEY` | The IndexNow key (must match the hosted `<key>.txt` file). |
| `-l, --key-location URL` | URL of the hosted key file, instead of `--key` (sends `keyLocation` in the payload). |
| `-c, --csv [FILE]` | Read URLs from a CSV file (one URL per row). Defaults to `urls.csv` when the flag is passed without a value. |
| `-n, --api-host API_HOST` | IndexNow API host to POST to (default: `api.indexnow.org`, the aggregator for Bing, Yandex, Seznam, Ask.com). |
| `-s, --sitemap URL` | Fetch page URLs from a sitemap instead of a CSV file. |
| `-y, --yes` | Skip the confirmation prompt and submit immediately. |
| `-d, --dry-run` | Print the JSON payload that would be sent, without submitting. |

Example:

```bash
# Submit from a CSV, verifying the payload first
uv run indexnow.py -H www.my-site.com -k a1b2c3d4e5f60718 -c my-urls.csv --dry-run
uv run indexnow.py -H www.my-site.com -k a1b2c3d4e5f60718 -c my-urls.csv --yes

# Or from a sitemap
uv run indexnow.py --host www.my-site.com --key-location https://www.my-site.com/a1b2c3d4e5f60718.txt --sitemap https://www.my-site.com/sitemap.xml
```

**Linting and Type Checking**

Development dependencies include [Ruff](https://docs.astral.sh/ruff/) and [Pyright](https://microsoft.github.io/pyright/), with configuration in `pyproject.toml`. Run them with:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
```
