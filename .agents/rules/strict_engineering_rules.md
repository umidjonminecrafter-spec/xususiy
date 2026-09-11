# STRICT ENGINEERING AND WORKFLOW RULES FOR ANTIGRAVITY

Ushbu qoidalar SmartTa'lim loyihasida kod sifati, barqarorlik va regressiyalarni oldini olish uchun qat'iy amal qilinishi shart bo'lgan talablardir:

---

## 1. Topshiriqlar berish va bajarish chegaralari (Strict Scoping)
- **Aniq nishon (Targeted Scope)**: Har bir task faqat aniq ko'rsatilgan fayl va klass/funksiya doirasida bajariladi. Topshiriqda ko'rsatilmagan boshqa fayllarga asossiz tegilmaydi ("boshqa hech qanday faylga tegma").
- **Katta va umumiy o'zgarishlar taqiqlanadi**: Hech qachon noaniq topshiriqlar asosida butun loyihaga ta'sir qiluvchi umumiy o'zgarishlar qilinmaydi.
- **Diff nazorati va minimal o'zgarish**: 
  - Har bir o'zgarishdan so'ng diff qat'iy ko'rib chiqiladi.
  - Bitta o'zgarish 50-100 qatordan oshishi qat'iy nazorat qilinadi va asossiz shishirilmaydi.

---

## 2. Ishlash tartibi (7-bosqichli standart)
Har qanday task quyidagi ketma-ketlikda bajariladi:
1. **DIAGNOSE** — Muammoning aniq kontekstini tushunish.
2. **ROOT CAUSE** — Xatolik yoki talabning asl sababini aniqlash.
3. **EXISTING CODE SEARCH** — Mavjud servis va modellardan foydalanish, ortiqcha kod yozmaslik.
4. **IMPACT ANALYSIS** — O'zgarishning boshqa modullarga ta'sirini tahlil qilish.
5. **MINIMAL FIX** — Faqat zarur bo'lgan minimal, toza va optimal kodni yozish.
6. **TEST** — Barcha testlarni (`manage.py test ...`) yugurtirib, 0 error/0 failure holatini tasdiqlash.
7. **PERFORMANCE CHECK** — N+1 so'rovlar, xotira yoki ortiqcha yuklama yo'qligini tekshirish.

---

## 3. Shartnoma va API himoyasi (Zero Breaking Changes)
- Mavjud Frontend/API shartnomalari (Contract) va response formatlari o'zgartirilmaydi.
- Moliyaviy hisob-kitoblar (`finance/services/` va `finance/tests_characterization.py`) doimo himoyalangan va 'muzlatilgan' holda qoladi.
