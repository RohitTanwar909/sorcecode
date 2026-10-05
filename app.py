from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def normalize_url(base_url, value):
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    # Ignore non-HTTP URLs
    if value.startswith((
        "javascript:",
        "mailto:",
        "tel:",
        "data:",
        "blob:",
        "#"
    )):
        return None

    try:
        return urljoin(base_url, value)
    except Exception:
        return None


def extract_urls(page_url, html):
    soup = BeautifulSoup(html, "html.parser")

    urls = set()

    # Standard HTML URL attributes
    attributes = [
        ("a", "href"),
        ("link", "href"),
        ("script", "src"),
        ("img", "src"),
        ("video", "src"),
        ("audio", "src"),
        ("source", "src"),
        ("iframe", "src"),
        ("embed", "src"),
        ("object", "data"),
        ("form", "action"),
        ("track", "src"),
        ("input", "src"),
    ]

    for tag_name, attribute in attributes:
        for tag in soup.find_all(tag_name):
            value = tag.get(attribute)

            if value:
                url = normalize_url(page_url, value)

                if url and url.startswith(("http://", "https://")):
                    urls.add(url)

    # srcset
    for tag in soup.find_all(attrs={"srcset": True}):
        srcset = tag.get("srcset", "")

        for item in srcset.split(","):
            item = item.strip()

            if not item:
                continue

            value = item.split()[0]

            url = normalize_url(page_url, value)

            if url and url.startswith(("http://", "https://")):
                urls.add(url)

    # data-* attributes
    for tag in soup.find_all(True):
        for attribute, value in tag.attrs.items():

            if not attribute.startswith("data-"):
                continue

            if not isinstance(value, str):
                continue

            # Try complete URL values
            url = normalize_url(page_url, value)

            if url and url.startswith(("http://", "https://")):
                urls.add(url)

            # Find URLs embedded inside JSON/text
            found = re.findall(
                r'https?://[^\s"\'<>]+',
                value
            )

            for found_url in found:
                found_url = found_url.rstrip("),]}")

                if found_url.startswith(("http://", "https://")):
                    urls.add(found_url)

    # URLs directly present in HTML/JavaScript
    direct_urls = re.findall(
        r'https?://[^\s"\'<>\\]+',
        html
    )

    for url in direct_urls:
        url = url.rstrip("),];}")

        if url.startswith(("http://", "https://")):
            urls.add(url)

    return sorted(urls)


@app.route("/", methods=["GET"])
def home():

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>URL Extractor API</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 900px;
            margin: 50px auto;
            padding: 20px;
        }

        input {
            width: 75%;
            padding: 12px;
            font-size: 16px;
        }

        button {
            padding: 12px 20px;
            font-size: 16px;
            cursor: pointer;
        }

        pre {
            background: #f4f4f4;
            padding: 20px;
            overflow-x: auto;
        }
    </style>
</head>

<body>

<h1>URL Extractor</h1>

<p>
Enter a webpage URL and extract URLs found inside its HTML source.
</p>

<input
    id="url"
    type="text"
    placeholder="https://example.com/page"
>

<button onclick="extractUrls()">
    Extract
</button>

<h2>Result</h2>

<pre id="result">Waiting...</pre>

<script>

async function extractUrls() {

    const url = document.getElementById("url").value;

    if (!url) {
        alert("Enter a URL");
        return;
    }

    document.getElementById("result").textContent =
        "Extracting...";

    try {

        const response = await fetch(
            "/api/extract?url=" +
            encodeURIComponent(url)
        );

        const data = await response.json();

        document.getElementById("result").textContent =
            JSON.stringify(data, null, 2);

    } catch (error) {

        document.getElementById("result").textContent =
            "Error: " + error.message;
    }
}

</script>

</body>
</html>
""")


@app.route("/api/extract", methods=["GET"])
def api_extract():

    url = request.args.get("url", "").strip()

    if not url:
        return jsonify({
            "success": False,
            "error": "Missing url parameter"
        }), 400

    if not url.startswith(("http://", "https://")):
        return jsonify({
            "success": False,
            "error": "URL must start with http:// or https://"
        }), 400

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True
        )

        response.raise_for_status()

        html = response.text

        urls = extract_urls(
            response.url,
            html
        )

        return jsonify({
            "success": True,
            "requested_url": url,
            "final_url": response.url,
            "status_code": response.status_code,
            "content_type": response.headers.get(
                "content-type",
                ""
            ),
            "source_size": len(html),
            "count": len(urls),
            "urls": urls
        })

    except requests.exceptions.Timeout:

        return jsonify({
            "success": False,
            "error": "Request timed out"
        }), 504

    except requests.exceptions.RequestException as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 502

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok"
    })


if __name__ == "__main__":

    import os

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
