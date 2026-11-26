# Setting up AE Buzz

AE Buzz puts every Buzz message on your Android phone, with sound: channel messages, DMs, thread
replies and @mentions. Setup takes about 15 minutes and Claude does most of it.

## Quick start

On your **Windows laptop**, open Claude Code and paste:

> Set up AE Buzz for me by following https://github.com/Rohan3280/buzz-android-notify/blob/main/SETUP.md

Claude will ask before installing anything. You'll only need to sign in to Google in your browser,
click one button in Firebase, and install the app on your phone.

You need:

- Windows 10 or 11, with the **Buzz desktop app** installed and signed in
- An Android phone (Android 8 or newer)
- A Google account for Firebase (free). If you work at Authority Entrepreneurs, use your
  **@authorityentrepreneurs.com** Google account. Any Google account works.

---

## Instructions for Claude

You are setting up AE Buzz for the person you're talking to. Work through the steps below in order,
on their Windows laptop, and tell them briefly what each step does.

**Rules**

- **Download the released apps. Never build anything from source**, and don't clone the repo.
- **Ask before installing software** (Node.js, the Firebase CLI, cloudflared), naming what you'll
  install and why.
- **The person signs in to Google themselves**, in their browser. Never ask for, see or type a
  password or a verification code.
- **Google account for Firebase:** ask which account to use. Recommend their work account ending in
  `@authorityentrepreneurs.com`, and use it unless they prefer another; any Google account works.
- **Keep AE Buzz's files in `%USERPROFILE%\.aebuzz\`.** `firebase-key.json` is a secret: never
  print its contents, commit it, upload it or send it anywhere.
- Use PowerShell. If a step fails, explain what happened in plain words and use the
  troubleshooting table at the end before improvising.

### Step 1: Check the laptop

1. Check that the Buzz desktop app is signed in on this laptop. AE Buzz uses the sign-in key Buzz
   saved in Windows Credential Manager:

   ```powershell
   cmdkey /list | Select-String -Pattern "buzz-desktop|buzz\.desktop"
   ```

   If nothing is listed, ask the person to install Buzz desktop and sign in, then run it again.
   Buzz doesn't need to stay open afterwards.

2. If `%APPDATA%\AE Buzz\config.json` already exists, AE Buzz was set up before on this laptop.
   Read it and ask whether to keep the existing pairing (then only do Steps 2, 5 and 8) or start
   fresh.

### Step 2: Download AE Buzz for Windows

```powershell
$dir = "$env:USERPROFILE\.aebuzz"
New-Item -ItemType Directory -Force $dir | Out-Null
Invoke-WebRequest "https://github.com/Rohan3280/buzz-android-notify/releases/latest/download/AE-Buzz.exe" -OutFile "$dir\AE Buzz.exe"
Unblock-File "$dir\AE Buzz.exe"
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AE Buzz.lnk")
$lnk.TargetPath = "$dir\AE Buzz.exe"; $lnk.WorkingDirectory = $dir; $lnk.Save()
```

If AE Buzz is already running (a cherry-blossom icon in the tray), ask the person to **Quit** it
from the tray menu first, so the file can be replaced.

### Step 3: Create their Firebase project

Firebase delivers the notifications to their phone. Each person uses their own free project.

1. Make sure the Firebase CLI is available (`firebase --version`). If not, ask to install it:
   Node.js LTS (`winget install --id OpenJS.NodeJS.LTS -e`), then open a new PowerShell and run
   `npm install -g firebase-tools`.
2. Sign in: run `firebase login`. The person completes the sign-in in their browser with the
   Google account they chose. If the CLI is already signed in to a different account, use
   `firebase login:add` and pass `--account <their email>` to every `firebase` command below.
3. Create the project with a unique ID of the form `aebuzz-<first name>-<4 random digits>`,
   lowercase (e.g. `aebuzz-priya-4821`):

   ```powershell
   firebase projects:create <project-id> --display-name "AE Buzz"
   ```

   - If it says the Terms of Service haven't been accepted, ask the person to open
     <https://console.firebase.google.com> once with that account and accept them, then retry.
   - If the account has run out of projects, ask whether to use an existing Firebase project
     they own instead.

4. Register the Android app (the package name must be exactly this):

   ```powershell
   firebase apps:create android "AE Buzz" --package-name com.igrisstudios.aebuzz --project <project-id>
   ```

   Note the App ID it prints (`1:…:android:…`).

5. Save the app's settings:

   ```powershell
   firebase apps:sdkconfig android <app-id> --project <project-id> --out "$env:USERPROFILE\.aebuzz\google-services.json"
   ```

6. Get the sending key. This one needs a click in the browser. Ask the person to open
   `https://console.firebase.google.com/project/<project-id>/settings/serviceaccounts/adminsdk`
   (fill in the project ID), click **Generate new private key**, then **Generate key**. A file named
   `<project-id>-firebase-adminsdk-….json` downloads to their Downloads folder. Move it without
   opening it:

   ```powershell
   $key = Get-ChildItem "$env:USERPROFILE\Downloads\<project-id>-firebase-adminsdk-*.json" | Sort-Object LastWriteTime | Select-Object -Last 1
   Move-Item $key.FullName "$env:USERPROFILE\.aebuzz\firebase-key.json" -Force
   (Get-Content "$env:USERPROFILE\.aebuzz\firebase-key.json" -Raw | ConvertFrom-Json).type   # should print: service_account
   ```

### Step 4: Point AE Buzz at their Firebase files

```powershell
$cfg = "$env:APPDATA\AE Buzz\config.json"
New-Item -ItemType Directory -Force (Split-Path $cfg) | Out-Null
@{
  firebase_key_path        = "$env:USERPROFILE\.aebuzz\firebase-key.json"
  firebase_app_config_path = "$env:USERPROFILE\.aebuzz\google-services.json"
} | ConvertTo-Json | Out-File -Encoding utf8 $cfg
```

(If you're keeping an existing `config.json` from Step 1, update just these two fields and remove
`local_server_dir` if present.)

### Step 5: Install cloudflared (used only while pairing)

Pairing needs the phone to reach the laptop once. AE Buzz opens a temporary Cloudflare link for
that by itself, using cloudflared. If `cloudflared --version` fails, ask to install it:

```powershell
winget install --id Cloudflare.cloudflared -e
```

### Step 6: Install the app on their phone

Ask the person to do this on their **phone**:

1. Open this link in the phone's browser and download the app:
   **<https://github.com/Rohan3280/buzz-android-notify/releases/latest/download/AE-Buzz.apk>**
2. Open the downloaded file and install it. Android asks to allow installing apps from the browser
   or Files app; allow it.
3. Open **AE Buzz** and allow notifications.
4. Tap **Make alerts instant** and set the battery setting to **Unrestricted**. Without this,
   Android may hold notifications back while the phone is idle.

(If the phone is connected by USB with USB debugging on and `adb` is available, you can instead
download the APK on the laptop and run `adb install -r AE-Buzz.apk`.)

### Step 7: Start AE Buzz and pair the phone

1. Start it: `Start-Process "$env:USERPROFILE\.aebuzz\AE Buzz.exe"`. Windows may show
   "Windows protected your PC" the first time; the person clicks **More info → Run anyway**.
2. A cherry-blossom icon appears in the tray (click the **^** next to the clock). Ask the person to
   right-click it and choose **Pair phone…**. A QR code appears after a few seconds.
3. On the phone, in AE Buzz, tap **Scan pairing code** and scan it. The laptop window changes to
   **Paired ✓**.

### Step 8: Check that it works

1. Read the log: `Get-Content "$env:APPDATA\AE Buzz\tray.log" -Tail 20`. Expect
   `reading Buzz messages from wss://…`, `following N channels` and `relay server started`.
2. When the next Buzz message arrives (any channel or DM), the log shows
   `…/notify "HTTP/1.1 202 Accepted"` and the phone rings. Ask the person to confirm.
3. Tell them: to stop a busy channel (for example #Attendance) from reaching their phone, **mute
   it in Buzz**. AE Buzz skips muted channels, except messages that @mention them.

### Step 9: Wrap up

Tell the person:

- Each day, open **AE Buzz** from the Start menu; it runs in the tray. **Quit** in the tray menu
  stops it. Their laptop must be on and AE Buzz running for messages to reach the phone.
- Buzz desktop doesn't need to be open.
- Their Firebase key is in `%USERPROFILE%\.aebuzz\firebase-key.json`. They shouldn't share it.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Tray says "No Buzz key — sign in to Buzz" | Sign in to the Buzz desktop app on this laptop, then restart AE Buzz. |
| Tray says "Buzz address not found" | Open Buzz desktop once and sign in, or add `"buzz_relay_url": "wss://<your Buzz server>"` to `%APPDATA%\AE Buzz\config.json`, then restart AE Buzz. |
| Tray says "Can't reach Buzz, retrying" | The laptop is offline or the Buzz server is down. AE Buzz reconnects by itself and catches up. |
| Tray says "Relay server exited" | See `%APPDATA%\AE Buzz\server.log`. Usually a wrong path to `firebase-key.json` or `google-services.json` in `config.json`. |
| Pairing window warns it couldn't open a link | Install cloudflared (Step 5), close the window and choose **Pair phone…** again. |
| Phone says the server didn't send Firebase settings | `firebase_app_config_path` in `config.json` is missing or wrong. Fix it, restart AE Buzz, pair again. |
| "google-services.json has no Android app with package…" | Redo Step 3.4 and 3.5 in the same project. |
| Nothing arrives on the phone | Check the phone's battery setting for AE Buzz is **Unrestricted** and the channel isn't muted in Buzz. Logs: `%APPDATA%\AE Buzz\tray.log`. |
| Pairing code expired | Codes last 10 minutes; choose **Pair phone…** again. |
