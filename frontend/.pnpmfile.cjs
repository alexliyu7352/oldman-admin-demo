const { existsSync } = require("node:fs");
const { resolve } = require("node:path");

const localPackage = resolve(
  __dirname,
  "../.local/oldman/frontend/packages/oldman-web"
);

module.exports = {
  hooks: {
    readPackage(packageManifest) {
      if (
        packageManifest.name === "oldman-admin-demo-extension"
        && existsSync(resolve(localPackage, "package.json"))
      ) {
        packageManifest.dependencies = {
          ...packageManifest.dependencies,
          "oldman-web": `file:${localPackage}`
        };
      }
      return packageManifest;
    }
  }
};
