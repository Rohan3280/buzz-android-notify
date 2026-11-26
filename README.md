# Buzz Android Notify (AE Buzz)

Get your laptop's [Buzz](https://buzz.xyz) notifications on your Android phone.

Buzz doesn't have Android push notifications yet. AE Buzz fills the gap: a small Windows tray app
signs in to your Buzz server as you, reads every new message in your channels and DMs, and
forwards it to an Android app through your own Firebase project. Channels you mute in Buzz are
skipped, except messages that @mention you.

> Unofficial. Not affiliated with or endorsed by Block, Inc. or the Buzz project.

<p align="center"><img src="assets/app-icon.png" width="128" alt="AE Buzz icon"></p>

## How it works

```
Buzz server         Windows laptop: AE Buzz.exe              Firebase Cloud     Android phone
new message    ─►   tray app (signed in as you)         ─►   Messaging      ─►  AE Buzz app shows it
                    + built-in relay server                  (your project)     (tap opens Buzz)
```

- **Tray app** (`desktop/`, Python): signs in to your Buzz server with the key the Buzz desktop
  app saved in Windows Credential Manager, follows every channel and DM you're in (including new
  ones), and sends each new message's sender, channel and text to the relay.
- **Relay server** (`server/`, FastAPI + SQLite): pairs a laptop with a phone and sends the
  notification through Firebase Cloud Messaging. `AE-Buzz.exe` includes it and starts it by
  itself; it can also run separately (e.g. on a VPS).
- **Android app** (`mobile/`, Flutter): pairs by scanning a QR code from the tray app, then
  receives notifications even when it's closed. It plays Buzz's "unison" sound, expands to show
  the full message, and opens the Buzz app when you tap it.

Everyone uses **their own Firebase project**. The prebuilt APK has no Firebase project baked in:
the pairing QR code carries your project's public settings, so the same APK works for anyone.

## Privacy

Notification titles and message text (up to 1,000 characters) pass through **your** relay
server and **your** Firebase project. The relay keeps only pairing records (secrets stored as
hashes) and doesn't store messages. Nothing goes to the authors of this repo.

The tray app uses your Buzz sign-in key only to sign in to your own Buzz server and to read your
mute list. The key stays in Windows Credential Manager on your laptop; AE Buzz never copies,
logs or sends it anywhere.

## Get started

Paste this into Claude Code on your Windows laptop and it sets everything up with you
(about 15 minutes):

> Set up AE Buzz for me by following https://github.com/Rohan3280/buzz-android-notify/blob/main/SETUP.md

Or follow **[SETUP.md](SETUP.md)** yourself. You'll need:

- Windows 10/11 with the Buzz desktop app, signed in (it doesn't need to stay open)
- An Android phone (Android 8+)
- A free Google account for Firebase

Downloads are on the [Releases](../../releases) page: `AE-Buzz.apk` for the phone and
`AE-Buzz.exe` for the laptop. Nothing needs to be built.

## Limitations

- Messages are only forwarded while the laptop is on and AE Buzz is running.
- Buzz reminders aren't forwarded: they live only inside the Buzz desktop app, not on the server.
- Windows and Android only.
- Pairing needs the phone to reach the laptop once: **Pair phone…** opens a temporary, free
  Cloudflare quick tunnel for that (needs cloudflared) and closes it afterwards.

## Building from source

- Server: `cd server && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`,
  tests with `.venv\Scripts\python -m pytest`.
- Tray app: `cd desktop && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
  (this includes the server's requirements), tests with `.venv\Scripts\python -m pytest`, run with
  `.venv\Scripts\python -m aebuzz_desktop`. From source, the tray starts a separately installed
  server when `local_server_dir` is set in `config.json`.
- `AE-Buzz.exe` (tray app + relay server), from `desktop/`:

  ```
  .venv\Scripts\python -m PyInstaller --onefile --windowed --name "AE Buzz" --icon aebuzz_desktop\icon.ico ^
    --add-data "aebuzz_desktop\icon.png;aebuzz_desktop" --paths ..\server --hidden-import aebuzz_server.__main__ ^
    --collect-submodules aebuzz_server --collect-submodules uvicorn --collect-all coincurve run_aebuzz.py
  ```
- Android app: Flutter 3.44+, `cd mobile && flutter build apk --release`. Without a signing key
  (see `mobile/android/app/build.gradle.kts`) release builds use the debug key.

## License

[Apache-2.0](LICENSE). The bundled "unison" sound is from Buzz, also Apache-2.0; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
