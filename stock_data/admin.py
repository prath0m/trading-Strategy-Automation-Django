from django.contrib import admin
from .models import StockSymbol, DataFetchRequest, APICredentials


@admin.register(StockSymbol)
class StockSymbolAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'instrument_token', 'created_at']
    search_fields = ['symbol', 'name']
    list_filter = ['created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DataFetchRequest)
class DataFetchRequestAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'from_date', 'to_date', 'interval', 'status', 'created_at']
    list_filter = ['status', 'interval', 'created_at']
    search_fields = ['symbol__symbol', 'symbol__name']
    readonly_fields = ['created_at', 'updated_at', 'file_path']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('symbol')


@admin.register(APICredentials)
class APICredentialsAdmin(admin.ModelAdmin):
    list_display = ['name', 'api_key', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Hide API secret in admin for security
        if 'api_secret' in form.base_fields:
            form.base_fields['api_secret'].widget.attrs['type'] = 'password'
        return form
