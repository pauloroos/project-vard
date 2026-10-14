import { defineConfig, configDefaults } from "vitest/config";

// Os testes do widget ficam em tests/; nucleo/, voz/ e reuniao/ têm suítes próprias (pytest e node --test).
export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, "nucleo/**", "voz/**", "reuniao/**", "scripts/**", ".worktrees/**", ".coordenacao/**"],
    environment: "jsdom",
  },
});
