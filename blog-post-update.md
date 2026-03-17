# 22 New Garmin Data Points Just Landed in Garmin Chat Connector

When we launched Garmin Chat Connector, it gave you 16 ways to ask questions about your Garmin data — sleep, Body Battery, HRV, training status, nutrition, and more. Today's update more than doubles that.

**We just shipped 22 new data tools**, unlocking deeper activity analysis, advanced performance metrics, body and health tracking, weekly trends, personal records, gear tracking, device info, and per-meal nutrition. Here's everything that's new.

---

## What Was Added

### Gear Tracking — Know When to Replace Your Shoes

Five new tools give you full visibility into the gear you've logged in Garmin Connect.

| Tool | What it returns |
|---|---|
| `get_gear` | All registered gear (shoes, bikes, etc.) — name, type, active/inactive status, total distance, and activity count |
| `get_gear_stats` | Total distance, time, and activity count for a specific piece of gear |
| `get_gear_activities` | Recent activities that used a specific item |
| `get_activity_gear` | Which shoes or bike were used in a specific activity |
| `get_gear_defaults` | Your default gear assignments by activity type (e.g. auto-assign shoes to running) |

**Try asking:** *"How many miles are on my running shoes?"* or *"What gear have I been using most this month?"*

---

### Activity Details — Go Beyond the Summary Card

Your activity summary tells you how far and how fast. These six tools tell you *everything else*.

| Tool | What it returns |
|---|---|
| `get_activity_details` | Full GPS track with per-second/per-lap timeseries: pace, heart rate, elevation, cadence, power |
| `get_activity_splits` | Per-lap split data — distance, duration, average pace, HR, elevation gain |
| `get_activity_hr_zones` | Time spent in each heart rate training zone (Z1–Z5) for a single activity |
| `get_activity_power_zones` | Time in each power training zone (for cycling activities) |
| `get_activity_exercise_sets` | Sets, reps, and weights logged for strength training workouts |
| `get_activity_weather` | Weather conditions at activity start: temperature, humidity, wind speed, description |

**Try asking:** *"How much of my long run was in Zone 2?"* or *"Show me the lap splits from my race on Saturday."*

---

### Advanced Performance Metrics — Your Physiological Fingerprint

These seven tools surface metrics that most athletes only find buried deep in the Garmin Connect app — now available in a single question.

| Tool | What it returns |
|---|---|
| `get_race_predictions` | Garmin's predicted finish times for 5K, 10K, half marathon, and marathon |
| `get_endurance_score` | Aerobic base fitness score built from sustained moderate-to-hard training efforts |
| `get_hill_score` | Climbing fitness metric based on power and heart rate during uphill segments |
| `get_lactate_threshold` | Heart rate and pace at your lactate threshold |
| `get_cycling_ftp` | Functional Threshold Power (FTP) in watts |
| `get_running_tolerance` | How well your body is adapting to recent running load — an early indicator of injury risk |
| `get_fitness_age` | Your biological fitness age estimate based on cardiovascular fitness |

**Try asking:** *"What does Garmin predict my marathon time would be?"* or *"What is my lactate threshold pace?"*

---

### Body & Health Tracking — Data Beyond the Workout

Four new tools bring your day-to-day health measurements into the conversation.

| Tool | What it returns |
|---|---|
| `get_resting_heart_rate` | Resting HR measured during sleep or rest for a specific date |
| `get_body_battery_events` | Timestamped log of every Body Battery charge and drain event throughout the day |
| `get_weigh_ins` | Weight log entries over a date range from a Garmin Index scale or manual entries |
| `get_blood_pressure` | Blood pressure readings (systolic/diastolic) logged in Garmin Connect |

**Try asking:** *"Has my resting heart rate been trending up or down this month?"* or *"Show me my weight over the last 30 days."*

---

### Weekly Trends — See the Arc, Not Just the Day

Three new tools shift the view from daily snapshots to multi-week trends — the context that makes individual data points meaningful.

| Tool | What it returns |
|---|---|
| `get_weekly_step_trends` | Weekly step totals over the past N weeks (default 12, up to 52) |
| `get_weekly_stress_trends` | Weekly average and peak stress scores over N weeks |
| `get_weekly_intensity_trends` | Weekly moderate and vigorous intensity minute totals over N weeks |

**Try asking:** *"How has my weekly stress changed over the last 3 months?"* or *"Am I consistently hitting my intensity minute goals week over week?"*

---

### Goals & Achievements — Your All-Time Best

Two new tools surface your personal records and earned badges.

| Tool | What it returns |
|---|---|
| `get_personal_records` | All-time PRs across activity types: fastest 1K, 5K, 10K, half, marathon, longest run, highest climb, and more |
| `get_earned_badges` | Completed badges and challenges: step milestones, distance achievements, activity streaks |

**Try asking:** *"What are my personal records for running?"* or *"What badges have I earned in Garmin Connect?"*

---

### Connected Devices — Know Your Kit

One new tool gives you a summary of the hardware tied to your account.

| Tool | What it returns |
|---|---|
| `get_devices` | All connected Garmin devices — watch model, firmware version, battery status, last sync time |

**Try asking:** *"What Garmin devices do I have connected?"* or *"When did my watch last sync?"*

---

### Per-Meal Nutrition — Breakfast, Lunch, Dinner, and Snacks

The existing `get_nutrition_log` returns your daily totals. This new tool breaks them down by meal.

| Tool | What it returns |
|---|---|
| `get_nutrition_meals` | Per-meal nutrition breakdown — calories, protein, carbs, fat, and fiber for breakfast, lunch, dinner, and snacks separately |

**Try asking:** *"How were my calories distributed across meals today?"* or *"Was my protein intake front-loaded or back-loaded today?"*

---

## The Full Picture: 38 Tools, One Connector

With today's update, Garmin Chat Connector now exposes **38 data tools** across 13 categories — every major data type that Garmin Connect tracks, accessible through natural language in Claude, ChatGPT, or any AI assistant that supports remote MCP connectors.

| Category | Tools |
|---|---|
| Daily Overview | 4 |
| Recovery & Wellness | 4 |
| Training Performance | 3 |
| Nutrition & Hydration | 2 |
| Body Metrics & Date Ranges | 3 |
| **Gear Tracking** *(new)* | **5** |
| **Activity Details** *(new)* | **6** |
| **Advanced Performance** *(new)* | **7** |
| **Body & Health Tracking** *(new)* | **4** |
| **Weekly Trends** *(new)* | **3** |
| **Goals & Achievements** *(new)* | **2** |
| **Connected Devices** *(new)* | **1** |
| **Nutrition Details** *(new)* | **1** |

No setup changes required. If you already have Garmin Chat Connector installed in Claude or ChatGPT, all 22 new tools are available immediately — just start asking.

---

## Not Connected Yet?

Getting set up takes about 60 seconds:

1. Visit the setup page and sign in with your Garmin Connect credentials
2. Copy your personal MCP URL
3. Paste it into Claude (**Settings → Connectors**) or ChatGPT (**Settings → Beta → MCP Servers**)

That's it. Your connector is tied to your account, not your device — add it once in a browser and it's instantly available in the Claude and ChatGPT apps on your phone too.

---

## Links

- **Community & support:** [Garmin Chat Forums](https://github.com/rod-trent/Garmin-Chat-Forums/discussions)
- **Desktop companion app:** [Garmin Chat for Windows](https://github.com/rod-trent/GarminChatLocal)
- **Support the project:** [buy.stripe.com/bJe9AUeaYcdT46z1F75os00](https://buy.stripe.com/bJe9AUeaYcdT46z1F75os00)

---

*Built with [FastMCP](https://github.com/jlowin/fastmcp), [garth](https://github.com/matin/garth), [garminconnect](https://github.com/cyberjunky/python-garminconnect), [Starlette](https://www.starlette.io/), and [Railway](https://railway.app).*
