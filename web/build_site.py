"""Assemble the website.

    python web/build_site.py

Writes:
  docs/index.html         full website with live weather and CSV download. Enable GitHub Pages on the /docs folder.
  web/dist/index.html     same file
  web/dist/fragment.html  preview build for the Claude artifact viewer (no network features)
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(p):
    with open(os.path.join(HERE, p), encoding="utf-8") as f:
        return f.read()


def main():
    t = read("template.html")
    data = read("data/synthetic_city.json").strip()
    # str.replace with a function-free literal avoids backslash handling in the data/JS
    page = (t.replace("/*CSS*/", read("style.css"))
             .replace("/*DATA*/", data)
             .replace("/*ENGINE*/", read("engine.js"))
             .replace("/*APP*/", read("app.js")))
    assert "/*CSS*/" not in page and "/*APP*/" not in page
    assert "</script" not in data  # data must not be able to close the script tag

    # Two builds from one template:
    #   standalone: live weather + Download CSV (needs a normal website host, e.g. GitHub Pages)
    #   preview:    for the Claude artifact viewer, which blocks network requests and downloads
    def strip(text, tag):
        return re.sub(r"<!--%s-->.*?<!--/%s-->" % (tag, tag), "", text, flags=re.S)

    def unwrap(text, tag):
        return text.replace("<!--%s-->" % tag, "").replace("<!--/%s-->" % tag, "")

    standalone = unwrap(strip(page, "PREVIEW"), "STANDALONE")
    preview = unwrap(strip(page, "STANDALONE"), "PREVIEW")
    for name in ("<!--STANDALONE", "<!--PREVIEW", "<!--/"):
        assert name not in standalone and name not in preview

    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    with open(os.path.join(HERE, "dist", "fragment.html"), "w", encoding="utf-8") as f:
        f.write(preview)

    title = re.search(r"<title>(.*?)</title>", standalone).group(1)
    head_end = standalone.index("</style>") + len("</style>")
    doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           + standalone[:head_end] + "\n</head>\n<body>\n" + standalone[head_end:] + "\n</body>\n</html>\n")
    for out in (os.path.join(HERE, "dist", "index.html"), os.path.join(ROOT, "docs", "index.html")):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(doc)
    open(os.path.join(ROOT, "docs", ".nojekyll"), "w").close()
    print(f"built '{title}': preview {len(preview) // 1024} KB, standalone {len(doc) // 1024} KB -> web/dist/ and docs/index.html")


if __name__ == "__main__":
    main()
