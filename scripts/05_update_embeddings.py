"""
Step 5: Import Embeddings to Database
=========================================
Reads scripts/output/paragraphs_with_embeddings.json and upserts
paragraph records (text + embeddings), preserving sentence-level data.

After this step, paragraph-level semantic search will be ready on your site.

Usage:
    python scripts/05_update_embeddings.py

Input:
    scripts/output/paragraphs_with_embeddings.json  — from Step 4

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key
    - Database schema created (Step 1)
    - Embeddings generated (Step 4)
"""

import json
import os
import sys
import time

from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'paragraphs_with_embeddings.json')
# Keep vector upserts small so Postgres can update the paragraph table and its
# vector index before the database statement timeout is reached.
BATCH_SIZE = 10


def load_config():
    with open('config.public.json', 'r') as f:
        public_config = json.load(f)
    with open('config.secret.json', 'r') as f:
        secrets = json.load(f)
    return public_config, secrets


def load_existing_embedded_texts(client):
    """Return the text for paragraph rows that already have a vector."""
    existing = {}
    page_size = 1000
    offset = 0

    while True:
        response = (
            client.table('paragraph_embeddings')
            .select('talk_id,paragraph_num,text')
            .not_.is_('embedding', 'null')
            .order('talk_id')
            .order('paragraph_num')
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        for row in page:
            key = (row['talk_id'], row['paragraph_num'])
            existing[key] = row['text']

        if len(page) < page_size:
            break
        offset += page_size

    return existing


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/04_embed_data.py first.")
        sys.exit(1)

    # Load embedded records
    print("Loading embeddings data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    # Verify embeddings are present
    with_embeddings = sum(1 for r in records if r.get('embedding'))
    without_embeddings = len(records) - with_embeddings

    print(f"   Loaded {len(records):,} records")
    print(f"   With embeddings:    {with_embeddings:,}")
    if without_embeddings:
        print(f"   Without embeddings: {without_embeddings:,} (will be imported without)")

    # Connect to Supabase
    public_config, secrets = load_config()
    client = create_client(public_config['SUPABASE_URL'], secrets['SUPABASE_SERVICE_KEY'])

    # Skip vectors already stored for identical paragraph text. This makes a
    # rerun resume after a timeout instead of re-upserting every successful row.
    existing_texts = load_existing_embedded_texts(client)
    pending_records = [
        record for record in records
        if existing_texts.get((record['talk_id'], record['paragraph_num'])) != record['text']
    ]
    already_done = len(records) - len(pending_records)
    print(f"   Already embedded and unchanged: {already_done:,}")
    print(f"   Need upload or refresh:         {len(pending_records):,}")

    # Upsert paragraph rows only. Existing sentence_embeddings data is untouched.
    print("\n" + "=" * 60)
    print("Updating paragraph embeddings (sentence embeddings are preserved)")
    print("=" * 60)

    # Upsert is safe to rerun: the table has a unique (talk_id, paragraph_num) key.
    print(f"\n   Updating {len(pending_records):,} records in batches of {BATCH_SIZE}...\n")

    success = 0
    errors = 0

    for i in tqdm(range(0, len(pending_records), BATCH_SIZE), desc="Importing"):
        batch = pending_records[i:i + BATCH_SIZE]
        try:
            client.table('paragraph_embeddings').upsert(
                batch,
                on_conflict='talk_id,paragraph_num'
            ).execute()
            success += len(batch)
        except Exception as e:
            print(f"\nError at batch {i // BATCH_SIZE}: {e}")
            errors += len(batch)
        time.sleep(0.1)

    print(f"\n✅ Import complete!")
    print(f"   Success: {success:,}")
    if errors:
        print(f"   Errors:  {errors:,}")

    # Verify
    result = client.table('paragraph_embeddings').select('id', count='exact').limit(1).execute()
    total = result.count or 0

    embedded_result = client.table('paragraph_embeddings') \
        .select('id', count='exact') \
        .not_.is_('embedding', 'null') \
        .limit(1).execute()
    with_emb = embedded_result.count or 0

    print(f"\n   Total rows:          {total:,}")
    print(f"   Rows with embeddings: {with_emb:,}")

    print(f"\n🎉 Semantic Search is now ready!")
    print(f"   Refresh your site — the 🧠 Semantic Search panel should turn GREEN.")
    print(f"\nNext: Deploy edge functions to light up 🤖 RAG!")


if __name__ == '__main__':
    main()
