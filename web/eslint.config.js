import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-webodm"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  { files: ["*.config.*"], extends: [tseslint.configs.disableTypeChecked] },
);
