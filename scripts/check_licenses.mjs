import { readFileSync } from "node:fs";

const allowed = new Set([
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "BlueOak-1.0.0",
  "CC0-1.0",
  "ISC",
  "MIT",
  "MIT-0",
  "MPL-2.0",
  "Python-2.0",
]);

// caniuse-lite's CC-BY-4.0 covers its browser-support dataset, not the app code.
const notices = new Map([["node_modules/caniuse-lite", "CC-BY-4.0"]]);

const lockfile = JSON.parse(readFileSync("web/package-lock.json", "utf8"));
const failures = [];

for (const [path, metadata] of Object.entries(lockfile.packages ?? {})) {
  if (!path.startsWith("node_modules/")) {
    continue;
  }
  const license = metadata.license ?? "UNKNOWN";
  if (notices.get(path) === license) {
    continue;
  }
  const expression = license.replace(/[()]/g, "");
  const terms = expression.split(/\s+(?:OR|AND)\s+/);
  if (!terms.every((term) => allowed.has(term))) {
    failures.push(`${path}: ${license}`);
  }
}

if (failures.length > 0) {
  console.error("Unapproved frontend dependency licenses:");
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log("Frontend dependency licenses are approved.");
}
