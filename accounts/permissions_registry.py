"""Markaziy permission registri.

Har bir permission `module.action` formatida.
Action: view | add | edit | delete | review | export | manage
"""

PERMISSIONS = {
    # === O'QUV JARAYONI ===
    "homework": {
        "label": "Vazifalar",
        "perms": {
            "homework.view": "Ko'rish",
            "homework.review": "Baholash / izoh berish",
            "homework.delete": "O'chirish",
        },
    },
    "tests": {
        "label": "Test natijalari",
        "perms": {
            "tests.view": "Ko'rish",
            "tests.delete": "O'chirish",
        },
    },
    "lessons_analytics": {
        "label": "Darslar tahlili",
        "perms": {
            "lessons_analytics.view": "Ko'rish",
        },
    },
    "attendance": {
        "label": "Davomat",
        "perms": {
            "attendance.view": "Ko'rish",
            "attendance.add": "Qo'shish",
            "attendance.edit": "Tahrirlash",
            "attendance.delete": "O'chirish",
        },
    },
    "certificate_requests": {
        "label": "Sertifikatlar",
        "perms": {
            "certificate_requests.view": "Ko'rish",
            "certificate_requests.review": "Boshqarish",
        },
    },

    # === FOYDALANUVCHILAR ===
    "users": {
        "label": "Foydalanuvchilar",
        "perms": {
            "users.view": "Ko'rish",
            "users.edit": "Tahrirlash",
            "users.block": "Bloklash / blokdan chiqarish",
            "users.set_password": "Parolni o'rnatish",
            "users.delete": "O'chirish",
        },
    },
    "password_resets": {
        "label": "Parol tiklash so'rovlari",
        "perms": {
            "password_resets.view": "Ko'rish",
            "password_resets.review": "Tasdiqlash / rad etish",
        },
    },
    "parents": {
        "label": "Ota-onalar",
        "perms": {
            "parents.view": "Ko'rish",
            "parents.add": "Qo'shish",
            "parents.edit": "Tahrirlash",
            "parents.delete": "O'chirish",
            "parents.message_reply": "Xabarga javob berish",
            "parents.password_review": "Parol so'rovini ko'rib chiqish",
        },
    },
    "requests": {
        "label": "So'rovlar",
        "perms": {
            "requests.enrollment_view": "Kursga yozilish — ko'rish",
            "requests.enrollment_review": "Kursga yozilish — tasdiqlash",
            "requests.unenroll_view": "Kursdan chiqish — ko'rish",
            "requests.unenroll_review": "Kursdan chiqish — tasdiqlash",
            "requests.premium_view": "Premium — ko'rish",
            "requests.premium_review": "Premium — tasdiqlash",
        },
    },

    # === KONTENT ===
    "messages": {
        "label": "Xabarlar",
        "perms": {
            "messages.view": "Ko'rish",
            "messages.add": "Yuborish",
            "messages.delete": "O'chirish",
        },
    },
    "blog": {
        "label": "Blog",
        "perms": {
            "blog.view": "Ko'rish",
            "blog.add": "Post qo'shish",
            "blog.edit": "Postni tahrirlash",
            "blog.delete": "Postni o'chirish",
            "blog.comment_delete": "Izohni o'chirish",
        },
    },
    "library": {
        "label": "Kutubxona",
        "perms": {
            "library.view": "Ko'rish",
            "library.book_add": "Kitob qo'shish",
            "library.book_edit": "Kitob tahrirlash",
            "library.book_delete": "Kitob o'chirish",
            "library.rental_add": "Ijaraga berish",
            "library.rental_return": "Qaytarib olish",
        },
    },

    # === SUPPORT ===
    "help_requests": {
        "label": "Yordam xatlari",
        "perms": {
            "help_requests.view": "Ko'rish",
            "help_requests.respond": "Javob yozish",
            "help_requests.delete": "O'chirish",
        },
    },
    "applications": {
        "label": "Arizalar",
        "perms": {
            "applications.view": "Ko'rish",
            "applications.edit": "Tahrirlash / status",
            "applications.delete": "O'chirish",
        },
    },
    "surveys": {
        "label": "So'rovnomalar",
        "perms": {
            "surveys.view": "Ko'rish",
            "surveys.add": "Qo'shish",
            "surveys.edit": "Tahrirlash",
            "surveys.delete": "O'chirish",
        },
    },

    # === SYSTEM ===
    "system": {
        "label": "Tizim",
        "perms": {
            "system.roles_manage": "Rollar va ruxsatlarni boshqarish",
            "system.logs_view": "Audit jurnalini ko'rish",
        },
    },
}


def all_permission_codes():
    """Barcha mavjud permission kodlari ro'yxati"""
    codes = []
    for group in PERMISSIONS.values():
        codes.extend(group["perms"].keys())
    return codes


def is_valid_permission(code: str) -> bool:
    return code in all_permission_codes()


# ---------- TAYYOR ROLLAR (default) ----------
# `permissions` ro'yxati True bo'lgan kodlar.

DEFAULT_ROLES = {
    "super_admin": {
        "name": "Super Admin",
        "description": "To'liq ruxsat - hamma narsa",
        "is_system": True,
        "permissions": all_permission_codes,  # callable -> hammasi
    },
    "academic_admin": {
        "name": "Akademik Admin",
        "description": "O'quv jarayoni, foydalanuvchilar, sertifikatlar, kutubxona",
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
            # Kutubxona — kitoblar va ijaralar bilan ishlash
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
        "description": "To'lovlar, premium",
        "is_system": True,
        "permissions": [
            "users.view",
            "requests.premium_view", "requests.premium_review",
        ],
    },
    "content_manager": {
        "name": "Content Manager",
        "description": "Blog, kutubxona, so'rovnomalar, xabarlar",
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
        "name": "Teacher Yordamchi",
        "description": "O'qituvchilarga yordam (vazifa, test, davomat)",
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
