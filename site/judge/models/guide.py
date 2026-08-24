from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from judge.models.problem import ProblemType


class AlgorithmGuide(models.Model):
    problem_type = models.ForeignKey(
        ProblemType,
        related_name='algorithm_guides',
        on_delete=models.PROTECT,
        verbose_name=_('algorithm tag'),
    )
    title = models.CharField(max_length=150, verbose_name=_('title'))
    summary = models.CharField(max_length=300, verbose_name=_('summary'))
    content = models.TextField(verbose_name=_('content'))
    is_published = models.BooleanField(default=False, db_index=True, verbose_name=_('published'))
    order = models.PositiveIntegerField(default=0, db_index=True, verbose_name=_('order'))
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='algorithm_guides',
        verbose_name=_('created by'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('guide_detail', args=(self.problem_type.name, self.pk))

    class Meta:
        ordering = ('order', 'title', 'id')
        verbose_name = '가이드'
        verbose_name_plural = '가이드'
