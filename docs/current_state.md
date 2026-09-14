# Current State: Trello Clone Integration

This document records the current state of files, directories, and tasks during the integration process.

## Current Progress Status
- **Status**: Completed, Integrated, and Isolated
- **Date**: 2026-06-26

## File Mapping and Disposition

### 1. Legacy Tasks Files to Be Deleted/Replaced
- [x] `src/pages/tasks.jsx` -> Replaced with new Trello entrypoint
- [x] `src/components/tasks/BoardHeader.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/Card.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/CardDetailModal.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/CreateBoardPopover.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/Header.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/List.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/NewBoardModal.jsx` -> Deprecated and deleted
- [x] `src/components/tasks/NewCardModal.jsx` -> Deprecated and deleted
- [x] `src/styles/tasks.css` -> Deprecated and deleted

### 2. Files to Keep
- `src/components/tasks/ScheduledMessages.jsx` (Used by Scheduled Messages feature)
- `src/components/tasks/ScheduledMessages.css` (Used by Scheduled Messages feature)

### 3. Trello Clone Source Directory
- [x] Folder: `src/trellom/src/` -> Transferred to `src/components/tasks/`
- [x] Folder: `src/trellom/` -> Deleted duplicate files

### 4. API Backend Connection Files
- [x] `src/api/tasksApi.js` -> Expanded for labels, checklists, checklist items, attachments, comments
- [x] `src/components/tasks/context/AppContext.jsx` -> Rewritten to replace localStorage with API calls, and resolved the `handleSetCurrentBoardId` reference error

## Final Actions Completed
1. Extended the API endpoints inside `tasksApi.js` to map checklists, items, labels, and attachments.
2. Synchronized `AppContext.jsx` with PythonAnywhere CRM backend API endpoints.
3. Implemented detail lazy-loading to optimize DB load.
4. Resolved esbuild issues and verified Vite compilation output.
5. Fixed `handleSetCurrentBoardId` reference issue in `AppContext.jsx`.
6. Refactored hardcoded colors across 12 component CSS files to use CSS variables defined in `App.css`.
7. Applied `:not(.trello-app-container *)` selectors in `src/index.css` to exclude the tasks board from global input/button height overrides, correcting overlap and spacing.
8. Created architectural design documentation (`docs/architecture.md`) and updated roadmap and decisions logs.
9. Elevated the CardModal header z-index to `10050` to resolve stacking context limits and ensure dropdown popovers render on top of body quick action buttons.
10. Refactored hardcoded hex and name colors in `CardModal.jsx` style attributes (including card titles, text containers, settings labels, and comment inputs) to use CSS variable references, enabling clear readability in light mode.
11. Implemented a rich markdown description editor with toolbar (Bold, Italic, Strikethrough, Headings, Lists, Links), `parseMarkdown` renderer, and formatting help popup — all dependency-free.
12. Integrated the task history API endpoint (`/api/v1/tasks/items/<id>/history/`) inside `tasksApi.js`, set up automatic `x-org-id` heading injection from localStorage, lazy-loaded it inside `AppContext.jsx`, and displayed actual activities inside the `CardModal` feed.
13. Removed the Trello Home dashboard page (`Home.jsx`, `Home.css`) and all routing logic. Updated `tasks.jsx` to always render `Board` directly. Created `BoardSelectorModal` component for managing boards from the board header grid button. Added `updateBoard` function and auto-select logic in `AppContext.jsx`. Added blank state UI for zero boards.

### 5. Phase 9: Board Management Consolidation
- [x] `src/components/tasks/pages/Home.jsx` -> Deleted (replaced by BoardSelectorModal)
- [x] `src/components/tasks/pages/Home.css` -> Deleted (replaced by BoardSelectorModal)
- [x] `src/components/tasks/components/BoardSelectorModal.jsx` -> New (board rename, switch, delete, background picker)
- [x] `src/components/tasks/components/BoardSelectorModal.css` -> New (premium dark/light theme styles)
- [x] `src/pages/tasks.jsx` -> Updated (always renders Board, no Home conditional)
- [x] `src/components/tasks/context/AppContext.jsx` -> Updated (auto-select first board, updateBoard function, smart delete/close)
- [x] `src/components/tasks/pages/Board.jsx` -> Updated (blank state, board selector modal integration)
- [x] `src/components/tasks/components/BoardMenu.jsx` -> Updated (removed setCurrentView('home'))
- [x] `src/components/tasks/i18n/translations.js` -> Updated (board management keys in uz/ru/en)

