from django.db.backends.signals import connection_created


def _optimize_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        # ============================================================
        # BARQARORLIK + KO'P O'YINCHILI YUKGA CHIDAMLILIK
        # ------------------------------------------------------------
        # WAL ishlatilmaydi: Windows'da (ko'p jarayon + antivirus + jarayonni
        # majburan to'xtatish) -wal/-shm fayllari buzilib, "malformed database
        # schema" / "disk I/O error" xatolariga olib kelgan.
        #   • journal_mode=DELETE — -wal/-shm fayllari umuman yaratilmaydi (xavfsiz).
        #   • synchronous=NORMAL  — FULL o'rniga. FULL har yozuvda fsync qilib
        #     yozuvni sekinlashtiradi; ko'p o'quvchi bir vaqtda o'ynaganda (real-time
        #     o'yin yurishlari) yozuv qulfini uzoq ushlab, boshqa o'quvchilar
        #     "Raqib yurmoqda"da qotib qolardi. NORMAL yozuvni tezlashtiradi →
        #     qulf qisqa ushlanadi → yurishlar tez tarqaladi. DELETE bilan birga
        #     ilova/antivirus/jarayon-to'xtatishdan buzilmaydi (faqat tok o'chishi
        #     kabi noyob holatda oxirgi yurish yo'qolishi mumkin — bu o'yin uchun
        #     maqbul). Kerak bo'lsa yana FULL'ga qaytarish mumkin.
        # ============================================================
        cursor.execute("PRAGMA journal_mode=DELETE;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # Boshqa jarayon DB'ni band qilsa, xato bermay 30s kutadi
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.execute("PRAGMA temp_store=MEMORY;")


connection_created.connect(_optimize_sqlite)
