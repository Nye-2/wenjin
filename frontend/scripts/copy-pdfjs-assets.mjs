import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const publicPdfjs = join(root, "public", "pdfjs");
const pdfjsDist = join(root, "node_modules", "pdfjs-dist");

await rm(publicPdfjs, { recursive: true, force: true });
await mkdir(publicPdfjs, { recursive: true });

await cp(join(pdfjsDist, "cmaps"), join(publicPdfjs, "cmaps"), {
  recursive: true,
});
await cp(join(pdfjsDist, "standard_fonts"), join(publicPdfjs, "standard_fonts"), {
  recursive: true,
});
