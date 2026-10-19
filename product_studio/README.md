# Offline digital product studio

This is a local-first starter for creating a single-file HTML utility prototype and a ZIP package. It uses the configured local model endpoint only when enabled; otherwise it creates a deterministic offline text utility template. It does not deploy, sell, or publish products.

From the repository root:

    python product_studio/build_product.py --title "Invoice Helper" --idea "A simple local tool to organize invoice notes"

Output is written under workspace/products/ and includes index.html, README.md, product-status.json, and a ZIP archive. The CEO pipeline supplies specialist research notes using `--source-file workspace/orchestration/<run>/source-notes.md`; these notes are included in the model prompt and copied into `research-notes.md` inside the product package. They remain unverified until a human reviews the source URLs and claims.

The generator applies a restrictive Content Security Policy and rejects HTML when its heuristic scan detects remote URLs/scripts, network APIs, embedded frames, form submission targets, or dynamic code patterns. This is defense-in-depth, not a true browser sandbox or security audit; obfuscated behavior may evade static scanning. Review and test generated HTML in an isolated browser profile before using real data or selling it. A deterministic fallback template is not a finished product; adapt its workflow to the chosen product idea.
