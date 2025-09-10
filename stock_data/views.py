from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.db.models import Avg, Min, Max, Count
from .models import APICredentials, TradingSignal, TradingStrategy, StrategyBacktest
from .forms import APICredentialsForm, AuthenticationForm, StockDataFetchForm
from .services import KiteDataService
from .strategy_service import TradingStrategyService
import json
import logging
from datetime import datetime, timedelta
import os
import pandas as pd
from io import BytesIO

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
                
                # Fetch new data using smart fetching (automatically handles chunking)
                historical_data = kite_service.fetch_historical_data_smart(
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
        
        # Fetch new data using smart fetching (automatically handles chunking)
        historical_data = kite_service.fetch_historical_data_smart(
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
        logger.info(f"chart_data_api: Loaded backtest {backtest_id} for symbol {backtest.symbol}")

        signals = TradingSignal.objects.filter(
            symbol=backtest.symbol,
            timestamp__gte=backtest.from_date,
            timestamp__lte=backtest.to_date
        ).order_by('timestamp')
        logger.info(f"chart_data_api: Found {signals.count()} signals for backtest {backtest_id}")

        kite_service = KiteDataService()
        available_files = kite_service.list_available_data_files()

        ohlc_data = []
        indicators_data = {
            'macd': [],
            'ma': []
        }

        for file_info in available_files:
            if file_info['symbol'] == backtest.symbol:
                logger.info(f"chart_data_api: Found matching symbol file: {file_info['filepath']}")
                try:
                    with open(file_info['filepath'], 'r') as f:
                        file_data = json.load(f)
                    logger.info(f"chart_data_api: Loaded file with {len(file_data.get('data', []))} records")

                    for record in file_data.get('data', []):
                        if isinstance(record, dict):
                            try:
                                open_val = float(record.get('open', 0))
                                high_val = float(record.get('high', 0))
                                low_val = float(record.get('low', 0))
                                close_val = float(record.get('close', 0))
                                volume_val = int(record.get('volume', 0))
                                date_val = record.get('date') or record.get('timestamp')
                                if (date_val and open_val > 0 and high_val > 0 and low_val > 0 and close_val > 0):
                                    ohlc_data.append({
                                        'date': date_val,
                                        'open': open_val,
                                        'high': high_val,
                                        'low': low_val,
                                        'close': close_val,
                                        'volume': volume_val
                                    })
                            except (ValueError, TypeError):
                                continue
                    logger.info(f"chart_data_api: Extracted {len(ohlc_data)} valid OHLC records")

                    if len(ohlc_data) >= 26:
                        close_prices = [d['close'] for d in ohlc_data]
                        for i in range(4, len(ohlc_data)):
                            try:
                                ma_prices = close_prices[i-4:i+1]
                                if all(p > 0 for p in ma_prices):
                                    ma_value = sum(ma_prices) / 5
                                    indicators_data['ma'].append({
                                        'date': ohlc_data[i]['date'],
                                        'value': ma_value
                                    })
                            except (IndexError, ZeroDivisionError):
                                continue
                        for i in range(25, len(ohlc_data)):
                            try:
                                ema12_prices = close_prices[i-11:i+1]
                                ema26_prices = close_prices[i-25:i+1]
                                if (all(p > 0 for p in ema12_prices) and all(p > 0 for p in ema26_prices)):
                                    ema12 = sum(ema12_prices) / 12
                                    ema26 = sum(ema26_prices) / 26
                                    macd_line = ema12 - ema26
                                    if i > 33:
                                        recent_macd = [indicators_data['macd'][j]['macd'] for j in range(max(0, len(indicators_data['macd'])-8), len(indicators_data['macd']))]
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
                    logger.error(f"chart_data_api: Error loading data file: {e}")
                    continue

        signals_data = []
        for signal in signals:
            try:
                price_val = float(signal.price)
                if price_val > 0:
                    signals_data.append({
                        'timestamp': signal.timestamp.isoformat(),
                        'signal_type': signal.signal_type,
                        'price': price_val,
                        'confidence': signal.confidence
                    })
            except (ValueError, TypeError):
                continue

        logger.info(f"chart_data_api: Returning {len(ohlc_data)} OHLC, {len(signals_data)} signals, {len(indicators_data['macd'])} MACD, {len(indicators_data['ma'])} MA")

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
        logger.error(f"chart_data_api: Backtest {backtest_id} not found")
        return JsonResponse({
            'success': False,
            'message': 'Backtest not found'
        }, status=404)
    except Exception as e:
        logger.error(f"chart_data_api: Error generating chart data: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error generating chart data: {str(e)}'
        }, status=500)


def export_strategy_data_to_excel(request):
    """Export strategy data with signals and backtest results to Excel"""
    try:
        # Get filters from request
        symbol = request.GET.get('symbol')
        strategy_id = request.GET.get('strategy')
        backtest_id = request.GET.get('backtest')
        
        if not symbol:
            messages.error(request, 'Symbol is required for export')
            return redirect('signals_view')
        
        # Create Excel workbook with multiple sheets
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Trading Signals
            signals_query = TradingSignal.objects.filter(symbol=symbol)
            if strategy_id:
                signals_query = signals_query.filter(strategy_id=strategy_id)
                
            signals = signals_query.order_by('timestamp')
            
            if signals.exists():
                signals_data = []
                for signal in signals:
                    try:
                        indicators = signal.indicators if signal.indicators else {}
                        # Convert timezone-aware datetimes to naive datetimes for Excel compatibility
                        timestamp_naive = signal.timestamp.replace(tzinfo=None) if signal.timestamp else None
                        created_at_naive = signal.created_at.replace(tzinfo=None) if signal.created_at else None
                        
                        signals_data.append({
                            'Timestamp': timestamp_naive,
                            'Symbol': signal.symbol,
                            'Strategy': signal.strategy.name if signal.strategy else '',
                            'Signal_Type': signal.signal_type,
                            'Price': float(signal.price) if signal.price else 0.0,
                            'Confidence': float(signal.confidence) if signal.confidence else 0.0,
                            'MA_5': float(indicators.get('MA_5', 0)) if indicators.get('MA_5') else '',
                            'MACD': float(indicators.get('MACD', 0)) if indicators.get('MACD') else '',
                            'MACD_Signal': float(indicators.get('MACD_Signal', 0)) if indicators.get('MACD_Signal') else '',
                            'MACD_Histogram': float(indicators.get('MACD_Histogram', 0)) if indicators.get('MACD_Histogram') else '',
                            'Close_Price': float(indicators.get('close', 0)) if indicators.get('close') else '',
                            'Volume': int(indicators.get('volume', 0)) if indicators.get('volume') else '',
                            'Created_At': created_at_naive
                        })
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"Error processing signal {signal.id}: {e}")
                        continue
                
                if signals_data:
                    signals_df = pd.DataFrame(signals_data)
                    signals_df.to_excel(writer, sheet_name='Trading_Signals', index=False)
                else:
                    # Create empty sheet if no valid signals
                    empty_df = pd.DataFrame({'Message': ['No valid signals found']})
                    empty_df.to_excel(writer, sheet_name='Trading_Signals', index=False)
            
            # Sheet 2: Backtest Results
            backtests_query = StrategyBacktest.objects.filter(symbol=symbol)
            if strategy_id:
                backtests_query = backtests_query.filter(strategy_id=strategy_id)
            if backtest_id:
                backtests_query = backtests_query.filter(id=backtest_id)
                
            backtests = backtests_query.order_by('-created_at')
            
            if backtests.exists():
                backtest_data = []
                for backtest in backtests:
                    try:
                        results_data = backtest.results_data if backtest.results_data else {}
                        # Convert timezone-aware datetime to naive datetime for Excel compatibility
                        created_at_naive = backtest.created_at.replace(tzinfo=None) if backtest.created_at else None
                        
                        backtest_data.append({
                            'Backtest_ID': backtest.id,
                            'Symbol': backtest.symbol,
                            'Strategy': backtest.strategy.name,
                            'From_Date': backtest.from_date,
                            'To_Date': backtest.to_date,
                            'Total_Trades': backtest.total_trades,
                            'Winning_Trades': backtest.winning_trades,
                            'Losing_Trades': backtest.losing_trades,
                            'Win_Rate_%': float(results_data.get('win_rate', 0)),
                            'Total_Return_%': float(backtest.total_return),
                            'Strategy_Return_%': float(backtest.strategy_return),
                            'Market_Return_%': float(backtest.market_return),
                            'Buy_Signals_Count': backtest.buy_signals_count,
                            'Sell_Signals_Count': backtest.sell_signals_count,
                            'Max_Drawdown_%': float(results_data.get('max_drawdown', 0)),
                            'Sharpe_Ratio': float(results_data.get('sharpe_ratio', 0)),
                            'Created_At': created_at_naive
                        })
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"Error processing backtest {backtest.id}: {e}")
                        continue
                
                if backtest_data:
                    backtest_df = pd.DataFrame(backtest_data)
                    backtest_df.to_excel(writer, sheet_name='Backtest_Results', index=False)
                else:
                    # Create empty sheet if no valid backtests
                    empty_df = pd.DataFrame({'Message': ['No valid backtest results found']})
                    empty_df.to_excel(writer, sheet_name='Backtest_Results', index=False)
            
            # Sheet 3: Signal Summary
            signal_summary = []
            buy_signals = signals.filter(signal_type='BUY')
            sell_signals = signals.filter(signal_type='SELL')
            hold_signals = signals.filter(signal_type='HOLD')
            
            # Use Django aggregation
            buy_stats = buy_signals.aggregate(
                count=Count('id'),
                avg_price=Avg('price'),
                avg_confidence=Avg('confidence'),
                min_price=Min('price'),
                max_price=Max('price')
            )
            
            sell_stats = sell_signals.aggregate(
                count=Count('id'),
                avg_price=Avg('price'),
                avg_confidence=Avg('confidence'),
                min_price=Min('price'),
                max_price=Max('price')
            )
            
            signal_summary.append({
                'Signal_Type': 'BUY',
                'Count': buy_stats['count'] or 0,
                'Avg_Price': buy_stats['avg_price'] or 0,
                'Avg_Confidence': buy_stats['avg_confidence'] or 0,
                'Min_Price': buy_stats['min_price'] or 0,
                'Max_Price': buy_stats['max_price'] or 0
            })
            
            signal_summary.append({
                'Signal_Type': 'SELL',
                'Count': sell_stats['count'] or 0,
                'Avg_Price': sell_stats['avg_price'] or 0,
                'Avg_Confidence': sell_stats['avg_confidence'] or 0,
                'Min_Price': sell_stats['min_price'] or 0,
                'Max_Price': sell_stats['max_price'] or 0
            })
            
            if hold_signals.exists():
                hold_stats = hold_signals.aggregate(
                    count=Count('id'),
                    avg_price=Avg('price'),
                    avg_confidence=Avg('confidence'),
                    min_price=Min('price'),
                    max_price=Max('price')
                )
                
                signal_summary.append({
                    'Signal_Type': 'HOLD',
                    'Count': hold_stats['count'] or 0,
                    'Avg_Price': hold_stats['avg_price'] or 0,
                    'Avg_Confidence': hold_stats['avg_confidence'] or 0,
                    'Min_Price': hold_stats['min_price'] or 0,
                    'Max_Price': hold_stats['max_price'] or 0
                })
            
            summary_df = pd.DataFrame(signal_summary)
            summary_df.to_excel(writer, sheet_name='Signal_Summary', index=False)
            
            # Sheet 4: Strategy Performance Comparison (if multiple strategies)
            if not strategy_id:
                all_backtests = StrategyBacktest.objects.filter(symbol=symbol)
                if all_backtests.exists():
                    performance_data = []
                    for backtest in all_backtests:
                        results_data = backtest.results_data if backtest.results_data else {}
                        performance_data.append({
                            'Strategy': backtest.strategy.name,
                            'Period': f"{backtest.from_date} to {backtest.to_date}",
                            'Total_Return_%': backtest.total_return,
                            'Win_Rate_%': results_data.get('win_rate', 0),
                            'Total_Trades': backtest.total_trades,
                            'Profit_Factor': results_data.get('profit_factor', 0),
                            'Max_Drawdown_%': results_data.get('max_drawdown', 0)
                        })
                    
                    performance_df = pd.DataFrame(performance_data)
                    performance_df.to_excel(writer, sheet_name='Performance_Comparison', index=False)
        
        # Prepare response
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        strategy_name = ""
        if strategy_id:
            try:
                strategy = TradingStrategy.objects.get(id=strategy_id)
                strategy_name = f"_{strategy.name}"
            except TradingStrategy.DoesNotExist:
                pass
        
        filename = f"Strategy_Data_{symbol}{strategy_name}_{timestamp}.xlsx"
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting strategy data to Excel: {e}", exc_info=True)
        messages.error(request, f'Error exporting data: {str(e)}')
        return redirect('signals_view')


def export_backtest_to_excel(request, backtest_id):
    """Export specific backtest results with detailed analysis to Excel"""
    try:
        backtest = StrategyBacktest.objects.get(id=backtest_id)
        
        # Get related signals
        signals = TradingSignal.objects.filter(
            symbol=backtest.symbol,
            strategy=backtest.strategy,
            timestamp__gte=backtest.from_date,
            timestamp__lte=backtest.to_date
        ).order_by('timestamp')
        
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Backtest Overview
            overview_data = [{
                'Metric': 'Symbol',
                'Value': backtest.symbol
            }, {
                'Metric': 'Strategy',
                'Value': backtest.strategy.name
            }, {
                'Metric': 'Period',
                'Value': f"{backtest.from_date} to {backtest.to_date}"
            }, {
                'Metric': 'Total Trades',
                'Value': backtest.total_trades
            }, {
                'Metric': 'Winning Trades',
                'Value': backtest.winning_trades
            }, {
                'Metric': 'Losing Trades',
                'Value': backtest.losing_trades
            }, {
                'Metric': 'Win Rate (%)',
                'Value': (backtest.winning_trades / backtest.total_trades * 100) if backtest.total_trades > 0 else 0
            }, {
                'Metric': 'Total Return (%)',
                'Value': backtest.total_return
            }, {
                'Metric': 'Strategy Return (%)',
                'Value': backtest.strategy_return
            }, {
                'Metric': 'Market Return (%)',
                'Value': backtest.market_return
            }, {
                'Metric': 'Buy Signals Count',
                'Value': backtest.buy_signals_count
            }, {
                'Metric': 'Sell Signals Count',
                'Value': backtest.sell_signals_count
            }]
            
            overview_df = pd.DataFrame(overview_data)
            overview_df.to_excel(writer, sheet_name='Backtest_Overview', index=False)
            
            # Sheet 2: Trade Signals
            if signals.exists():
                signals_data = []
                trade_number = 1
                for signal in signals:
                    try:
                        indicators = signal.indicators if signal.indicators else {}
                        # Convert timezone-aware datetime to naive datetime for Excel compatibility
                        timestamp_naive = signal.timestamp.replace(tzinfo=None) if signal.timestamp else None
                        
                        signals_data.append({
                            'Trade_Number': trade_number if signal.signal_type == 'BUY' else '',
                            'Timestamp': timestamp_naive,
                            'Signal_Type': signal.signal_type,
                            'Price': float(signal.price) if signal.price else 0.0,
                            'Confidence': float(signal.confidence) if signal.confidence else 0.0,
                            'MA_5': float(indicators.get('MA_5', 0)) if indicators.get('MA_5') else '',
                            'MACD': float(indicators.get('MACD', 0)) if indicators.get('MACD') else '',
                            'MACD_Signal': float(indicators.get('MACD_Signal', 0)) if indicators.get('MACD_Signal') else '',
                            'MACD_Histogram': float(indicators.get('MACD_Histogram', 0)) if indicators.get('MACD_Histogram') else '',
                            'Volume': int(indicators.get('volume', 0)) if indicators.get('volume') else '',
                            'Profit_Loss': '',  # Will be calculated separately
                            'Profit_Loss_%': ''
                        })
                        if signal.signal_type == 'BUY':
                            trade_number += 1
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.warning(f"Error processing signal {signal.id}: {e}")
                        continue
                
                if signals_data:
                    signals_df = pd.DataFrame(signals_data)
                    
                    # Calculate profit/loss for matched buy-sell pairs
                    buy_signals_data = [s for s in signals_data if s['Signal_Type'] == 'BUY']
                    sell_signals_data = [s for s in signals_data if s['Signal_Type'] == 'SELL']
                    
                    for i, buy in enumerate(buy_signals_data):
                        if i < len(sell_signals_data):
                            sell = sell_signals_data[i]
                            try:
                                profit_loss = float(sell['Price']) - float(buy['Price'])
                                profit_loss_pct = (profit_loss / float(buy['Price'])) * 100 if float(buy['Price']) > 0 else 0
                                
                                # Update the sell signal row with profit/loss
                                for idx, row in signals_df.iterrows():
                                    if (str(row['Timestamp']) == str(sell['Timestamp']) and 
                                        row['Signal_Type'] == 'SELL' and
                                        abs(float(row['Price']) - float(sell['Price'])) < 0.01):  # Use small tolerance for float comparison
                                        signals_df.at[idx, 'Profit_Loss'] = profit_loss
                                        signals_df.at[idx, 'Profit_Loss_%'] = profit_loss_pct
                                        break
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Error calculating profit/loss for trade {i}: {e}")
                                continue
                    
                    signals_df.to_excel(writer, sheet_name='Trade_Signals', index=False)
                else:
                    # Create empty sheet if no valid signals
                    empty_df = pd.DataFrame({'Message': ['No valid signals found']})
                    empty_df.to_excel(writer, sheet_name='Trade_Signals', index=False)
        
        # Prepare response
        output.seek(0)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Backtest_{backtest.symbol}_{backtest.strategy.name}_{timestamp}.xlsx"
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except StrategyBacktest.DoesNotExist:
        messages.error(request, 'Backtest not found')
        return redirect('backtest_view')
    except Exception as e:
        logger.error(f"Error exporting backtest to Excel: {e}", exc_info=True)
        messages.error(request, f'Error exporting backtest: {str(e)}')
        return redirect('backtest_view')
