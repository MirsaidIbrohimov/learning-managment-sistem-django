from rest_framework import serializers
from django.db.models import Q
from accounts.models import Book, BookRental, BookRentalRequest, CustomUser


class BookListSerializer(serializers.ModelSerializer):
    is_available = serializers.BooleanField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    active_rentals_count = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'isbn', 'description',
            'cover_image_url', 'total_copies', 'available_copies',
            'is_available', 'active_rentals_count', 'created_at',
        ]

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and request:
            return request.build_absolute_uri(obj.cover_image.url)
        return None

    def get_active_rentals_count(self, obj):
        return obj.total_copies - obj.available_copies


class BookDetailSerializer(BookListSerializer):
    similar_books = serializers.SerializerMethodField()
    my_request_status = serializers.SerializerMethodField()
    my_active_rental = serializers.SerializerMethodField()

    class Meta(BookListSerializer.Meta):
        fields = BookListSerializer.Meta.fields + [
            'similar_books', 'my_request_status', 'my_active_rental',
        ]

    def get_similar_books(self, obj):
        similar = Book.objects.filter(author=obj.author).exclude(pk=obj.pk)[:5]
        return BookListSerializer(similar, many=True, context=self.context).data

    def get_my_request_status(self, obj):
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return None
        req = BookRentalRequest.objects.filter(book=obj, student=user).exclude(
            status__in=['cancelled', 'rejected']
        ).first()
        if req:
            return {'id': req.id, 'status': req.status, 'status_display': req.get_status_display()}
        return None

    def get_my_active_rental(self, obj):
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return None
        rental = BookRental.objects.filter(
            book=obj, student=user, status__in=['active', 'overdue']
        ).first()
        if rental:
            return {
                'id': rental.id,
                'return_date': rental.return_date,
                'is_overdue': rental.is_overdue,
                'days_until_return': rental.days_until_return,
            }
        return None


class BookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ['title', 'author', 'isbn', 'description', 'cover_image', 'total_copies']

    def validate(self, data):
        title = data.get('title', '').strip()
        author = data.get('author', '').strip()
        isbn = data.get('isbn', '').strip()

        # Duplicate: nom+muallif YOKI ISBN
        dup_q = Q(title__iexact=title, author__iexact=author)
        if isbn:
            dup_q |= Q(isbn__iexact=isbn)

        qs = Book.objects.filter(dup_q)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        existing = qs.first()
        if existing:
            if isbn and existing.isbn and existing.isbn.lower() == isbn.lower():
                reason = f"ISBN «{isbn}» allaqaçon mavjud"
            else:
                reason = "Nom va muallif bir xil"
            raise serializers.ValidationError({
                'duplicate': True,
                'reason': reason,
                'message': f"Bu kitob allaqaçon mavjud ({reason}): \"{existing.title}\" — {existing.author}",
                'existing_id': existing.pk,
                'existing_title': existing.title,
                'existing_author': existing.author,
                'existing_isbn': existing.isbn or '',
                'existing_copies': existing.total_copies,
                'existing_available': existing.available_copies,
            })
        return data

    def validate_total_copies(self, value):
        if value < 1:
            raise serializers.ValidationError("Nusxalar soni 1 dan kam bölmasligi kerak.")
        return value

    def create(self, validated_data):
        validated_data['available_copies'] = validated_data.get('total_copies', 1)
        return super().create(validated_data)


class BookDuplicateCheckSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300, required=False, default='')
    author = serializers.CharField(max_length=200, required=False, default='')
    isbn = serializers.CharField(max_length=50, required=False, default='')

    def check(self):
        title = self.validated_data.get('title', '').strip()
        author = self.validated_data.get('author', '').strip()
        isbn = self.validated_data.get('isbn', '').strip()

        # Exact duplicate: nom+muallif YOKI ISBN
        exact = None
        isbn_exact = None
        if isbn:
            isbn_exact = Book.objects.filter(isbn__iexact=isbn).first()
        if title and author:
            exact = Book.objects.filter(title__iexact=title, author__iexact=author).first()

        # Asosiy duplicate: ISBN ustuvor
        primary = isbn_exact or exact
        duplicate_reason = None
        if isbn_exact:
            duplicate_reason = 'isbn'
        elif exact:
            duplicate_reason = 'title_author'

        # Öxşaş kitoblar — exact bor bölsa ham körsatiladi, faqat exact ni özi çiqarilmaydi
        similar_qs = Book.objects.none()
        if title or author:
            q = Q()
            if title:
                q |= Q(title__icontains=title)
            if author:
                q |= Q(author__icontains=author)
            similar_qs = Book.objects.filter(q)
            if primary:
                similar_qs = similar_qs.exclude(pk=primary.pk)
            similar_qs = similar_qs[:8]

        def book_dict(b):
            return {
                'id': b.pk,
                'title': b.title,
                'author': b.author,
                'isbn': b.isbn or '',
                'total_copies': b.total_copies,
                'available_copies': b.available_copies,
            }

        return {
            'has_exact_duplicate': primary is not None,
            'duplicate_reason': duplicate_reason,
            'exact': book_dict(primary) if primary else None,
            'similar_books': [book_dict(b) for b in similar_qs],
        }


class BookRentalRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookRentalRequest
        fields = ['book', 'message']

    def validate(self, data):
        book = data['book']
        student = self.context['request'].user

        if not book.is_available:
            raise serializers.ValidationError("Bu kitob hozirda mavjud emas — barça nusxalar ijarada.")

        active_request = BookRentalRequest.objects.filter(
            book=book, student=student
        ).exclude(status__in=['cancelled', 'rejected']).first()
        if active_request:
            raise serializers.ValidationError(
                f"Siz bu kitob uçun allaqaçon ariza berdingiz (holat: {active_request.get_status_display()})."
            )

        active_rental = BookRental.objects.filter(
            book=book, student=student, status__in=['active', 'overdue']
        ).first()
        if active_rental:
            raise serializers.ValidationError("Siz bu kitobni allaqaçon ijarada olganrsiz.")

        return data


class BookRentalRequestSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_author = serializers.CharField(source='book.author', read_only=True)
    book_cover = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_phone = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        model = BookRentalRequest
        fields = [
            'id', 'book', 'book_title', 'book_author', 'book_cover',
            'student', 'student_name', 'student_phone',
            'status', 'status_display', 'message', 'admin_note',
            'processed_by', 'processed_by_name', 'processed_at',
            'rental', 'can_cancel', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'student', 'status', 'processed_by', 'processed_at', 'rental',
        ]

    def get_book_cover(self, obj):
        request = self.context.get('request')
        if obj.book.cover_image and request:
            return request.build_absolute_uri(obj.book.cover_image.url)
        return None

    def get_student_phone(self, obj):
        return getattr(obj.student, 'phone', None)

    def get_processed_by_name(self, obj):
        if obj.processed_by:
            return obj.processed_by.full_name
        return None


class BookRentalSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_author = serializers.CharField(source='book.author', read_only=True)
    book_cover = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    given_by_name = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    days_until_return = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = BookRental
        fields = [
            'id', 'book', 'book_title', 'book_author', 'book_cover',
            'student', 'student_name',
            'given_by', 'given_by_name',
            'given_date', 'return_date', 'actual_return_date',
            'status', 'status_display', 'notes',
            'is_overdue', 'days_until_return',
            'created_at', 'updated_at',
        ]

    def get_book_cover(self, obj):
        request = self.context.get('request')
        if obj.book.cover_image and request:
            return request.build_absolute_uri(obj.book.cover_image.url)
        return None

    def get_given_by_name(self, obj):
        if obj.given_by:
            return obj.given_by.full_name
        return None


class LibraryStatsSerializer(serializers.Serializer):
    total_books = serializers.IntegerField()
    total_copies = serializers.IntegerField()
    available_copies = serializers.IntegerField()
    rented_copies = serializers.IntegerField()
    active_rentals = serializers.IntegerField()
    overdue_rentals = serializers.IntegerField()
    pending_requests = serializers.IntegerField()
    total_requests = serializers.IntegerField()
    returned_today = serializers.IntegerField()
