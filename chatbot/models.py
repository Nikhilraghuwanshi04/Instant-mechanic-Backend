from django.db import models


class Conversation(models.Model):
    """Ek chat thread: user aur mechanic bot ki poori baat-cheet."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        DIAGNOSED = 'diagnosed', 'Diagnosed'
        BOOKED = 'booked', 'Booked'
        CLOSED = 'closed', 'Closed'

    title = models.CharField(max_length=200, default='New conversation')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    state = models.JSONField(default=dict, blank=True)
    vehicle_make = models.CharField(max_length=100, blank=True, default='')
    vehicle_model = models.CharField(max_length=100, blank=True, default='')
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'#{self.pk} — {self.title}'


class Message(models.Model):
    """Conversation ke andar ek message bubble (user ka ya bot ka)."""

    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    class GeneratedBy(models.TextChoices):
        USER = 'user', 'User'
        RULE_ENGINE = 'rule_engine', 'Rule Engine'
        GEMINI = 'gemini', 'Gemini'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    generated_by = models.CharField(
        max_length=20, choices=GeneratedBy.choices, default=GeneratedBy.USER
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_role_display()}: {self.content[:50]}'


class MediaUpload(models.Model):
    """Upload hui file ki record — asli file disk pe rehti hai, DB mein uska path."""

    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        AUDIO = 'audio', 'Audio'
        VIDEO = 'video', 'Video'

    class AnalysisStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ANALYZED = 'analyzed', 'Analyzed'
        SKIPPED = 'skipped', 'Skipped'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='media_uploads'
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_uploads',
    )
    file = models.FileField(upload_to='uploads/')
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    original_name = models.CharField(max_length=255)
    size_bytes = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100, blank=True, default='')
    analysis_status = models.CharField(
        max_length=20, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING
    )
    analysis_result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_media_type_display()}: {self.original_name}'


class Diagnosis(models.Model):
    """Rule engine ya Gemini se nikla structured diagnosis."""

    class Confidence(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    class GeneratedBy(models.TextChoices):
        RULE_ENGINE = 'rule_engine', 'Rule Engine'
        GEMINI = 'gemini', 'Gemini'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='diagnoses'
    )
    summary = models.JSONField(default=dict)
    likely_issue = models.CharField(max_length=200)
    reasoning = models.TextField()
    confidence = models.CharField(max_length=10, choices=Confidence.choices)
    can_drive = models.BooleanField(default=False)
    next_step = models.TextField()
    recommended_service = models.CharField(max_length=200)
    generated_by = models.CharField(max_length=20, choices=GeneratedBy.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} — {self.likely_issue} ({self.confidence})'


class Booking(models.Model):
    """Mechanic appointment — ek diagnosis ke liye sirf ek booking ban sakti hai."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    booking_ref = models.CharField(max_length=20, unique=True)
    diagnosis = models.OneToOneField(
        Diagnosis, on_delete=models.CASCADE, related_name='booking'
    )
    customer_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    preferred_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.booking_ref} — {self.customer_name}'
