from django.db.backends.signals import connection_created


def _optimize_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        # ============================================================
        # BARQARORLIK + KÖP ÖYINÇILI YUKGA ÇIDAMLILIK
        # ------------------------------------------------------------
        # WAL işlatilmaydi: Windows'da (köp jarayon + antivirus + jarayonni
        # majburan töxtatiş) -wal/-shm fayllari buzilib, "malformed database
        # schema" / "disk I/O error" xatolariga olib kelgan.
        #   • journal_mode=DELETE — -wal/-shm fayllari umuman yaratilmaydi (xavfsiz).
        #   • synchronous=NORMAL  — FULL örniga. FULL har yozuvda fsync qilib
        #     yozuvni sekinlaştiradi; köp öquvçi bir vaqtda öynaganda (real-time
        #     öyin yurişlari) yozuv qulfini uzoq uşlab, boşqa öquvçilar
        #     "Raqib yurmoqda"da qotib qolardi. NORMAL yozuvni tezlaştiradi →
        #     qulf qisqa uşlanadi → yurişlar tez tarqaladi. DELETE bilan birga
        #     ilova/antivirus/jarayon-töxtatishdan buzilmaydi (faqat tok öçişi
        #     kabi noyob holatda oxirgi yuriş yöqolişi mumkin — bu öyin uçun
        #     maqbul). Kerak bölsa yana FULL'ga qaytariş mumkin.
        # ============================================================
        cursor.execute("PRAGMA journal_mode=DELETE;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # Boşqa jarayon DB'ni band qilsa, xato bermay 30s kutadi
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.execute("PRAGMA temp_store=MEMORY;")


connection_created.connect(_optimize_sqlite)
