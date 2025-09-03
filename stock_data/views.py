from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from .models import APICredentials, TradingSignal, TradingStrategy, StrategyBacktest
from .forms import APICredentialsForm, AuthenticationForm, StockDataFetchForm
from .services import KiteDataService
from .strategy_service import TradingStrategyService
import json
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

def index(request):
    """Main dashboard view with data fetching form."""
    credentials = APICredentials.objects.first()
    fetch_form = StockDataFetchForm()
    
    # Handle form submission
    if request.method == 'POST':
        fetch_form = StockDataFetchForm(request.POST)
        if fetch_form.is_valid():
            # Check authentication
            if not credentials or not credentials.is_authenticated:
                messages.error(request, 'Please authenticate your API first in Settings.')
                return redirect('settings')
            
            # Get form data
            symbol = fetch_form.cleaned_data['symbol']
            
            # Handle date conversion safely
            from_date_obj = fetch_form.cleaned_data['from_date']
            to_date_obj = fetch_form.cleaned_data['to_date']
            
            # Convert to string format - handle both date objects and strings
            if isinstance(from_date_obj, str):
                from_date = from_date_obj
            else:
                from_date = from_date_obj.strftime('%Y-%m-%d')
                
            if isinstance(to_date_obj, str):
                to_date = to_date_obj
            else:
                to_date = to_date_obj.strftime('%Y-%m-%d')
                
            interval = fetch_form.cleaned_data['interval']
            
            try:
                # Fetch data using KiteDataService
                kite_service = KiteDataService(api_credentials=credentials)
                
                # Check if data already exists
                existing_data = kite_service.load_data_from_json(symbol, from_date, to_date, interval)
                if existing_data:
                    messages.info(request, f'Data for {symbol} already exists. Showing existing data.')
                    return redirect(f'/data/?file={kite_service.get_json_filename(symbol, from_date, to_date, interval)}')
                
                # Fetch new data
                historical_data = kite_service.fetch_historical_data_by_symbol(
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval
                )
                
                # Save to JSON file
                filepath = kite_service.save_data_to_json(historical_data, symbol, from_date, to_date, interval)
                
                messages.success(request, f'Successfully fetched {len(historical_data)} records for {symbol}!')
                
                # Redirect to data view with the new file
                filename = os.path.basename(filepath)
                return redirect(f'/data/?file={filename}')
                
            except Exception as e:
                logger.error(f"Error fetching data: {str(e)}", exc_info=True)
                messages.error(request, f'Error fetching data: {str(e)}')
    
    # Get available data files
    kite_service = KiteDataService()
    available_files = kite_service.list_available_data_files()
    
    context = {
        'fetch_form': fetch_form,
        'credentials': credentials,
        'is_authenticated': credentials.is_authenticated if credentials else False,
        'available_files': available_files[:5],  # Show latest 5 files
    }
    
    return render(request, 'index.html', context)

def settings(request):
    """API settings and authentication view."""
    credentials = APICredentials.objects.first()
    login_url = None
    
    if request.method == 'POST':
        if 'api_form' in request.POST:
            # Handle API credentials form
            form = APICredentialsForm(request.POST, instance=credentials)
            if form.is_valid():
                credentials = form.save()
                messages.success(request, 'API credentials saved successfully!')
                
                # Generate login URL
                try:
                    login_url = credentials.get_kite_login_url()
                    messages.info(request, 'Please click the login link below to authenticate with Zerodha.')
                except Exception as e:
                    messages.error(request, f'Error generating login URL: {str(e)}')
                    
        elif 'auth_form' in request.POST:
            # Handle authentication form
            auth_form = AuthenticationForm(request.POST)
            logger.info(f"Auth form submission - Form valid: {auth_form.is_valid()}, Credentials exist: {credentials is not None}")
            
            if auth_form.is_valid() and credentials:
                request_token = auth_form.cleaned_data['request_token']
                logger.info(f"Processing authentication with request_token: {request_token[:10]}...")
                
                try:
                    kite_service = KiteDataService(api_credentials=credentials)
                    logger.info("Attempting to generate session...")
                    session_data = kite_service.generate_session(request_token)
                    
                    logger.info(f"Session data received: {session_data}")
                    
                    # Save tokens
                    credentials.access_token = session_data.get('access_token')
                    credentials.refresh_token = session_data.get('refresh_token') 
                    credentials.user_id = session_data.get('user_id')
                    credentials.is_authenticated = True
                    credentials.token_expires_at = datetime.now() + timedelta(days=1)
                    credentials.save()
                    
                    logger.info(f"Authentication successful for user: {credentials.user_id}")
                    messages.success(request, f'Authentication successful! Welcome {credentials.user_id}. You can now fetch stock data.')
                    return redirect('settings')
                    
                except Exception as e:
                    logger.error(f"Authentication failed: {str(e)}", exc_info=True)
                    messages.error(request, f'Authentication failed: {str(e)}')
            else:
                if not credentials:
                    messages.error(request, 'Please save API credentials first.')
                else:
                    if not auth_form.is_valid():
                        for field, errors in auth_form.errors.items():
                            for error in errors:
                                messages.error(request, f'{field}: {error}')
                    messages.error(request, 'Invalid request token or form data.')
    
    # Initialize forms
    form = APICredentialsForm(instance=credentials)
    auth_form = AuthenticationForm()
    
    # Generate login URL if credentials exist
    if credentials and credentials.api_key and credentials.api_secret:
        try:
            login_url = credentials.get_kite_login_url()
        except Exception as e:
            logger.error(f"Error generating login URL: {e}")
    
    context = {
        'form': form,
        'auth_form': auth_form,
        'credentials': credentials,
        'login_url': login_url,
        'is_authenticated': credentials.is_authenticated if credentials else False,
    }
    
    return render(request, 'settings.html', context)

def data_view(request):
    """Enhanced data view showing JSON file contents with pagination."""
    kite_service = KiteDataService()
    available_files = kite_service.list_available_data_files()
    
    # Get selected file from query params
    selected_file = request.GET.get('file')
    data_content = None
    pagination_info = None
    
    if selected_file:
        # Load data from selected JSON file
        for file_info in available_files:
            if file_info['filename'] == selected_file:
                try:
                    with open(file_info['filepath'], 'r') as f:
                        file_data = json.load(f)
                    
                    # Pagination logic
                    page = int(request.GET.get('page', 1))
                    per_page = int(request.GET.get('per_page', 100))
                    
                    all_data = file_data.get('data', [])
                    total_records = len(all_data)
                    
                    # Calculate pagination
                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    paginated_data = all_data[start_idx:end_idx]
                    
                    total_pages = (total_records + per_page - 1) // per_page
                    
                    data_content = {
                        'metadata': {
                            'symbol': file_data.get('metadata', {}).get('symbol') or file_data.get('symbol'),
                            'from_date': file_data.get('metadata', {}).get('from_date') or file_data.get('from_date'),
                            'to_date': file_data.get('metadata', {}).get('to_date') or file_data.get('to_date'),
                            'interval': file_data.get('metadata', {}).get('interval') or file_data.get('interval'),
                            'total_records': total_records,
                            'fetched_at': file_data.get('metadata', {}).get('generated_at') or file_data.get('fetched_at'),
                        },
                        'records': paginated_data
                    }
                    
                    pagination_info = {
                        'current_page': page,
                        'total_pages': total_pages,
                        'per_page': per_page,
                        'total_records': total_records,
                        'start_record': start_idx + 1,
                        'end_record': min(end_idx, total_records),
                        'has_previous': page > 1,
                        'has_next': page < total_pages,
                        'previous_page': page - 1 if page > 1 else None,
                        'next_page': page + 1 if page < total_pages else None,
                    }
                    
                except Exception as e:
                    messages.error(request, f'Error loading file {selected_file}: {str(e)}')
                break
    
    context = {
        'available_files': available_files,
        'selected_file': selected_file,
        'data_content': data_content,
        'pagination': pagination_info,
    }
    
    return render(request, 'data.html', context)

@csrf_exempt
def fetch_data_api(request):
    """API endpoint to fetch stock data and save to JSON."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol', '').upper()
        interval = data.get('interval', 'minute')
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        
        if not symbol:
            return JsonResponse({'error': 'Symbol is required'}, status=400)
        
        # Check if credentials exist and are authenticated
        credentials = APICredentials.objects.first()
        if not credentials or not credentials.is_authenticated:
            return JsonResponse({
                'error': 'API not authenticated. Please configure and authenticate your API in settings.'
            }, status=401)
        
        # Check if token is still valid
        if not credentials.is_token_valid():
            return JsonResponse({
                'error': 'Token expired. Please re-authenticate in settings.'
            }, status=401)
        
        # Fetch data
        kite_service = KiteDataService(api_credentials=credentials)
        
        # Check if data already exists
        existing_data = kite_service.load_data_from_json(symbol, from_date, to_date, interval)
        if existing_data:
            return JsonResponse({
                'success': True,
                'message': f'Data already exists with {existing_data["total_records"]} records',
                'data_count': existing_data['total_records'],
                'file_exists': True
            })
        
        # Fetch new data
        historical_data = kite_service.fetch_historical_data_by_symbol(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        # Save to JSON file
        filepath = kite_service.save_data_to_json(historical_data, symbol, from_date, to_date, interval)
        filename = os.path.basename(filepath)
        
        return JsonResponse({
            'success': True,
            'message': f'Fetched {len(historical_data)} records and saved to JSON file',
            'data_count': len(historical_data),
            'filename': filename,
            'filepath': filepath
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error fetching data: {e}", exc_info=True)
        return JsonResponse({'error': f'Error: {str(e)}'}, status=500)

def test_connection(request):
    """Test API connection."""
    credentials = APICredentials.objects.first()
    
    if not credentials or not credentials.is_authenticated:
        return JsonResponse({
            'success': False,
            'message': 'API not configured or authenticated'
        })
    
    try:
        kite_service = KiteDataService()
        profile = kite_service.test_connection(credentials.access_token)
        
        return JsonResponse({
            'success': True,
            'message': 'Connection successful',
            'user_data': profile
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Connection failed: {str(e)}'
        })


def strategy_view(request):
    """View to manage and execute trading strategies"""
    kite_service = KiteDataService()
    available_files = kite_service.list_available_data_files()
    
    # Get all strategies and recent backtests
    strategies = TradingStrategy.objects.all()
    recent_backtests = StrategyBacktest.objects.all()[:10]
    recent_signals = TradingSignal.objects.all()[:50]
    
    context = {
        'available_files': available_files,
        'strategies': strategies,
        'recent_backtests': recent_backtests,
        'recent_signals': recent_signals,
    }
    
    return render(request, 'strategy.html', context)


@csrf_exempt
def execute_strategy(request):
    """API endpoint to execute trading strategy on a data file"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        file_path = data.get('file_path')
        symbol = data.get('symbol', '').upper()
        
        if not file_path or not symbol:
            return JsonResponse({'error': 'file_path and symbol are required'}, status=400)
        
        # Check if file exists
        if not os.path.exists(file_path):
            return JsonResponse({'error': 'Data file not found'}, status=404)
        
        # Execute strategy
        strategy_service = TradingStrategyService()
        results = strategy_service.run_strategy_on_file(file_path, symbol)
        
        if results["success"]:
            return JsonResponse({
                'success': True,
                'message': results["message"],
                'signals_created': results["signals_created"],
                'backtest_results': results["backtest_results"],
                'backtest_id': results["backtest_id"]
            })
        else:
            return JsonResponse({
                'success': False,
                'error': results["error"],
                'message': results["message"]
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error executing strategy: {e}", exc_info=True)
        return JsonResponse({'error': f'Error: {str(e)}'}, status=500)


def signals_view(request):
    """View to display trading signals"""
    symbol = request.GET.get('symbol')
    strategy_id = request.GET.get('strategy')
    
    # Filter signals
    signals = TradingSignal.objects.all()
    if symbol:
        signals = signals.filter(symbol=symbol)
    if strategy_id:
        signals = signals.filter(strategy_id=strategy_id)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(signals, 50)
    page = request.GET.get('page', 1)
    signals_page = paginator.get_page(page)
    
    # Get available symbols and strategies for filters
    symbols = TradingSignal.objects.values_list('symbol', flat=True).distinct()
    strategies = TradingStrategy.objects.all()
    
    context = {
        'signals': signals_page,
        'symbols': symbols,
        'strategies': strategies,
        'selected_symbol': symbol,
        'selected_strategy': strategy_id,
    }
    
    return render(request, 'signals.html', context)


def backtest_view(request):
    """View to display backtest results"""
    backtest_id = request.GET.get('id')
    
    if backtest_id:
        try:
            backtest = StrategyBacktest.objects.get(id=backtest_id)
            context = {
                'backtest': backtest,
                'detailed_view': True
            }
        except StrategyBacktest.DoesNotExist:
            messages.error(request, 'Backtest not found')
            return redirect('backtest_view')
    else:
        # List all backtests
        backtests = StrategyBacktest.objects.all()
        context = {
            'backtests': backtests,
            'detailed_view': False
        }
    
    return render(request, 'backtest.html', context)


def charts_view(request):
    """View to display strategy charts"""
    # Get all backtests for the dropdown
    backtests = StrategyBacktest.objects.all().order_by('-created_at')
    
    context = {
        'backtests': backtests,
    }
    
    return render(request, 'charts.html', context)


@csrf_exempt
def chart_data_api(request, backtest_id):
    """API endpoint to get chart data for a specific backtest"""
    try:
        backtest = StrategyBacktest.objects.get(id=backtest_id)
        
        # Get signals for this backtest
        signals = TradingSignal.objects.filter(
            symbol=backtest.symbol,
            timestamp__gte=backtest.from_date,
            timestamp__lte=backtest.to_date
        ).order_by('timestamp')
        
        # Load OHLC data from the original data file
        kite_service = KiteDataService()
        available_files = kite_service.list_available_data_files()
        
        ohlc_data = []
        indicators_data = {
            'macd': [],
            'ma': []
        }
        
        # Find the data file for this backtest
        for file_info in available_files:
            if file_info['symbol'] == backtest.symbol:
                logger.info(f"Found matching symbol file: {file_info['filepath']}")
                
                try:
                    with open(file_info['filepath'], 'r') as f:
                        file_data = json.load(f)
                    
                    logger.info(f"Loaded file with {len(file_data.get('data', []))} records")
                    
                    # Extract OHLC data with validation
                    for record in file_data.get('data', []):
                        if isinstance(record, dict):
                            try:
                                # Validate and convert data
                                open_val = float(record.get('open', 0))
                                high_val = float(record.get('high', 0))
                                low_val = float(record.get('low', 0))
                                close_val = float(record.get('close', 0))
                                volume_val = int(record.get('volume', 0))
                                date_val = record.get('date') or record.get('timestamp')
                                
                                # Basic validation - only skip obviously invalid data
                                if (date_val and open_val > 0 and high_val > 0 and 
                                    low_val > 0 and close_val > 0):
                                    
                                    ohlc_data.append({
                                        'date': date_val,
                                        'open': open_val,
                                        'high': high_val,
                                        'low': low_val,
                                        'close': close_val,
                                        'volume': volume_val
                                    })
                            except (ValueError, TypeError):
                                # Skip invalid records
                                continue
                    
                    logger.info(f"Extracted {len(ohlc_data)} valid OHLC records")
                    
                    # Calculate indicators with improved validation
                    if len(ohlc_data) >= 26:  # Minimum required for MACD
                        close_prices = [d['close'] for d in ohlc_data]
                        
                        # Simple Moving Average (5 period) with validation
                        for i in range(4, len(ohlc_data)):
                            try:
                                ma_prices = close_prices[i-4:i+1]
                                if all(p > 0 for p in ma_prices):  # Ensure all prices are valid
                                    ma_value = sum(ma_prices) / 5
                                    indicators_data['ma'].append({
                                        'date': ohlc_data[i]['date'],
                                        'value': ma_value
                                    })
                            except (IndexError, ZeroDivisionError):
                                continue
                        
                        # Improved MACD calculation with validation
                        for i in range(25, len(ohlc_data)):
                            try:
                                # Calculate EMAs with validation
                                ema12_prices = close_prices[i-11:i+1]
                                ema26_prices = close_prices[i-25:i+1]
                                
                                if (all(p > 0 for p in ema12_prices) and 
                                    all(p > 0 for p in ema26_prices)):
                                    
                                    ema12 = sum(ema12_prices) / 12
                                    ema26 = sum(ema26_prices) / 26
                                    macd_line = ema12 - ema26
                                    
                                    # Signal line (simplified 9-period EMA of MACD)
                                    if i > 33:  # Ensure we have enough data for signal
                                        recent_macd = [indicators_data['macd'][j]['macd'] 
                                                     for j in range(max(0, len(indicators_data['macd'])-8), 
                                                                   len(indicators_data['macd']))]
                                        recent_macd.append(macd_line)
                                        signal_line = sum(recent_macd) / len(recent_macd)
                                    else:
                                        signal_line = macd_line
                                    
                                    histogram = macd_line - signal_line
                                    
                                    indicators_data['macd'].append({
                                        'date': ohlc_data[i]['date'],
                                        'macd': macd_line,
                                        'signal': signal_line,
                                        'histogram': histogram
                                    })
                            except (IndexError, ZeroDivisionError, TypeError):
                                continue
                    
                    break
                except Exception as e:
                    logger.error(f"Error loading data file: {e}")
                    continue
        
        # Format signals data with validation
        signals_data = []
        for signal in signals:
            try:
                price_val = float(signal.price)
                if price_val > 0:  # Only include valid prices
                    signals_data.append({
                        'timestamp': signal.timestamp.isoformat(),
                        'signal_type': signal.signal_type,
                        'price': price_val,
                        'confidence': signal.confidence
                    })
            except (ValueError, TypeError):
                continue
        
        return JsonResponse({
            'success': True,
            'ohlc_data': ohlc_data,
            'signals': signals_data,
            'indicators': indicators_data,
            'backtest_info': {
                'symbol': backtest.symbol,
                'from_date': backtest.from_date.strftime('%Y-%m-%d'),
                'to_date': backtest.to_date.strftime('%Y-%m-%d'),
                'strategy_name': backtest.strategy.name
            }
        })
        
    except StrategyBacktest.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Backtest not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error generating chart data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error generating chart data: {str(e)}'
        }, status=500)
