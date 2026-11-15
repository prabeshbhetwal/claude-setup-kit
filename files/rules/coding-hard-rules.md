---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs,cjs,py,go,rs,java,kt,swift,rb,php,cs,c,cpp,h,hpp,vue,svelte,sql,sh}"
---
# Coding Hard Rules

- Source files ≤300 lines; near 250, extract helpers, types and sub-components into sibling modules or domain folders.
- Keep domain models, data access, external integrations and orchestrators in separate files. Never duplicate logic; extract shared routines into common utilities.
- Small, well-typed interfaces; no barrel exports (`index.ts`); explicit, local imports.
- After code changes: run lint, format and unit tests. Reject copy-paste fixes.
- Ponytail picks the smallest change; the 300-line ceiling wins when they conflict.
