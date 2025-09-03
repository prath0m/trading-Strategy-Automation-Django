from django import forms
from django.core.exceptions import ValidationError
from .models import StockSymbol, DataFetchRequest, APICredentials
from datetime import date, datetime, timedelta


# Nifty 50 symbols with their instrument tokens
NIFTY50_SYMBOLS = {
    'RELIANCE': {'name': 'Reliance Industries Ltd', 'token': 738561},
    'TCS': {'name': 'Tata Consultancy Services Ltd', 'token': 2953217},
    'HDFCBANK': {'name': 'HDFC Bank Ltd', 'token': 341249},
    'BHARTIARTL': {'name': 'Bharti Airtel Ltd', 'token': 2714625},
    'ICICIBANK': {'name': 'ICICI Bank Ltd', 'token': 1270529},
    'INFY': {'name': 'Infosys Ltd', 'token': 408065},
    'HINDUNILVR': {'name': 'Hindustan Unilever Ltd', 'token': 356865},
    'SBIN': {'name': 'State Bank of India', 'token': 779521},
    'LT': {'name': 'Larsen & Toubro Ltd', 'token': 2939649},
    'ITC': {'name': 'ITC Ltd', 'token': 424961},
    'KOTAKBANK': {'name': 'Kotak Mahindra Bank Ltd', 'token': 492033},
    'BAJFINANCE': {'name': 'Bajaj Finance Ltd', 'token': 81153},
    'ASIANPAINT': {'name': 'Asian Paints Ltd', 'token': 60417},
    'MARUTI': {'name': 'Maruti Suzuki India Ltd', 'token': 2815745},
    'HCLTECH': {'name': 'HCL Technologies Ltd', 'token': 1850625},
    'AXISBANK': {'name': 'Axis Bank Ltd', 'token': 54273},
    'TITAN': {'name': 'Titan Company Ltd', 'token': 897537},
    'SUNPHARMA': {'name': 'Sun Pharmaceutical Industries Ltd', 'token': 857857},
    'WIPRO': {'name': 'Wipro Ltd', 'token': 3787777},
    'ULTRACEMCO': {'name': 'UltraTech Cement Ltd', 'token': 2952193},
    'NESTLEIND': {'name': 'Nestle India Ltd', 'token': 4598529},
    'POWERGRID': {'name': 'Power Grid Corporation of India Ltd', 'token': 3834113},
    'NTPC': {'name': 'NTPC Ltd', 'token': 2977281},
    'TATAMOTORS': {'name': 'Tata Motors Ltd', 'token': 884737},
    'JSWSTEEL': {'name': 'JSW Steel Ltd', 'token': 3001089},
    'M&M': {'name': 'Mahindra & Mahindra Ltd', 'token': 519937},
    'TECHM': {'name': 'Tech Mahindra Ltd', 'token': 3465729},
    'INDUSINDBK': {'name': 'IndusInd Bank Ltd', 'token': 1346049},
    'BAJAJFINSV': {'name': 'Bajaj Finserv Ltd', 'token': 4268801},
    'BRITANNIA': {'name': 'Britannia Industries Ltd', 'token': 140033},
    'ONGC': {'name': 'Oil & Natural Gas Corporation Ltd', 'token': 633601},
    'ADANIENT': {'name': 'Adani Enterprises Ltd', 'token': 3861249},
    'TATASTEEL': {'name': 'Tata Steel Ltd', 'token': 895745},
    'COALINDIA': {'name': 'Coal India Ltd', 'token': 5215745},
    'CIPLA': {'name': 'Cipla Ltd', 'token': 177665},
    'DRREDDY': {'name': 'Dr Reddy\'s Laboratories Ltd', 'token': 225537},
    'EICHERMOT': {'name': 'Eicher Motors Ltd', 'token': 232961},
    'HINDALCO': {'name': 'Hindalco Industries Ltd', 'token': 348929},
    'GRASIM': {'name': 'Grasim Industries Ltd', 'token': 315393},
    'BPCL': {'name': 'Bharat Petroleum Corporation Ltd', 'token': 134657},
    'BAJAJ-AUTO': {'name': 'Bajaj Auto Ltd', 'token': 4267265},
    'ADANIPORTS': {'name': 'Adani Ports and Special Economic Zone Ltd', 'token': 3861761},
    'APOLLOHOSP': {'name': 'Apollo Hospitals Enterprise Ltd', 'token': 41729},
    'HEROMOTOCO': {'name': 'Hero MotoCorp Ltd', 'token': 345089},
    'DIVISLAB': {'name': 'Divi\'s Laboratories Ltd', 'token': 3050241},
    'SBILIFE': {'name': 'SBI Life Insurance Company Ltd', 'token': 5582849},
    'SHRIRAMFIN': {'name': 'Shriram Finance Ltd', 'token': 4306689},
    'HDFCLIFE': {'name': 'HDFC Life Insurance Company Ltd', 'token': 119553},
    'LTIM': {'name': 'LTIMindtree Ltd', 'token': 11483906},
    'TRENT': {'name': 'Trent Ltd', 'token': 1964545},
}


# Comprehensive Nifty 50 symbols with their instrument tokens
NIFTY50_SYMBOLS = {
    'RELIANCE': {'name': 'Reliance Industries Ltd', 'token': 738561},
    'TCS': {'name': 'Tata Consultancy Services Ltd', 'token': 2953217},
    'HDFCBANK': {'name': 'HDFC Bank Ltd', 'token': 341249},
    'BHARTIARTL': {'name': 'Bharti Airtel Ltd', 'token': 2714625},
    'ICICIBANK': {'name': 'ICICI Bank Ltd', 'token': 1270529},
    'INFY': {'name': 'Infosys Ltd', 'token': 408065},
    'HINDUNILVR': {'name': 'Hindustan Unilever Ltd', 'token': 356865},
    'SBIN': {'name': 'State Bank of India', 'token': 779521},
    'LT': {'name': 'Larsen & Toubro Ltd', 'token': 2939649},
    'ITC': {'name': 'ITC Ltd', 'token': 424961},
    'KOTAKBANK': {'name': 'Kotak Mahindra Bank Ltd', 'token': 492033},
    'BAJFINANCE': {'name': 'Bajaj Finance Ltd', 'token': 81153},
    'ASIANPAINT': {'name': 'Asian Paints Ltd', 'token': 60417},
    'MARUTI': {'name': 'Maruti Suzuki India Ltd', 'token': 2815745},
    'HCLTECH': {'name': 'HCL Technologies Ltd', 'token': 1850625},
    'AXISBANK': {'name': 'Axis Bank Ltd', 'token': 54273},
    'TITAN': {'name': 'Titan Company Ltd', 'token': 897537},
    'SUNPHARMA': {'name': 'Sun Pharmaceutical Industries Ltd', 'token': 857857},
    'WIPRO': {'name': 'Wipro Ltd', 'token': 3787777},
    'ULTRACEMCO': {'name': 'UltraTech Cement Ltd', 'token': 2952193},
    'NESTLEIND': {'name': 'Nestle India Ltd', 'token': 4598529},
    'POWERGRID': {'name': 'Power Grid Corporation of India Ltd', 'token': 3834113},
    'NTPC': {'name': 'NTPC Ltd', 'token': 2977281},
    'TATAMOTORS': {'name': 'Tata Motors Ltd', 'token': 884737},
    'JSWSTEEL': {'name': 'JSW Steel Ltd', 'token': 3001089},
    'M&M': {'name': 'Mahindra & Mahindra Ltd', 'token': 519937},
    'TECHM': {'name': 'Tech Mahindra Ltd', 'token': 3465729},
    'INDUSINDBK': {'name': 'IndusInd Bank Ltd', 'token': 1346049},
    'BAJAJFINSV': {'name': 'Bajaj Finserv Ltd', 'token': 4268801},
    'BRITANNIA': {'name': 'Britannia Industries Ltd', 'token': 140033},
    'ONGC': {'name': 'Oil & Natural Gas Corporation Ltd', 'token': 633601},
    'ADANIENT': {'name': 'Adani Enterprises Ltd', 'token': 3861249},
    'TATASTEEL': {'name': 'Tata Steel Ltd', 'token': 895745},
    'COALINDIA': {'name': 'Coal India Ltd', 'token': 5215745},
    'CIPLA': {'name': 'Cipla Ltd', 'token': 177665},
    'DRREDDY': {'name': 'Dr Reddy\'s Laboratories Ltd', 'token': 225537},
    'EICHERMOT': {'name': 'Eicher Motors Ltd', 'token': 232961},
    'HINDALCO': {'name': 'Hindalco Industries Ltd', 'token': 348929},
    'GRASIM': {'name': 'Grasim Industries Ltd', 'token': 315393},
    'BPCL': {'name': 'Bharat Petroleum Corporation Ltd', 'token': 134657},
    'BAJAJ-AUTO': {'name': 'Bajaj Auto Ltd', 'token': 4267265},
    'ADANIPORTS': {'name': 'Adani Ports and Special Economic Zone Ltd', 'token': 3861761},
    'APOLLOHOSP': {'name': 'Apollo Hospitals Enterprise Ltd', 'token': 41729},
    'HEROMOTOCO': {'name': 'Hero MotoCorp Ltd', 'token': 345089},
    'DIVISLAB': {'name': 'Divi\'s Laboratories Ltd', 'token': 3050241},
    'SBILIFE': {'name': 'SBI Life Insurance Company Ltd', 'token': 5582849},
    'SHRIRAMFIN': {'name': 'Shriram Finance Ltd', 'token': 4306689},
    'HDFCLIFE': {'name': 'HDFC Life Insurance Company Ltd', 'token': 119553},
    'LTIM': {'name': 'LTIMindtree Ltd', 'token': 11483906},
    'TRENT': {'name': 'Trent Ltd', 'token': 1964545},
}


class StockDataFetchForm(forms.Form):
    """Comprehensive form for fetching stock data with date range and all symbols"""
    
    symbol = forms.ChoiceField(
        choices=[(k, f"{k} - {v['name']}") for k, v in NIFTY50_SYMBOLS.items()],
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg',
            'id': 'symbol-select',
            'style': 'height: 50px;'
        }),
        help_text="Select a Nifty 50 stock symbol to fetch data"
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
            
            if interval == 'minute' and delta.days > 60:
                raise ValidationError(
                    "For minute-wise data, maximum date range is 60 days. "
                    "Please use a smaller date range or choose a different interval."
                )
            elif interval in ['3minute', '5minute'] and delta.days > 100:
                raise ValidationError(
                    f"For {interval} data, maximum date range is 100 days. "
                    "Please use a smaller date range."
                )
            elif delta.days > 365:
                raise ValidationError(
                    "Maximum date range is 365 days. Please use a smaller date range."
                )
        
        return cleaned_data
    
    def get_symbol_info(self):
        """Get symbol information including name and token"""
        symbol = self.cleaned_data.get('symbol')
        if symbol and symbol in NIFTY50_SYMBOLS:
            return NIFTY50_SYMBOLS[symbol]
        return None


class DataFetchForm(forms.Form):
    """Form for submitting data fetch requests"""
    
    symbol = forms.ChoiceField(
        choices=[(k, f"{k} - {v['name']}") for k, v in NIFTY50_SYMBOLS.items()],
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'symbol-select'
        }),
        help_text="Select a Nifty 50 stock symbol"
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
        if symbol in NIFTY50_SYMBOLS:
            return {
                'symbol': symbol,
                'name': NIFTY50_SYMBOLS[symbol]['name'],
                'instrument_token': NIFTY50_SYMBOLS[symbol]['token']
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
