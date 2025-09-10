import json
import os
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None
import logging
from typing import Dict, List, Any, Optional, Union
import time
try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)

# Define Kite data limits based on interval
KITE_LIMITS = {
    'minute': 60,      # 60 days
    '3minute': 100,    # 100 days
    '5minute': 100,    # 100 days
    '10minute': 100,   # 100 days
    '15minute': 200,   # 200 days
    '30minute': 200,   # 200 days
    '60minute': 400,   # 400 days
    'hour': 400,       # 400 days (alias for 60minute)
    'day': 2000,       # 2000 days
    'daily': 2000      # 2000 days (alias for day)
}


def calculate_date_chunks(from_date, to_date, interval):
    """Calculate the number of chunks needed based on Kite limits"""
    # Get the limit for this interval
    limit_days = KITE_LIMITS.get(interval, 60)  # Default to 60 days if interval not found
    
    # Calculate total days requested
    total_days = (to_date - from_date).days
    
    if total_days <= limit_days:
        return [(from_date, to_date)]
    
    # Calculate chunks
    chunks = []
    current_start = from_date
    
    while current_start < to_date:
        current_end = min(current_start + timedelta(days=limit_days), to_date)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return chunks


def get_kite_limit_info(interval: str) -> Dict[str, Any]:
    """Get information about Kite API limits for a given interval"""
    limit_days = KITE_LIMITS.get(interval, 60)
    return {
        'interval': interval,
        'limit_days': limit_days,
        'limit_description': f"Maximum {limit_days} days per API call for {interval} data",
        'recommended_use': "Use chunked fetching for date ranges exceeding this limit"
    }


def estimate_api_calls(from_date, to_date, interval: str) -> Dict[str, Any]:
    """Estimate the number of API calls needed for a date range and interval"""
    total_days = (to_date - from_date).days
    limit_days = KITE_LIMITS.get(interval, 60)
    
    if total_days <= limit_days:
        chunks_needed = 1
    else:
        chunks_needed = len(calculate_date_chunks(from_date, to_date, interval))
    
    return {
        'total_days': total_days,
        'limit_days': limit_days,
        'chunks_needed': chunks_needed,
        'estimated_api_calls': chunks_needed,
        'within_single_call': total_days <= limit_days,
        'requires_chunking': total_days > limit_days
    }


def fetch_and_combine_data(kite_service, symbol, from_date, to_date, interval):
    """Fetch data in chunks and combine them"""
    # Import the trading symbols from forms
    from .forms import TRADING_SYMBOLS
    
    # Get instrument token for symbol
    symbol_info = TRADING_SYMBOLS.get(symbol.upper())
    if not symbol_info:
        raise ValueError(f"Symbol {symbol} not found in supported trading instruments")
    
    instrument_token = symbol_info['token']
    
    # Calculate the chunks needed
    date_chunks = calculate_date_chunks(from_date, to_date, interval)
    
    logger.info(f"Fetching data for {symbol} in {len(date_chunks)} chunks due to Kite limits")
    
    all_data = []
    successful_chunks = 0
    
    for i, (chunk_start, chunk_end) in enumerate(date_chunks, 1):
        try:
            logger.info(f"Fetching chunk {i}/{len(date_chunks)}: {chunk_start} to {chunk_end}")
            
            # Use the service's fetch_historical_data method directly with instrument token
            chunk_data = kite_service.fetch_historical_data(
                instrument_token=instrument_token,
                from_date=chunk_start,
                to_date=chunk_end,
                interval=interval
            )
            
            if chunk_data:
                all_data.extend(chunk_data)
                successful_chunks += 1
                logger.info(f"Successfully fetched {len(chunk_data)} records for chunk {i}")
            else:
                logger.warning(f"No data returned for chunk {i}")
                
        except Exception as e:
            logger.error(f"Error fetching chunk {i} ({chunk_start} to {chunk_end}): {str(e)}")
            # Continue with other chunks even if one fails
            continue
        
        # Add delay between chunks to respect API rate limits
        time.sleep(1)
    
    if not all_data:
        raise Exception("No data could be fetched from any chunks")
    
    # Remove duplicates and sort by date
    if all_data:
        # Convert to DataFrame for easier manipulation if pandas available
        if pd is not None:
            df = pd.DataFrame(all_data)
            
            # Remove duplicates based on date/timestamp
            if 'date' in df.columns:
                df = df.drop_duplicates(subset=['date']).sort_values('date')
            elif 'timestamp' in df.columns:
                df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
            
            # Convert back to list of dictionaries
            all_data = df.to_dict('records')
        else:
            # Fallback deduplication without pandas
            seen_dates = set()
            deduplicated_data = []
            for record in all_data:
                date_key = record.get('date') or record.get('timestamp')
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    deduplicated_data.append(record)
            
            # Sort by date
            all_data = sorted(deduplicated_data, key=lambda x: x.get('date') or x.get('timestamp', ''))
    
    logger.info(f"Combined data: {len(all_data)} total records from {successful_chunks}/{len(date_chunks)} successful chunks")
    return all_data


class KiteDataService:
    """Service class for handling Zerodha Kite API operations and JSON storage"""
    
    def __init__(self, api_credentials=None):
        if api_credentials:
            self.api_key = api_credentials.api_key
            self.api_secret = api_credentials.api_secret
            self.access_token = api_credentials.access_token
            self.refresh_token = api_credentials.refresh_token
            self.credentials = api_credentials
        else:
            self.api_key = None
            self.api_secret = None
            self.access_token = None
            self.refresh_token = None
            self.credentials = None
        
        self.kite = None
        self.session_data = None
        
        # Create data storage directory
        self.data_dir = os.path.join(settings.BASE_DIR, 'data_storage')
        os.makedirs(self.data_dir, exist_ok=True)
        
    def get_json_filename(self, symbol: str, from_date: str, to_date: str, interval: str) -> str:
        """Generate filename for JSON data storage"""
        return f"{symbol}_{from_date}_{to_date}_{interval}.json"
    
    def get_json_filepath(self, symbol: str, from_date: str, to_date: str, interval: str) -> str:
        """Get full file path for JSON data storage"""
        filename = self.get_json_filename(symbol, from_date, to_date, interval)
        return os.path.join(self.data_dir, filename)
    
    def save_data_to_json(self, data: List[Dict], symbol: str, from_date: str, to_date: str, interval: str) -> str:
        """Save fetched data to JSON file"""
        filepath = self.get_json_filepath(symbol, from_date, to_date, interval)
        
        # Prepare metadata
        metadata = {
            'symbol': symbol,
            'from_date': from_date,
            'to_date': to_date,
            'interval': interval,
            'total_records': len(data),
            'fetched_at': datetime.now().isoformat(),
            'data': data
        }
        
        # Save to JSON file
        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        logger.info(f"Saved {len(data)} records to {filepath}")
        return filepath
    
    def load_data_from_json(self, symbol: str, from_date: str, to_date: str, interval: str) -> Optional[Dict]:
        """Load data from JSON file if it exists"""
        filepath = self.get_json_filepath(symbol, from_date, to_date, interval)
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                logger.info(f"Loaded {data.get('total_records', 0)} records from {filepath}")
                return data
            except Exception as e:
                logger.error(f"Error loading JSON file {filepath}: {e}")
                return None
        return None
    
    def list_available_data_files(self) -> List[Dict]:
        """List all available JSON data files with metadata"""
        files = []
        
        if not os.path.exists(self.data_dir):
            return files
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.data_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    # Extract metadata from the file
                    metadata = data.get('metadata', {})
                    
                    # Extract file info from metadata
                    file_info = {
                        'filename': filename,
                        'filepath': filepath,
                        'symbol': metadata.get('symbol'),
                        'from_date': metadata.get('from_date'),
                        'to_date': metadata.get('to_date'),
                        'interval': metadata.get('interval'),
                        'total_records': metadata.get('records_count', len(data.get('data', []))),
                        'fetched_at': metadata.get('generated_at'),
                        'file_size': os.path.getsize(filepath)
                    }
                    files.append(file_info)
                except Exception as e:
                    logger.error(f"Error reading file {filename}: {e}")
        
        # Sort by fetched_at descending (handle None values)
        files.sort(key=lambda x: x.get('fetched_at') or '1900-01-01T00:00:00', reverse=True)
        return files
        
    def initialize_kite(self):
        """Initialize KiteConnect instance"""
        if not KiteConnect:
            logger.error("KiteConnect not available")
            return False
            
        if not self.api_key:
            logger.error("API key not provided")
            return False
            
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self.kite.set_access_token(self.access_token)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize KiteConnect: {str(e)}")
            return False
    
    def get_login_url(self) -> str:
        """Get the login URL for Kite authentication"""
        if not self.initialize_kite():
            return None
        return self.kite.login_url()
    
    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """
        Generate session using request token
        Returns session data with access_token and refresh_token
        """
        if not self.initialize_kite():
            raise Exception("KiteConnect not initialized")
            
        try:
            session_data = self.kite.generate_session(
                request_token, api_secret=self.api_secret
            )
            
            # Update credentials in database
            if self.credentials:
                self.credentials.access_token = session_data.get("access_token")
                self.credentials.refresh_token = session_data.get("refresh_token")
                self.credentials.user_id = session_data.get("user_id")
                self.credentials.request_token = request_token
                self.credentials.is_authenticated = True
                
                # Set token expiry (Kite tokens expire daily)
                self.credentials.token_expires_at = timezone.now() + timedelta(hours=24)
                self.credentials.save()
                
                # Set access token for current session
                self.access_token = session_data.get("access_token")
                self.kite.set_access_token(self.access_token)
            
            return session_data
            
        except Exception as e:
            logger.error(f"Session generation failed: {str(e)}")
            raise
    
    def refresh_access_token(self) -> bool:
        """
        Refresh access token using refresh token
        Returns True if successful
        """
        if not self.refresh_token or not self.initialize_kite():
            return False
            
        try:
            new_session = self.kite.renew_access_token(
                self.refresh_token, api_secret=self.api_secret
            )
            
            if self.credentials:
                self.credentials.access_token = new_session.get("access_token")
                self.credentials.token_expires_at = timezone.now() + timedelta(hours=24)
                self.credentials.save()
                
                self.access_token = new_session.get("access_token")
                self.kite.set_access_token(self.access_token)
            
            return True
            
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if the service is properly authenticated"""
        if not self.credentials:
            return False
            
        if not self.credentials.is_authenticated or not self.credentials.access_token:
            return False
            
        # Check if token is still valid
        if not self.credentials.is_token_valid():
            # Try to refresh the token
            return self.refresh_access_token()
            
        return True
    
    def authenticate(self, request_token: str = None) -> bool:
        """
        Authenticate with Kite API
        Returns True if successful, False otherwise
        """
        try:
            # If already authenticated and token is valid, return True
            if self.is_authenticated():
                return True
                
            # If request token provided, generate new session
            if request_token:
                self.generate_session(request_token)
                return True
            
            # Try to refresh existing token
            if self.refresh_token:
                return self.refresh_access_token()
                
            # No valid authentication available
            logger.warning("No valid authentication method available")
            return False
                
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            return False
        """Get the login URL for Kite authentication"""
        if not self.initialize_kite():
            return None
        return self.kite.login_url()
    
    def fetch_historical_data_by_symbol(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        interval: str = "minute"
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data by symbol name
        Converts symbol to instrument token and fetches data with proper chunking
        """
        # Import the trading symbols from forms
        from .forms import TRADING_SYMBOLS
        
        # Get instrument token for symbol
        symbol_info = TRADING_SYMBOLS.get(symbol.upper())
        if not symbol_info:
            raise ValueError(f"Symbol {symbol} not found in supported trading instruments")
        
        instrument_token = symbol_info['token']
        
        # Convert string dates to datetime
        from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        
        # Calculate date range in days
        date_diff = (to_date_obj - from_date_obj).days
        
        # Get the limit for this interval
        limit_days = KITE_LIMITS.get(interval, 60)
        
        # Check if we need to use chunked fetching based on Kite limits
        if date_diff > limit_days:
            logger.info(f"Date range ({date_diff} days) exceeds Kite limit ({limit_days} days) for {interval} interval. Using chunked fetching.")
            return self.fetch_data_in_batches(
                instrument_token=instrument_token,
                from_date=from_date_obj,
                to_date=to_date_obj,
                interval=interval
            )
        else:
            # For smaller date ranges within limits, use single fetch
            logger.info(f"Date range ({date_diff} days) within Kite limit ({limit_days} days) for {interval} interval. Using single fetch.")
            return self.fetch_historical_data(
                instrument_token=instrument_token,
                from_date=from_date_obj,
                to_date=to_date_obj,
                interval=interval
            )
    
    def fetch_historical_data_smart(
        self,
        symbol: str,
        from_date: Union[str, datetime],
        to_date: Union[str, datetime],
        interval: str = "minute"
    ) -> List[Dict[str, Any]]:
        """
        Smart data fetching that automatically handles any size request
        Uses the most efficient method based on date range and interval
        """
        # Convert string dates to datetime if needed
        if isinstance(from_date, str):
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        else:
            from_date_obj = from_date
            
        if isinstance(to_date, str):
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        else:
            to_date_obj = to_date
        
        # Get estimation info to determine the best approach
        estimation = estimate_api_calls(from_date_obj, to_date_obj, interval)
        
        logger.info(f"Smart fetch for {symbol}: {estimation['total_days']} days of {interval} data")
        logger.info(f"Estimated {estimation['chunks_needed']} API calls using {'chunked' if estimation['requires_chunking'] else 'single'} approach")
        
        # Automatically use the most efficient approach
        if estimation['requires_chunking']:
            logger.info("Using chunked fetching for optimal performance")
            return self.fetch_historical_data_chunked(symbol, from_date_obj, to_date_obj, interval)
        else:
            logger.info("Using single fetch (within API limits)")
            return self.fetch_historical_data_by_symbol(
                symbol, 
                from_date_obj.strftime("%Y-%m-%d"), 
                to_date_obj.strftime("%Y-%m-%d"), 
                interval
            )
    
    def fetch_historical_data_chunked(
        self,
        symbol: str,
        from_date: Union[str, datetime],
        to_date: Union[str, datetime],
        interval: str = "minute"
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data using the new chunked approach with proper error handling
        This method uses the fetch_and_combine_data function for maximum reliability
        """
        # Convert string dates to datetime if needed
        if isinstance(from_date, str):
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        else:
            from_date_obj = from_date
            
        if isinstance(to_date, str):
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        else:
            to_date_obj = to_date
        
        try:
            # Use the new fetch_and_combine_data function
            return fetch_and_combine_data(
                kite_service=self,
                symbol=symbol,
                from_date=from_date_obj,
                to_date=to_date_obj,
                interval=interval
            )
        except Exception as e:
            logger.error(f"Error in chunked fetch for {symbol}: {str(e)}")
            # Fallback to the existing method
            logger.info("Falling back to existing fetch method")
            return self.fetch_historical_data_by_symbol(
                symbol=symbol,
                from_date=from_date_obj.strftime("%Y-%m-%d") if hasattr(from_date_obj, 'strftime') else str(from_date_obj),
                to_date=to_date_obj.strftime("%Y-%m-%d") if hasattr(to_date_obj, 'strftime') else str(to_date_obj),
                interval=interval
            )
    
    def get_fetch_info(
        self, 
        symbol: str, 
        from_date: Union[str, datetime], 
        to_date: Union[str, datetime], 
        interval: str = "minute"
    ) -> Dict[str, Any]:
        """
        Get information about how data will be fetched for given parameters
        Useful for showing users what to expect before actual fetching
        """
        # Convert string dates to datetime if needed
        if isinstance(from_date, str):
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        else:
            from_date_obj = from_date
            
        if isinstance(to_date, str):
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        else:
            to_date_obj = to_date
        
        # Get estimation info
        estimation = estimate_api_calls(from_date_obj, to_date_obj, interval)
        limit_info = get_kite_limit_info(interval)
        
        # Calculate expected records (rough estimation)
        total_days = estimation['total_days']
        if interval == "minute":
            # Assume 6.25 hours of trading per day * 60 minutes = 375 minutes
            expected_records = total_days * 375
        elif interval == "day":
            expected_records = total_days
        elif interval == "60minute":
            expected_records = total_days * 6  # 6 hours of trading
        elif interval == "15minute":
            expected_records = total_days * 25  # ~25 records per trading day
        elif interval == "5minute":
            expected_records = total_days * 75  # ~75 records per trading day
        else:
            expected_records = total_days * 100  # rough estimate
        
        return {
            'symbol': symbol,
            'from_date': from_date_obj.isoformat(),
            'to_date': to_date_obj.isoformat(),
            'interval': interval,
            'estimation': estimation,
            'limit_info': limit_info,
            'expected_records': expected_records,
            'fetch_strategy': 'chunked' if estimation['requires_chunking'] else 'single',
            'estimated_time_seconds': estimation['chunks_needed'] * 2  # ~2 seconds per chunk with delays
        }
    
    def validate_fetch_parameters(
        self, 
        symbol: str, 
        from_date: Union[str, datetime], 
        to_date: Union[str, datetime], 
        interval: str = "minute"
    ) -> Dict[str, Any]:
        """
        Validate fetch parameters and return any warnings or recommendations
        """
        warnings = []
        recommendations = []
        
        # Convert string dates to datetime if needed
        if isinstance(from_date, str):
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
        else:
            from_date_obj = from_date
            
        if isinstance(to_date, str):
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        else:
            to_date_obj = to_date
        
        # Check symbol validity
        try:
            from .forms import TRADING_SYMBOLS
            if symbol.upper() not in TRADING_SYMBOLS:
                warnings.append(f"Symbol '{symbol}' not found in supported instruments")
        except ImportError:
            warnings.append("Could not validate symbol - forms module not available")
        
        # Check date range
        if from_date_obj >= to_date_obj:
            warnings.append("From date should be earlier than to date")
        
        total_days = (to_date_obj - from_date_obj).days
        
        # Check for very large date ranges
        if interval == "minute" and total_days > 365:
            warnings.append("Fetching minute data for more than 1 year may take significant time")
            recommendations.append("Consider using hourly or daily data for long-term analysis")
        
        if total_days > 2000:
            warnings.append("Date range exceeds 2000 days - this is the maximum for daily data")
        
        # Check interval validity
        valid_intervals = list(KITE_LIMITS.keys())
        if interval not in valid_intervals:
            warnings.append(f"Invalid interval '{interval}'. Valid options: {', '.join(valid_intervals)}")
        
        # Get fetch info
        fetch_info = self.get_fetch_info(symbol, from_date_obj, to_date_obj, interval)
        
        if fetch_info['estimation']['chunks_needed'] > 50:
            warnings.append(f"This request will require {fetch_info['estimation']['chunks_needed']} API calls")
            recommendations.append("Consider breaking this into smaller date ranges")
        
        return {
            'valid': len(warnings) == 0,
            'warnings': warnings,
            'recommendations': recommendations,
            'fetch_info': fetch_info
        }

    def fetch_historical_data(
        self, 
        instrument_token: int, 
        from_date: Union[str, datetime], 
        to_date: Union[str, datetime], 
        interval: str = "minute"
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data for a given instrument
        Returns list of OHLCV data
        """
        try:
            # Ensure we're authenticated
            if not self.is_authenticated():
                logger.warning("Not authenticated with Kite API, using sample data")
                if isinstance(from_date, str):
                    from_date = datetime.strptime(from_date, "%Y-%m-%d")
                if isinstance(to_date, str):
                    to_date = datetime.strptime(to_date, "%Y-%m-%d")
                return self._generate_sample_data(from_date, to_date, interval)
                
            if not self.initialize_kite():
                logger.warning("Failed to initialize Kite API, using sample data")
                if isinstance(from_date, str):
                    from_date = datetime.strptime(from_date, "%Y-%m-%d")
                if isinstance(to_date, str):
                    to_date = datetime.strptime(to_date, "%Y-%m-%d")
                return self._generate_sample_data(from_date, to_date, interval)
            
            # Handle date conversion - support both string and datetime inputs
            if isinstance(from_date, str):
                from_date_str = from_date
                from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
            else:
                from_date_str = from_date.strftime("%Y-%m-%d")
                from_date_obj = from_date
                
            if isinstance(to_date, str):
                to_date_str = to_date
                to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
            else:
                to_date_str = to_date.strftime("%Y-%m-%d")
                to_date_obj = to_date
            
            logger.info(f"Fetching data from Kite API - Token: {instrument_token}, "
                       f"From: {from_date_str}, To: {to_date_str}, Interval: {interval}")
            
            # Fetch data from Kite API
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date_str,
                to_date=to_date_str,
                interval=interval
            )
            
            logger.info(f"Kite API returned {len(data) if data else 0} records")
            
            if not data:
                logger.warning("No data returned from Kite API, using sample data")
                return self._generate_sample_data(from_date_obj, to_date_obj, interval)
            
            # Convert datetime objects to strings for JSON serialization
            processed_data = []
            for record in data:
                processed_record = {
                    'date': record['date'].isoformat() if hasattr(record['date'], 'isoformat') else str(record['date']),
                    'open': float(record['open']),
                    'high': float(record['high']),
                    'low': float(record['low']),
                    'close': float(record['close']),
                    'volume': int(record['volume']),
                }
                processed_data.append(processed_record)
            
            logger.info(f"Processed {len(processed_data)} records from Kite API")
            return processed_data
            
        except Exception as e:
            logger.error(f"Error fetching historical data from Kite API: {str(e)}")
            logger.info("Falling back to sample data due to API error")
            # Return sample data for testing when API fails
            if isinstance(from_date, str):
                from_date = datetime.strptime(from_date, "%Y-%m-%d")
            if isinstance(to_date, str):
                to_date = datetime.strptime(to_date, "%Y-%m-%d")
            return self._generate_sample_data(from_date, to_date, interval)
    
    def fetch_data_in_batches(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "minute",
        batch_days: int = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data in batches to handle large date ranges
        Uses proper Kite API limits based on interval
        """
        # Use Kite limits if batch_days not specified
        if batch_days is None:
            batch_days = KITE_LIMITS.get(interval, 60)
        
        # Calculate chunks based on Kite limits
        date_chunks = calculate_date_chunks(from_date, to_date, interval)
        
        logger.info(f"Starting batch fetch from {from_date.date()} to {to_date.date()} "
                   f"with {len(date_chunks)} chunks for {interval} interval")
        
        all_data = []
        successful_chunks = 0
        
        for i, (chunk_start, chunk_end) in enumerate(date_chunks, 1):
            logger.info(f"Fetching chunk {i}/{len(date_chunks)}: {chunk_start.date()} to {chunk_end.date()}")
            
            try:
                batch_data = self.fetch_historical_data(
                    instrument_token, chunk_start, chunk_end, interval
                )
                
                if batch_data:
                    # Filter out any duplicate records (by date/timestamp)
                    existing_dates = {record.get('date') for record in all_data}
                    new_records = [record for record in batch_data 
                                 if record.get('date') not in existing_dates]
                    
                    all_data.extend(new_records)
                    successful_chunks += 1
                    logger.info(f"Chunk {i}: Added {len(new_records)} new records, total: {len(all_data)}")
                else:
                    logger.warning(f"Chunk {i}: No data received")
                    
            except Exception as e:
                logger.error(f"Error fetching chunk {i} ({chunk_start.date()} to {chunk_end.date()}): {str(e)}")
                # Continue with next chunk instead of failing completely
                continue
            
            # Add delay to respect API rate limits (Zerodha allows 3 requests per second)
            time.sleep(1)  # 1 second delay between batches for safety
        
        if not all_data:
            logger.error("No data could be fetched from any chunks")
            return []
        
        logger.info(f"Batch fetching completed. Total records: {len(all_data)} from {successful_chunks}/{len(date_chunks)} successful chunks")
        
        # Sort data by date to ensure chronological order
        all_data.sort(key=lambda x: x.get('date', ''))
        
        return all_data
    
    def save_data_to_json(
        self, 
        data: List[Dict[str, Any]], 
        symbol: str, 
        from_date: Union[str, datetime], 
        to_date: Union[str, datetime],
        interval: str
    ) -> str:
        """
        Save data to JSON file in the data_storage directory
        Returns the file path
        """
        try:
            # Create data storage directory if it doesn't exist
            storage_dir = os.path.join(settings.BASE_DIR, 'data_storage')
            os.makedirs(storage_dir, exist_ok=True)
            
            # Handle date conversion - support both string and datetime inputs
            if isinstance(from_date, str):
                from_date_obj = datetime.strptime(from_date, '%Y-%m-%d')
                from_date_str = from_date.replace('-', '')
            else:
                from_date_obj = from_date
                from_date_str = from_date.strftime("%Y%m%d")
                
            if isinstance(to_date, str):
                to_date_obj = datetime.strptime(to_date, '%Y-%m-%d')
                to_date_str = to_date.replace('-', '')
            else:
                to_date_obj = to_date
                to_date_str = to_date.strftime("%Y%m%d")
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            filename = f"{symbol}_{interval}_{from_date_str}_to_{to_date_str}_{timestamp}.json"
            file_path = os.path.join(storage_dir, filename)
            
            # Prepare metadata
            metadata = {
                'symbol': symbol,
                'interval': interval,
                'from_date': from_date_obj.isoformat() if hasattr(from_date_obj, 'isoformat') else from_date,
                'to_date': to_date_obj.isoformat() if hasattr(to_date_obj, 'isoformat') else to_date,
                'records_count': len(data),
                'generated_at': datetime.now().isoformat(),
                'file_size_mb': 0  # Will be calculated after saving
            }
            
            # Prepare final data structure
            final_data = {
                'metadata': metadata,
                'data': data
            }
            
            # Save to JSON file
            with open(file_path, 'w') as f:
                json.dump(final_data, f, indent=2, default=str)
            
            # Calculate file size
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            metadata['file_size_mb'] = round(file_size, 2)
            
            # Update file with correct metadata
            with open(file_path, 'w') as f:
                json.dump(final_data, f, indent=2, default=str)
            
            logger.info(f"Data saved to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving data to JSON: {str(e)}")
            raise
    
    def _generate_sample_data(
        self, 
        from_date: datetime, 
        to_date: datetime, 
        interval: str
    ) -> List[Dict[str, Any]]:
        """
        Generate sample data for testing when API is not available
        """
        sample_data = []
        current_date = from_date
        
        # Determine time delta and max records based on interval
        if interval == "minute":
            delta = timedelta(minutes=1)
            # For minute data, generate for trading hours only (9:15 AM to 3:30 PM IST)
            # That's about 375 minutes per trading day
            trading_days = 0
            temp_date = from_date
            while temp_date <= to_date:
                # Skip weekends (Saturday=5, Sunday=6)
                if temp_date.weekday() < 5:
                    trading_days += 1
                temp_date += timedelta(days=1)
            max_records = trading_days * 375  # 375 minutes per trading day
        elif interval in ["3minute", "5minute", "15minute", "30minute"]:
            if interval == "3minute":
                delta = timedelta(minutes=3)
                records_per_day = 125
            elif interval == "5minute":
                delta = timedelta(minutes=5)
                records_per_day = 75
            elif interval == "15minute":
                delta = timedelta(minutes=15)
                records_per_day = 25
            elif interval == "30minute":
                delta = timedelta(minutes=30)
                records_per_day = 13
            
            trading_days = sum(1 for d in range((to_date - from_date).days + 1) 
                             if (from_date + timedelta(days=d)).weekday() < 5)
            max_records = trading_days * records_per_day
        elif interval == "60minute":
            delta = timedelta(hours=1)
            trading_days = sum(1 for d in range((to_date - from_date).days + 1) 
                             if (from_date + timedelta(days=d)).weekday() < 5)
            max_records = trading_days * 6  # 6 hours per trading day
        elif interval == "day":
            delta = timedelta(days=1)
            max_records = (to_date - from_date).days + 1
        else:
            delta = timedelta(days=1)
            max_records = (to_date - from_date).days + 1
        
        base_price = 100.0
        record_count = 0
        
        logger.info(f"Generating sample data from {from_date.date()} to {to_date.date()}, "
                   f"expected ~{max_records} records for {interval} interval")
        
        while current_date <= to_date and record_count < max_records:
            # For intraday intervals, only generate data during trading hours
            if interval != "day":
                # Skip weekends
                if current_date.weekday() >= 5:
                    current_date += timedelta(days=1)
                    continue
                    
                # For minute-level data, only generate during trading hours (9:15 to 15:30 IST)
                if interval in ["minute", "3minute", "5minute", "15minute", "30minute", "60minute"]:
                    trading_start_hour = 9
                    trading_start_minute = 15
                    trading_end_hour = 15
                    trading_end_minute = 30
                    
                    current_hour = current_date.hour
                    current_minute = current_date.minute
                    
                    # Check if current time is within trading hours
                    current_time_minutes = current_hour * 60 + current_minute
                    start_time_minutes = trading_start_hour * 60 + trading_start_minute
                    end_time_minutes = trading_end_hour * 60 + trading_end_minute
                    
                    if current_time_minutes < start_time_minutes:
                        # Jump to start of trading day
                        current_date = current_date.replace(hour=trading_start_hour, minute=trading_start_minute)
                    elif current_time_minutes > end_time_minutes:
                        # Jump to next trading day
                        current_date = (current_date + timedelta(days=1)).replace(hour=trading_start_hour, minute=trading_start_minute)
                        continue
            
            # Generate realistic OHLCV data
            import random
            
            variation = random.uniform(-2, 2)
            open_price = base_price + variation
            high_price = open_price + random.uniform(0, 2)
            low_price = open_price - random.uniform(0, 2)
            close_price = low_price + random.uniform(0, high_price - low_price)
            volume = random.randint(1000, 100000)
            
            sample_data.append({
                'date': current_date.isoformat(),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume
            })
            
            base_price = close_price  # Use close as next base
            current_date += delta
            record_count += 1
        
        logger.info(f"Generated {len(sample_data)} sample records for testing")
        return sample_data
    
    def get_data_statistics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics for the data"""
        if not data:
            return {}
        
        if pd is not None:
            # Use pandas for efficient calculations
            df = pd.DataFrame(data)
            stats = {
                'total_records': len(data),
                'date_range': {
                    'start': data[0]['date'],
                    'end': data[-1]['date']
                },
                'price_stats': {
                    'max_high': float(df['high'].max()),
                    'min_low': float(df['low'].min()),
                    'avg_close': float(df['close'].mean()),
                    'total_volume': int(df['volume'].sum())
                }
            }
        else:
            # Fallback calculations without pandas
            highs = [float(record['high']) for record in data]
            lows = [float(record['low']) for record in data]
            closes = [float(record['close']) for record in data]
            volumes = [int(record['volume']) for record in data]
            
            stats = {
                'total_records': len(data),
                'date_range': {
                    'start': data[0]['date'],
                    'end': data[-1]['date']
                },
                'price_stats': {
                    'max_high': max(highs),
                    'min_low': min(lows),
                    'avg_close': sum(closes) / len(closes),
                    'total_volume': sum(volumes)
                }
            }
        
        return stats


class KiteAuthService:
    """Service for handling Kite authentication flow"""
    
    @staticmethod
    def get_active_credentials():
        """Get active API credentials"""
        from .models import APICredentials
        try:
            return APICredentials.objects.filter(is_active=True).first()
        except:
            return None
    
    @staticmethod
    def create_kite_service() -> Optional[KiteDataService]:
        """Create KiteDataService with active credentials"""
        credentials = KiteAuthService.get_active_credentials()
        if credentials:
            return KiteDataService(api_credentials=credentials)
        return None
    
    @staticmethod
    def get_login_url() -> Optional[str]:
        """Get Kite login URL using active credentials"""
        service = KiteAuthService.create_kite_service()
        if service:
            return service.get_login_url()
        return None
    
    @staticmethod
    def authenticate_with_request_token(request_token: str) -> bool:
        """Authenticate using request token"""
        service = KiteAuthService.create_kite_service()
        if service:
            try:
                service.generate_session(request_token)
                return True
            except Exception as e:
                logger.error(f"Authentication failed: {str(e)}")
                return False
        return False
