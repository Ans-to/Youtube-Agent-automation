# Offline digital product studio

This is a local-first starter for creating a single-file HTML utility prototype and a ZIP package. It uses the configured local model endpoint only when enabled; otherwise it creates a deterministic offline text utility template. It does not deploy, sell, or publish products.

From the repository root:

    python product_studio/build_product.py --title "Invoice Helper" --idea "A simple local tool to organize invoice notes"

Output is written under workspace/products/ and includes index.html, README.md, product-status.json, and a ZIP archive.

The generator performs a basic static scan for remote scripts/resources, network requests, and dynamic code execution patterns. This is a warning mechanism, not a security audit. Review and test generated HTML before using real data or selling it. A deterministic fallback template is not a finished product; adapt its workflow to the chosen product idea.
