# 🤖 Nifty Iron Condor Signal Bot — 100% Free

Live option chain data from NSE India → Iron Condor signals → Telegram  
Hosted FREE on GitHub Actions. No server. No cost. No Zerodha API needed.

---

## 🏗 Architecture

```
NSE India API (free)
      ↓
  GitHub Actions (free cloud runner)
  runs at 9:25 AM IST every weekday
      ↓
  Iron Condor Signal Engine
  (VIX filter + OI analysis + scoring)
      ↓
  Telegram Bot (free)
      ↓
  Your phone 📱
```

---

## 🚀 Complete Setup — Step by Step

### STEP 1: Create a Telegram Bot (5 min)

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Give it a name e.g. `NiftySignalBot`
4. BotFather gives you a token like: `7123456789:AAFxxxxxxxxxxxxxxxxxx`
5. **Copy this token**

**Get your Chat ID:**
1. Search **@userinfobot** on Telegram
2. Send `/start`
3. It replies with your Chat ID e.g. `987654321`
4. **Copy this number**

---

### STEP 2: Fork this repo on GitHub

1. Go to [github.com](https://github.com) → Sign up free if needed
2. Create a **New Repository** → name it `nifty-signal-bot`
3. Upload all files from this folder into the repo

File structure should be:
```
nifty-signal-bot/
├── .github/
│   └── workflows/
│       └── nifty_bot.yml
├── src/
│   ├── main.py
│   ├── nse_data.py
│   ├── strategy.py
│   └── telegram_bot.py
├── requirements.txt
└── README.md
```

---

### STEP 3: Add Secrets to GitHub

This is how your bot token is stored safely (never hardcoded in code).

1. Go to your GitHub repo
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these two secrets:

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID number |

---

### STEP 4: Enable GitHub Actions

1. In your repo, click the **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"**
3. Done! The bot will now run automatically.

---

### STEP 5: Test it manually

1. Go to **Actions** tab in your repo
2. Click **"Nifty Iron Condor Signal Bot"**
3. Click **"Run workflow"** → select mode **"test"** → Run
4. Watch the logs — you should see option chain data printed
5. Change mode to **"entry"** to send a real Telegram message

---

## ⏰ When Does it Run?

| Time (IST) | Action |
|---|---|
| **9:25 AM** | Fetches option chain, analyses, sends Entry Signal |
| Every 5 min **9:30–3:15 PM** | Checks if target/SL hit, sends Exit Signal |
| **3:15 PM** | Force exit signal if still in position |
| Weekends | Does nothing |

---

## 📱 What Your Telegram Messages Look Like

**Entry Signal:**
```
📊 NIFTY IRON CONDOR — ENTRY SIGNAL
━━━━━━━━━━━━━━━━━━━━━━━━
📈 Spot   : ₹25,454
🌡 VIX    : 13.46
📉 PCR    : 1.09
📅 Expiry : 20-Feb-2026
━━━━━━━━━━━━━━━━━━━━━━━━
LEGS TO PLACE:
🔴 SELL 25550 CE  @ ₹82
🟢 BUY  25650 CE  @ ₹41
🔴 SELL 25350 PE  @ ₹77
🟢 BUY  25250 PE  @ ₹38
━━━━━━━━━━━━━━━━━━━━━━━━
💰 Net Premium  : ₹80
🎯 Target Exit  : ₹32 (60% capture)
🛑 Stop Loss    : ₹160
📈 Max Profit   : ₹4,000 / lot
📉 Max Loss     : ₹1,000 / lot
━━━━━━━━━━━━━━━━━━━━━━━━
🟢 Signal Grade : A (82/100)
```

**Exit Signal:**
```
🚨 EXIT SIGNAL — CLOSE NOW
📌 Reason: 🎯 Target hit — premium at ₹31
🟢 Approx P&L: +₹2,450 / lot
LEGS TO CLOSE:
🟢 BUY BACK 25550 CE
🔴 SELL     25650 CE
🟢 BUY BACK 25350 PE
🔴 SELL     25250 PE
```

---

## 🆓 Is it truly free?

| Resource | Free Tier | Our Usage |
|---|---|---|
| GitHub Actions | 2,000 min/month | ~300 min/month ✅ |
| NSE India API | Free, no key needed | ✅ |
| Telegram Bot API | Free forever | ✅ |
| **Total cost** | | **₹0** |

---

## ⚙️ Customise the Strategy (src/strategy.py)

| Setting | Default | Change to |
|---|---|---|
| `OTM_OFFSET` | 1 strike | 2 for more conservative |
| `SPREAD_WIDTH` | 100 pts | 50 for tighter spread |
| `MIN_NET_PREMIUM` | ₹40 | Raise to ₹60 for better trades only |
| `MAX_VIX` | 18 | Lower to 15 for safer days only |
| `TARGET_DECAY` | 40% | In main.py, `target_exit` formula |

---

## ⚠️ Known Limitations

1. **NSE API can be slow** — sometimes takes 3–5 sec to respond. The code handles this.
2. **GitHub Actions can be ~1 min late** — this is normal, not critical for signals.
3. **Exit position is stored in /tmp** — GitHub Actions resets between runs. This means exit checks read from a fresh fetch each time (no persistent state). If you want persistent exit monitoring, use Render.com free tier instead (see below).

---

## 🔄 Alternative: Deploy on Render.com (always-on, also free)

If you want the bot to run as a persistent process:

1. Go to [render.com](https://render.com) → Sign up free
2. New → **Background Worker**
3. Connect your GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `cd src && python main.py entry` 
6. Add environment variables: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
7. Deploy

Render free tier stays alive (no sleep for background workers).

---

## ⚠️ Disclaimer

This bot is for **educational purposes only**. It does not constitute financial advice.  
Options trading involves significant risk. Always verify signals before placing trades.  
Past performance does not guarantee future results.
