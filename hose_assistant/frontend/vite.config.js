import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  // Relative base: the SPA must work under HA Ingress's proxied path.
  base: "",
  plugins: [preact(), tailwindcss()],
  build: { outDir: "dist", emptyOutDir: true },
});
