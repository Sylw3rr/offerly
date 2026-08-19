/**
 * Cloudflare Email Worker — hands forwarded mail to Offerly.
 *
 * Routing sends every address on the zone here. This does as little as it can:
 * reads the message, signs it with the shared secret, and posts it. It does not
 * parse MIME — the application does that, with a standard library that has met
 * far more broken mail than anything worth maintaining here.
 *
 * Deploy: Cloudflare → Email → Email Routing → Email Workers.
 * Secrets (Settings → Variables): OFFERLY_ENDPOINT, OFFERLY_SECRET.
 */

const MAX_BYTES = 512 * 1024;

async function sign(secret, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async email(message, env) {
    // `message.to` is the envelope recipient — the address that actually
    // routed here, which for a catch-all is not always the To: header.
    const raw = await new Response(message.raw).text();

    const payload = JSON.stringify({
      to: message.to,
      from: message.from,
      message_id: message.headers.get("message-id") || "",
      raw: raw.length > MAX_BYTES ? raw.slice(0, MAX_BYTES) : raw,
    });

    const response = await fetch(env.OFFERLY_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Offerly-Signature": await sign(env.OFFERLY_SECRET, payload),
      },
      body: payload,
    });

    // Rejecting the message tells the sending server to retry, which is what
    // should happen if Offerly is down — better than losing the mail.
    if (!response.ok) {
      message.setReject(`Offerly returned ${response.status}`);
    }
  },
};
