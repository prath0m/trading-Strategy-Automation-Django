from django.db import models
from django.utils import timezone
import os
from django.conf import settings


class StockSymbol(models.Model):
    """Model to store stock symbols and their metadata"""
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    instrument_token = models.IntegerField()
    exchange = models.CharField(max_length=10, default='NSE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"
    
    class Meta:
        ordering = ['symbol']


class DataFetchRequest(models.Model):
    """Model to store data fetch requests and their status"""
    INTERVAL_CHOICES = [
        ('minute', 'Minute'),
        ('day', 'Day'),
        ('5minute', '5 Minutes'),
        ('15minute', '15 Minutes'),
        ('30minute', '30 Minutes'),
        ('60minute', '60 Minutes'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    symbol = models.ForeignKey(StockSymbol, on_delete=models.CASCADE)
    from_date = models.DateField()
    to_date = models.DateField()
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='minute')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    total_records = models.IntegerField(default=0)
    file_path = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.symbol.symbol} - {self.from_date} to {self.to_date} ({self.interval})"
    
    def get_file_path(self):
        """Generate file path for storing JSON data"""
        if not self.file_path:
            filename = f"{self.symbol.symbol}_{self.from_date}_{self.to_date}_{self.interval}.json"
            self.file_path = os.path.join('data_storage', filename)
        return self.file_path
    
    def get_full_file_path(self):
        """Get full file path for file operations"""
        return os.path.join(settings.BASE_DIR, self.get_file_path())
    
    class Meta:
        ordering = ['-created_at']


class StockData(models.Model):
    """Model to store actual stock price data"""
    symbol = models.CharField(max_length=20, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    open_price = models.DecimalField(max_digits=10, decimal_places=2)
    high_price = models.DecimalField(max_digits=10, decimal_places=2)
    low_price = models.DecimalField(max_digits=10, decimal_places=2)
    close_price = models.DecimalField(max_digits=10, decimal_places=2)
    volume = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.symbol} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-timestamp']
        unique_together = ('symbol', 'timestamp')
        indexes = [
            models.Index(fields=['symbol', 'timestamp']),
        ]


class APICredentials(models.Model):
    """Model to store API credentials and tokens"""
    name = models.CharField(max_length=50, unique=True)
    api_key = models.CharField(max_length=100)
    api_secret = models.CharField(max_length=100)
    access_token = models.CharField(max_length=100, blank=True, null=True)
    refresh_token = models.CharField(max_length=100, blank=True, null=True)
    request_token = models.CharField(max_length=100, blank=True, null=True)
    user_id = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_authenticated = models.BooleanField(default=False)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        status = 'Authenticated' if self.is_authenticated else 'Not Authenticated'
        return f"{self.name} - {status}"
    
    def is_token_valid(self):
        """Check if access token is still valid"""
        if not self.access_token or not self.token_expires_at:
            return False
        return timezone.now() < self.token_expires_at
    
    def get_kite_login_url(self):
        """Get Kite Connect login URL"""
        try:
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=self.api_key)
            return kite.login_url()
        except:
            return None
    
    class Meta:
        ordering = ['-created_at']


class TradingStrategy(models.Model):
    """Model to store trading strategy configurations"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    parameters = models.JSONField(default=dict)  # Store strategy parameters as JSON
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class TradingSignal(models.Model):
    """Model to store trading signals generated by strategies"""
    SIGNAL_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('HOLD', 'Hold'),
    ]
    
    symbol = models.CharField(max_length=20, db_index=True)
    strategy = models.ForeignKey(TradingStrategy, on_delete=models.CASCADE)
    signal_type = models.CharField(max_length=4, choices=SIGNAL_CHOICES)
    timestamp = models.DateTimeField(db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    confidence = models.FloatField(default=1.0)  # Signal confidence 0.0 to 1.0
    indicators = models.JSONField(default=dict)  # Store indicator values
    notes = models.TextField(blank=True)
    is_executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.symbol} - {self.signal_type} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['symbol', 'timestamp']),
            models.Index(fields=['signal_type', 'timestamp']),
        ]


class StrategyBacktest(models.Model):
    """Model to store backtest results"""
    strategy = models.ForeignKey(TradingStrategy, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20)
    from_date = models.DateField()
    to_date = models.DateField()
    
    # Performance metrics
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    total_return = models.FloatField(default=0.0)
    max_drawdown = models.FloatField(default=0.0)
    sharpe_ratio = models.FloatField(null=True, blank=True)
    
    # Strategy specific data
    buy_signals_count = models.IntegerField(default=0)
    sell_signals_count = models.IntegerField(default=0)
    market_return = models.FloatField(default=0.0)
    strategy_return = models.FloatField(default=0.0)
    
    # Results storage
    results_data = models.JSONField(default=dict)  # Store detailed results
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.strategy.name} - {self.symbol} ({self.from_date} to {self.to_date})"
    
    def win_rate(self):
        if self.total_trades == 0:
            return 0
        return (self.winning_trades / self.total_trades) * 100
    
    class Meta:
        ordering = ['-created_at']
