# ANTIGRAVITY AGENT RULES

## Qat'iy Muhandislik Qoidalari (Strict Engineering Rules)

1. **Topshiriq chegarasi (Strict Scoping)**:
   - Faqat ko'rsatilgan aniq fayl, klass yoki funksiya doirasida ishlang.
   - Topshiriqda ko'rsatilmagan begona fayllarga mutlaqo tegmang.
2. **Kichik va aniq diff (Minimal Diffs)**:
   - Har bir javobdan so'ng diff qat'iy tekshiriladi.
   - 50-100 qatordan katta har qanday o'zgarishga shubha bilan qarang va keraksiz kod yozishdan saqlaning.
3. **Muntazam Test Verifikatsiyasi**:
   - Har qanday kod tahriridan keyin loyihadagi barcha unit va regression testlar (`python manage.py test ...`) to'liq yashil (`OK`) holatda bo'lishi shart.
4. **Moliya xavfsizligi**:
   - Moliya va hisob-kitob servislari (`finance/services/`) va ularning xatti-harakati qat'iy himoyalangan (`tests_characterization.py`) holda saqlanadi.
