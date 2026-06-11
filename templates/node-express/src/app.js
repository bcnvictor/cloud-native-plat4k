import express from "express";

export const app = express();

app.get("/", (req, res) => {
  res.json({ message: "Hello from the CNP node-express template" });
});

app.get("/healthz", (req, res) => {
  res.json({ status: "ok" });
});
