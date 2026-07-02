from django.utils import timezone
from rest_framework import serializers

from .models import AnswerOption, Attempt, Question, QuestionType, Quiz, QuizQuestion, QuizSettings

# Seed of the Phase 2 question-type registry (docs/QUIZ_MODULE_REDESIGN.md
# §3.2). For now this is a plain rules table; Phase 2 promotes each entry to
# a full strategy class (render/validate/grade) without touching callers.
QUESTION_TYPE_RULES = {
    QuestionType.SINGLE_CHOICE: {'requires_options': True, 'min_options': 2, 'correct_rule': 'exactly_one'},
    QuestionType.TRUE_FALSE: {'requires_options': True, 'min_options': 2, 'correct_rule': 'exactly_one'},
    QuestionType.MULTIPLE_CHOICE: {'requires_options': True, 'min_options': 2, 'correct_rule': 'at_least_one'},
    QuestionType.SHORT_ANSWER: {'requires_options': False, 'min_options': 0, 'correct_rule': None},
    QuestionType.ESSAY: {'requires_options': False, 'min_options': 0, 'correct_rule': None},
}


class AnswerOptionSerializer(serializers.ModelSerializer):
    # Writable (not the default read-only pk field) so QuestionSerializer.update()
    # can tell "this option already exists, keep its row (and image)" apart from
    # "this is a brand new option" -- see _sync_options below. Never trusted
    # blindly: _sync_options only honours an id that's already among this
    # specific question's own options.
    id = serializers.IntegerField(required=False)

    class Meta:
        model = AnswerOption
        fields = ['id', 'text', 'image', 'is_correct', 'order']


class QuestionSerializer(serializers.ModelSerializer):
    options = AnswerOptionSerializer(many=True, required=False)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Question
        fields = [
            'id', 'type', 'text', 'image', 'explanation', 'hints', 'code_language',
            'metadata', 'difficulty', 'points_default', 'status', 'usage_count',
            'last_used_at', 'created_by', 'created_at', 'updated_at', 'options',
        ]
        read_only_fields = ['id', 'usage_count', 'last_used_at', 'created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        q_type = attrs.get('type', getattr(self.instance, 'type', None) or QuestionType.SINGLE_CHOICE)
        rules = QUESTION_TYPE_RULES.get(q_type)
        if rules is None:
            raise serializers.ValidationError({'type': f'Unknown question type "{q_type}".'})

        if rules['requires_options']:
            if 'options' in attrs:
                opts = attrs['options']
                if len(opts) < rules['min_options']:
                    raise serializers.ValidationError(
                        {'options': f"At least {rules['min_options']} options are required for this question type."}
                    )
                correct_count = sum(1 for o in opts if o.get('is_correct'))
                if rules['correct_rule'] == 'exactly_one' and correct_count != 1:
                    raise serializers.ValidationError({'options': 'Exactly one option must be marked correct.'})
                if rules['correct_rule'] == 'at_least_one' and correct_count < 1:
                    raise serializers.ValidationError({'options': 'At least one option must be marked correct.'})
                texts = [o.get('text', '').strip().lower() for o in opts]
                if len(set(texts)) != len(texts):
                    raise serializers.ValidationError({'options': 'Answer options must be unique — duplicate option text found.'})
            elif self.instance is None:
                raise serializers.ValidationError({'options': 'This question type requires answer options.'})
        elif q_type == QuestionType.SHORT_ANSWER:
            metadata = attrs.get('metadata', getattr(self.instance, 'metadata', None) or {})
            if not metadata.get('correct_answers'):
                raise serializers.ValidationError(
                    {'metadata': 'short_answer questions require metadata.correct_answers (a list of acceptable answers).'}
                )
        return attrs

    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        question = Question.objects.create(**validated_data)
        self._save_options(question, options_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if options_data is not None:
            self._sync_options(instance, options_data)
        return instance

    @staticmethod
    def _save_options(question, options_data):
        AnswerOption.objects.bulk_create([
            AnswerOption(
                question=question,
                text=opt.get('text', ''),
                image=opt.get('image'),
                is_correct=opt.get('is_correct', False),
                order=opt.get('order', i),
            )
            for i, opt in enumerate(options_data)
        ])

    @staticmethod
    def _sync_options(question, options_data):
        """
        Diffs incoming options against the question's existing rows by id
        instead of the old delete-all-then-recreate approach. That approach
        silently wiped every AnswerOption.image on every edit (a fresh row
        has no image until someone re-uploads one) -- see the Phase 1 known
        limitation noted in docs/QUIZ_MODULE_REDESIGN.md. Preserving row
        identity for options the client still references keeps a previously
        uploaded image intact across unrelated edits (e.g. fixing a typo).

        An incoming id is only honoured if it's already one of *this*
        question's own options -- there is no path for a client to hijack
        another question's option row by guessing its id.
        """
        existing = {o.id: o for o in question.options.all()}
        seen_ids = set()
        to_create = []

        for i, opt in enumerate(options_data):
            order = opt.get('order', i)
            opt_id = opt.get('id')
            row = existing.get(opt_id) if opt_id else None
            if row is not None:
                row.text = opt.get('text', row.text)
                row.is_correct = opt.get('is_correct', row.is_correct)
                row.order = order
                row.save(update_fields=['text', 'is_correct', 'order'])
                seen_ids.add(opt_id)
            else:
                to_create.append(AnswerOption(
                    question=question,
                    text=opt.get('text', ''),
                    is_correct=opt.get('is_correct', False),
                    order=order,
                ))

        if to_create:
            AnswerOption.objects.bulk_create(to_create)

        removed_ids = set(existing) - seen_ids
        if removed_ids:
            for oid in removed_ids:
                existing[oid].image.delete(save=False)  # don't orphan the file on disk
            AnswerOption.objects.filter(id__in=removed_ids).delete()


class QuestionDuplicateOptionSerializer(serializers.Serializer):
    """Used only to shape the response of the `duplicate` action."""
    id = serializers.IntegerField()


class QuizSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizSettings
        fields = [
            'time_limit_minutes', 'passing_score', 'allow_retry', 'attempts_allowed',
            'shuffle_questions', 'shuffle_answers', 'question_count', 'negative_marking',
        ]


class QuizQuestionSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    question_id = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(), source='question', write_only=True
    )
    points = serializers.IntegerField(read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ['id', 'question', 'question_id', 'order', 'points_override', 'points', 'group']


class QuizSerializer(serializers.ModelSerializer):
    settings = QuizSettingsSerializer()
    question_count_actual = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    lesson_label = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = [
            'id', 'lesson', 'lesson_label', 'title', 'description', 'status', 'created_by',
            'created_at', 'updated_at', 'settings', 'question_count_actual',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'lesson_label']

    def get_question_count_actual(self, obj):
        return obj.quiz_questions.count()

    def get_lesson_label(self, obj):
        """Human-readable "Profession — Lesson title" for the builder's
        lesson-picker display in edit mode, so the UI doesn't need a second
        round trip just to show what a raw lesson id means."""
        if not obj.lesson_id:
            return None
        lesson = obj.lesson
        profession_name = lesson.profession.name if lesson.profession_id else ''
        return f"{profession_name} — {lesson.title}" if profession_name else lesson.title

    def create(self, validated_data):
        settings_data = validated_data.pop('settings')
        quiz = Quiz.objects.create(**validated_data)
        QuizSettings.objects.create(quiz=quiz, **settings_data)
        return quiz

    def update(self, instance, validated_data):
        settings_data = validated_data.pop('settings', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if settings_data is not None:
            for attr, value in settings_data.items():
                setattr(instance.settings, attr, value)
            instance.settings.save()
        return instance


class AttemptSerializer(serializers.ModelSerializer):
    """
    Summary representation of an Attempt -- returned by every action on
    AttemptViewSet. Deliberately excludes question content: the in-progress
    question payload (correctness hidden) and the post-submit review payload
    (correctness revealed) are assembled separately in views.py, since which
    one is safe to send depends on `status` and must never be controlled by
    the serializer alone.
    """
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = [
            'id', 'quiz', 'quiz_title', 'status', 'attempt_number', 'resume_token',
            'score', 'total_questions', 'correct_count', 'passed', 'coin_awarded', 'coins_earned',
            'started_at', 'expires_at', 'submitted_at', 'remaining_seconds',
        ]
        read_only_fields = fields

    def get_remaining_seconds(self, obj):
        if obj.status != Attempt.Status.IN_PROGRESS:
            return 0
        return max(0, int((obj.expires_at - timezone.now()).total_seconds()))
