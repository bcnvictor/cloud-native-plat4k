import { app } from "./app.js";

const port = process.env.PORT || 8000;

app.listen(port, () => {
  console.log(`node-express template listening on port ${port}`);
});
