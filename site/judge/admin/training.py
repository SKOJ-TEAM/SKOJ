from django.contrib import admin

from judge.models import Campus, Cohort, TrainingClass


class CohortAdmin(admin.ModelAdmin):
    fields = ('number', 'is_active')
    list_display = ('number', 'is_active')
    list_filter = ('is_active',)
    ordering = ('-number',)


class CampusAdmin(admin.ModelAdmin):
    fields = ('code', 'name', 'is_active')
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


class TrainingClassAdmin(admin.ModelAdmin):
    fields = ('cohort', 'campus', 'number', 'is_active')
    list_display = ('cohort', 'campus', 'number', 'is_active')
    list_filter = ('cohort', 'campus', 'is_active')
    list_select_related = ('cohort', 'campus')
    ordering = ('-cohort__number', 'campus__name', 'number')
