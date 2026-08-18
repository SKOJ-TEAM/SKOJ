from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class PatchNote(models.Model):
    """패치 노트 모델"""
    
    title = models.CharField(
        max_length=200,
        verbose_name="제목",
        help_text="패치 노트 제목 (예: Patch Note)"
    )
    
    version = models.CharField(
        max_length=50,
        verbose_name="버전",
        help_text="패치 버전 (예: 2025.03.04)"
    )
    
    content = models.TextField(
        verbose_name="내용",
        help_text="패치 노트 내용 (HTML 형식 지원)"
    )
    
    is_published = models.BooleanField(
        default=True,
        verbose_name="게시 여부",
        help_text="체크하면 웹사이트에 표시됩니다"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="작성자",
        related_name="patch_notes"
    )
    
    order = models.IntegerField(
        default=0,
        verbose_name="순서",
        help_text="낮은 숫자가 먼저 표시됩니다"
    )

    class Meta:
        verbose_name = "패치 노트"
        verbose_name_plural = "패치 노트"
        ordering = ['order', '-created_at']  # 순서별(오름차순), 최신순

    def __str__(self):
        return f"{self.title} - {self.version}"

    def save(self, *args, **kwargs):
        # order가 None인 경우에만 자동으로 설정 (0은 유효한 값으로 처리)
        if self.order is None:
            # 새로운 패치 노트의 경우 가장 높은 순서 + 1
            max_order = PatchNote.objects.aggregate(
                models.Max('order')
            )['order__max'] or 0
            self.order = max_order + 1
        super().save(*args, **kwargs)
