# Localization: Russian & Uzbek Language Support

This document outlines the localization strategy, component integration, and progress status of the translation process in smartTalim.

---

## 1. Localization Architecture

Translation is driven by a React context provider (`LanguageContext.jsx`) which exposes the active language (`uz` or `ru`) and a utility translation hook `t(key, fallback)`.

- **Context Location**: `src/context/LanguageContext.jsx`
- **Dictionaries**:
  - `src/translations/uz.json` (Uzbek locale file)
  - `src/translations/ru.json` (Russian locale file)

### Usage Pattern in Components
```javascript
import { useLanguage } from "../../context/LanguageContext";

const MyComponent = () => {
  const { t } = useLanguage();
  
  return (
    <div>
      <h2>{t("namespace.keyTitle", "Default Uzbek Title")}</h2>
    </div>
  );
};
```

---

## 2. Completed Modules

### Phase A: Groups Section (`Guruhlar`)
Successfully localized all attendance, reschedule, and group management screens.

- **Key Component**: [Group-item.jsx](file:///home/lite/Documents/smartTalim/src/components/groups/Group-item.jsx)
- **Translated Elements**:
  - Sub-navigation Tabs: `O'quvchilar` (Students), `Davomat` (Attendance), `Topshiriqlar` (Homework), `Guruh tarixi` (History).
  - Attendance Grid Tooltips: Cell status types (`Keldi`, `Bekor`, `Baho`, `Dam olish kuni`, `Imtihon`).
  - Dars Scheduler Modals: Topic inputs, scheduling popovers, and student suspension/removal confirmations.
  - Date and Month formatters.

### Phase B: Students Section (`Talabalar`)
All user-facing tables, detail views, and entry forms are fully translated under the `"students"` namespace.

- **Key Components**:
  - [Students.jsx](file:///home/lite/Documents/smartTalim/src/pages/Students.jsx) (Main student list page, Excel export utilities, filters, search bar).
  - [Profile.jsx](file:///home/lite/Documents/smartTalim/src/components/students/Profile.jsx) (Detail page including tab mapping via dynamic keys, note editors).
  - [AddStudentModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/AddStudentModal.jsx) & [EditStudentModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/EditStudentModal.jsx) (Creation and update inputs, validation warnings, dynamic field list labels).
  - [PaymentModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/PaymentModal.jsx) (Payment methods and amount input fields).
  - [ReceiptModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/ReceiptModal.jsx) (Payment checkout previews, receipts, barcode lines, print labels, cashiers, metadata).
  - [SmsModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/SmsModal.jsx) (SMS dispatch console).
  - [AddGroupModal.jsx](file:///home/lite/Documents/smartTalim/src/components/students/AddGroupModal.jsx) (Enrolling students into active groups).

---

## 3. Best Practices for Adding Translations

1. **Keep Fallbacks Consistent**:
   Always provide the original Uzbek text as the second argument in `t()`. This acts as a robust fail-safe.
2. **Translate dynamic array mappings outside hooks**:
   If list definitions (e.g. status lists, input descriptors) are declared outside the functional component where `t` is unavailable, refactor the structure to use key references:
   ```javascript
   // Define meta keys outside
   const fields = [
     { name: "first_name", labelKey: "students.firstName", labelDefault: "Ism" }
   ];
   
   // Map them inside the component
   {fields.map(f => (
     <label>{t(f.labelKey, f.labelDefault)}</label>
   ))}
   ```
3. **Update both JSON files**:
   When introducing a new key inside a component, immediately add the respective properties to both `uz.json` and `ru.json` to keep translation tables synced.
