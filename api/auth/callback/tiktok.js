export default function handler(req, res) {
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  const code = (req.query && req.query.code) || "";
  const error = (req.query && req.query.error) || "";
  const error_desc = (req.query && req.query.error_description) || "";

  let bodyContent = "";
  if (error) {
    bodyContent = '<h1 class="err">❌ Authorization Failed</h1><p class="err">' + error + ': ' + error_desc + '</p>';
  } else {
    bodyContent = '<h1>🎉 TikTok Authorized!</h1>' +
      '<p>Copy the authorization code below and paste it back into your app:</p>' +
      '<div id="codeDisplay" class="code-box">' + (code || "No code found in URL") + '</div>' +
      '<button onclick="copyCode()">📋 Copy Authorization Code</button>';
  }

  const html = '<!DOCTYPE html>' +
'<html lang="en">' +
'<head>' +
'  <meta charset="UTF-8">' +
'  <title>TikTok Authorization - ORX Labs</title>' +
'  <style>' +
'    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }' +
'    .card { background: #161e31; border: 1px solid #2a3859; padding: 40px; border-radius: 16px; max-width: 600px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }' +
'    h1 { color: #38bdf8; margin-top: 0; }' +
'    .code-box { background: #0f172a; border: 1px solid #334155; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 1.1rem; word-break: break-all; color: #34d399; margin: 20px 0; user-select: all; }' +
'    button { background: #fe2c55; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 1rem; font-weight: bold; cursor: pointer; }' +
'    button:hover { background: #e02447; }' +
'    .err { color: #f87171; }' +
'  </style>' +
'</head>' +
'<body>' +
'  <div class="card">' +
     bodyContent +
'  </div>' +
'  <script>' +
'    function copyCode() {' +
'      const text = document.getElementById("codeDisplay").innerText;' +
'      if (text) {' +
'        navigator.clipboard.writeText(text);' +
'        alert("Authorization code copied!");' +
'      }' +
'    }' +
'  </script>' +
'</body>' +
'</html>';

  return res.status(200).send(html);
}
