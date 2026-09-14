# Architecture Decisions: Trello Clone Integration

This document outlines key technical decisions made during the integration of the Trello clone into smartTalim's tasks system.

## 1. Localized Translation Provider
**Decision**: Retain Trello's self-contained `LanguageContext.js` and `translations.js` inside the tasks component subtree, renaming the hooks or utilizing them inside a local context wrapper.
**Rationale**: The Trello clone features a comprehensive and specialized terminology vocabulary (over 200 items including card actions, background names, template details, etc.). Moving all of these keys into smartTalim's global translation JSON files (`uz.json` and `ru.json`) would introduce unnecessary noise and make those files less maintainable. A local provider keeps this vocabulary scoped to the Trello code.

## 2. Dependency-Free UUID Generation
**Decision**: Replace Trello's `uuid` NPM package dependency with a browser-native cryptographic UUID generator in `AppContext.js`:
```javascript
const uuidv4 = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};
```
**Rationale**: This keeps the smartTalim project package footprint minimal and avoids running unnecessary `npm install` steps, while ensuring complete reliability across modern desktop browsers.

## 3. Style Bleed Prevention (Style Scoping)
**Decision**: Scope Trello's `App.css` styles under a custom wrapper class `.trello-app-container` instead of referencing the `body` tag directly.
**Rationale**: Trello's global styles override the `body` tag's background color, margins, and default font-family. In a single page application like smartTalim, importing these styles globally would leak dark background styling and custom scrolls onto dashboard, student registry, finance, and other sections. Scoping ensures style containment.

## 4. Transition from Local Storage to Remote API
**Decision**: Replace `localStorage` synchronization with direct REST API requests to `https://musojon1995.pythonanywhere.com`.
**Rationale**: The backend has newly added endpoints supporting full Trello structures (Boards, Columns, Items, Labels, Checklists, Checklist Items, Attachments, Comments). Transitioning to REST API synchronization provides a real multi-user shared experience and aligns tasks functionality with the rest of the CRM dashboard features.

## 5. Lazy-Loading Card Sub-Relations
**Decision**: Fetch checklists, checklist items, attachments, and comments only when a card is selected (opened in `CardModal`), rather than loading them eagerly during initial board load.
**Rationale**: Eagerly loading these details would cause an N+1 query problem, forcing the browser to issue dozens of parallel network requests for a populated board. Lazy-loading on card open keeps initial load lightweight, saves server resources, and remains seamless to the end user.

## 6. Color Management via Theme CSS Variables
**Decision**: Refactor all hardcoded component colors (across 12 CSS files) to use CSS variables defined under the root `.trello-app-container` class, with specific overrides in dark mode.
**Rationale**: This enables dynamic, instant dark/light mode switches across all boards, card details, lists, menus, and setting dialogues. By centralizing the theme properties in `App.css`, we avoid color inconsistencies and ensure readability under any system-level theme.

## 7. Global Layout and Height Isolation
**Decision**: Use `:not(.trello-app-container *)` exclusion filters on global element rules (like `button`, `input`, and `.modal-content input`) in `src/index.css`.
**Rationale**: Global rules forcing `height: 40px !important` on all buttons and 100% width on modal inputs broke the layout of components in the tasks board (overlapping checkbox list items, compressed settings options, and oversized icon buttons). Excluding the tasks container ensures that the tasks board's own spacing, sizing, and styling rules are respected.

## 8. Card Detail Modal Stacking Context Elevation
**Decision**: Elevate the inline styling of `zIndex` on the `.task-card-modal-header` from `10` to `10050`.
**Rationale**: The `...` actions button and the list switcher dropdowns inside the card modal header rendered underneath the body's quick action buttons (like `+ Qo'shish`, `Yorliqlar`). This occurred because the header's stacking context was capped at `zIndex: 10`, while the action buttons in the modal body resided inside `.relative` wrappers with `z-index: 10020`. Elevating the header's z-index to `10050` puts the header and its dropdown children above the body elements, resolving all rendering and overlap issues.

## 9. Refactoring Hardcoded Inline Colors in JSX style Attributes
**Decision**: Programmatically refactor all hardcoded hex colors and theme colors inside React `style` attributes in `CardModal.jsx` (such as `#e8edf2`, `#b6c2cf`, `#22272b`, `#2c333a`, `#3d4b5c`) to utilize dynamic CSS variables.
**Rationale**: Inline styles have the highest specificity in CSS, which meant the card modal title, comment fields, settings labels, and dropdown panels retained hardcoded dark theme colors (e.g., light gray title on a white background) even when the user toggled the application to light mode. Transitioning these inline styles to CSS variable references (e.g. `var(--tasks-text-primary)`) ensures the modal's internal text and inputs adapt to light and dark themes correctly.

## 10. Rich Markdown Editor for Card Description
**Decision**: Implement a custom, dependency-free markdown parser and formatting toolbar inside `CardModal.jsx` for editing the card description.
**Rationale**: Users expect rich-text controls (headers, bold, italics, strikethroughs, lists, links) inside descriptions. Writing a lightweight regex-based `parseMarkdown` function and toolbar insertion helper enables this native formatting experience without importing large external NPM packages, keeping the smartTalim bundle size minimal.

## 11. Nested Task History API Endpoint Integration
**Decision**: Integrate the nested API endpoint `/api/v1/tasks/items/<id>/history/` to fetch actual actions and logs of tasks instead of utilizing mock data inside the `CardModal` feed.
**Rationale**: Showing actual users' actions (movements, checklists edits, creation, edits) creates a real-world collaboration experience. Since organization isolation is key, retrieving `org_id` from localStorage and injecting it via custom `x-org-id` headers ensures context isolation matching backend specifications.

## 12. Consolidation of Home Dashboard into Board Selector Modal
**Decision**: Remove the full-page Home dashboard (`Home.jsx`) and replace its board management functionality with a compact `BoardSelectorModal` triggered from the board header's grid icon button.
**Rationale**: The Home dashboard occupied an entire page to display boards, favorites, templates, and workspace settings — functionality that duplicated what was already accessible from the board header menu and sidebar. Consolidating board creation, renaming, background switching, deletion, and board switching into a single modal reduces navigation friction and keeps the user focused on the active board. The tasks page now always renders a board directly (or a blank state if none exist), eliminating the extra routing layer (`currentView: 'home' | 'board'`). This also simplifies the `AppContext` state management by auto-selecting the first available board on initial load and after deletion/closing, removing the need for manual view toggling.

## 13. Resolving Datetime Validation and ISO Parsing
**Decision**: Format JSON-formatted dates from state into ISO-8601 `YYYY-MM-DDThh:mm:ss` format inside `updateCard` in `AppContext.jsx` before making request to `tasksApi`, and add regex-based ISO-8601 extraction logic in `parseCardDates` in `CardModal.jsx`.
**Rationale**: The backend `due_date` column is a strict Django/Postgres DateTime field that rejects JSON-stringified payloads with a 400 Bad Request error. Normalizing dates into ISO format solves validation errors while remaining backward compatible, and regex extraction allows displaying standard API datetime fields correctly on card reload.

## 14. Split Scrollable Panels for Card Modal Details & Comments
**Decision**: When the comments/activity panel is active, set the height of `.task-card-modal-body` to 100% of the remaining modal height, hide its overflow, and enable vertical scrolling (`overflowY: 'auto'`) independently on `.task-card-modal-content` (left details pane) and `.task-card-modal-right-panel` (right comments pane).
**Rationale**: If a card has extensive descriptions, attachments, checklists, and comments, a single scrollbar on the modal container causes the text-editor, covers, header buttons, and comment input fields to scroll out of view. Enabling independent scrolling mimics premium Trello/Jira UX, keeping comments and details readable and interactive without disorienting layout movements.


