# Rojak Scraper

This repository contains a Python command line tool that collects Malay–English "rojak" sentences from popular Shopee Malaysia products and stores them in Google Sheets. Reviews are gathered from the "Health & Beauty" category (ID `11000168`) by default, filtered using lightweight heuristics, and written to a spreadsheet so you can build a dataset for further analysis.

## Features

- Fetches the most popular products in a Shopee category using the public JSON endpoints.
- Scrapes up to 20 review pages per product (configurable) and evaluates each comment with Malay/English heuristics.
- Deduplicates sentences to avoid storing the same comment twice.
- Streams the cleaned dataset directly into Google Sheets using a service account.
- Supports long-running collection via a continuous loop mode.

## Getting Started

1. **Create a virtual environment** (recommended) and install the dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Prepare Google Sheets credentials**:

   - Create a Google Cloud project and enable the *Google Sheets API* and *Google Drive API*.
   - Create a service account and download its JSON key.
   - Share the target spreadsheet with the service account email (this is required even when the script creates the sheet for you).

3. **Run the scraper**. The example below writes to a sheet named `Shopee Rojak Dataset` and stops after processing 30 popular products. The command adds the `src/` directory to `PYTHONPATH` so Python can find the package without installing it. **If you see the error `PYTHONPATH=src : The term 'PYTHONPATH=src' is not recognized`, it means PowerShell parsed the inline assignment as a command—use one of the Windows-specific variants below.**

   <details>
   <summary><strong>macOS / Linux (bash, zsh, etc.)</strong></summary>

   ```bash
   PYTHONPATH=src python -m rojak_scraper.cli \
       --credentials /path/to/service-account.json \
       --sheet-title "Shopee Rojak Dataset" \
       --max-products 30 \
       --review-pages 20 \
       --batch-size 25
   ```

   </details>

   <details>
   <summary><strong>Windows PowerShell</strong></summary>

   ```powershell
   $env:PYTHONPATH = "$(Get-Location)\src"
   python -m rojak_scraper.cli `
       --credentials C:/path/to/service-account.json `
       --sheet-title "Shopee Rojak Dataset" `
       --max-products 30 `
       --review-pages 20 `
       --batch-size 25
   ```

   PowerShell requires setting the `PYTHONPATH` variable separately. The assignment above scopes it to the current shell session. Replace the credential path with the actual location of your service account JSON file.

   </details>

   <details>
   <summary><strong>Windows Command Prompt (cmd.exe)</strong></summary>

   ```cmd
   set PYTHONPATH=%CD%\src
   python -m rojak_scraper.cli ^
       --credentials C:\path\to\service-account.json ^
       --sheet-title "Shopee Rojak Dataset" ^
       --max-products 30 ^
       --review-pages 20 ^
       --batch-size 25
   ```

   The `set` command only applies to the current window. Close and reopen the prompt or run it again to clear the variable.

   </details>

   <details>
   <summary><strong>Troubleshooting: “PYTHONPATH=src is not recognized”</strong></summary>

   This message comes from Windows shells when you copy the macOS/Linux example verbatim. Instead of placing the environment variable in front of the command, set it using either `$env:PYTHONPATH = "$(Get-Location)\src"` (PowerShell) or `set PYTHONPATH=%CD%\src` (Command Prompt) before running `python -m rojak_scraper.cli`.

   </details>

   The script logs progress to the console and appends the following columns to the worksheet:

   | Product Name | Product URL | Review ID | Rating | Comment |
   |--------------|-------------|-----------|--------|---------|

4. **Continuous collection**. If you want the scraper to keep running until you terminate it, pass the `--continuous` flag. The tool will pause (default 30 minutes) between iterations. Adjust the pause using `--loop-sleep`:

   ```bash
   PYTHONPATH=src python -m rojak_scraper.cli \
       --credentials /path/to/service-account.json \
       --continuous \
       --loop-sleep 900
   ```

## Configuration Notes

- The heuristics classify a comment as rojak when Malay words make up at least 60% of the tokens and there are at least two English words. The `langdetect` library adds an additional Malay-language confidence check.
- API calls are throttled with a configurable delay (`--delay`, default 1.5 seconds) to reduce the risk of being rate limited. Increase the delay if you encounter HTTP 429 responses.
- By default the client ignores system proxy variables, which helps when corporate proxies block Shopee. If you need the system proxy, pass `--use-system-proxy`.
- Shopee may change their API responses at any time. Handle credentials carefully and follow Shopee’s terms of service when running the scraper.

## Development

The package exposes a reusable API:

```python
from rojak_scraper import ShopeeClient, GoogleSheetsWriter, filter_rojak_sentences
```

Unit tests are not included because the scraper relies on live network calls and Google APIs. Consider adding integration tests with mocked responses if you plan to extend this project.

