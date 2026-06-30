"""Kutubxona API views — Student va Admin uchun to'liq CRUD."""

from datetime import date, timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Book, BookRental, BookRentalRequest, CustomUser, Message
from api.permissions import IsNotBlocked

from .serializers import (
    BookListSerializer,
    BookDetailSerializer,
    BookCreateSerializer,
    BookDuplicateCheckSerializer,
    BookRentalRequestCreateSerializer,
    BookRentalRequestSerializer,
    BookRentalSerializer,
    LibraryStatsSerializer,
)

AUTH = [IsAuthenticated, IsNotBlocked]


def _is_admin_or_assistant(user):
    return user.role in ('admin', 'assistant_admin')


# ─────────────────────────────────────────────────────────────
#  STUDENT: Kitoblar ro'yxati va detail
# ─────────────────────────────────────────────────────────────

class BookListView(APIView):
    permission_classes = AUTH

    def get(self, request):
        books = Book.objects.all()
        search = request.query_params.get('search', '').strip()
        available_only = request.query_params.get('available') == '1'
        sort = request.query_params.get('sort', 'title')

        if search:
            books = books.filter(
                Q(title__icontains=search) | Q(author__icontains=search) | Q(isbn__icontains=search)
            )
        if available_only:
            books = books.filter(available_copies__gt=0)

        sort_map = {
            'title': 'title',
            '-title': '-title',
            'author': 'author',
            'newest': '-created_at',
            'oldest': 'created_at',
            'available': '-available_copies',
        }
        books = books.order_by(sort_map.get(sort, 'title'))

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response({
            'count': books.count(),
            'results': serializer.data,
        })


class BookDetailView(APIView):
    permission_classes = AUTH

    def get(self, request, pk):
        try:
            book = Book.objects.get(pk=pk)
        except Book.DoesNotExist:
            return Response({'detail': 'Kitob topilmadi.'}, status=404)
        serializer = BookDetailSerializer(book, context={'request': request})
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────
#  STUDENT: Duplicate tekshirish (faqat GET, hamma uchun)
# ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes(AUTH)
def check_duplicate(request):
    """?title=...&author=...&isbn=... → takrorlanish tekshiruvi"""
    serializer = BookDuplicateCheckSerializer(data={
        'title': request.query_params.get('title', ''),
        'author': request.query_params.get('author', ''),
        'isbn': request.query_params.get('isbn', ''),
    })
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    return Response(serializer.check())


# ─────────────────────────────────────────────────────────────
#  STUDENT: Ariza berish
# ─────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes(AUTH)
def request_book(request, pk):
    """O'quvchi kitob ijarasi arizasi beradi."""
    try:
        book = Book.objects.get(pk=pk)
    except Book.DoesNotExist:
        return Response({'detail': 'Kitob topilmadi.'}, status=404)

    data = request.data.copy()
    data['book'] = book.pk
    serializer = BookRentalRequestCreateSerializer(data=data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    req = serializer.save(student=request.user)

    # Admin va assistant_adminlarga xabar
    admins = CustomUser.objects.filter(role__in=['admin', 'assistant_admin'], is_active=True)
    for admin in admins:
        Message.objects.create(
            sender=request.user,
            recipient=admin,
            message_type='notification',
            content=(
                f"📚 Yangi kitob arizasi!\n"
                f"O'quvchi: {request.user.full_name}\n"
                f"Kitob: «{book.title}» — {book.author}\n"
                f"Ariza #{ req.pk }"
            ),
        )

    return Response(
        BookRentalRequestSerializer(req, context={'request': request}).data,
        status=201
    )


# ─────────────────────────────────────────────────────────────
#  STUDENT: Mening arizalarim
# ─────────────────────────────────────────────────────────────

class MyRentalRequestsView(APIView):
    permission_classes = AUTH

    def get(self, request):
        requests_qs = BookRentalRequest.objects.filter(
            student=request.user
        ).select_related('book', 'processed_by').order_by('-created_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            requests_qs = requests_qs.filter(status=status_filter)

        serializer = BookRentalRequestSerializer(
            requests_qs, many=True, context={'request': request}
        )
        return Response({'count': requests_qs.count(), 'results': serializer.data})


@api_view(['POST'])
@permission_classes(AUTH)
def cancel_request(request, pk):
    """O'quvchi arizasini bekor qiladi."""
    try:
        req = BookRentalRequest.objects.get(pk=pk, student=request.user)
    except BookRentalRequest.DoesNotExist:
        return Response({'detail': 'Ariza topilmadi.'}, status=404)

    if req.status != 'pending':
        return Response({'detail': 'Faqat kutilayotgan arizani bekor qilish mumkin.'}, status=400)

    req.status = 'cancelled'
    req.save()
    return Response({'detail': 'Ariza bekor qilindi.', 'status': 'cancelled'})


# ─────────────────────────────────────────────────────────────
#  STUDENT: Mening ijaralarim
# ─────────────────────────────────────────────────────────────

class MyRentalsView(APIView):
    permission_classes = AUTH

    def get(self, request):
        rentals = BookRental.objects.filter(
            student=request.user
        ).select_related('book', 'given_by').order_by('-created_at')

        active = rentals.filter(status__in=['active', 'overdue'])
        returned = rentals.filter(status='returned')

        return Response({
            'active_count': active.count(),
            'returned_count': returned.count(),
            'active': BookRentalSerializer(active, many=True, context={'request': request}).data,
            'returned': BookRentalSerializer(returned, many=True, context={'request': request}).data,
        })


# ─────────────────────────────────────────────────────────────
#  ADMIN: Kitoblar CRUD
# ─────────────────────────────────────────────────────────────

class AdminBookListCreateView(APIView):
    permission_classes = AUTH

    def get(self, request):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

        books = Book.objects.all()
        search = request.query_params.get('search', '').strip()
        sort = request.query_params.get('sort', 'title')
        available_only = request.query_params.get('available') == '1'

        if search:
            books = books.filter(
                Q(title__icontains=search) | Q(author__icontains=search) | Q(isbn__icontains=search)
            )
        if available_only:
            books = books.filter(available_copies__gt=0)

        sort_map = {
            'title': 'title', '-title': '-title',
            'author': 'author', 'newest': '-created_at',
            'oldest': 'created_at', 'available': '-available_copies',
        }
        books = books.order_by(sort_map.get(sort, 'title'))

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response({'count': books.count(), 'results': serializer.data})

    def post(self, request):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

        serializer = BookCreateSerializer(data=request.data)
        if not serializer.is_valid():
            # Duplicate xatolikni to'g'ri qaytarish
            errors = serializer.errors
            if 'duplicate' in str(errors):
                return Response(errors, status=409)
            return Response(errors, status=400)

        book = serializer.save()
        return Response(
            BookListSerializer(book, context={'request': request}).data,
            status=201
        )


class AdminBookDetailView(APIView):
    permission_classes = AUTH

    def _get_book(self, pk):
        try:
            return Book.objects.get(pk=pk)
        except Book.DoesNotExist:
            return None

    def get(self, request, pk):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)
        book = self._get_book(pk)
        if not book:
            return Response({'detail': 'Kitob topilmadi.'}, status=404)
        return Response(BookDetailSerializer(book, context={'request': request}).data)

    def put(self, request, pk):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)
        book = self._get_book(pk)
        if not book:
            return Response({'detail': 'Kitob topilmadi.'}, status=404)

        serializer = BookCreateSerializer(book, data=request.data, partial=True)
        if not serializer.is_valid():
            errors = serializer.errors
            if 'duplicate' in str(errors):
                return Response(errors, status=409)
            return Response(errors, status=400)

        # total_copies o'zgarganda available_copies ni moslashtirish
        old_total = book.total_copies
        new_total = serializer.validated_data.get('total_copies', old_total)
        diff = new_total - old_total
        book = serializer.save()
        if diff != 0:
            book.available_copies = max(0, book.available_copies + diff)
            book.save(update_fields=['available_copies'])

        return Response(BookListSerializer(book, context={'request': request}).data)

    def delete(self, request, pk):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)
        book = self._get_book(pk)
        if not book:
            return Response({'detail': 'Kitob topilmadi.'}, status=404)

        active = BookRental.objects.filter(book=book, status__in=['active', 'overdue']).count()
        if active:
            return Response(
                {'detail': f'Bu kitobning {active} ta faol ijarasi bor. Avval qaytaring.'},
                status=400
            )
        book.delete()
        return Response({'detail': 'Kitob o\'chirildi.'}, status=204)


# ─────────────────────────────────────────────────────────────
#  ADMIN: Arizalar (requests)
# ─────────────────────────────────────────────────────────────

class AdminRequestListView(APIView):
    permission_classes = AUTH

    def get(self, request):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

        requests_qs = BookRentalRequest.objects.select_related(
            'book', 'student', 'processed_by'
        ).all()

        status_filter = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()

        if status_filter:
            requests_qs = requests_qs.filter(status=status_filter)
        if search:
            requests_qs = requests_qs.filter(
                Q(book__title__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )

        requests_qs = requests_qs.order_by('-created_at')
        serializer = BookRentalRequestSerializer(
            requests_qs, many=True, context={'request': request}
        )
        return Response({
            'count': requests_qs.count(),
            'pending_count': BookRentalRequest.objects.filter(status='pending').count(),
            'results': serializer.data,
        })


@api_view(['POST'])
@permission_classes(AUTH)
def approve_request(request, pk):
    """Admin arizani tasdiqlaydi va ijara yaratadi."""
    if not _is_admin_or_assistant(request.user):
        return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

    try:
        req = BookRentalRequest.objects.select_related('book', 'student').get(pk=pk)
    except BookRentalRequest.DoesNotExist:
        return Response({'detail': 'Ariza topilmadi.'}, status=404)

    if req.status != 'pending':
        return Response({'detail': 'Faqat kutilayotgan arizani tasdiqlash mumkin.'}, status=400)

    book = req.book
    if not book.is_available:
        return Response({'detail': f'«{book.title}» kitobi hozirda mavjud emas.'}, status=400)

    # Qaytarish sanasi (default 14 kun)
    days = int(request.data.get('days', 14))
    days = max(1, min(days, 90))
    return_date = date.today() + timedelta(days=days)
    admin_note = request.data.get('admin_note', '')

    # Ijara yaratish
    rental = BookRental.objects.create(
        book=book,
        student=req.student,
        given_by=request.user,
        return_date=return_date,
        notes=admin_note,
    )
    book.available_copies -= 1
    book.save(update_fields=['available_copies'])

    # Arizani yangilash
    req.status = 'approved'
    req.processed_by = request.user
    req.processed_at = timezone.now()
    req.admin_note = admin_note
    req.rental = rental
    req.save()

    # O'quvchiga xabar
    Message.objects.create(
        sender=request.user,
        recipient=req.student,
        message_type='notification',
        content=(
            f"✅ Sizning kitob arizangiz tasdiqlandi!\n"
            f"Kitob: «{book.title}» — {book.author}\n"
            f"Qaytarish sanasi: {return_date.strftime('%d.%m.%Y')}\n"
            f"Iltimos, kitobni o'z vaqtida qaytaring!"
        ),
    )

    return Response({
        'detail': 'Ariza tasdiqlandi va ijara yaratildi.',
        'rental': BookRentalSerializer(rental, context={'request': request}).data,
    })


@api_view(['POST'])
@permission_classes(AUTH)
def reject_request(request, pk):
    """Admin arizani rad etadi."""
    if not _is_admin_or_assistant(request.user):
        return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

    try:
        req = BookRentalRequest.objects.select_related('book', 'student').get(pk=pk)
    except BookRentalRequest.DoesNotExist:
        return Response({'detail': 'Ariza topilmadi.'}, status=404)

    if req.status != 'pending':
        return Response({'detail': 'Faqat kutilayotgan arizani rad etish mumkin.'}, status=400)

    admin_note = request.data.get('admin_note', '')
    req.status = 'rejected'
    req.processed_by = request.user
    req.processed_at = timezone.now()
    req.admin_note = admin_note
    req.save()

    # O'quvchiga xabar
    Message.objects.create(
        sender=request.user,
        recipient=req.student,
        message_type='notification',
        content=(
            f"❌ Kitob arizangiz rad etildi.\n"
            f"Kitob: «{req.book.title}» — {req.book.author}\n"
            + (f"Sabab: {admin_note}" if admin_note else "")
        ),
    )

    return Response({'detail': 'Ariza rad etildi.', 'status': 'rejected'})


# ─────────────────────────────────────────────────────────────
#  ADMIN: Ijaralar
# ─────────────────────────────────────────────────────────────

class AdminRentalListView(APIView):
    permission_classes = AUTH

    def get(self, request):
        if not _is_admin_or_assistant(request.user):
            return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

        rentals = BookRental.objects.select_related('book', 'student', 'given_by').all()

        status_filter = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()
        sort = request.query_params.get('sort', '-created_at')

        if status_filter:
            rentals = rentals.filter(status=status_filter)
        if search:
            rentals = rentals.filter(
                Q(book__title__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )

        sort_map = {
            '-created_at': '-created_at',
            'created_at': 'created_at',
            'return_date': 'return_date',
            '-return_date': '-return_date',
            'book': 'book__title',
            'student': 'student__last_name',
        }
        rentals = rentals.order_by(sort_map.get(sort, '-created_at'))

        today = date.today()
        overdue_count = rentals.filter(status='active', return_date__lt=today).count()
        active_count = rentals.filter(status__in=['active', 'overdue']).count()

        serializer = BookRentalSerializer(rentals, many=True, context={'request': request})
        return Response({
            'count': rentals.count(),
            'active_count': active_count,
            'overdue_count': overdue_count,
            'results': serializer.data,
        })


@api_view(['POST'])
@permission_classes(AUTH)
def return_rental(request, pk):
    """Admin kitobni qaytarilgan deb belgilaydi."""
    if not _is_admin_or_assistant(request.user):
        return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

    try:
        rental = BookRental.objects.select_related('book', 'student').get(pk=pk)
    except BookRental.DoesNotExist:
        return Response({'detail': 'Ijara topilmadi.'}, status=404)

    if rental.status == 'returned':
        return Response({'detail': 'Bu ijara allaqachon qaytarilgan.'}, status=400)

    rental.mark_returned(request.user)

    # O'quvchiga xabar
    Message.objects.create(
        sender=request.user,
        recipient=rental.student,
        message_type='notification',
        content=(
            f"✅ «{rental.book.title}» kitobi muvaffaqiyatli qaytarildi. Rahmat!"
        ),
    )

    return Response({
        'detail': 'Kitob qaytarildi.',
        'rental': BookRentalSerializer(rental, context={'request': request}).data,
    })


# ─────────────────────────────────────────────────────────────
#  ADMIN: Statistika
# ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes(AUTH)
def library_stats(request):
    if not _is_admin_or_assistant(request.user):
        return Response({'detail': 'Ruxsat yo\'q.'}, status=403)

    today = date.today()
    all_books = Book.objects.all()
    total_books = all_books.count()
    total_copies = sum(b.total_copies for b in all_books)
    available_copies = sum(b.available_copies for b in all_books)
    rented_copies = total_copies - available_copies

    data = {
        'total_books': total_books,
        'total_copies': total_copies,
        'available_copies': available_copies,
        'rented_copies': rented_copies,
        'active_rentals': BookRental.objects.filter(status__in=['active', 'overdue']).count(),
        'overdue_rentals': BookRental.objects.filter(status='active', return_date__lt=today).count(),
        'pending_requests': BookRentalRequest.objects.filter(status='pending').count(),
        'total_requests': BookRentalRequest.objects.count(),
        'returned_today': BookRental.objects.filter(actual_return_date=today).count(),
    }
    return Response(LibraryStatsSerializer(data).data)
