from django.db.backends.signals import connection_created


def _optimize_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        # ============================================================
        # BARQARORLIK > TEZLIK (Windows'da takroriy DB buzilishi sabab)
        # ------------------------------------------------------------
        # Avval WAL + synchronous=NORMAL + mmap_size ishlatilgan edi va
        # Windows'da bir necha bor "malformed database schema" hamda
        # "disk I/O error" xatolariga olib keldi (ko'p jarayon + antivirus
        # + jarayonni majburan to'xtatish = -wal/-shm fayllari buziladi).
        #
        # Shu sabab eng ishonchli, buzilishga chidamli sozlamaga o'tdik:
        #   • journal_mode=DELETE — -wal/-shm fayllari umuman yaratilmaydi
        #   • synchronous=FULL    — har bir yozuv diskka kafolatli yoziladi
        # ============================================================
        cursor.execute("PRAGMA journal_mode=DELETE;")
        cursor.execute("PRAGMA synchronous=FULL;")
        # Boshqa jarayon DB'ni band qilsa, xato bermay 30s kutadi
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA cache_size=-64000;")
        cursor.execute("PRAGMA temp_store=MEMORY;")


connection_created.connect(_optimize_sqlite)
