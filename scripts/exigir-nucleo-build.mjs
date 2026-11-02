// Guarda do build padrão: o instalador exige o núcleo em build/nucleo/.
// Uso: beforeBuildCommand do tauri.conf.json base. Falha claramente em vez de
// gerar instalador sem núcleo; o release usa `npm run tauri:build`.
console.error(
  "Build padrão recusado: o instalador exige o núcleo em build/nucleo/.\n" +
    "Use `npm run tauri:build` (monta o núcleo e inclui no instalador).",
);
process.exit(1);
