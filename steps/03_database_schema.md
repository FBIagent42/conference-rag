# Step 3: Database Schema — Setting Up for 🔍 Keyword Search

```
  🏁 LAUNCH ──→ 🔐 SIGN IN ──→ ▶ 🔍 KEYWORD ──→ 🧠 SEMANTIC ──→ 🤖 RAG ──→ 🚀 YOURS
                                   ~~~~~~~~~~~
                                   YOU ARE HERE (step 1 of 2)
```

## What You'll Learn
- What pgvector is and why it's useful for AI applications
- How vector similarity search works at the database level
- What Row Level Security (RLS) is and why it matters
- How database functions (stored procedures) work
- **The difference between public and protected data access**

## Why This Matters

Your database is the foundation for all three search modes. The schema creates a sentence table for the original chunks and a separate paragraph table for the paragraph-chunking comparison. Keeping the tables separate lets you add paragraph embeddings without deleting your existing sentence embeddings.

## What to Do

### 1. Run the Schema Creation Script

```bash
python scripts/01_create_schema.py
```

This script creates:
- **pgvector extension** — Adds vector data type and similarity operators to PostgreSQL
- **`sentence_embeddings` table** — Stores the original sentence chunks (🔒 **auth-only**)
- **`paragraph_embeddings` table** — Stores paragraph chunks alongside the original sentence data (🔒 **auth-only**)
- **`page_views` table** — Records every page visit (🌍 **public**)
- **RLS policies** — Controls who can access each table
- **`match_sentences()` and `match_paragraphs()` functions** — Separate vector searches for each chunking strategy

> 💡 **Ask your AI assistant**: *"What is pgvector and how does cosine similarity search work?"*

### Two Tables, Two Access Levels

| Table | Who can read? | Who can write? | Why? |
|-------|--------------|----------------|------|
| `page_views` | 🌍 Anyone (anon + authenticated) | 🌍 Anyone | Public analytics — no secrets here |
| `sentence_embeddings` | 🔒 Authenticated users only | 🔒 Service role only | Protected content — requires login |
| `paragraph_embeddings` | 🔒 Authenticated users only | 🔒 Service role only | Paragraph chunks for comparison |

This is **Row Level Security (RLS)** in action. Both embedding tables are auth-only; paragraph_embeddings adds a chunking strategy while leaving sentence rows intact. page_views remains public.

### Understanding the Schema

```sql
-- sentence_embeddings: Protected data
CREATE POLICY "Allow authenticated users to read"
ON sentence_embeddings FOR SELECT
TO authenticated          -- ← Only logged-in users
USING (true);

-- page_views: Public data
CREATE POLICY "Allow public reads"
ON page_views FOR SELECT
TO anon, authenticated    -- ← Anyone, even without login
USING (true);
```

> 💡 **Ask your AI assistant**: *"Explain Row Level Security in PostgreSQL. Why is it more secure than checking permissions in application code?"*

### 🧪 Hands-On: See RLS in Action

After the script completes, try this experiment. Ask your AI assistant to help you write a quick Python snippet that uses **just the anon key** (not the service key) to:

1. **Query `page_views`** → ✅ Should work! The anon key can read this table.
2. **Query `sentence_embeddings`** → ❌ Should return **zero rows**! RLS blocks unauthenticated access.

Here's a starting point:

```python
from supabase import create_client
import json

with open('config.public.json') as f:
    public = json.load(f)

# Connect with the ANON key (not service key!)
client = create_client(public['SUPABASE_URL'], public['SUPABASE_ANON_KEY'])

# This works — page_views has a public SELECT policy
result = client.table('page_views').select('*').limit(5).execute()
print(f"page_views: {len(result.data)} rows ✅")

# This returns nothing — sentence_embeddings requires authentication
result = client.table('sentence_embeddings').select('*').limit(5).execute()
print(f"sentence_embeddings: {len(result.data)} rows (expected: 0) 🔒")
```

> 💡 **Try it!** Seeing the output first-hand makes the RLS concept click.

> 🤔 **Think about it**: The anon key is in your `config.public.json`. Anyone can see it. So why is your data still safe?

### The Security Model

```
┌────────────────────────────────────────┐
│ Supabase-Managed Security              │
│                                        │
│  anon key → RLS decides what you see   │
│  ┌─────────────────┐  ┌────────────┐  │
│  │ page_views      │  │ embeddings │  │
│  │ 🌍 public read  │  │ 🔒 auth    │  │
│  │ 🌍 public write │  │   only     │  │
│  └─────────────────┘  └────────────┘  │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Self-Built Security (Edge Functions)   │
│                                        │
│  OpenAI API key → Supabase can't       │
│  protect this for you — YOU build      │
│  the secure layer with Edge Functions  │
│  ┌──────────────┐  ┌──────────────┐   │
│  │ embed-       │  │ generate-    │   │
│  │ question     │  │ answer       │   │
│  │ 🔒 auth +    │  │ 🔒 auth +    │   │
│  │    API key   │  │    API key   │   │
│  └──────────────┘  └──────────────┘   │
└────────────────────────────────────────┘
```

**Key insight**: Supabase protects your *database* with RLS, but it can't protect *third-party API keys* like OpenAI. That's why you'll build Edge Functions — they're the secure intermediary you control.

## Verification

- [ ] Script prints "✅ Database schema created successfully!"
- [ ] Script prints "✅ Table verified" with a row count
- [ ] You can see `sentence_embeddings`, `paragraph_embeddings`, and `page_views` in Supabase Dashboard → Table Editor
- [ ] (Optional) The RLS test snippet shows `page_views` is readable but `sentence_embeddings` returns 0 rows

## → Next: [Step 04: Scrape & Import Data](04_scrape_and_import.md)
