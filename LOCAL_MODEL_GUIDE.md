# Local model setup for Offline Agent HQ

This project does not require a paid AI API. The model server is optional and must run on the same device as the Python process. The default configuration keeps model generation disabled.

## Recommended starting point for the Windows 10 PC

For an 8 GB RAM computer with unknown GPU, start with a small 3B–4B instruct model in a 4-bit quantization (Q4). Use a short context window, initially 2,048–4,096 tokens. A 7B model may be too slow or run out of memory depending on GPU, quantization, and other programs. Keep at least several GB of free disk space for model weights and browser/FFmpeg output.

Use a local inference server that exposes an OpenAI-compatible chat-completions endpoint, such as a compatible LM Studio local server or llama.cpp server. Example endpoint formats:
- LM Studio default commonly uses http://127.0.0.1:1234/v1/chat/completions
- llama.cpp can be configured to use http://127.0.0.1:8080/v1/chat/completions

The actual port and model identifier depend on your local server configuration. No API key is required by this project, and the code rejects non-loopback model URLs.

## Enable it

1. Install and download a small quantized instruct model using your chosen local inference application.
2. Start its local server and confirm the chat-completions endpoint is active.
3. Copy config.example.json to config.json if config.json does not exist.
4. Set model.enabled to true, base_url to the exact loopback endpoint, and model to the identifier expected by the server.
5. Run a small draft task first and check RAM usage and response time.

Example model section for a local server on port 1234:

    {
      "enabled": true,
      "base_url": "http://127.0.0.1:1234/v1/chat/completions",
      "model": "local-model",
      "max_output_tokens": 900,
      "timeout_seconds": 240
    }

Replace local-model with the actual model identifier required by your server. Keep config.json out of Git; it is ignored by .gitignore.

## Important limits

- A local model can generate text but does not automatically browse the web, verify current facts, or access your other apps.
- Video production and product generation are drafts until a human reviews the files.
- Android/Termux is suitable for the lightweight task queue and dashboard, but the Puppeteer/FFmpeg video renderer should be run on the PC.
- A model running on the PC does not automatically become available to the phone. To keep the setup private and simple, run the relevant Python workflow on the same device as the local model server.
