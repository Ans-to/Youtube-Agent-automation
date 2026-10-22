# Installing Agent HQ as an app

Agent HQ runs as a local server with a browser front end. "Installing" it means
the browser puts the front end in its own window, with its own icon, its own
Start-menu or home-screen entry, and no address bar. That is a real installed
app on both platforms.

Underneath it is still your own Python process on your own machine, which is the
point: nothing is uploaded, and no account is involved.

---

## Windows

### 1. Start it

In the project folder, double-click **`START_HERE.bat`** the first time. It
installs Python and the optional pieces it can, then opens the app.

After the first time, double-click **`start_windows.bat`**. The browser opens by
itself at `http://127.0.0.1:8765`.

Keep that black window open. It *is* the server. Closing it stops the app.

### 2. Install it

With the app open in **Edge** or **Chrome**:

- **Edge:** click the `App available` / install icon at the right of the address
  bar, or menu → **Apps** → **Install this site as an app**.
- **Chrome:** click the install icon at the right of the address bar, or menu →
  **Cast, save and share** → **Install page as app**.

Tick "Pin to taskbar" or "Create desktop shortcut" if offered. You now have an
Agent HQ window that opens without a browser frame, and an entry in the Start
menu.

### 3. If something goes wrong

| What you see | What it means |
| --- | --- |
| `Port 8765 is already in use` | A previous window is still running. Use it, or start with `python dashboard.py --port 8766`. |
| Blank page, spinning forever | The server window was closed. Start it again. |
| No install icon in the address bar | You are not on `127.0.0.1` or `localhost`. Install prompts only appear for a secure origin; loopback counts, a LAN IP does not. |
| `Python 3.10 or newer was not found` | Run `START_HERE.bat`, or install Python from python.org and tick "Add to PATH". |

---

## Android

Android runs the same Python code inside Termux, which is a real Linux
environment. The app is installed to the home screen from the phone's browser.

### 1. Install the prerequisites

Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/) or
the official Termux GitHub releases. The Play Store build is outdated; avoid it.

Open Termux and paste these lines one at a time:

```
pkg update
pkg install python git
```

### 2. Get the project and start it

```
git clone https://github.com/Ans-to/Youtube-Agent-automation.git
cd Youtube-Agent-automation
cp config.example.json config.json
python dashboard.py
```

Run `ls` first if you already have a `config.json`; skip the copy so you do not
overwrite your settings.

### 3. Install it to the home screen

1. Open **Chrome** on the phone.
2. Go to `http://127.0.0.1:8765`.
3. Menu (three dots) → **Add to Home screen** → **Install**.

You get an Agent HQ icon on the home screen that opens full screen, without
browser chrome.

Android will keep the server alive only while Termux is running. To start it
again later, open Termux, `cd Youtube-Agent-automation`, and run
`python dashboard.py`.

### 4. What a phone should and should not be asked to do

The dashboard, the task queue, documents, web pages, small CLI tools, data
reports and test repair all work. Long video renders do not: a phone will hit
memory, heat and background-process limits. On a phone, Agent HQ also picks its
smallest resource tier automatically and says so when a run starts.

---

## Why the icons are generated, not drawn

`tools/make_icons.py` draws `web/icons/*.png` from the same geometry as
`web/icon.svg`, using only the standard library. A browser will not offer to
install an app whose manifest advertises bitmaps it cannot fetch, so these files
are part of the install, not decoration.

Regenerate them, or verify the committed ones:

```
python tools/make_icons.py
python tools/make_icons.py --check
```

---

## Honest limits of this install path

- **It is a web app in its own window, not a native `.exe` or `.apk`.** That is
  what keeps it free, offline and identical on both platforms. A packaged
  installer would add hundreds of megabytes and a build service.
- **The server must be running.** Tapping the installed icon while the Python
  process is stopped shows the offline page, not the app.
- **No sync between phone and PC.** Each install has its own queue and workspace.
  They do not talk to each other, by design.
- **No LAN or internet access.** The server binds to loopback only, so the app
  cannot be reached from another device, including your own phone viewing your
  PC.
- **Auto-start on login is not set up.** Windows can start anything at login from
  the Startup folder; that is a manual step and is not done for you.

---

## Check it yourself

```
python -m unittest tests.test_dashboard_pwa tests.test_app_icons -v
```

That covers the manifest, the icon sizes, the content types the server returns,
the service worker precache, the launch behaviour, and whether the committed
icons match the generator.
