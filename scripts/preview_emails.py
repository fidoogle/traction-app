"""Look at every email the app can send, using made-up data.

  python -m scripts.preview_emails              writes email-preview/ (one .html and one .txt
                                                per email, plus an index.html to click through)
  python -m scripts.preview_emails --send me@district.org
                                                also sends them all through the configured mail
                                                server, to see how Outlook, Gmail or your phone
                                                shows them (needs SMTP_HOST etc. to be set)

Nothing here touches the database.
"""

import argparse
import html
from pathlib import Path

from app.core.email import render_email, send_email
from app.core.email_samples import SAMPLES, context_for


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="email-preview", help="folder to write to (default: email-preview)")
    parser.add_argument("--send", metavar="ADDRESS", help="also email every sample to this address")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    links = []
    for name in sorted(SAMPLES):
        text, page = render_email(name, **context_for(name))
        (out / f"{name}.html").write_text(page, encoding="utf-8")
        (out / f"{name}.txt").write_text(text, encoding="utf-8")
        links.append(f'<li><a href="{name}.html">{html.escape(name)}</a> (<a href="{name}.txt">plain text</a>)</li>')
        if args.send:
            result = send_email(args.send, f"[Preview] {name}", text, page)
            print(f"{name}: {'sent' if result.ok else 'NOT sent - ' + result.error}")
    (out / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Email previews</title><h1>Email previews</h1><ul>"
        + "".join(links)
        + "</ul>",
        encoding="utf-8",
    )
    print(f"Wrote {len(SAMPLES)} emails to {out.resolve()}")


if __name__ == "__main__":
    main()
