# Mine to Model

An interactive map of the AI data center supply chain, from uranium, gas, copper and chips to the companies that buy the compute. It shows stock prices, analyst targets and upside, and updates itself every morning at 6am Pacific.

Same setup as Open Brain: **GitHub** holds the code, **Vercel** hosts the site, **Supabase** stores your watchlist, and a **Telegram** bot sends alerts. Build it one level at a time. Each level works on its own.

| Level | What you get | Time |
|---|---|---|
| 1 | Your own link, with prices and analyst targets refreshed daily at 6am Pacific | 20 min |
| 2 | The "Since yesterday" view: biggest moves and analyst changes | already on after Level 1 |
| 3 | Watchlist and notes, saved to your Supabase account | 15 min |
| 4 | Telegram alerts when a stock hits your buy price | 10 min |

---

## What's in this folder

```
index.html                          the website (the map, table and themes)
data/stocks.json                    prices and targets; the daily job rewrites this
data/tickers.json                   which ticker to fetch for each company
data/names.json                     company names (used in alert messages)
data/history/                       one snapshot per day, kept for future charts
scripts/update_stocks.py            the daily update script
scripts/requirements.txt            the one Python library it needs (yfinance)
.github/workflows/daily-update.yml  the 6am schedule (GitHub Actions)
supabase/schema.sql                 the watchlist table (Level 3)
```

On a Mac, Finder hides folders that start with a dot, so you may not see `.github`. It's there. Press Cmd+Shift+. in Finder to show it.

---

## Level 1: put it online with a 6am daily update

### 1. Create the GitHub repo
1. On github.com, click **New repository**.
2. Name it `mine-to-model`. Pick **Public** or **Private** (both work).
3. Click **Create repository**.

### 2. Upload the files
1. On the new repo's page, click **uploading an existing file**.
2. Drag in everything from this folder: `index.html`, `README.md`, `.gitignore`, and the `data`, `scripts` and `supabase` folders.
3. Click **Commit changes**.

The browser uploader often skips the hidden `.github` folder, so add the schedule file by hand:

1. Click **Add file → Create new file**.
2. In the name box, type exactly `.github/workflows/daily-update.yml`. The slashes create the folders.
3. Open `daily-update.yml` from this folder in any text editor, copy everything, and paste it into GitHub.
4. Click **Commit changes**.

### 3. Let the daily job save its updates
1. In the repo, go to **Settings → Actions → General**.
2. Under **Workflow permissions**, choose **Read and write permissions**.
3. Click **Save**.

### 4. Run the first update yourself
1. Open the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Daily stock update** in the left sidebar.
3. Click **Run workflow**, then the green **Run workflow** button.
4. Wait 2–4 minutes for the green check mark.

If you click into the run, the log ends with a line like `Updated 63 of 65 tickers`. A few misses are normal. Any company that fails keeps yesterday's numbers and is marked "not updated".

### 5. Host it on Vercel
1. On vercel.com, click **Add New → Project** and import `mine-to-model`.
2. Framework preset: **Other**. Leave the build settings empty, since it's a plain HTML site.
3. Click **Deploy**.

That's your link.

From now on it runs by itself. Every morning around 6am Pacific, GitHub fetches new prices, saves `data/stocks.json`, and Vercel redeploys within a minute.

**Good to know**
- 6am Pacific is before the market opens. Each morning's prices are the previous day's close, plus any analyst changes made overnight.
- GitHub can start scheduled jobs 5–20 minutes late when it's busy.
- GitHub pauses schedules in repos with no activity for 60 days. The daily commits count as activity, so this shouldn't happen. If it does, the Actions tab has a button to turn the schedule back on.
- The written company notes (what could push a stock up or hold it back) are a snapshot from October 2026. Only the numbers update.
- After the first run, the analyst numbers come from Yahoo Finance instead of S&P Global, so they'll shift a little from what you saw in Claude.

---

## Level 2: "Since yesterday"

Nothing to set up. After two daily runs, the top of the page shows:
- the biggest gains and drops from the last trading session
- every analyst target change of 1% or more
- any rating changes

---

## Level 3: watchlist and notes (Supabase)

### 1. Create the table
1. In Supabase, create a new project (or reuse one). Wait for it to finish setting up.
2. Go to **SQL Editor → New query**.
3. Paste in everything from `supabase/schema.sql` and click **Run**.

This creates a `watchlist` table where each person can only see their own rows.

### 2. Allow email sign-in links to your site
1. Go to **Authentication → URL Configuration**.
2. Set **Site URL** to your Vercel link, for example `https://mine-to-model.vercel.app`.
3. Add the same link under **Redirect URLs**.

### 3. Connect the website
1. In Supabase, open **Project Settings → API** (in newer versions, **Data API** and **API Keys**).
2. Copy the **Project URL** and the **anon public** key.
3. In GitHub, open `index.html` and click the pencil icon to edit.
4. Near the top, find `window.MTM_CONFIG` and paste both values between the quotes:

```js
window.MTM_CONFIG = {
  app: true,
  supabaseUrl: "https://xxxx.supabase.co",
  supabaseAnonKey: "eyJ..."
};
```

5. Commit. Vercel redeploys.

### 4. Use it
1. On your site, a **Watchlist** box appears next to the legend. Enter your email and click **Email me a sign-in link**, then open the link from your email.
2. Tap any company. The side panel now has **Add to watchlist**, a buy price and a notes box.
3. Starred companies show a ★ on the map. The table gets a **★ My watchlist** filter, and "Since yesterday" adds a **Your watchlist** column.

The anon key is meant to be public. The security comes from the Row Level Security rules in `schema.sql`, which stop anyone else from reading or changing your rows. Never put the **service role** key in `index.html`.

---

## Level 4: Telegram price alerts

The 6am job checks each watchlist company that has a buy price. When the price is at or below it, you get one Telegram message. The alert re-arms once the price goes back above your buy price, so you won't get the same alert every morning.

### 1. Set up the bot
1. In Telegram, message **@BotFather**, send `/newbot` and follow the steps. Copy the **bot token**. You can also reuse your Open Brain bot's token.
2. Send your new bot any message, such as "hi".
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser, with your token in place of `<YOUR_TOKEN>`.
4. Find `"chat":{"id":` in the page. That number is your **chat id**.

### 2. Add the secrets to GitHub
In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**, and add each of these:

| Name | Value |
|---|---|
| `SUPABASE_URL` | your Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase **service_role** key (API settings). Keep it secret; it only goes here. |
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | the number from getUpdates |

### 3. Test it
1. Give a watchlist company a buy price above today's price.
2. In **Actions → Daily stock update**, click **Run workflow**.

You should get a Telegram message within a few minutes. After the test, set the buy price back to what you actually want.

---

## Adding a company or fixing a ticker

- **To track another ticker:** add a line to `data/tickers.json`, for example `"newco": {"symbol": "NEWC", "yahoo": "NEWC"}`.
- **To show the company on the map:** it also needs an entry in the `N` list inside `index.html`. That's the part to ask Claude for. Paste the request together with the current `index.html` and it can add the company with its links.
- **Foreign listings** use Yahoo's suffixes: `.L` London, `.TW` Taiwan, `.KS` Korea, `.PA` Paris. Those stocks show prices in their local currency.

## If Yahoo stops working

`yfinance` is a free, unofficial connection to Yahoo Finance. It occasionally breaks for a few days until the library is updated. If the daily log shows most tickers failing:

1. Wait a day. The site keeps showing the last good numbers.
2. If it keeps failing, sign up at financialmodelingprep.com. The free plan covers only about 87 large stocks; the Starter plan (about $22 a month) covers all US stocks.
3. Add your key as a repository secret named `FMP_API_KEY`. The script then uses it for US tickers automatically. Foreign tickers still use Yahoo.

## Test runs

- **From GitHub:** Actions → Daily stock update → Run workflow. Manual runs ignore the 6am check.
- **On your own computer:**

  ```
  pip install yfinance
  MTM_FORCE=1 python scripts/update_stocks.py
  ```

  Add `MTM_MOCK=1` to try it with made-up price moves and no internet calls.

---

This is research, not financial advice. Analyst targets are often too optimistic and tend to follow the stock price.
