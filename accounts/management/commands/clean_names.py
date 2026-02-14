from django.core.management.base import BaseCommand
from accounts.models import CustomUser
import unicodedata


class Command(BaseCommand):
    help = "O'quvchilarning ism va familiyalaridan stiker va emojilarni tozalash"

    def handle(self, *args, **options):
        users = CustomUser.objects.all()
        cleaned_count = 0
        
        for user in users:
            original_first = user.first_name
            original_last = user.last_name
            
            user.first_name = self._clean_name(user.first_name) if user.first_name else ''
            user.last_name = self._clean_name(user.last_name) if user.last_name else ''
            
            if user.first_name != original_first or user.last_name != original_last:
                user.save(update_fields=['first_name', 'last_name'])
                self.stdout.write(
                    f"Tozalandi: '{original_first} {original_last}' -> '{user.first_name} {user.last_name}'"
                )
                cleaned_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"\nJami {cleaned_count} ta foydalanuvchi tozalandi."))
    
    @staticmethod
    def _clean_name(name):
        cleaned = ''
        for char in name:
            cat = unicodedata.category(char)
            if cat.startswith('L') or cat.startswith('M') or char in " -'ʻʼ":
                cleaned += char
        return cleaned.strip()
