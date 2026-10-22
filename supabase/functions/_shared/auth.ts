import { createClient, type User } from "npm:@supabase/supabase-js@2";

export type AuthResult =
  | { ok: true; user: User }
  | { ok: false; status: number; message: string };

/** Validate the bearer token with Supabase Auth before processing a request. */
export async function getAuthenticatedUser(request: Request): Promise<AuthResult> {
  const authorization = request.headers.get("Authorization");
  const match = authorization?.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return { ok: false, status: 401, message: "Missing bearer token" };
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY");
  if (!supabaseUrl || !supabaseAnonKey) {
    console.error("Supabase Auth environment is not configured");
    return { ok: false, status: 500, message: "Authentication is not configured" };
  }

  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    const { data, error } = await supabase.auth.getUser(match[1]);
    if (error || !data.user) {
      return { ok: false, status: 401, message: "Invalid or expired access token" };
    }
    return { ok: true, user: data.user };
  } catch (error) {
    console.error("Supabase Auth verification request failed:", error);
    return { ok: false, status: 503, message: "Could not verify the access token" };
  }
}
