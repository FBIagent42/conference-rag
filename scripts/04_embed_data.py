"""
Step 4: Generate Embeddings
===============================
Reads scripts/output/paragraphs.json and generates an OpenAI embedding
for each paragraph chunk. Saves the result to scripts/output/paragraphs_with_embeddings.json.

This is the most expensive step (~$0.60 in API costs). The output is
saved to disk so you won't lose your work if the next step fails.

Usage:
    python scripts/04_embed_data.py

Input:
    scripts/output/paragraphs.json  — from Step 3 (import)

Output:
    scripts/output/paragraphs_with_embeddings.json  — paragraph records with embedding vectors

Prerequisites:
    - config.secret.json with OPENAI_API_KEY
    - scripts/output/paragraphs.json from the import step
"""

import json
import os
import sys
import time

from openai import OpenAI
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'paragraphs.json')
OUTPUT_FILE = os.path.join('scripts', 'output', 'paragraphs_with_embeddings.json')
BATCH_SIZE = 100


def load_secrets():
    with open('config.secret.json', 'r') as f:
        return json.load(f)


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/03_import_data.py first.")
        sys.exit(1)

    # Load paragraph chunks
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    print("=" * 60)
    print(f"Generating Embeddings for {len(records):,} Paragraph Chunks")
    print("=" * 60)
    print(f"   Model: text-embedding-3-small (1,536 dimensions)")
    print(f"   Batch size: {BATCH_SIZE}\n")

    # Resume by stable paragraph identity so failed batches are retried safely.
    embedded_by_key = {}
    source_by_key = {
        (record['talk_id'], record['paragraph_num']): record
        for record in records
    }
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        for embedded_record in existing:
            key = (embedded_record.get('talk_id'), embedded_record.get('paragraph_num'))
            source_record = source_by_key.get(key)
            vector = embedded_record.get('embedding')
            if (source_record and embedded_record.get('text') == source_record['text']
                    and isinstance(vector, list) and len(vector) == 1536):
                embedded_by_key[key] = embedded_record

    records_to_embed = [
        record for record in records
        if (record['talk_id'], record['paragraph_num']) not in embedded_by_key
    ]
    if not records_to_embed:
        print(f"✅ All {len(records):,} paragraph chunks already have embeddings in {OUTPUT_FILE}")
        print(f"   Delete {OUTPUT_FILE} to re-generate.")
        return
    if embedded_by_key:
        print(f"   ⏩ Resuming: {len(embedded_by_key):,} chunks have vectors; "
              f"{len(records_to_embed):,} remain")

    # Generate embeddings
    secrets = load_secrets()
    client = OpenAI(api_key=secrets['OPENAI_API_KEY'])

    errors = 0

    for i in tqdm(range(0, len(records_to_embed), BATCH_SIZE), desc="Embedding"):
        batch = records_to_embed[i:i + BATCH_SIZE]
        batch_texts = [r['text'] for r in batch]

        try:
            response = client.embeddings.create(
                model='text-embedding-3-small',
                input=batch_texts
            )

            for record, item in zip(batch, response.data):
                record_with_embedding = dict(record)
                record_with_embedding['embedding'] = item.embedding
                key = (record['talk_id'], record['paragraph_num'])
                embedded_by_key[key] = record_with_embedding

        except Exception as e:
            print(f"\n   ❌ Batch error: {e}")
            errors += len(batch)

        # Checkpoint every batch; a rerun retries only chunks without vectors.
        embedded_records = [
            embedded_by_key[(record['talk_id'], record['paragraph_num'])]
            for record in records
            if (record['talk_id'], record['paragraph_num']) in embedded_by_key
        ]
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(embedded_records, f, ensure_ascii=False)

        time.sleep(0.1)

    # Final ordered save
    embedded_records = [
        embedded_by_key[(record['talk_id'], record['paragraph_num'])]
        for record in records
        if (record['talk_id'], record['paragraph_num']) in embedded_by_key
    ]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(embedded_records, f, ensure_ascii=False)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"\n✅ Embedding complete!")
    print(f"   Embedded: {len(embedded_records):,} paragraph chunks")
    if errors:
        print(f"   Errors:   {errors:,}")

    # Estimate cost
    total_chars = sum(len(r['text']) for r in embedded_records)
    est_tokens = total_chars / 4  # rough estimate
    cost = (est_tokens / 1_000_000) * 0.020
    print(f"   💰 Estimated cost: ${cost:.4f}")

    print(f"\n💾 Saved to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")
    print(f"   This file is your safety net — embeddings are preserved on disk.")
    print(f"\nNext: python scripts/05_update_embeddings.py")


if __name__ == '__main__':
    main()
