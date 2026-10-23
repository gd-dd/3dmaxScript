# Host compatibility packages

Layout: releases/<host-range>/<tool-version>/<tool-id>/tool.json.

Example range: 2024.1~2026.3 (inclusive). This is an example, not a compatibility claim. Current packages are unverified. Keep original script UI unchanged. After testing, publish a new package under the confirmed range, update compatibility.range and testedVersions in tool.json and tools-index.json. Do not overwrite previously released tool versions. The shelf reads tools-index.json and pins all files to one Git commit.
