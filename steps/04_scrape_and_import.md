# Step 4: Scrape & Import Data — 🔍 First Green Light!

```
  🏁 LAUNCH ──→ 🔐 SIGN IN ──→ ▶ 🔍 KEYWORD ──→ 🧠 SEMANTIC ──→ 🤖 RAG ──→ 🚀 YOURS
                                   ~~~~~~~~~~~
                                   YOU ARE HERE (step 2 of 2)
```

## What You'll Learn
- How web scraping works (HTTP requests + HTML parsing)
- What BeautifulSoup does and how CSS selectors find data
- How to structure scraped data as JSON
- How data pipelines work (scrape → split → import)

## Why This Matters

This is where your app starts coming alive. Once you import conference talk data, **Keyword Search lights up green** — your first tangible proof that the full pipeline is working. 🎉

## What to Do

### 1. Scrape Conference Talks

Make sure your virtual environment is activated, then run:

```bash
python scripts/02_scrape_data.py
```

This takes a few minutes — it's downloading and parsing ~400 web pages.

The script:
1. **Finds conference index pages** for the last 5 years (April + October each year)
2. **Extracts talk URLs** from each conference page
3. **Scrapes each talk** in parallel (title, speaker, calling, year, season, URL, full text)
4. **Saves structured JSON** to `scripts/output/talks.json`

### What the Output Looks Like

```json
{
    "title": "The Prodigal and the Road That Leads Home",
    "speaker": "President Dallin H. Oaks",
    "calling": "First Counselor in the First Presidency",
    "year": 2024,
    "season": "April",
    "url": "https://www.churchofjesuschrist.org/study/...",
    "text": "The full text of the talk as one string..."
}
```

### Understanding the Scraper

Take a look at `scripts/02_scrape_data.py`:

| Function | What It Does |
|----------|-------------|
| `setup_session()` | Creates an HTTP session with a browser-like user agent |
| `get_conference_urls()` | Generates URLs for each conference (April + October per year) |
| `get_talk_urls()` | Extracts individual talk URLs from a conference index page |
| `scrape_talk()` | Scrapes a single talk page and returns structured data |

> 💡 **Ask your AI assistant**: *"Why does the scraper use `ThreadPoolExecutor`? What is concurrent scraping?"*

### 2. Import Text to Supabase

Now import the scraped data into your database:

```bash
python scripts/03_import_data.py
```

This script:
1. Reads `scripts/output/talks.json`
2. Splits each talk into paragraph chunks, preserving source paragraph breaks
3. Imports paragraph text to `paragraph_embeddings` (**text only** — no embeddings yet), leaving `sentence_embeddings` untouched
4. Saves `scripts/output/paragraphs.json` locally (for the embedding step)
5. Verifies the final row count

> 💡 **Check scripts/output/**: After running, look at `scripts/output/talks.json` and `scripts/output/paragraphs.json` to see the intermediate data. Re-run `02_scrape_data.py` first so the talk text contains paragraph breaks. Older flattened files are grouped into bounded fallback chunks.

> 💡 **Why no embeddings yet?** We import the text first so you can see keyword search working right away. Embeddings take ~15 minutes to generate and are added in Step 5. This separation lets you experience the difference between keyword search (works now!) and semantic search (next step).

### 3. See Your First Green Light! 🟢

After the import completes:

1. **Go to your deployed site** and **refresh the page** (hard refresh: Ctrl+Shift+R)
2. **Log in** with your magic link
3. The **🔍 Keyword Search** panel should now show **🟢 Ready**!

Try searching for `"faith"` or `"temple"` — you should see results!

## Verification

- [ ] `02_scrape_data.py` completes and reports scraping ~300-400+ talks
- [ ] `scripts/output/talks.json` exists and contains talk objects
- [ ] `03_import_data.py` completes and reports imported paragraph chunks
- [ ] `scripts/output/paragraphs.json` exists with paragraph records
- [ ] Supabase Dashboard → Table Editor → `paragraph_embeddings` shows data, and the existing `sentence_embeddings` rows remain
- [ ] On your site: **🔍 Keyword Search** turns green and returns results!

## 🎉 Milestone: First green light! Keyword Search works!

> 💾 **Good time to commit!** `git add -A && git commit -m "Import conference data" && git push`
## → Next: [Step 05: Embeddings & Semantic Search](05_embeddings.md)
