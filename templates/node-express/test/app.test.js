import { test } from "node:test";
import assert from "node:assert";
import { app } from "../src/app.js";

test("GET /healthz returns ok", async () => {
  const server = app.listen(0);
  const { port } = server.address();
  try {
    const res = await fetch(`http://127.0.0.1:${port}/healthz`);
    const body = await res.json();
    assert.strictEqual(res.status, 200);
    assert.strictEqual(body.status, "ok");
  } finally {
    server.close();
  }
});
