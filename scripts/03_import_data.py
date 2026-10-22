"""
Step 3: Import Talk Data to Supabase
======================================
Reads scripts/output/talks.json, splits each talk into paragraphs,
imports the text records to Supabase (without embeddings), and
saves the paragraph records locally for the embedding step.

After this step, KEYWORD SEARCH will light up green on your site!
Embeddings are added in the next step to enable semantic search.

Usage:
    python scripts/03_import_data.py

Input:
    scripts/output/talks.json  — from Step 2 (scraping)

Output:
    scripts/output/paragraphs.json  — paragraph chunks with talk_id + paragraph_num

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key
    - Database schema created (Step 1)
    - Talks scraped (Step 2)
"""

import json
import os
import re
import sys
import time
import uuid

from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'talks.json')
OUTPUT_FILE = os.path.join('scripts', 'output', 'paragraphs.json')
BATCH_SIZE = 100
MAX_PARAGRAPH_CHARS = 1800


def load_config():
    with open('config.public.json', 'r') as f:
        public_config = json.load(f)
    with open('config.secret.json', 'r') as f:
        secrets = json.load(f)
    return public_config, secrets


def split_long_paragraph(paragraph, max_chars=MAX_PARAGRAPH_CHARS):
    """Split an unusually long paragraph into sentence-preserving chunks."""
    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    chunks = []
    current = ''

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        elif not current:
            current = sentence
        else:
            current = f'{current} {sentence}'

        # Bound a single unusually long sentence as well.
        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max_chars:].strip()

    if current:
        chunks.append(current)
    return chunks


def split_into_paragraphs(text):
    """Use source paragraph breaks; group legacy flat text into bounded chunks."""
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    paragraphs = [
        re.sub(r'\s+', ' ', part).strip()
        for part in re.split(r'\n\s*\n', normalized)
        if part.strip()
    ]

    # Older scraper output flattened paragraphs onto one line. Group that text
    # by sentence so an entire talk does not become a single embedding input.
    if len(paragraphs) <= 1:
        paragraphs = split_long_paragraph(re.sub(r'\s+', ' ', normalized))

    chunks = []
    for paragraph in paragraphs:
        chunks.extend(split_long_paragraph(paragraph))
    return [chunk for chunk in chunks if len(chunk) > 20]


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/02_scrape_data.py first.")
        sys.exit(1)

    # Load talks
    print("=" * 60)
    print("Importing Talk Data to Supabase")
    print("=" * 60)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        talks = json.load(f)
    print(f"   Loaded {len(talks)} talks\n")

    # Split into paragraph records (no embeddings yet)
    print("Splitting talks into paragraphs...")
    paragraph_records = []
    for talk in tqdm(talks, desc="Splitting"):
        # Keep IDs stable across reruns so the unique (talk_id, paragraph_num)
        # key lets this script safely upsert instead of deleting existing rows.
        talk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, talk.get('url') or talk['title']))
        paragraphs = split_into_paragraphs(talk['text'])
        for i, paragraph in enumerate(paragraphs, 1):
            paragraph_records.append({
                'talk_id': talk_id,
                'title': talk['title'],
                'speaker': talk['speaker'],
                'calling': talk['calling'],
                'year': int(talk['year']) if talk['year'] else None,
                'season': talk['season'],
                'url': talk['url'],
                'paragraph_num': i,
                'embedding': None,
                'text': paragraph
            })

    print(f"✅ Split {len(talks)} talks into {len(paragraph_records):,} paragraph chunks")
    print(f"   Average: {len(paragraph_records) / len(talks):.1f} chunks per talk\n")

    # Save paragraph chunks locally (for embedding step to use)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(paragraph_records, f, ensure_ascii=False)
    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"💾 Saved {len(paragraph_records):,} paragraph chunks to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")

    # Connect to Supabase
    public_config, secrets = load_config()
    client = create_client(public_config['SUPABASE_URL'], secrets['SUPABASE_SERVICE_KEY'])

    # Upsert paragraph rows only. Existing sentence_embeddings data is untouched.
    print("\n" + "=" * 60)
    print("Checking for existing data...")
    print("=" * 60)

    try:
        result = client.table('paragraph_embeddings').select('id', count='exact').limit(1).execute()
        existing_count = result.count or 0
        print(f"   Found {existing_count:,} existing rows; matching paragraph IDs will be updated.")
    except Exception as e:
        print(f"   ⚠️ Could not check existing data: {e}")
        print("   Proceeding with import anyway...")

    # Import in batches
    print("\n" + "=" * 60)
    print(f"Importing {len(paragraph_records):,} records to Supabase")
    print("=" * 60)
    print("   (Text only — embeddings will be added in the next step)\n")

    success = 0
    errors = 0

    for i in tqdm(range(0, len(paragraph_records), BATCH_SIZE), desc="Importing"):
        batch = paragraph_records[i:i + BATCH_SIZE]
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

    # Final verification
    result = client.table('paragraph_embeddings').select('id', count='exact').limit(1).execute()
    print(f"\n   Total rows in database: {result.count or 0:,}")

    print(f"\n🎉 Keyword Search is now ready!")
    print(f"   Refresh your site — the 🔍 Keyword Search panel should turn GREEN.")
    print(f"\nNext: python scripts/04_embed_data.py")


if __name__ == '__main__':
    main()
