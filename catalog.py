"""inson.lab kitoblari: sotuv matnlari, rasmlar va parchalar."""

BOOKS = [
    {
        "slug": "b1", "file": "01_Korinmas_iplar", "title": "Ko'rinmas iplar",
        "short": "manipulyatsiyadan himoya", "pages": 51, "emoji": "🧵",
        "pain": "Meni gapga solib, istamagan ishimga ko'ndirishadi",
        "hook": "Sizni kim, qachon va qanday boshqarayotganini sezasizmi?",
        "about": ("Manipulyator baqirmaydi. U «chunki», aybdorlik hissi, jimlik va haddan tashqari "
                  "mehr bilan ishlaydi. Bu kitob 14 ta usulni ilmiy tajribalar asosida ochib beradi "
                  "va har biriga tayyor himoya javobini beradi."),
        "bullets": [
            "Love bombing: juda tez, juda ko'p mehr qachon tuzoq bo'ladi",
            "Nega odamlar og'ritadigan munosabatdan keta olmaydi",
            "Jimlik jazosi va aybdorlik bilan boshqarish",
            "DARVO: aybdor qanday qilib «qurbon»ga aylanadi",
            "«Yo'q» deyishning 5 shakli va TO'XTA protokoli",
        ],
    },
    {
        "slug": "b2", "file": "02_Yurak_algoritmi", "title": "Yurak algoritmi",
        "short": "sevgi va munosabatlar ilmi", "pages": 43, "emoji": "❤️",
        "pain": "Munosabatlarimda tushunmovchilik ko'p",
        "hook": "Nega ba'zi juftliklar 30 yil birga, boshqalari 3 yilda ajraladi?",
        "about": ("Birga qolgan juftliklar bir-birining kichik so'roviga 86% holatda javob bergan, "
                  "ajrashganlar esa atigi 33%. Bu kitob jalb, bog'lanish va sevgini saqlash haqidagi 25+ tadqiqotni sodda tilda, "
                  "o'zbek hayotidan misollar bilan tushuntiradi."),
        "bullets": [
            "Bog'lanish uslublari: nega biri doim qo'rqadi, biri qochadi",
            "Gotmanning 5 : 1 qoidasi va munosabatni buzadigan «to'rt otliq»",
            "«Sevgi tillari» haqida ilm aslida nima deydi",
            "Yaxshi xabarga qanday javob munosabatni mustahkamlaydi",
            "O'z bog'lanish uslubingizni aniqlash testi",
        ],
    },
    {
        "slug": "b3", "file": "03_Indamas_til", "title": "Indamas til",
        "short": "tana tili, miflarsiz", "pages": 38, "emoji": "👁",
        "pain": "Odamlarni ichidan tushunishni xohlayman",
        "hook": "Yolg'onni ko'zidan bilaman deysizmi? Ilm boshqacha deydi.",
        "about": ("Internetdagi tana tili maslahatlarining yarmi mif. Bu kitob qaysi belgilar "
                  "haqiqatan ishlashini va qaysilari ilmiy tekshiruvdan o'tmaganini ko'rsatadi: "
                  "ko'z, tabassum, qo'l, masofa va ovoz."),
        "bullets": [
            "Ko'zga qarash: necha soniya qulay, necha soniya noqulay",
            "Haqiqiy tabassumni soxtasidan qanday ajratish mumkin",
            "Mikroifodalar: ilmmi yoki serial uchun shou",
            "Xameleon effekti: nega takrorlash yaqinlashtiradi",
            "8 ta mashhur mif va ularning o'rniga nima ishlaydi",
        ],
    },
    {
        "slug": "b4", "file": "04_Tasir_kodi", "title": "Ta'sir kodi",
        "short": "odamlarni halol ishontirish", "pages": 37, "emoji": "🎯",
        "pain": "Gapim o'tmaydi, odamlarni ishontira olmayman",
        "hook": "To'rt so'z rozilikni 10% dan 47% ga oshirdi. Qaysi so'zlar?",
        "about": ("Ishda, savdoda, oilada: kim ishontira olsa, o'sha yutadi. Bu kitob "
                  "manipulyatsiyasiz, halol ta'sir qilishning ilmiy usullarini tayyor iboralar va "
                  "30 kunlik mashq rejasi bilan beradi."),
        "bullets": [
            "«Lekin siz erkinsiz»: rozilikni 2 baravar oshiradigan to'rt so'z",
            "Ben Franklin effekti: yordam so'rash nega sizni yoqimli qiladi",
            "Hikoya va statistika: nima ko'proq harakatga keltiradi",
            "Muzokarada birinchi raqam va «aniq son» sirri",
            "Tayyor iboralar va 30 kunlik reja",
        ],
    },
    {
        "slug": "b5", "file": "05_Pul_miyasi", "title": "Pul miyasi",
        "short": "pul psixologiyasi", "pages": 37, "emoji": "💸",
        "pain": "Pulim qayerga ketayotganini bilmayman",
        "hook": "Nega aqlli odamlar ham pulni noto'g'ri sarflaydi?",
        "about": ("Pul muammosi ko'pincha matematikada emas, miyada. Bu kitob miya pulni qanday "
                  "«aldab» sarflatishini va 7 ta oddiy qoida bilan uni o'zingizga ishlatishni "
                  "o'rgatadi."),
        "bullets": [
            "«Bepul» so'zi nega miyani o'chiradi",
            "Karta bilan to'laganda nega 2 baravar ko'p sarflaymiz",
            "Pul baxt keltiradimi: 2023-yilgi so'nggi javob",
            "Kelajakdagi o'zingiz bilan tanishish tejashni oshiradi",
            "7 qoida va 30 kunlik reja",
        ],
    },
]

BOOKS.append({
    "slug": "b6", "file": "06_Marketing_xaritasi", "title": "Marketing xaritasi",
    "short": "biznes uchun marketing reja", "pages": 41, "emoji": "🗺", "price": 69000,
    "pain": "Biznesimga mijoz kam, marketingim tartibsiz",
    "hook": "Butun marketingingiz bitta sahifaga sig'masa, u hali reja emas.",
    "about": ("Kichik biznes uchun bir sahifalik marketing reja: kimga sotish, nima deyish, mijozni "
              "qanday topish va qaytarish. 12 bob, 20+ tadqiqot, to'ldiriladigan xarita shabloni "
              "va 30 kunlik ishga tushirish rejasi."),
    "bullets": [
        "Nega «hammaga» sotish hech kimga sotmaslik degani",
        "Kam tanlov — ko'p sotuv: murabbo tajribasi",
        "Narx psixologiyasi: langar, aldov varianti va «9»",
        "Lidga 1 soat ichida javob berish nega 7 baravar samaraliroq",
        "1 sahifalik marketing xaritasi + 30 kunlik reja",
    ],
})

PSY = [b for b in BOOKS if not b.get("price")]

BUNDLE = {
    "slug": "all", "title": "5 kitob to'plami", "emoji": "🔥",
    "hook": "Insonni to'liq tushunish uchun hammasi bitta joyda.",
}

BY_SLUG = {b["slug"]: b for b in BOOKS}
