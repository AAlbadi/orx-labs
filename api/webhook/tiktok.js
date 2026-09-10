export default async function handler(req, res) {
  // TikTok Webhook Endpoint
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, TikTok-Signature");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const challenge = req.query?.challenge || req.body?.challenge;
  if (challenge) {
    return res.status(200).json({ challenge: challenge });
  }

  if (req.method === "POST") {
    return res.status(200).json({ status: "ok", received: true });
  }

  return res.status(200).json({ status: "ok", service: "tiktok-webhook" });
}
