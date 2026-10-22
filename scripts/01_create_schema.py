"""
Step 1: Create Database Schema
================================
Creates the sentence_embeddings, paragraph_embeddings, and question_embedding_cache tables,
pgvector extension, Row Level Security policies, and the match_sentences()
function in your Supabase database.

Usage:
    python scripts/01_create_schema.py

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key, access token, and project ref
    - Supabase project created
"""

import json
import sys
import time

# Load configuration from both config files
with open('config.public.json', 'r') as f:
    public_config = json.load(f)
with open('config.secret.json', 'r') as f:
    secrets = json.load(f)

SUPABASE_URL = public_config['SUPABASE_URL']
SUPABASE_SERVICE_KEY = secrets['SUPABASE_SERVICE_KEY']
SUPABASE_ACCESS_TOKEN = secrets['SUPABASE_ACCESS_TOKEN']
SUPABASE_PROJECT_REF = secrets['SUPABASE_PROJECT_REF']


def create_schema():
    import requests
    from supabase import create_client

    print("=" * 60)
    print("Creating Database Schema")
    print("=" * 60)

    schema_sql = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create sentence_embeddings table
CREATE TABLE IF NOT EXISTS sentence_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talk_id UUID NOT NULL,
    title TEXT NOT NULL,
    speaker TEXT,
    calling TEXT,
    year INTEGER,
    season TEXT,
    url TEXT,
    sentence_num INTEGER,
    text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for talk_id grouping
CREATE INDEX IF NOT EXISTS sentence_embeddings_talk_id_idx 
ON sentence_embeddings(talk_id);

-- Enable Row Level Security
ALTER TABLE sentence_embeddings ENABLE ROW LEVEL SECURITY;

-- RLS policy: authenticated users can read
DROP POLICY IF EXISTS "Allow authenticated users to read" ON sentence_embeddings;
CREATE POLICY "Allow authenticated users to read"
ON sentence_embeddings FOR SELECT
TO authenticated
USING (true);

-- Cache question embeddings so repeated questions do not need a new
-- OpenAI embedding request. No client policies are created; access will
-- be provided by the server-side Edge Function.
CREATE TABLE IF NOT EXISTS question_embedding_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_question TEXT NOT NULL UNIQUE,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE question_embedding_cache ENABLE ROW LEVEL SECURITY;

-- ============================================
-- Page Views table (PUBLIC access for RLS demo)
-- ============================================
-- This table intentionally has PUBLIC policies so students can
-- contrast it with sentence_embeddings (auth-only).

CREATE TABLE IF NOT EXISTS page_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visited_at TIMESTAMPTZ DEFAULT NOW(),
    page_url TEXT,
    user_agent TEXT
);

ALTER TABLE page_views ENABLE ROW LEVEL SECURITY;

-- Anyone (including unauthenticated visitors) can insert page views
DROP POLICY IF EXISTS "Allow public inserts" ON page_views;
CREATE POLICY "Allow public inserts"
ON page_views FOR INSERT
TO anon, authenticated
WITH CHECK (true);

-- Anyone can read page views (for the counter)
DROP POLICY IF EXISTS "Allow public reads" ON page_views;
CREATE POLICY "Allow public reads"
ON page_views FOR SELECT
TO anon, authenticated
USING (true);

-- Store paragraph chunks separately from the existing sentence-level data.
CREATE TABLE IF NOT EXISTS paragraph_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    talk_id UUID NOT NULL,
    title TEXT NOT NULL,
    speaker TEXT,
    calling TEXT,
    year INTEGER,
    season TEXT,
    url TEXT,
    paragraph_num INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (talk_id, paragraph_num)
);

CREATE INDEX IF NOT EXISTS paragraph_embeddings_talk_order_idx
ON paragraph_embeddings(talk_id, paragraph_num);

CREATE INDEX IF NOT EXISTS paragraph_embeddings_embedding_hnsw_idx
ON paragraph_embeddings USING hnsw (embedding vector_cosine_ops);

ALTER TABLE paragraph_embeddings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow authenticated users to read paragraphs" ON paragraph_embeddings;
CREATE POLICY "Allow authenticated users to read paragraphs"
ON paragraph_embeddings FOR SELECT
TO authenticated
USING (true);

-- Return distinct filter values from either chunk table, visible under RLS.
CREATE OR REPLACE FUNCTION get_search_filter_options()
RETURNS TABLE (
  year integer,
  season text,
  speaker text
)
LANGUAGE sql STABLE
AS $$
  SELECT DISTINCT
    filter_values.year,
    filter_values.season,
    filter_values.speaker
  FROM (
    SELECT se.year, se.season, se.speaker FROM sentence_embeddings AS se
    UNION
    SELECT pe.year, pe.season, pe.speaker FROM paragraph_embeddings AS pe
  ) AS filter_values
  WHERE filter_values.year IS NOT NULL
     OR filter_values.season IS NOT NULL
     OR (filter_values.speaker IS NOT NULL AND btrim(filter_values.speaker) <> '')
  ORDER BY filter_values.year DESC NULLS LAST,
           filter_values.season NULLS LAST,
           filter_values.speaker NULLS LAST;
$$;

GRANT EXECUTE ON FUNCTION get_search_filter_options() TO authenticated;

-- Recreate similarity search with optional year, month (stored as season), and speaker filters.
DROP FUNCTION IF EXISTS match_sentences(vector, integer);
CREATE OR REPLACE FUNCTION match_sentences(
  query_embedding vector(1536),
  match_count int DEFAULT 20,
  filter_year integer DEFAULT NULL,
  filter_season text DEFAULT NULL,
  filter_speaker text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  talk_id uuid,
  title text,
  speaker text,
  url text,
  text text,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    sentence_embeddings.id,
    sentence_embeddings.talk_id,
    sentence_embeddings.title,
    sentence_embeddings.speaker,
    sentence_embeddings.url,
    sentence_embeddings.text,
    1 - (sentence_embeddings.embedding <=> query_embedding) as similarity
  FROM sentence_embeddings
  WHERE sentence_embeddings.embedding IS NOT NULL
    AND (filter_year IS NULL OR sentence_embeddings.year = filter_year)
    AND (filter_season IS NULL OR sentence_embeddings.season = filter_season)
    AND (filter_speaker IS NULL OR sentence_embeddings.speaker = filter_speaker)
  ORDER BY sentence_embeddings.embedding <=> query_embedding
  LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_sentences(vector, integer, integer, text, text) TO authenticated;

-- Paragraph-level vector search with the same optional UI filters.
DROP FUNCTION IF EXISTS match_paragraphs(vector, integer);
DROP FUNCTION IF EXISTS match_paragraphs(vector, integer, integer, text, text);
CREATE FUNCTION match_paragraphs(
  query_embedding vector(1536),
  match_count integer DEFAULT 20,
  filter_year integer DEFAULT NULL,
  filter_season text DEFAULT NULL,
  filter_speaker text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  talk_id uuid,
  title text,
  speaker text,
  url text,
  text text,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    pe.id,
    pe.talk_id,
    pe.title,
    pe.speaker,
    pe.url,
    pe.text,
    1 - (pe.embedding <=> query_embedding) AS similarity
  FROM paragraph_embeddings AS pe
  WHERE pe.embedding IS NOT NULL
    AND (filter_year IS NULL OR pe.year = filter_year)
    AND (filter_season IS NULL OR pe.season = filter_season)
    AND (filter_speaker IS NULL OR pe.speaker = filter_speaker)
  ORDER BY pe.embedding <=> query_embedding
  LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_paragraphs(vector, integer, integer, text, text) TO authenticated;
"""

    url = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json={"query": schema_sql})
    if resp.status_code in (200, 201):
        print("✅ Database schema created successfully!")
    else:
        print(f"❌ Schema creation failed: {resp.status_code}")
        print(resp.text[:500])
        return False

    # Verify table exists via PostgREST
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    for attempt in range(5):
        try:
            result = client.table('sentence_embeddings').select('id', count='exact').limit(1).execute()
            print(f"✅ sentence_embeddings verified. Current rows: {result.count or 0}")
            paragraph_result = client.table('paragraph_embeddings').select('id', count='exact').limit(1).execute()
            print(f"✅ paragraph_embeddings verified. Current rows: {paragraph_result.count or 0}")
            return True
        except Exception:
            if attempt < 4:
                print(f"   Waiting for schema cache to refresh... ({attempt + 1}/5)")
                time.sleep(3)
            else:
                print("⚠️  Table created but PostgREST cache hasn't refreshed yet.")
                print("   This is normal — it should be ready by import time.")
                return True


if __name__ == '__main__':
    if not create_schema():
        sys.exit(1)
    print("\n✅ Schema ready! Next: python scripts/02_scrape_data.py")
