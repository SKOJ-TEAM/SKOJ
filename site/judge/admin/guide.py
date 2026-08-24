from django.contrib import admin
from django.forms import ModelForm
from django.urls import reverse_lazy

from judge.models import AlgorithmGuide
from judge.widgets import AdminMartorWidget


class AlgorithmGuideForm(ModelForm):
    class Meta:
        model = AlgorithmGuide
        fields = '__all__'
        widgets = {
            'content': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('guide_preview')}),
        }


@admin.register(AlgorithmGuide)
class AlgorithmGuideAdmin(admin.ModelAdmin):
    form = AlgorithmGuideForm
    fields = ('problem_type', 'title', 'summary', 'content', 'is_published', 'order', 'created_by')
    readonly_fields = ('created_by',)
    list_display = ('title', 'problem_type', 'is_published', 'order', 'updated_at')
    list_filter = ('is_published', 'problem_type')
    list_editable = ('is_published', 'order')
    search_fields = ('title', 'summary', 'content', 'problem_type__full_name')
    ordering = ('order', 'title')

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
