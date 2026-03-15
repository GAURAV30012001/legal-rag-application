
// server.js
const express = require("express");
const path = require("path");

const app = express();
const staticDir = path.join(__dirname);

// Serve static files
app.use(express.static(staticDir));

// SPA fallback (optional): serve index.html for all routes
app.get("*", (req, res) => {
  res.sendFile(path.join(staticDir, "index.html"));
});

const port = process.env.PORT || 8080;
app.listen(port, () => {
  console.log(`Server listening on ${port}`);
});