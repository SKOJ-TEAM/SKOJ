from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from judge.models.patch_note import PatchNote


@admin.register(PatchNote)
class PatchNoteAdmin(admin.ModelAdmin):
    list_display = (
        'title', 
        'version', 
        'is_published', 
        'created_by', 
        'created_at', 
        'updated_at',
        'preview_link'
    )
    list_filter = ('is_published', 'created_at', 'created_by')
    search_fields = ('title', 'version', 'content')
    ordering = ('order', '-created_at')
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('title', 'version', 'is_published', 'order')
        }),
        ('내용', {
            'fields': ('content',),
            'description': 'HTML 태그를 사용할 수 있습니다.'
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # 새로 생성하는 경우
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def preview_link(self, obj):
        """미리보기 링크"""
        if obj.pk:
            url = reverse('about')  # about 페이지 URL
            return format_html(
                '<a href="{}" target="_blank">미리보기</a>',
                url
            )
        return "-"
    preview_link.short_description = "미리보기"
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = []
        if obj:  # 수정하는 경우
            readonly_fields.append('created_by')
        return readonly_fields
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'content':
            kwargs['widget'] = admin.widgets.AdminTextareaWidget(attrs={'rows': 20, 'cols': 80})
        return super().formfield_for_dbfield(db_field, **kwargs)
