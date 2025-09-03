from django.urls import path
from . import views

urlpatterns = [
    # Main pages
    path('', views.index, name='index'),
    path('data/', views.data_view, name='data_view'),
    path('settings/', views.settings, name='settings'),
    path('strategy/', views.strategy_view, name='strategy_view'),
    path('signals/', views.signals_view, name='signals_view'),
    path('backtest/', views.backtest_view, name='backtest_view'),
    path('charts/', views.charts_view, name='charts_view'),
    
    # API endpoints
    path('fetch-data/', views.fetch_data_api, name='fetch_data_api'),
    path('execute-strategy/', views.execute_strategy, name='execute_strategy'),
    path('test-connection/', views.test_connection, name='test_connection'),
    path('api/chart-data/<int:backtest_id>/', views.chart_data_api, name='chart_data_api'),
]
