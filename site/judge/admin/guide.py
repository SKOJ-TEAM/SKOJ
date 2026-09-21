from django.contrib import admin
from django.contrib.admin.filters import FieldListFilter
from django.forms import ModelForm
from django.http import JsonResponse
from django.urls import path, reverse_lazy
from django.utils.html import format_html

from judge.models import AlgorithmGuide, GuideImage, ProblemGroup
from judge.widgets import AdminMartorWidget


class AlgorithmGuideForm(ModelForm):
    class Meta:
        model = AlgorithmGuide
        fields = '__all__'
        widgets = {
            'content': AdminMartorWidget(attrs={'data-markdownfy-url': reverse_lazy('guide_preview')}),
        }


class GuideCombinedInputFilter(FieldListFilter):
    title = ' '
    template = 'admin/input_filter/input_filter_guide.html'
    filter_keys = ('is_published__exact', 'problem_group__id__exact')

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.request = request
        self.group_lookups = tuple(
            (str(group_id), full_name)
            for group_id, full_name in ProblemGroup.objects.order_by('full_name').values_list('id', 'full_name')
        )
        self.group_handles = {group_id for group_id, _ in self.group_lookups}

    def expected_parameters(self):
        return self.filter_keys

    def choices(self, changelist):
        return ()

    def queryset(self, request, queryset):
        is_published = request.GET.get('is_published__exact')
        problem_group = request.GET.get('problem_group__id__exact')
        if is_published in ('0', '1'):
            queryset = queryset.filter(is_published=(is_published == '1'))
        if problem_group in self.group_handles:
            queryset = queryset.filter(problem_group_id=problem_group)
        return queryset


@admin.register(AlgorithmGuide)
class AlgorithmGuideAdmin(admin.ModelAdmin):
    form = AlgorithmGuideForm
    fields = ('problem_group', 'title', 'summary', 'content', 'is_published', 'order', 'created_by')
    readonly_fields = ('created_by',)
    list_display = ('title', 'problem_group', 'is_published', 'order', 'updated_at')
    list_filter = (('id', GuideCombinedInputFilter),)
    list_editable = ('is_published', 'order')
    search_fields = ('title', 'summary', 'content', 'problem_group__full_name')
    ordering = ('order', 'title')

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(GuideImage)
class GuideImageAdmin(admin.ModelAdmin):
    fields = ('title', 'alt_text', 'image', 'preview', 'uploaded_by', 'created_at')
    readonly_fields = ('preview', 'uploaded_by', 'created_at')
    list_display = ('thumbnail', 'title', 'alt_text', 'uploaded_by', 'created_at')
    search_fields = ('title', 'alt_text', 'uploaded_by__username')
    ordering = ('-created_at',)

    def get_urls(self):
        return [
            path('library/', self.admin_site.admin_view(self.library), name='judge_guideimage_library'),
        ] + super().get_urls()

    def library(self, request):
        query = request.GET.get('q', '').strip()
        images = self.get_queryset(request)
        if query:
            images = images.filter(title__icontains=query)
        return JsonResponse({'images': [
            {
                'title': item.title,
                'alt': item.markdown_alt,
                'url': item.image.url,
            }
            for item in images[:100]
        ]})

    @admin.display(description='미리보기')
    def preview(self, obj):
        if not obj or not obj.image:
            return '-'
        return format_html('<img src="{}" alt="" style="max-width:600px;max-height:400px">', obj.image.url)

    @admin.display(description='이미지')
    def thumbnail(self, obj):
        return format_html('<img src="{}" alt="" style="width:72px;height:48px;object-fit:cover">', obj.image.url)

    def save_model(self, request, obj, form, change):
        if obj.uploaded_by_id is None:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
