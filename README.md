# Do'kon bot

PDF kitoblar, yopiq kanal va konsultatsiya sotadigan Telegram bot.

## Qanday ishlaydi
1. Mijoz /start bosadi va mahsulotni tanlaydi.
2. Bot karta raqamini ko'rsatadi, mijoz to'lab chek skrinshotini yuboradi.
3. Chek senga "Tasdiqlash / Rad etish" tugmalari bilan keladi.
4. Tasdiqlasang, bot o'zi yetkazadi:
   - PDF: faylni yuboradi
   - Yopiq kanal: bir martalik shaxsiy havola beradi
   - Konsultatsiya: mijozga xabar beradi, senga uning kontaktini yuboradi

## Admin
- Botga birinchi bo'lib @atadjanov_jasur akkauntidan /start bosiladi, shunda bot seni admin qilib oladi.
- /admin: mahsulot qo'shish, o'chirish va statistika.

## Railway'ga joylash
1. Bu papkani GitHub repository'ga yuklang.
2. railway.app'da: New Project, Deploy from GitHub repo, shu repo.
3. Variables bo'limiga qo'shing:
   - `BOT_TOKEN` = BotFather'dan olingan token
   - `DB_PATH` = `/data/shop.db`
4. Settings, Volumes: yangi volume qo'shing, mount path `/data`. Bu bo'lmasa, har yangilanishda mahsulotlar va buyurtmalar o'chib ketadi.
5. Settings'da start buyrug'i `python bot.py` ekanini tekshiring.

Ixtiyoriy o'zgaruvchilar: `CARD_NUMBER`, `CARD_HOLDER`, `ADMIN_USERNAME`.

**Muhim:** bot tokenini kod ichiga yozmang, faqat Railway Variables'ga kiriting.
