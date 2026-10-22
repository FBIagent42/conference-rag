import { getAuthenticatedUser } from "../_shared/auth.ts";
import { getCorsHeaders } from "../_shared/cors.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

function normalizeQuestion(question: string): string {
  return question.normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();
}

function parseEmbedding(value: unknown): number[] | null {
  let parsed = value;
  // PostgREST can return pgvector values as their textual representation.
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return null;
    }
  }

  if (
    !Array.isArray(parsed) || parsed.length !== 1536 ||
    !parsed.every((item) => typeof item === "number" && Number.isFinite(item))
  ) {
    return null;
  }
  return parsed;
}

function createCacheClient() {
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) return null;

  // This privileged client is server-side only. The cache table has RLS
  // enabled without client policies, so it must never be sent to the browser.
  return createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

async function findCachedEmbedding(
  cacheClient: ReturnType<typeof createClient>,
  normalizedQuestion: string,
): Promise<number[] | null> {
  const { data, error } = await cacheClient
    .from("question_embedding_cache")
    .select("embedding")
    .eq("normalized_question", normalizedQuestion)
    .maybeSingle();

  if (error) throw error;
  if (!data) return null;
  return parseEmbedding(data.embedding);
}

function jsonResponse(
  request: Request,
  body: Record<string, unknown>,
  status = 200,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...getCorsHeaders(request),
      "Content-Type": "application/json",
    },
  });
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: getCorsHeaders(request) });
  }

  if (request.method !== "POST") {
    return jsonResponse(request, { error: "Method not allowed" }, 405);
  }

  // Authenticate before parsing the question or calling OpenAI.
  const auth = await getAuthenticatedUser(request);
  if (!auth.ok) {
    return jsonResponse(request, { error: auth.message }, auth.status);
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, { error: "Request body must be valid JSON" }, 400);
  }

  if (typeof payload !== "object" || payload === null || !("question" in payload)) {
    return jsonResponse(request, { error: "Provide a question in the request body" }, 400);
  }

  const question = (payload as { question?: unknown }).question;
  if (typeof question !== "string" || !question.trim()) {
    return jsonResponse(request, { error: "Question must be a non-empty string" }, 400);
  }
  if (question.length > 2000) {
    return jsonResponse(request, { error: "Question is too long (maximum 2,000 characters)" }, 400);
  }

  const normalizedQuestion = normalizeQuestion(question);
  const cacheClient = createCacheClient();

  if (cacheClient) {
    try {
      const cachedEmbedding = await findCachedEmbedding(cacheClient, normalizedQuestion);
      if (cachedEmbedding) {
        console.log("Question embedding cache hit");
        return jsonResponse(request, { embedding: cachedEmbedding });
      }
    } catch (error) {
      // Caching is an optimization; a cache lookup issue should not prevent
      // the normal embedding flow from working.
      console.error("Question embedding cache lookup failed:", error);
    }
  } else {
    console.error("Question embedding cache unavailable: Supabase service role is not configured");
  }

  const openAiApiKey = Deno.env.get("OPENAI_API_KEY");
  if (!openAiApiKey) {
    console.error("OPENAI_API_KEY Edge Function secret is not configured");
    return jsonResponse(request, { error: "Embedding service is not configured" }, 500);
  }

  try {
    const openAiResponse = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${openAiApiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "text-embedding-3-small",
        input: question.trim(),
      }),
    });

    if (!openAiResponse.ok) {
      console.error("OpenAI embedding request failed with status", openAiResponse.status);
      return jsonResponse(request, { error: "OpenAI embedding request failed" }, 502);
    }

    const result = await openAiResponse.json();
    const embedding = result?.data?.[0]?.embedding;
    if (!Array.isArray(embedding) || embedding.length !== 1536) {
      console.error("OpenAI returned an invalid embedding response");
      return jsonResponse(request, { error: "Invalid embedding response" }, 502);
    }

    if (cacheClient) {
      try {
        const { error: insertError } = await cacheClient
          .from("question_embedding_cache")
          .insert({ normalized_question: normalizedQuestion, embedding });

        if (insertError?.code === "23505") {
          // Another request may have inserted the same question while OpenAI
          // was generating this vector. Use the winner's cached vector.
          try {
            const concurrentEmbedding = await findCachedEmbedding(cacheClient, normalizedQuestion);
            if (concurrentEmbedding) {
              return jsonResponse(request, { embedding: concurrentEmbedding });
            }
          } catch (error) {
            console.error("Could not read concurrently cached embedding:", error);
          }
        } else if (insertError) {
          console.error("Could not save question embedding to cache:", insertError);
        }
      } catch (error) {
        // If saving fails, still return the vector so semantic search works.
        console.error("Question embedding cache insert failed:", error);
      }
    }

    return jsonResponse(request, { embedding });
  } catch (error) {
    console.error("Embedding request failed:", error);
    return jsonResponse(request, { error: "Could not generate an embedding" }, 502);
  }
});
