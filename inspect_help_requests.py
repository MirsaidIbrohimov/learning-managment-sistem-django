
import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import HelpRequest



def inspect_help_requests():
    print("Searching for orphan image file in DB...")
    target_file = 'Skrinshot_2024-11-12_135229.png'
    
    # Check if any request contains this string in its image path
    found = False
    for req in HelpRequest.objects.all():
        if req.image and target_file in str(req.image):
            print(f"FOUND! Request ID: {req.id}")
            print(f"User: {req.user.username}")
            print(f"Subject: {req.subject}")
            print(f"Image Field: {req.image}")
            found = True
    
    if not found:
        print(f"File '{target_file}' NOT found in any HelpRequest record in DB.")
        
    print("\nListing all requests with ANY image:")
    count = 0
    for req in HelpRequest.objects.exclude(image='').exclude(image__isnull=True):
         print(f"ID: {req.id}, Image: {req.image}")
         count += 1
    if count == 0:
        print("No requests with images found in DB.")



if __name__ == "__main__":
    inspect_help_requests()
