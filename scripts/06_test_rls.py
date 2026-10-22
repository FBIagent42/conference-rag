"""Quickly check the public and authenticated-only table policies using the anon key.

Usage:
    python scripts/06_test_rls.py

Requires config.public.json with SUPABASE_URL and SUPABASE_ANON_KEY.
Does not load or use config.secret.json.
"""

import json

from supabase import create_client


with open("config.public.json", "r", encoding="utf-8") as f:
    public = json.load(f)

client = create_client(public["SUPABASE_URL"], public["SUPABASE_ANON_KEY"])


def check_public_page_views():
    try:
        result = client.table("page_views").select("*").limit(5).execute()
        print(f"page_views: query allowed; received {len(result.data or [])} rows")
    except Exception as exc:
        print(f"page_views: query failed: {exc}")


def check_protected_embeddings(table_name):
    try:
        result = client.table(table_name).select("*").limit(5).execute()
        rows = result.data or []
        if rows:
            print(
                f"{table_name}: UNEXPECTED access; received {len(rows)} rows. "
                "Review the table's RLS policies."
            )
        else:
            print(
                f"{table_name}: 0 rows, as expected for anon. "
                "This could also mean the table is empty."
            )
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "42501" in message or "permission denied" in lowered or "not allowed" in lowered:
            print(f"{table_name}: access denied for anon, as expected")
        else:
            print(f"{table_name}: query failed: {message}")


if __name__ == "__main__":
    check_public_page_views()
    check_protected_embeddings("sentence_embeddings")
    check_protected_embeddings("paragraph_embeddings")
