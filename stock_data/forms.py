from django import forms
from django.core.exceptions import ValidationError
from .models import StockSymbol, DataFetchRequest, APICredentials
from datetime import date, datetime, timedelta


# Comprehensive trading symbols with correct Kite API format
TRADING_SYMBOLS = {
    # Major Indices (use correct instrument symbols)
    'NIFTY50': {'name': 'Nifty 50 Index', 'token': 256265, 'category': 'Index'},
    'BANKNIFTY': {'name': 'Nifty Bank Index', 'token': 260105, 'category': 'Index'}, 
    'NIFTYIT': {'name': 'Nifty IT Index', 'token': 260105, 'category': 'Index'},
    'NIFTYAUTO': {'name': 'Nifty Auto Index', 'token': 260363, 'category': 'Index'},
    'NIFTYPHARMA': {'name': 'Nifty Pharma Index', 'token': 260369, 'category': 'Index'},
    'NIFTYFMCG': {'name': 'Nifty FMCG Index', 'token': 260361, 'category': 'Index'},
    'NIFTYMETAL': {'name': 'Nifty Metal Index', 'token': 260365, 'category': 'Index'},
    'NIFTYREALTY': {'name': 'Nifty Realty Index', 'token': 260371, 'category': 'Index'},
    'NIFTYENERGY': {'name': 'Nifty Energy Index', 'token': 260359, 'category': 'Index'},
    'NIFTYPSUBANK': {'name': 'Nifty PSU Bank Index', 'token': 260367, 'category': 'Index'},
    'NIFTYMIDCAP50': {'name': 'Nifty Midcap 50', 'token': 260365, 'category': 'Index'},
    'NIFTYSMALLCAP50': {'name': 'Nifty Smallcap 50', 'token': 260367, 'category': 'Index'},
    'SENSEX': {'name': 'BSE Sensex', 'token': 265, 'category': 'Index'},
    
    # Nifty 50 Stocks (these symbols work directly with Kite)
    'RELIANCE': {'name': 'Reliance Industries Ltd', 'token': 738561, 'category': 'Large Cap'},
    'TCS': {'name': 'Tata Consultancy Services Ltd', 'token': 2953217, 'category': 'Large Cap'},
    'HDFCBANK': {'name': 'HDFC Bank Ltd', 'token': 341249, 'category': 'Large Cap'},
    'BHARTIARTL': {'name': 'Bharti Airtel Ltd', 'token': 2714625, 'category': 'Large Cap'},
    'ICICIBANK': {'name': 'ICICI Bank Ltd', 'token': 1270529, 'category': 'Large Cap'},
    'INFY': {'name': 'Infosys Ltd', 'token': 408065, 'category': 'Large Cap'},
    'HINDUNILVR': {'name': 'Hindustan Unilever Ltd', 'token': 356865, 'category': 'Large Cap'},
    'SBIN': {'name': 'State Bank of India', 'token': 779521, 'category': 'Large Cap'},
    'LT': {'name': 'Larsen & Toubro Ltd', 'token': 2939649, 'category': 'Large Cap'},
    'ITC': {'name': 'ITC Ltd', 'token': 424961, 'category': 'Large Cap'},
    'KOTAKBANK': {'name': 'Kotak Mahindra Bank Ltd', 'token': 492033, 'category': 'Large Cap'},
    'BAJFINANCE': {'name': 'Bajaj Finance Ltd', 'token': 81153, 'category': 'Large Cap'},
    'ASIANPAINT': {'name': 'Asian Paints Ltd', 'token': 60417, 'category': 'Large Cap'},
    'MARUTI': {'name': 'Maruti Suzuki India Ltd', 'token': 2815745, 'category': 'Large Cap'},
    'HCLTECH': {'name': 'HCL Technologies Ltd', 'token': 1850625, 'category': 'Large Cap'},
    'AXISBANK': {'name': 'Axis Bank Ltd', 'token': 54273, 'category': 'Large Cap'},
    'TITAN': {'name': 'Titan Company Ltd', 'token': 897537, 'category': 'Large Cap'},
    'SUNPHARMA': {'name': 'Sun Pharmaceutical Industries Ltd', 'token': 857857, 'category': 'Large Cap'},
    'WIPRO': {'name': 'Wipro Ltd', 'token': 3787777, 'category': 'Large Cap'},
    'ULTRACEMCO': {'name': 'UltraTech Cement Ltd', 'token': 2952193, 'category': 'Large Cap'},
    'NESTLEIND': {'name': 'Nestle India Ltd', 'token': 4598529, 'category': 'Large Cap'},
    'POWERGRID': {'name': 'Power Grid Corporation of India Ltd', 'token': 3834113, 'category': 'Large Cap'},
    'NTPC': {'name': 'NTPC Ltd', 'token': 2977281, 'category': 'Large Cap'},
    'TATAMOTORS': {'name': 'Tata Motors Ltd', 'token': 884737, 'category': 'Large Cap'},
    'JSWSTEEL': {'name': 'JSW Steel Ltd', 'token': 3001089, 'category': 'Large Cap'},
    'M&M': {'name': 'Mahindra & Mahindra Ltd', 'token': 519937, 'category': 'Large Cap'},
    'TECHM': {'name': 'Tech Mahindra Ltd', 'token': 3465729, 'category': 'Large Cap'},
    'INDUSINDBK': {'name': 'IndusInd Bank Ltd', 'token': 1346049, 'category': 'Large Cap'},
    'BAJAJFINSV': {'name': 'Bajaj Finserv Ltd', 'token': 4268801, 'category': 'Large Cap'},
    'BRITANNIA': {'name': 'Britannia Industries Ltd', 'token': 140033, 'category': 'Large Cap'},
    'ONGC': {'name': 'Oil & Natural Gas Corporation Ltd', 'token': 633601, 'category': 'Large Cap'},
    'ADANIENT': {'name': 'Adani Enterprises Ltd', 'token': 3861249, 'category': 'Large Cap'},
    'TATASTEEL': {'name': 'Tata Steel Ltd', 'token': 895745, 'category': 'Large Cap'},
    'COALINDIA': {'name': 'Coal India Ltd', 'token': 5215745, 'category': 'Large Cap'},
    'CIPLA': {'name': 'Cipla Ltd', 'token': 177665, 'category': 'Large Cap'},
    'DRREDDY': {'name': 'Dr Reddy\'s Laboratories Ltd', 'token': 225537, 'category': 'Large Cap'},
    'EICHERMOT': {'name': 'Eicher Motors Ltd', 'token': 232961, 'category': 'Large Cap'},
    'HINDALCO': {'name': 'Hindalco Industries Ltd', 'token': 348929, 'category': 'Large Cap'},
    'GRASIM': {'name': 'Grasim Industries Ltd', 'token': 315393, 'category': 'Large Cap'},
    'BPCL': {'name': 'Bharat Petroleum Corporation Ltd', 'token': 134657, 'category': 'Large Cap'},
    'BAJAJ-AUTO': {'name': 'Bajaj Auto Ltd', 'token': 4267265, 'category': 'Large Cap'},
    'ADANIPORTS': {'name': 'Adani Ports and Special Economic Zone Ltd', 'token': 3861761, 'category': 'Large Cap'},
    'APOLLOHOSP': {'name': 'Apollo Hospitals Enterprise Ltd', 'token': 41729, 'category': 'Large Cap'},
    'HEROMOTOCO': {'name': 'Hero MotoCorp Ltd', 'token': 345089, 'category': 'Large Cap'},
    'DIVISLAB': {'name': 'Divi\'s Laboratories Ltd', 'token': 3050241, 'category': 'Large Cap'},
    'SBILIFE': {'name': 'SBI Life Insurance Company Ltd', 'token': 5582849, 'category': 'Large Cap'},
    'SHRIRAMFIN': {'name': 'Shriram Finance Ltd', 'token': 4306689, 'category': 'Large Cap'},
    'HDFCLIFE': {'name': 'HDFC Life Insurance Company Ltd', 'token': 119553, 'category': 'Large Cap'},
    'LTIM': {'name': 'LTIMindtree Ltd', 'token': 11483906, 'category': 'Large Cap'},
    'TRENT': {'name': 'Trent Ltd', 'token': 1964545, 'category': 'Large Cap'},
    
    # Popular Mid Cap Stocks
    'PAGEIND': {'name': 'Page Industries Ltd', 'token': 637185, 'category': 'Mid Cap'},
    'GODREJCP': {'name': 'Godrej Consumer Products Ltd', 'token': 295169, 'category': 'Mid Cap'},
    'MARICO': {'name': 'Marico Ltd', 'token': 531201, 'category': 'Mid Cap'},
    'PIDILITIND': {'name': 'Pidilite Industries Ltd', 'token': 681985, 'category': 'Mid Cap'},
    'VOLTAS': {'name': 'Voltas Ltd', 'token': 2707457, 'category': 'Mid Cap'},
    'INDIGO': {'name': 'InterGlobe Aviation Ltd', 'token': 7707649, 'category': 'Mid Cap'},
    'VEDL': {'name': 'Vedanta Ltd', 'token': 784129, 'category': 'Mid Cap'},
    'SAIL': {'name': 'Steel Authority of India Ltd', 'token': 758529, 'category': 'Mid Cap'},
    'NMDC': {'name': 'NMDC Ltd', 'token': 584449, 'category': 'Mid Cap'},
    'IOC': {'name': 'Indian Oil Corporation Ltd', 'token': 415745, 'category': 'Mid Cap'},
    
    # Popular Small Cap Stocks  
    'SUZLON': {'name': 'Suzlon Energy Ltd', 'token': 857345, 'category': 'Small Cap'},
    'ZEEL': {'name': 'Zee Entertainment Enterprises Ltd', 'token': 975873, 'category': 'Small Cap'},
    'YESBANK': {'name': 'Yes Bank Ltd', 'token': 3675137, 'category': 'Small Cap'},
    'SPICEJET': {'name': 'SpiceJet Ltd', 'token': 2084865, 'category': 'Small Cap'},
    'RPOWER': {'name': 'Reliance Power Ltd', 'token': 2744321, 'category': 'Small Cap'},
    
    # ETFs
    'NIFTYBEES': {'name': 'Nippon India ETF Nifty BeES', 'token': 15083, 'category': 'ETF'},
    'BANKBEES': {'name': 'Nippon India ETF Bank BeES', 'token': 1195265, 'category': 'ETF'},
    'GOLDBEES': {'name': 'Goldman Sachs Gold BEeS', 'token': 1154561, 'category': 'ETF'},
}


# Helper function to create grouped choices for better UX
def get_grouped_symbol_choices():
    """Create grouped choices for better symbol selection UI"""
    indices = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'Index']
    large_cap = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'Large Cap']
    mid_cap = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'Mid Cap']
    small_cap = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'Small Cap']
    etf = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'ETF']
    currency = [(k, f"{k} - {v['name']}") for k, v in TRADING_SYMBOLS.items() if v['category'] == 'Currency']
    
    return [
        ('Indices', indices),
        ('Large Cap Stocks', large_cap),
        ('Mid Cap Stocks', mid_cap),
        ('Small Cap Stocks', small_cap),
        ('ETFs', etf),
        ('Currency Futures', currency),
    ]

# Simple choices for forms that don't support grouped choices
def get_simple_symbol_choices():
    """Get simple symbol choices sorted by category and name"""
    return sorted([(k, f"{k} - {v['name']} ({v['category']})") 
                   for k, v in TRADING_SYMBOLS.items()], 
                  key=lambda x: (TRADING_SYMBOLS[x[0]]['category'], x[1]))


class StockDataFetchForm(forms.Form):
    """Comprehensive form for fetching stock data with date range and all trading symbols"""
    
    symbol = forms.ChoiceField(
        choices=get_simple_symbol_choices(),
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg',
            'id': 'symbol-select',
            'style': 'height: 50px;'
        }),
        help_text="Select a trading symbol (Indices, Stocks, ETFs, Currency) to fetch data"
    )
    
    from_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control form-control-lg',
            'max': date.today().isoformat(),
            'style': 'height: 50px;'
        }),
        help_text="Start date for data fetching",
        initial=lambda: date.today() - timedelta(days=30)  # Default to 30 days ago
    )
    
    to_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control form-control-lg',
            'max': date.today().isoformat(),
            'style': 'height: 50px;'
        }),
        help_text="End date for data fetching",
        initial=date.today  # Default to today
    )
    
    interval = forms.ChoiceField(
        choices=[
            ('minute', 'Minute'),
            ('3minute', '3 Minutes'),
            ('5minute', '5 Minutes'),
            ('15minute', '15 Minutes'),
            ('30minute', '30 Minutes'),
            ('60minute', '60 Minutes'),
            ('day', 'Daily'),
        ],
        initial='minute',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg',
            'style': 'height: 50px;'
        }),
        help_text="Data interval (minute-wise recommended for detailed analysis)"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        interval = cleaned_data.get('interval')
        
        if from_date and to_date:
            if from_date > to_date:
                raise ValidationError("From date must be before To date")
            
            if to_date > date.today():
                raise ValidationError("To date cannot be in the future")
            
            # Check if date range is reasonable for the selected interval
            delta = to_date - from_date
            
            # Updated limits based on Kite API behavior and practical considerations
            if interval == 'minute' and delta.days > 60:
                raise ValidationError(
                    "For minute-wise data, maximum date range is 60 days due to API limitations. "
                    "Please use a smaller date range or choose a different interval."
                )
            elif interval in ['3minute', '5minute'] and delta.days > 100:
                raise ValidationError(
                    f"For {interval} data, maximum date range is 100 days due to API limitations. "
                    "Please use a smaller date range."
                )
            elif interval in ['15minute', '30minute'] and delta.days > 200:
                raise ValidationError(
                    f"For {interval} data, maximum date range is 200 days due to API limitations. "
                    "Please use a smaller date range."
                )
            elif interval == '60minute' and delta.days > 400:
                raise ValidationError(
                    "For hourly data, maximum date range is 400 days due to API limitations. "
                    "Please use a smaller date range."
                )
            elif delta.days > 365:
                raise ValidationError(
                    "Maximum date range is 365 days. Please use a smaller date range."
                )
            
            # Add warning for large date ranges that might take time
            if interval == 'minute' and delta.days > 7:
                # Note: This doesn't raise ValidationError, just a helpful message
                pass  # Could add a message here if needed
        
        return cleaned_data
    
    def get_symbol_info(self):
        """Get symbol information including name and token"""
        symbol = self.cleaned_data.get('symbol')
        if symbol and symbol in TRADING_SYMBOLS:
            return TRADING_SYMBOLS[symbol]
        return None


class DataFetchForm(forms.Form):
    """Form for submitting data fetch requests"""
    
    symbol = forms.ChoiceField(
        choices=get_simple_symbol_choices(),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'symbol-select'
        }),
        help_text="Select a trading symbol (Indices, Stocks, ETFs, Currency)"
    )
    
    from_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'max': date.today().isoformat()
        }),
        help_text="Start date for data fetching"
    )
    
    to_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'max': date.today().isoformat()
        }),
        help_text="End date for data fetching"
    )
    
    interval = forms.ChoiceField(
        choices=DataFetchRequest.INTERVAL_CHOICES,
        initial='minute',
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        help_text="Data interval (minute-wise recommended for detailed analysis)"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        
        if from_date and to_date:
            if from_date > to_date:
                raise ValidationError("From date must be before To date")
            
            if to_date > date.today():
                raise ValidationError("To date cannot be in the future")
            
            # Check if date range is too large for minute data
            interval = cleaned_data.get('interval')
            if interval == 'minute':
                delta = to_date - from_date
                if delta.days > 60:  # More than 60 days
                    raise ValidationError(
                        "For minute-wise data, maximum date range is 60 days. "
                        "Please use a smaller date range or choose a different interval."
                    )
        
        return cleaned_data
    
    def clean_symbol(self):
        symbol = self.cleaned_data['symbol']
        if symbol in TRADING_SYMBOLS:
            return {
                'symbol': symbol,
                'name': TRADING_SYMBOLS[symbol]['name'],
                'instrument_token': TRADING_SYMBOLS[symbol]['token'],
                'category': TRADING_SYMBOLS[symbol]['category']
            }
        else:
            raise ValidationError("Invalid symbol selected")


class APICredentialsForm(forms.ModelForm):
    """Form for API credentials"""
    
    class Meta:
        model = APICredentials
        fields = ['name', 'api_key', 'api_secret']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Configuration Name (e.g., Main Account)'
            }),
            'api_key': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Zerodha API Key'
            }),
            'api_secret': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Zerodha API Secret'
            }),
        }
        help_texts = {
            'name': 'A name to identify this API configuration',
            'api_key': 'API Key from your Zerodha Kite Connect app',
            'api_secret': 'API Secret from your Zerodha Kite Connect app'
        }
    
    def save(self, commit=True):
        # Deactivate all existing credentials before saving new one
        if commit:
            APICredentials.objects.filter(is_active=True).update(is_active=False)
        
        instance = super().save(commit=False)
        instance.is_active = True
        instance.is_authenticated = False  # Will be set to True after authentication
        
        if commit:
            instance.save()
        
        return instance


class AuthenticationForm(forms.Form):
    """Form for handling Kite authentication with request token"""
    
    request_token = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter the request token from Kite login',
            'autocomplete': 'off'
        }),
        help_text="Copy the request_token parameter from the redirect URL after Kite login"
    )
    
    def clean_request_token(self):
        request_token = self.cleaned_data['request_token'].strip()
        
        # Basic validation
        if len(request_token) < 10:
            raise ValidationError("Request token appears to be too short")
        
        # Check for common patterns that indicate invalid token
        if request_token in ['your_token_here', 'XXXXXX', 'token']:
            raise ValidationError("Please enter the actual request token from Zerodha redirect URL")
            
        # Check if it looks like a valid token (alphanumeric)
        if not request_token.replace('-', '').replace('_', '').isalnum():
            raise ValidationError("Request token contains invalid characters")
            
        return request_token


class SearchFilterForm(forms.Form):
    """Form for search and filter functionality"""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by symbol or name...',
            'id': 'search-input'
        })
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status')] + DataFetchRequest.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    interval = forms.ChoiceField(
        required=False,
        choices=[('', 'All Intervals')] + DataFetchRequest.INTERVAL_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
