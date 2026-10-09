// @ts-check
import tseslint from "typescript-eslint";

import base from "../../eslint.config.mjs";

export default tseslint.config(...base, ...tseslint.configs.recommended);
