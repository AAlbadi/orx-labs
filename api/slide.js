export default async function handler(req, res) {
  const { u, url, src } = req.query;
  const target = u || url || src;
  if (!target) {
    return res.status(400).send("Missing target image URL (?u=...)");
  }

  try {
    let fetchUrl = target;
    if (!target.startsWith("http://") && !target.startsWith("https://")) {
      try {
        fetchUrl = Buffer.from(target, "base64").toString("utf-8");
      } catch (_) {}
    }

    const upstream = await fetch(fetchUrl, {
      headers: {
        "User-Agent": "TikTok-Media-Relay/1.0",
      },
    });

    if (!upstream.ok) {
      return res.status(upstream.status).send("Upstream error: " + upstream.statusText);
    }

    let contentType = upstream.headers.get("content-type") || "image/jpeg";
    if (req.url.includes(".jpg") || req.url.includes(".jpeg") || req.query.format === "jpg") {
      contentType = "image/jpeg";
    }
    res.setHeader("Content-Type", contentType);
    res.setHeader("Cache-Control", "public, max-age=86400, s-maxage=86400");
    res.setHeader("Access-Control-Allow-Origin", "*");

    const arrayBuffer = await upstream.arrayBuffer();
    return res.status(200).send(Buffer.from(arrayBuffer));
  } catch (err) {
    return res.status(500).send("Relay error: " + err.message);
  }
}
