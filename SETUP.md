# Setting up AE Buzz

About 20–30 minutes the first time. After that you just open **AE Buzz** from the Start menu.

Using Claude Code or another coding agent? You can ask it to "follow SETUP.md in this repo";
it can do every step except the ones in the Firebase console, which need your Google sign-in.

Throughout, keep your Firebase files in a private folder outside the repo, for example
`C:\Users\<you>\.aebuzz\`. **Never commit or share the service-account key.**

## 1. Create your Firebase project (once)

1. Go to <https://console.firebase.google.com> and **Create a project** (any name, e.g. "AE Buzz").
   Google Analytics isn't needed. The free Spark plan is enough; sending notifications is free.
2. In the project, click **Add app → Android** and enter the package name exactly:
   `com.igrisstudios.aebuzz`. Skip the SDK steps.
3. Download **google-services.json** and save it to `C:\Users\<you>\.aebuzz\google-services.json`.
4. Open **Project settings → Service accounts → Generate new private key → Generate key**, and save
   the file as `C:\Users\<you>\.aebuzz\firebase-key.json`. This one is a secret.

## 2. Install the Android app

1. On your phone, download `AE-Buzz.apk` from this repo's [Releases](../../releases) page.
2. Open it and allow your browser or file manager to install unknown apps when asked.
3. Open **AE Buzz** once and allow notifications.

## 3. Set up the laptop

1. Install **Python 3.12** from <https://www.python.org/downloads/> (tick "Add python.exe to PATH").
2. Download this repo (green **Code → Download ZIP**, or `git clone`) to a folder such as
   `C:\Users\<you>\buzz-android-notify`.
3. Install the relay server. In PowerShell:

   ```powershell
   cd C:\Users\<you>\buzz-android-notify\server
   py -3.12 -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```

4. Tell AE Buzz where everything is. Adjust the paths, then run:

   ```powershell
   $cfg = "$env:APPDATA\AE Buzz\config.json"
   New-Item -ItemType Directory -Force (Split-Path $cfg) | Out-Null
   @{
     server_url               = "http://127.0.0.1:8000"
     local_server_dir         = "C:\Users\<you>\buzz-android-notify\server"
     firebase_key_path        = "C:\Users\<you>\.aebuzz\firebase-key.json"
     firebase_app_config_path = "C:\Users\<you>\.aebuzz\google-services.json"
   } | ConvertTo-Json | Set-Content -Encoding utf8 $cfg
   ```

5. Download `AE-Buzz.exe` from [Releases](../../releases) and put it somewhere permanent, e.g.
   `C:\Users\<you>\.aebuzz\AE Buzz.exe`. Right-click it and choose **Pin to Start** (optional).
6. Make sure Windows lets apps read notifications: **Settings → Privacy & security →
   Notifications → Let apps access your notifications** must be **On**.

## 4. Pair your phone (once)

Your phone has to reach the relay server once, while pairing. A free Cloudflare quick tunnel
does that without opening any ports.

1. Install cloudflared: `winget install --id Cloudflare.cloudflared`
2. In one PowerShell window, start the tunnel and copy the `https://….trycloudflare.com` address it
   prints:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

3. In a second PowerShell window, start the server with that address (adjust the paths):

   ```powershell
   cd C:\Users\<you>\buzz-android-notify\server
   $env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\<you>\.aebuzz\firebase-key.json"
   $env:AEBUZZ_FIREBASE_APP_CONFIG     = "C:\Users\<you>\.aebuzz\google-services.json"
   $env:AEBUZZ_PUBLIC_URL              = "https://<the-address>.trycloudflare.com"
   $env:AEBUZZ_DB                      = "aebuzz.db"
   .\.venv\Scripts\python -m aebuzz_server
   ```

4. Open **AE Buzz.exe**. A cherry-blossom icon appears in the tray (click the **^** arrow next
   to the clock). Right-click it and choose **Pair phone…**.
5. On the phone, open AE Buzz, tap **Scan pairing code**, and scan the QR code. The laptop window
   changes to **Paired ✓**.
6. On the phone, tap **Make alerts instant** and set Battery to **Unrestricted**.
7. Close both PowerShell windows (Ctrl+C), then in the tray choose **Quit**.

## 5. Daily use

Open **AE Buzz** (the `.exe`). It starts the relay server by itself, and **Quit** in the tray
menu stops both. Keep Buzz running; when its window isn't focused, its notifications show up on
your phone within a few seconds.

You only need the tunnel again if you pair a new phone or re-pair.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Tray says "Relay server not found" | Check `local_server_dir` in `%APPDATA%\AE Buzz\config.json` points to the `server` folder that contains `.venv`. |
| Tray says "Relay server exited" | Look at `%APPDATA%\AE Buzz\server.log`. Usually a wrong path to `firebase-key.json` or `google-services.json`. |
| Phone says the server didn't send Firebase settings | The server was started without `AEBUZZ_FIREBASE_APP_CONFIG`. Restart it as in step 4.3 and show a new code. |
| "google-services.json has no Android app with package…" | In Firebase, add the Android app with package `com.igrisstudios.aebuzz` and download the file again. |
| Nothing arrives on the phone | Buzz doesn't notify while its window is focused; minimise it. Check the phone's battery setting for AE Buzz is Unrestricted. Logs: `%APPDATA%\AE Buzz\tray.log`. |
| Pairing code expired | Codes last 10 minutes; choose **Pair phone…** again. |
