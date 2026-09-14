# Roadmap: Trello Clone Integration into smartTalim Tasks

This document tracks the chronological steps of replacing the simple Tasks page in the project with the advanced Trello clone app and integrating it with the Django REST API backend.

## Steps

- [x] **Phase 1: Planning and Setup**
  - [x] Analyze codebase structure and identify target files to replace
  - [x] Gather Trello clone files from `src/trellom/`
  - [x] Design integration and scoped stylesheet strategy to avoid style bleeding
  - [x] Initialize documentation under `docs/` (`roadmap.md`, `decisions.md`, `current_state.md`)
- [x] **Phase 2: File Transfer and Cleanup**
  - [x] Move Trello clone pages, components, context, and i18n from `src/trellom/src/` to `src/components/tasks/`
  - [x] Clean up deprecated tasks files in `src/components/tasks/` (leaving `ScheduledMessages.*` untouched)
- [x] **Phase 3: Code Integration and Adaptation**
  - [x] Replace external package `uuid` with a built-in cryptographic random UUID generator to keep the project lightweight and dependency-free
  - [x] Wrap Trello's App in `trello-app-container` class and scope style files to prevent global style bleeding (specifically body backgrounds/margins)
  - [x] Create the new entrypoint `src/pages/tasks.jsx` wrapping Trello in `LanguageProvider` and `AppProvider`
- [x] **Phase 4: Backend API Integration**
  - [x] Extend `src/api/tasksApi.js` to support new API endpoints: Labels, Checklists, Checklist Items, Attachments, and Comments.
  - [x] Connect `AppContext.jsx` state management directly to backend endpoints, replacing `localStorage` sync.
  - [x] Implement lazy-loading of checklists, attachments, and comments in `CardModal` to optimize backend request loads.
- [x] **Phase 5: Verification and Quality Assurance**
  - [x] Verify compilation and runtime performance using the local development server
  - [x] Check for style regressions on other pages of smartTalim
  - [x] Validate backend card CRUD, label assignments, checklists, comments, and file attachments
- [x] **Phase 6: Dark and Light Theme Integration**
  - [x] Define localized CSS variables in `App.css` mapping color palettes for light and dark themes
  - [x] Refactor Trello pages and subcomponents (12+ files) to use standardized variables
  - [x] Isolate the tasks sandbox styling to avoid bleeding and Bootstrap overrides
  - [x] Apply CSS `:not()` exclusions in `index.css` to protect tasks board buttons and input fields from forced global heights, resolving layout and overlapping text issues
  - [x] Elevate card detail modal header stacking context `zIndex` to `10050` to prevent dropdown menus (actions and list switcher) from rendering underneath body quick action buttons
  - [x] Refactor hardcoded inline styles in `CardModal.jsx` to use CSS variables, resolving light-mode text readability and input styling issues

- [x] **Phase 7: Rich Description Editor**
  - [x] Implement a zero-dependency markdown toolbar (Bold, Italic, Strikethrough, H1-H3, Bullet/Numbered Lists, Links)
  - [x] Build `parseMarkdown()` renderer supporting bold, italic, strikethrough, headings, lists, links, inline code, code blocks, blockquotes, and horizontal rules
  - [x] Add `DescriptionEditor` component with edit/preview toggle and formatting help popup
  - [x] Style the editor and preview using CSS variables from the tasks board theme system
  - [x] Integrate the editor into `CardModal` description section with save/cancel functionality

- [x] **Phase 8: Task History API Integration**
  - [x] Add `getHistory` function to `tasksApi.js` items endpoint with header-based `x-org-id` isolation
  - [x] Lazy-load history data during card details fetching inside `fetchCardDetails` in `AppContext.jsx`
  - [x] Map API activity logs to custom elements inside `CardModal.jsx` getActivities feed, keeping local mock logs as zaxira (fallback)

- [x] **Phase 9: Remove Home Dashboard and Add Board Selector Modal**
  - [x] Remove the Trello Home dashboard page (`Home.jsx`, `Home.css`) and all related routing logic
  - [x] Update `tasks.jsx` entrypoint to always render `Board` directly, eliminating the `currentView` conditional
  - [x] Create `BoardSelectorModal` component for managing boards (rename, change background, switch, delete) from the board header grid button
  - [x] Update `AppContext.jsx` to auto-select the first available board on initial load and after board deletion/closing
  - [x] Add `updateBoard` function to `AppContext` for generalized board property updates via PATCH API
  - [x] Add blank state UI in `Board.jsx` for when no active boards exist, with a premium create board prompt
  - [x] Register board management translation keys across Uzbek, Russian, and English languages

- [x] **Phase 10: UX Refinements and Bug Fixes**
  - [x] Convert frontend JSON-formatted dueDate to ISO-8601 string format in `AppContext.jsx` before sending to the backend API, resolving date validation failures
  - [x] Update `parseCardDates` in `CardModal.jsx` to correctly parse standard ISO-8601 date strings returned from the database into local time/date inputs and AM/PM format
  - [x] Reposition the attachment menu dropdown upward (`bottom: 'calc(100% + 4px)', top: 'auto'`) inside `CardModal.jsx` to prevent page height shifting and clipping
  - [x] Prepend the backend server base URL `VITE_API_BASE_URL` to relative paths for uploaded image and document attachments in `CardModal.jsx` to make previews and link downloads fully functional
  - [x] Implement independent scrollable panels for the left details (`.task-card-modal-content`) and right comments (`.task-card-modal-right-panel`) inside the card modal when the comments panel is active, keeping the cover and header pinned to the top of the viewport




