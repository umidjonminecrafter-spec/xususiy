# O'rnatish va Ishga Tushirish

Ushbu bo'limda **smartTalim** loyihasini lokal kompyuterda ishga tushirish qadamlari tasvirlangan.

## Texnologiyalar steki
* **Frontend**: React (Vite, React Router DOM, Bootstrap, Chart.js / Nivo)
* **Backend**: Django REST Framework (Python)
* **Ishga tushirish vositasi**: Concurrently (frontend va backend serverlarini bir vaqtda ishga tushirish uchun)

---

## Tizimni lokal ishga tushirish bosqichlari

### 1. Repozitoriyani yuklab olish
Avval loyihani GitHub yoki boshqa git platformasidan klon qilib oling:
```bash
git clone <repo-url>
cd smartTalim
```

### 2. Frontend muhitini sozlash (Node.js)
Kutubxonalarni o'rnatish uchun quyidagi buyruqni bering:
```bash
npm install
```

`.env` faylini loyihaning ildiz papkasida (root) yarating va kerakli backend API manzillarini kiriting:
```env
VITE_API_URL=http://127.0.0.1:8000
# boshqa sozlamalar...
```

### 3. Backend muhitini sozlash (Django)
Loyiha ichida `smarttalim_backend` papkasi mavjud bo'lishi kerak. U yerda virtual muhit (`.venv`) yarating va kerakli python kutubxonalarini o'rnating:
```bash
cd smarttalim_backend
python -m venv .venv
source .venv/bin/activate  # Windows uchun: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

### 4. Loyihani bir vaqtda ishga tushirish
Loyihaning ildiz (root) papkasiga qayting va quyidagi buyruqni bering:
```bash
npm run dev
```
Bu buyruq `concurrently` paketi yordamida:
* **Vite** frontend serverini (odatda `http://localhost:5173`) ishga tushiradi.
* **Django** backend serverini (`http://127.0.0.1:8000`) ishga tushiradi.

---

## Yuzaga kelishi mumkin bo'lgan muammolar va yechimlar

### 1. API ulanish xatoligi (Network Error)
* **Sababi**: Django backend serveri ishlamayotgan bo'lishi yoki `.env` faylidagi `VITE_API_URL` noto'g'ri ko'rsatilgan bo'lishi mumkin.
* **Yechim**: `smarttalim_backend` papkasiga kirib, backend alohida to'g'ri ishlayotganini tekshiring va `.env` dagi URL'larni qayta tekshiring.

### 2. Port band bo'lishi
* **Sababi**: 5173 yoki 8000 portlari boshqa dasturlar tomonidan band qilingan.
* **Yechim**: Ishlayotgan jarayonlarni o'chiring yoki portlarni alohida ishga tushiruvchi buyruqlar orqali o'zgartiring.
