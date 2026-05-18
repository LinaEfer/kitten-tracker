# 🐱 Kitten Tracker

Monitors **Opale Sibérienne** website and Facebook page for available male kittens:
- **Siberian Neva Masquerade** — male
- **Maine Coon black smoke** — male

Sends **email** + **push notifications** (ntfy or Pushover) the moment a match is detected.

---

## Monitoring Frequency

| Source | Interval |
|---|---|
| opalesiberienne.fr | Every 30 minutes |
| Facebook profile | Every 4 hours |

---

## Setup — Two Options

### Option A: Run on your own computer (simplest)

**1. Install Python 3.11+**
Download from https://python.org

**2. Install dependencies**
```bash
cd kitten-tracker
pip install -r requirements.txt
playwright install chromium
```

**3. Configure `config.json`**

Fill in these fields:
```json
{
  "notifications": {
    "email": {
      "enabled": true,
      "sender_email": "yourgmail@gmail.com",
      "sender_password": "xxxx xxxx xxxx xxxx",   ← Gmail App Password (see below)
      "recipient_email": "your@email.com"
    },
    "ntfy": {
      "enabled": true,
      "topic": "my-kitten-alert-12345"            ← any unique name you choose
    }
  },
  "facebook_email": "your@facebook.com",          ← optional, for private pages
  "facebook_password": "yourpassword"
}
```

**4. Set up Gmail App Password**
- Go to https://myaccount.google.com/apppasswords
- Create an app password for "Mail"
- Paste the 16-character password into `sender_password`

**5. Set up push notifications (free) with ntfy**
- Install the **ntfy** app on your phone (iOS or Android)
- Choose a unique topic name (e.g. `vasilina-kitten-2024`)
- Subscribe to it in the app
- Put the same topic name in `config.json`

**6. Test your setup**
```bash
python main.py --test-notify
```
You should receive an email and a push notification.

**7. Start monitoring**
```bash
# Run once:
python main.py

# Run continuously (recommended):
python main.py --loop
```

Keep the terminal open, or run it in the background:
```bash
# Mac/Linux background:
nohup python main.py --loop &

# Windows: use Task Scheduler to run main.py on a schedule
```

---

### Option B: Run free on GitHub (no computer needed, recommended)

This runs automatically in the cloud every 30 minutes, even when your computer is off.

**1. Create a free GitHub account** at https://github.com

**2. Create a new repository**
- Click "New repository"
- Name it `kitten-tracker`
- Set it to **Private**
- Upload all the files from this folder

**3. Add secrets** (Settings → Secrets and variables → Actions → New repository secret):

| Secret name | Value |
|---|---|
| `EMAIL_SENDER` | your Gmail address |
| `EMAIL_PASSWORD` | your Gmail App Password |
| `EMAIL_RECIPIENT` | email where you want alerts |
| `NTFY_TOPIC` | your ntfy topic name (optional) |
| `FACEBOOK_EMAIL` | Facebook login (optional) |
| `FACEBOOK_PASSWORD` | Facebook password (optional) |

**4. Enable Actions**
Go to the "Actions" tab in your repository and click "Enable workflows"

**5. Test it manually**
Go to Actions → "Kitten Tracker" → "Run workflow"

That's it! GitHub will now run the tracker every 30 minutes automatically. Free forever.

---

## How it works

1. **Scraper** fetches both pages (plain HTTP for the website, headless browser for Facebook)
2. **Detector** compares new content to the last saved snapshot
3. If new content contains keyword matches (breed + sex/availability), **Notifier** fires
4. You get an email with the matching text and a direct link to the page

### Keywords monitored
- Breeds: `neva masquerade`, `sibérien`, `maine coon`
- Colors: `black smoke`, `fumée noire`
- Sex: `mâle`, `male`
- Availability: `disponible`, `available`, `à vendre`, `chaton`, `portée`, `naissance`

---

## Troubleshooting

**No email received after test?**
- Make sure you used an App Password, not your real Gmail password
- Check your spam folder
- Gmail 2FA must be enabled before App Passwords work

**Facebook page not loading?**
- Facebook blocks bots aggressively. If it fails consistently, the scraper will log an error and retry next cycle.
- Adding your Facebook login credentials in config.json improves reliability.

**Checking logs**
```bash
cat tracker.log
```

---

## File structure

```
kitten-tracker/
├── main.py          # Orchestrator — run this
├── scraper.py       # Fetches pages (requests + Playwright)
├── detector.py      # Compares snapshots, finds keyword matches
├── notifier.py      # Sends email, ntfy, Pushover alerts
├── config.json      # Your settings (fill this in)
├── requirements.txt # Python dependencies
├── snapshots/       # Auto-created — stores page snapshots
├── tracker.log      # Auto-created — run log
└── .github/
    └── workflows/
        └── monitor.yml  # GitHub Actions schedule
```
