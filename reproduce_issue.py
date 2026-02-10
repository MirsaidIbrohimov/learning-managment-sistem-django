
import os
import django
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from accounts.models import CustomUser, HelpRequest

def run_test():
    print("Setting up test environment...")
    # Create or get a user
    username = 'testuser_debug'
    password = 'testpassword123'
    try:
        user = CustomUser.objects.get(username=username)
        print(f"User {username} already exists.")
    except CustomUser.DoesNotExist:
        user = CustomUser.objects.create_user(username=username, password=password, role='student')
        print(f"User {username} created.")

    client = Client()
    login_success = client.login(username=username, password=password)
    print(f"Login successful: {login_success}")

    # Prepare image
    image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    test_image = SimpleUploadedFile("test_image.png", image_content, content_type="image/png")

    print("Submitting help request...")
    # Count before
    count_before = HelpRequest.objects.filter(user=user).count()

    response = client.post('/help/submit/', {
        'subject': 'Test Subject for Debug',
        'message': 'This is a test message to debug duplicate and image issues.',
        'image': test_image
    })

    print(f"Response status: {response.status_code}")
    print(f"Response content: {response.content.decode('utf-8')}")

    # Count after
    count_after = HelpRequest.objects.filter(user=user).count()
    print(f"Count before: {count_before}")
    print(f"Count after: {count_after}")

    if count_after == count_before + 1:
        print("SUCCESS: Exactly one request created.")
    elif count_after > count_before + 1:
        print(f"FAILURE: {count_after - count_before} requests created! (Duplicate issue reproduced in backend?)")
    else:
        print("FAILURE: No request created or count weird.")

    # Check image
    latest_req = HelpRequest.objects.filter(user=user).latest('created_at')
    if latest_req.image:
        print(f"Image saved: {latest_req.image.name}")
        print(f"Image url: {latest_req.image.url}")
        if os.path.exists(latest_req.image.path):
             print("Image file exists on disk.")
        else:
             print("Image file DOES NOT exist on disk.")
    else:
        print("FAILURE: Image field is empty!")

if __name__ == "__main__":
    run_test()
