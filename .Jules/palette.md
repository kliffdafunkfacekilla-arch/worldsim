
## 2024-05-26 - Asynchronous Loading States in Dashboard
**Learning:** During map refresh, users had no visual indication that the button click registered until the map updated, leading to potential duplicate clicks. Also, screen readers lacked context for icon-only buttons and the map canvas.
**Action:** Always bind the `disabled` attribute on submission/refresh buttons to the start of asynchronous JS functions, and clean it up in a `finally` block. Added `aria-label` to the map and `aria-busy` to the loading overlay to communicate state changes to assistive tech.
