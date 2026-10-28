"""Markaziy permission registri.

Har bir permission `module.action` formatida.
Action: view | add | edit | delete | review | export | manage
"""

PERMISSIONS = {
    # === ÖQUV JARAYONI ===
    "homework": {
        "label": "Vazifalar",
        "perms": {
            "homework.view": "Köriş",
            "homework.review": "Baholaş / izoh beriş",
            "homework.delete": "Öçiriş",
        },
    },
    "tests": {
        "label": "Test natijalari",
        "perms": {
            "tests.view": "Köriş",
            "tests.delete": "Öçiriş",
        },
    },
    "lessons_analytics": {
        "label": "Darslar tahlili",
        "perms": {
            "lessons_analytics.view": "Köriş",
        },
    },
    "attendance": {
        "label": "Davomat",
        "perms": {
            "attendance.view": "Köriş",
            "attendance.add": "Qöşiş",
            "attendance.edit": "Tahrirlaş",
            "attendance.delete": "Öçiriş",
        },
    },
    "certificate_requests": {
        "label": "Sertifikatlar",
        "perms": {
            "certificate_requests.view": "Köriş",
            "certificate_requests.review": "Boşqariş",
        },
    },

    # === FOYDALANUVÇILAR ===
    "users": {
        "label": "Foydalanuvçilar",
        "perms": {
            "users.view": "Köriş",
            "users.edit": "Tahrirlaş",
            "users.block": "Bloklaş / blokdan çiqariş",
            "users.set_password": "Parolni örnatiş",
            "users.delete": "Öçiriş",
        },
    },
    "parents": {
        "label": "Ota-onalar",
        "perms": {
            "parents.view": "Köriş",
            "parents.add": "Qöşiş",
            "parents.edit": "Tahrirlaş",
            "parents.delete": "Öçiriş",
            "parents.message_reply": "Xabarga javob beriş",
            "parents.password_review": "Parol sörovini körib çiqiş",
        },
    },
    "requests": {
        "label": "Sörovlar",
        "perms": {
            "requests.enrollment_view": "Kursga yoziliş — köriş",
            "requests.enrollment_review": "Kursga yoziliş — tasdiqlaş",
            "requests.unenroll_view": "Kursdan çiqiş — köriş",
            "requests.unenroll_review": "Kursdan çiqiş — tasdiqlaş",
            "requests.premium_view": "Premium — köriş",
            "requests.premium_review": "Premium — tasdiqlaş",
        },
    },

    # === KONTENT ===
    "messages": {
        "label": "Xabarlar",
        "perms": {
            "messages.view": "Köriş",
            "messages.add": "Yuboriş",
            "messages.delete": "Öçiriş",
        },
    },
    "blog": {
        "label": "Blog",
        "perms": {
            "blog.view": "Köriş",
            "blog.add": "Post qöşiş",
            "blog.edit": "Postni tahrirlaş",
            "blog.delete": "Postni öçiriş",
            "blog.comment_delete": "Izohni öçiriş",
        },
    },
    "library": {
        "label": "Kutubxona",
        "perms": {
            "library.view": "Köriş",
            "library.book_add": "Kitob qöşiş",
            "library.book_edit": "Kitob tahrirlaş",
            "library.book_delete": "Kitob öçiriş",
            "library.rental_add": "Ijaraga beriş",
            "library.rental_return": "Qaytarib oliş",
        },
    },

    # === SUPPORT ===
    "help_requests": {
        "label": "Yordam xatlari",
        "perms": {
            "help_requests.view": "Köriş",
            "help_requests.respond": "Javob yoziş",
            "help_requests.delete": "Öçiriş",
        },
    },
    "applications": {
        "label": "Arizalar",
        "perms": {
            "applications.view": "Köriş",
            "applications.edit": "Tahrirlaş / status",
            "applications.delete": "Öçiriş",
        },
    },
    "surveys": {
        "label": "Sörovnomalar",
        "perms": {
            "surveys.view": "Köriş",
            "surveys.add": "Qöşiş",
            "surveys.edit": "Tahrirlaş",
            "surveys.delete": "Öçiriş",
        },
    },

    # === SYSTEM ===
    "system": {
        "label": "Tizim",
        "perms": {
            "system.roles_manage": "Rollar va ruxsatlarni boşqariş",
            "system.logs_view": "Audit jurnalini köriş",
        },
    },
}


def all_permission_codes():
    """Barça mavjud permission kodlari röyxati"""
    codes = []
    for group in PERMISSIONS.values():
        codes.extend(group["perms"].keys())
    return codes


def is_valid_permission(code: str) -> bool:
    return code in all_permission_codes()


# ---------- TAYYOR ROLLAR (default) ----------
# `permissions` röyxati True bölgan kodlar.

DEFAULT_ROLES = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Töliq ruxsat - hamma narsa",
        "is_system": True,
        "permissions": all_permission_codes,  # callable -> hammasi
    },
    "academic_admin": {
        "name": "Akademik Admin",
        "description": "Öquv jarayoni, foydalanuvçilar, sertifikatlar, kutubxona",
        "is_system": True,
        "permissions": [
            "homework.view", "homework.review",
            "tests.view",
            "lessons_analytics.view",
            "attendance.view", "attendance.add", "attendance.edit",
            "certificate_requests.view", "certificate_requests.review",
            "users.view", "users.edit",
            "password_resets.view", "password_resets.review",
            "parents.view",
            "requests.enrollment_view", "requests.enrollment_review",
            "requests.unenroll_view", "requests.unenroll_review",
            # Kutubxona — kitoblar va ijaralar bilan işlaş
            "library.view",
            "library.book_add", "library.book_edit",
            "library.rental_add", "library.rental_return",
        ],
    },
    "support": {
        "name": "Support",
        "description": "Yordam xatlari, arizalar, ota-ona xabarlari",
        "is_system": True,
        "permissions": [
            "users.view",
            "help_requests.view", "help_requests.respond",
            "applications.view", "applications.edit",
            "parents.view", "parents.message_reply",
            "messages.view", "messages.add",
        ],
    },
    "finance_admin": {
        "name": "Finance Admin",
        "description": "Tölovlar, premium",
        "is_system": True,
        "permissions": [
            "users.view",
            "requests.premium_view", "requests.premium_review",
        ],
    },
    "content_manager": {
        "name": "Content Manager",
        "description": "Blog, kutubxona, sörovnomalar, xabarlar",
        "is_system": True,
        "permissions": [
            "blog.view", "blog.add", "blog.edit", "blog.delete", "blog.comment_delete",
            "library.view", "library.book_add", "library.book_edit",
                "library.rental_add", "library.rental_return",
            "surveys.view", "surveys.add", "surveys.edit", "surveys.delete",
            "messages.view", "messages.add",
        ],
    },
    "teacher_assistant": {
        "name": "Teacher Yordamçi",
        "description": "Öqituvçilarga yordam (vazifa, test, davomat)",
        "is_system": True,
        "permissions": [
            "homework.view", "homework.review",
            "tests.view",
            "lessons_analytics.view",
            "attendance.view", "attendance.add",
            "users.view",
        ],
    },
}


def get_default_role_permissions(code: str):
    role = DEFAULT_ROLES.get(code)
    if not role:
        return []
    perms = role["permissions"]
    if callable(perms):
        perms = perms()
    return list(perms)
