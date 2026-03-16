# Garmin Chat Connector: Talk to Your Garmin Data — From Any AI Chat App

If you own a Garmin watch, you already know how much data it collects — steps, sleep stages, HRV, Body Battery, VO2 Max, training load, and more. The problem has always been *accessing* that data in a conversational way. You can tap through the Garmin Connect app, but you can't just ask it a question.

**Garmin Chat Connector** solves that. It is a cloud-hosted [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that connects your Garmin Connect account directly to AI chat assistants — no local software, no setup files, no configuration. You get a personal MCP URL, paste it into your AI app, and start asking questions about your health data in plain English.

---

## Where Did This Come From?

Garmin Chat Connector is a companion to [Garmin Chat for Windows](https://github.com/rod-trent/GarminChatLocal), a desktop app that lets you converse with your Garmin data through Claude for Desktop. The desktop app works great on a PC — but you cannot run a local MCP server from a mobile device.

Garmin Chat Connector is the bridge for mobile (and web). Instead of a locally-running server, it is a hosted MCP endpoint in the cloud. Each user gets a private, token-protected URL that they paste into Claude, ChatGPT, or any other AI tool that supports custom MCP connectors.

---

## Already Using Garmin Chat for Windows? You're Going to Love This.

If you use [Garmin Chat for Windows](https://github.com/rod-trent/GarminChatLocal) on your desktop, you already know how useful it is to have a natural language conversation with your Garmin data. Garmin Chat Connector brings that same experience to your phone — no new learning curve, no new app to install.

Here's all it takes:

1. **Set up the connector** — visit the setup page, enter your Garmin credentials, and get your personal MCP URL (takes about 60 seconds)
2. **Open Claude or ChatGPT on your mobile device** — both apps are free to download on iOS and Android
3. **Add the connector** — paste your MCP URL into the app's connector settings
4. **Start chatting** — the same questions you ask on your desktop work identically on mobile

That's it. The same 16 Garmin data tools you rely on in the desktop app are available on your phone, through the same AI assistants you already use. Whether you're at the gym, out for a run, or just checking in on your recovery between meetings — your Garmin data is always a question away.

**Currently supported platforms:**

| AI App | Supported | Notes |
|---|---|---|
| **Claude** (web, iOS, Android) | Yes | Via Claude.ai remote connectors |
| **ChatGPT** (web, iOS, Android) | Yes | Via ChatGPT custom connectors (developer/beta mode) |
| Other AI assistants | Coming | Remote MCP support is spreading quickly |

---

## What Can You Ask?

Once connected, you can have natural language conversations about your fitness and health data:

- *"How well did I sleep last night?"*
- *"What's my Body Battery right now? Should I train hard or take it easy?"*
- *"Show me my runs from the past two weeks."*
- *"What's my current VO2 Max and training status?"*
- *"How much water did I log today?"*
- *"Give me a full health snapshot for this morning."*
- *"Summarize my training load over the last month."*

The connector exposes **16 data tools** across five categories:

### Daily Overview
| Tool | What it returns |
|---|---|
| `get_health_snapshot` | Everything at once: steps, sleep, Body Battery, stress, HRV, heart rate, and training status |
| `get_today_summary` | Step count, calories burned, distance, active minutes, and goal progress |
| `get_sleep_summary` | Total sleep, time in each stage (deep / light / REM / awake), and sleep score |
| `get_activities` | Recent workouts: type, duration, distance, pace, calories, and heart rate zones |

### Recovery & Wellness
| Tool | What it returns |
|---|---|
| `get_body_battery` | Current Body Battery level, daily high/low, and charge/drain events |
| `get_stress_summary` | Average and max stress score, time in each stress category |
| `get_hrv_status` | Last night's HRV, 5-day baseline, and status (balanced / unbalanced / poor) |
| `get_heart_rate` | Resting, average, and max heart rate for the day |

### Training Performance
| Tool | What it returns |
|---|---|
| `get_training_status` | VO2 Max, fitness age, training load, and current training status |
| `get_training_readiness` | Readiness score (0–100) and the contributing factors |
| `get_intensity_minutes` | Weekly moderate and vigorous minutes vs. the WHO-recommended 150 min/week goal |

### Nutrition & Hydration
| Tool | What it returns |
|---|---|
| `get_nutrition_log` | Calories consumed, macros (protein, carbs, fat, fiber, sugar), and food log entries |
| `get_hydration` | Water intake in millilitres and US cups |

### Body Metrics & Range Queries
| Tool | What it returns |
|---|---|
| `get_body_metrics` | Weight, BMI, body fat %, muscle mass, bone mass (requires Garmin Index scale) |
| `get_spo2_and_respiration` | Blood oxygen saturation (SpO2) and breathing rate |
| `get_activities_by_date_range` | All workouts between two dates — ideal for weekly or monthly summaries |

---

## How to Connect

### Step 1 — Set Up Your Account

Visit the setup page and enter your **Garmin Connect email and password**. If your account has two-factor authentication enabled, you'll be prompted for your MFA code.

Your credentials are used once to obtain OAuth tokens from Garmin Connect — they are **never stored**. Only the encrypted OAuth tokens are persisted.

After setup you'll receive a personal MCP URL that looks like:

```
https://your-instance.railway.app/garmin/?token=abc123...
```

Keep this URL private. It is the key to your data. You can revoke it at any time from the disconnect page.

---

### Step 2A — Add to Claude

1. Open the **Claude app** (mobile or web at [claude.ai](https://claude.ai))
2. Go to **Settings → Connectors** (or Integrations)
3. Tap **Add Connector**, paste your MCP URL, and name it **Garmin Chat**
4. After adding, open the connector settings and set tool permissions to **Always allow** — otherwise Claude will prompt for approval on every single request
5. Start chatting! Try: *"How did I sleep last night?"* or *"Give me a health overview for today"*

---

### Step 2B — Add to ChatGPT

> **Note:** MCP connector support in ChatGPT is currently available in **developer / beta mode**. Make sure it is enabled in your account settings before proceeding.

1. Open **ChatGPT** and go to **Settings → Beta features**, then enable **MCP servers**
2. In a new chat, click the **Tools** icon (or go to **Settings → Connectors**) and choose **Add custom MCP server**
3. Paste your MCP URL and give the connection a name, then save
4. Start chatting! Try: *"What's my Body Battery right now?"* or *"Summarize my training this week"*

---

## How It Works Under the Hood

```
Your Garmin Watch
       │  syncs to
       ▼
Garmin Connect (cloud)
       │  API
       ▼
┌──────────────────────────────────┐
│     Garmin Chat Connector        │  ← deployed on Railway
│                                  │
│  /setup  → web setup form        │
│  /garmin/?token=…  → MCP server  │
│                                  │
│  PostgreSQL (encrypted tokens)   │
└──────────────────────────────────┘
       │  MCP over HTTPS
       ▼
Claude / ChatGPT / other AI tools
```

When you set up your account, the connector authenticates with Garmin Connect via Garmin's OAuth flow, encrypts the resulting tokens using Fernet symmetric encryption, and stores them in a PostgreSQL database. Each user gets a unique, randomly-generated access token.

When your AI tool calls a data tool:
1. The connector looks up your encrypted Garmin tokens by your access token
2. Decrypts and injects them into an isolated, in-memory Garmin client
3. Fetches the requested data from the Garmin Connect API
4. Returns formatted text that the AI reads and summarizes in natural language
5. Saves any refreshed OAuth tokens back to the database
6. Discards the in-memory client — no shared state between requests

Each request is fully isolated. Multiple users can connect to the same instance simultaneously without their sessions interfering.

---

## Security & Privacy

- Your **Garmin credentials** are used once during setup and never stored
- Only **OAuth tokens** are persisted — encrypted at rest with Fernet symmetric encryption
- Your **personal access token** (the `?token=` part of your URL) is a randomly-generated 32-byte hex string and is never logged in full
- All traffic is encrypted over **HTTPS**
- Revoking your connection at `/disconnect` immediately deletes all associated tokens from the database


## Frequently Asked Questions

**Does this work with all Garmin devices?**
Yes. Each tool returns "No data available" gracefully if your device doesn't support a particular metric (e.g., Training Readiness requires newer hardware; nutrition data requires manual logging in Garmin Connect).

**Can multiple people use the same hosted instance?**
Yes. The connector is designed for multi-user deployment. Each user gets their own isolated token and encrypted Garmin session.

**Will my session expire?**
Garmin OAuth tokens are automatically refreshed on every request. The updated tokens are saved back to the database, so your session stays active indefinitely under normal use.

**Is this affiliated with Garmin?**
No. This is an independent project that uses the Garmin Connect API via the [`garth`](https://github.com/matin/garth) and [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) Python libraries.

**What if something breaks or I have a question?**
Head over to the [Garmin Chat Community Forums](https://github.com/rod-trent/Garmin-Chat-Forums/discussions) on GitHub Discussions — it's the best place to report issues, ask questions, and share what you're building.

---

## Support the Project

Garmin Chat Connector is free to use. If you find it useful, please consider supporting it — it helps cover the hosting costs and encourages continued development and support for additional AI platforms.

[**Support for $4.99 / year →**](https://buy.stripe.com/bJe9AUeaYcdT46z1F75os00)

No pressure — the connector works the same either way. But if you're going to use it regularly, it makes sense. Thank you.

---

## Links

- **Community & support:** [Garmin Chat Forums](https://github.com/rod-trent/Garmin-Chat-Forums/discussions)
- **Desktop companion app:** [Garmin Chat for Windows](https://github.com/rod-trent/GarminChatLocal)
- **Support the project:** [buy.stripe.com/bJe9AUeaYcdT46z1F75os00](https://buy.stripe.com/bJe9AUeaYcdT46z1F75os00)

---

*Built with [FastMCP](https://github.com/jlowin/fastmcp), [garth](https://github.com/matin/garth), [garminconnect](https://github.com/cyberjunky/python-garminconnect), [Starlette](https://www.starlette.io/), and [Railway](https://railway.app).*
