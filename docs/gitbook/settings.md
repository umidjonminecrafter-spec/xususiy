# Tizim Sozlamalari (Settings)

**Sozlamalar** bo'limi — o'quv markazining barcha ichki parametrlari, avtomatlashtirish shartlari, filiallar, dars xonalari, maosh va KPI formulalari, integratsiyalar va ma'lumotlar zaxiralarini sozlash uchun xizmat qiladi. Bu bo'lim faqat Owner va Admin huquqiga ega foydalanuvchilarga ko'rinadi.

---

## 1. Ofis va Filial Sozlamalari

### A. Filiallar (Branches)
Markazning barcha jismoniy va virtual filiallarini boshqarish.

![Filiallar sahifasi](assets/settings/branchespage.png)
![Filial yaratish](assets/settings/createbranch.png)

#### Filial qo'shish yo'riqnomasi:
1. Sozlamalardagi `Filiallar` bo'limiga o'ting.
2. `Yangi filial` tugmasini bosing.
3. Filial nomi, to'liq manzili va aloqa telefon raqamini kiritib saqlang.
4. Yaratilgan filial avtomatik ravishda yuqori navbar filiallar dropdown ro'yxatida paydo bo'ladi.

### B. Xonalar (Rooms)
Darslar tashkil etiladigan xonalar ro'yxatini sozlash.

![Xonalar sahifasi](assets/settings/roomspage.png)
![Xona yaratish](assets/settings/createroom.png)

#### Xona qo'shish yo'riqnomasi:
1. `Xonalar` bo'limida `Xona qo'shish` tugmasini bosing.
2. Xona nomini (masalan: *London xonasi*, *Room 3*) va sig'imini (maksimal o'quvchi soni) yozing.
3. Bu sozlama guruh yaratilayotganda xonaning sig'imi va dars vaqtlari mosligini tekshirish uchun tizim tomonidan qo'llaniladi.

### C. Bayram kunlari (Holidays)
Markaz yopiq bo'ladigan va dars o'tilmaydigan rasmiy bayram va dam olish kunlarini belgilash.

![Bayramlar sahifasi](assets/settings/office/holidays.png)
![Bayram yaratish](assets/settings/office/createholiday.png)

* **Qanday ishlaydi**: Bayram kuni kiritilgandan so'ng, tizim shu kunga to'g'ri kelgan barcha guruh darslarini avtomatik ravishda keyingi dars kuniga ko'chiradi va talabalarning balansidan pul yechilmaydi.

---

## 2. Xodimlar, Ketganlar va Arxiv

### A. Xodimlar boshqaruvi va Darajalari
Markazda faoliyat yuritadigan ma'muriy jamoani tizimga qo'shish, ularga tizimga kirish uchun rollar (Admin, Menejer, Receptionist) biriktirish va ularning malaka darajalarini sozlash.

![Xodimlar bosh sahifasi](assets/settings/employeemain.png)
![Xodimlar darajalari](assets/settings/employeelevels.png)

* **Xodim qo'shish**: Ism, telefon, rol va oylik fiks maoshini ko'rsatib xodim yaratiladi.
* **Malaka darajalari (Levels)**: Xodimlarning tajribasiga ko'ra darajalar belgilash (masalan: *Junior Admin*, *Senior Admin*).

### B. Arxivlar (Archive) va Arxiv sabablari
Tizim ma'lumotlar bazasi toza va tez ishlashi uchun eskirgan yoki tark etgan talaba, guruh va o'qituvchilarni arxivlash oynasi.

![Arxiv sahifasi](assets/settings/office/archivepage.png)
![Arxivlash sabablari](assets/settings/office/archivereasons.png)
![Xodimlar arxivi](assets/settings/employeearchive.png)

* **Arxivlash sababi**: Ma'lumot arxivga yuborilayotganda sababi ko'rsatiladi (masalan: *Kurs tugadi*, *Boshqa shaharga ko'chdi*).
* **Qayta tiklash**: Arxivdagi ma'lumotlarni istalgan vaqtda bitta tugma bilan faollashtirish mumkin.
* **Arxivdan lidlarga yuborish (Send to Lead from Archive)**: Arxivlangan eski talabani qaytadan marketing savdo taxtasiga (Leads Kanban) potentsial mijoz sifatida yo'naltirish oynasi.
  ![Arxivdan lidga o'tkazish](assets/settings/office/sendtoleadfromarchive.png)

### C. Guruhdan ketganlar (Left Group) va Lidlarga yo'naltirish
Dars guruhlarini ma'lum sabablar bilan tark etgan talabalar monitoringi.

![Ketgan guruhdagilar](assets/settings/office/leftgroup.png)
* **Ketgan talabani lidga o'tkazish**: Guruhdan ketgan o'quvchini qaytadan yangi guruhlarga jalb qilish uchun uni marketing voronkasiga (Leads) qaytarish oynasi.
  ![Ketgan guruhdan lidlarga o'tkazish](assets/settings/office/sentoleadfromleftgroup.png)

---

## 3. Kurslar, Imtihonlar va Baholash

### A. Kurslarni sozlash (Courses Setup)
Markazda o'tiladigan fan yo'nalishlarini (Kurslar) yaratish va ularning standart narxlarini belgilash.

![Kurslar sahifasi](assets/settings/coursepage.png)
![Kurs yaratish](assets/settings/createcoursemodal.png)

* **Kurs narxi**: Kursning oylik standart narxi.
* **Avtomatlashtirish qoidalari**: Balansdan pul yechish turi (darsbay yoki oylik).

### B. Imtihonlar va Baholash tizimi
Kurslar davomida olinadigan test va imtihonlarni sozlash, ularning baholash mezonlarini o'rnatish.

![Imtihonlar bosh sahifasi](assets/settings/main/exammain.png)
![Imtihon yaratish](assets/settings/main/createexam.png)
![Baholash darajalari](assets/settings/edu/levels.png)

* **Baholash darajalari**: Imtihon ballari bo'yicha baholarni belgilash (masalan: `90-100 ball` = *A (A'lo)*, `80-89 ball` = *B (Yaxshi)*).

---

## 4. Moliyaviy avtomatlashtirish sozlamalari

O'quv markazining moliya tizimini avtomatlashtirish qoidalari.

![Hisoblar va to'lovlar](assets/settings/main/hisoblarvatolovlar.png)

* **O'qituvchi maosh foizlari (Salary Percents)**: O'qituvchilar talabalar to'lagan summaning necha foizini oylik sifatida olishini belgilash:
  ![Maosh foizlari](assets/settings/finance/monthly.png)
* **KPI sozlamalari**: Administrator va menejerlar uchun oylik rejaning bajarilish foiziga qarab bonus yoki jarima hisoblash formulalarini sozlash:
  ![KPI sozlamalari](assets/settings/finance/kpi.png)
* **Menejer bonus/jarimalari**: Yig'ilgan to'lovlar rejasidan kelib chiqib avtomatik qo'shiladigan bonus yoki jarimalar:
  ![Menejer bonus jarimalari](assets/settings/finance/managerbonusand.png)
* **Bo'lim bonuslari**: Muayyan bo'limlar (masalan: *Call center*, *Marketing*) erishgan natijalar uchun mukofotlar:
  ![Bo'lim bonuslari](assets/settings/finance/financebonus.png)
* **Avtomatik chegirmalar (Auto Discounts)**: Bir oiladan ikki kishi o'qiganda, yoki birdaniga ikki oyga to'lov qilganda talabaga avtomatik chegirma berish qoidalari:
  ![Avtomatik chegirmalar](assets/settings/finance/avtochegrima.png)

---

## 5. Chek shablonlari va Maxsus Maydonlar

### A. Chek Sozlamalari (Receipt - Chek)
To'lov qilgandan so'ng chop etiladigan qog'oz cheki dizayni va matnini tahrirlash oynasi.

![Chek sozlamalari](assets/settings/main/chek.png)

* Chek yuqorisidagi kompaniya logotipi, manzili, chek ostidagi rahmatnoma yoki eslatma matnini (masalan: *To'langan pullar qaytarilmaydi*) sozlash.

### B. Talaba Maxsus Maydonlari (Custom Student Fields)
Talaba kartochkasi yaratilayotganda kiritiladigan qo'shimcha ma'lumot turlarini kiritish (masalan: *Maktab raqami*, *Ota-onasining kasbi*).

![Talaba maydonlari](assets/settings/main/studentfields.png)
