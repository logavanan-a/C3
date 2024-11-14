from django.contrib import admin
from import_export.admin import ImportExportModelAdmin, ImportExportMixin
from import_export.formats import base_formats
from import_export import resources, fields
from import_export.fields import Field
from .models import ChartMeta, DashboardWidgetSummaryLog, ReportMeta
from application_masters.admin import ImportExportFormat


@admin.register(ChartMeta)
class ChartMetaAdmin(ImportExportModelAdmin, ImportExportFormat):
    list_display = ['chart_title', 'chart_type', 'page_slug',
                    'chart_note', 'div_class', 'display_order', 'status']
    fields = ['chart_type', 'chart_slug', 'page_slug',
              'chart_title', 'vertical_axis_title', 'horizontal_axis_title',
              'chart_note', 'chart_tooltip', 'chart_height',
              'click_handler', 'chart_options', 'div_class',
              'chart_query', 'filter_info', 'display_order', 'status']
    list_filter = ['chart_type', ]
    search_fields = ['chart_type', 'chart_title']


@admin.register(DashboardWidgetSummaryLog)
class DashboardWidgetSummaryLogAdmin(ImportExportModelAdmin, ImportExportFormat):
    list_display = ['log_key', 'last_successful_update',
                    'most_recent_update', 'most_recent_update_time_taken_millis']
    fields = ['log_key', 'last_successful_update', 'most_recent_update',
              'most_recent_update_time_taken_millis', 'most_recent_update_status', 'status']
    search_fields = ['last_successful_update', 'most_recent_update']

@admin.register(ReportMeta)
class ReportMetaAdmin(ImportExportModelAdmin, ImportExportFormat):
    list_display = ['report_title', 'page_slug', 'report_slug',
                    'display_order', 'site_id', 'status']
    fields = ['page_slug', 'report_slug',  'report_title', 'report_header',
               'site_id', 'display_order', 'report_query', 'filter_info', 'sort_info', 'status']
    search_fields = ['report_title', 'report_slug']

