# Buzz Android Notify (AE Buzz)

Get your laptop's [Buzz](https://buzz.xyz) notifications on your Android phone.

Buzz doesn't have Android push notifications yet. AE Buzz fills the gap: a small Windows tray app
watches the notifications Buzz desktop shows, and forwards them to an Android app through
your own Firebase project.

> Unofficial. Not affiliated with or endorsed by Block, Inc. or the Buzz project.

<p align="center"><img src="assets/app-icon.png" width="128" alt="AE Buzz icon"></p>

## How it works

```
Windows laptop                         Your relay server           Firebase Cloud     Android phone
Buzz desktop shows a notification  ─►  (runs on your laptop   ─►  Messaging      ─►  AE Buzz app shows it
AE Buzz tray app reads it              or a VPS)                   (your project)     (tap opens Buzz)
```

- **Tray app** (`desktop/`, Python): polls Windows' notification list for Buzz toasts and sends
  each one's title and message to the relay.
- **Relay server** (`server/`, FastAPI + SQLite): pairs a laptop with a phone and sends the
  notification through Firebase Cloud Messaging.
- **Android app** (`mobile/`, Flutter): pairs by scanning a QR code from the tray app, then
  receives notifications even when it's closed. It plays Buzz's "unison" sound, expands to show
  the full message, and opens the Buzz app when you tap it.

Everyone uses **their own Firebase project**. The prebuilt APK has no Firebase project baked in:
the pairing QR code carries your project's public settings, so the same APK works for anyone.

## Privacy

Notification titles and message text (up to 1,000 characters) pass through **your** relay
server and **your** Firebase project. The relay keeps only pairing records (secrets stored as
hashes) and doesn't store messages. Nothing goes to the authors of this repo.

## Get started

Follow **[SETUP.md](SETUP.md)**: about 20–30 minutes the first time. You'll need:

- Windows 10/11 with the Buzz desktop app
- An Android phone (Android 8+)
- A free Google account for Firebase
- Python 3.12 (for the relay server)

Downloads are on the [Releases](../../releases) page: `AE-Buzz.apk` for the phone and
`AE-Buzz.exe` for the laptop.

## Limitations

- Notifications are only forwarded while the laptop is on and both Buzz and AE Buzz are running.
- Buzz doesn't show notifications while its window is focused, so nothing is forwarded then
  either (you're at your laptop anyway).
- Windows and Android only.
- Pairing needs the relay to be reachable from your phone briefly (SETUP.md uses a free
  Cloudflare quick tunnel).

## Building from source

- Server: `cd server && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`,
  tests with `.venv\Scripts\python -m pytest`.
- Tray app: `cd desktop && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`,
  run with `.venv\Scripts\python -m aebuzz_desktop`.
- Android app: Flutter 3.44+, `cd mobile && flutter build apk --release`. Without a signing key
  (see `mobile/android/app/build.gradle.kts`) release builds use the debug key.

## License

[Apache-2.0](LICENSE). The bundled "unison" sound is from Buzz, also Apache-2.0; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
