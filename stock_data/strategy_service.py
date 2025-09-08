import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from .models import TradingSignal, TradingStrategy, StrategyBacktest
import logging

logger = logging.getLogger(__name__)


class TradingStrategyService:
    """Service to implement and execute trading strategies"""
    
    def __init__(self):
        self.strategy_name = "MACD_MA_CrossOver_Strategy"
        
    def load_data_from_json(self, file_path: str) -> pd.DataFrame:
        """Load stock data from JSON file and convert to DataFrame"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Extract data records
            records = data.get('data', [])
            if not records:
                raise ValueError("No data records found in JSON file")
            
            # Convert to DataFrame
            df = pd.DataFrame(records)
            
            # Convert date column to datetime and set as index
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            # Ensure numeric columns
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading data from JSON: {str(e)}")
            raise
    
    def resample_data(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Resample data to different timeframes"""
        try:
            # Resample to different timeframes
            df_15m = df.resample("15min").agg({
                "open": "first", 
                "high": "max", 
                "low": "min", 
                "close": "last", 
                "volume": "sum"
            }).dropna()
            
            df_1h = df.resample("1h").agg({
                "open": "first", 
                "high": "max", 
                "low": "min", 
                "close": "last", 
                "volume": "sum"
            }).dropna()
            
            df_1d = df.resample("1D").agg({
                "open": "first", 
                "high": "max", 
                "low": "min", 
                "close": "last", 
                "volume": "sum"
            }).dropna()
            
            return {
                "15min": df_15m,
                "1h": df_1h,
                "1D": df_1d
            }
            
        except Exception as e:
            logger.error(f"Error resampling data: {str(e)}")
            raise
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        try:
            df = df.copy()
            
            # Moving Averages
            df["MA_5"] = df["close"].rolling(window=5).mean()
            
            # MACD
            exp12 = df["close"].ewm(span=12, adjust=False).mean()
            exp26 = df["close"].ewm(span=26, adjust=False).mean()
            df["MACD"] = exp12 - exp26
            df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
            df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            raise
    
    def implement_strategy(self, df_15m: pd.DataFrame, df_1h: pd.DataFrame, df_1d: pd.DataFrame) -> pd.DataFrame:
        """Implement the MACD MA CrossOver strategy"""
        try:
            # Initialize signals
            df_15m = df_15m.copy()
            df_15m["Signal"] = 0
            df_15m["Signal_Type"] = ""
            df_15m["Signal_Price"] = 0.0
            df_15m["Signal_Confidence"] = 0.0
            
            in_trade = False
            
            for i in range(5, len(df_15m)):
                current_15m_time = df_15m.index[i]
                
                # Find the most recent 1H and 1D candles
                try:
                    current_1h_candle = df_1h[df_1h.index <= current_15m_time].iloc[-1]
                    current_1d_candle = df_1d[df_1d.index <= current_15m_time].iloc[-1]
                except (IndexError, KeyError):
                    continue
                
                # Buy conditions
                if not in_trade:
                    ma_cross_up = df_15m["MA_5"].iloc[i] > df_15m["close"].iloc[i - 1]
                    all_green = (
                        df_15m["close"].iloc[i] > df_15m["open"].iloc[i]
                        and current_1h_candle["close"] > current_1h_candle["open"]
                        and current_1d_candle["close"] > current_1d_candle["open"]
                    )
                    
                    if ma_cross_up and all_green:
                        df_15m.loc[df_15m.index[i], "Signal"] = 1  # Buy signal
                        df_15m.loc[df_15m.index[i], "Signal_Type"] = "BUY"
                        df_15m.loc[df_15m.index[i], "Signal_Price"] = df_15m["close"].iloc[i]
                        df_15m.loc[df_15m.index[i], "Signal_Confidence"] = 0.8
                        in_trade = True
                
                # Sell conditions
                else:
                    macd_red_histogram = df_15m["MACD_Histogram"].iloc[i] < 0
                    ma_cross_down = (
                        df_15m["MA_5"].iloc[i] < df_15m["MA_5"].iloc[i - 1]
                        and df_15m["MA_5"].iloc[i - 1] >= df_15m["MA_5"].iloc[i - 2]
                    )
                    
                    if macd_red_histogram and ma_cross_down:
                        df_15m.loc[df_15m.index[i], "Signal"] = -1  # Sell signal
                        df_15m.loc[df_15m.index[i], "Signal_Type"] = "SELL"
                        df_15m.loc[df_15m.index[i], "Signal_Price"] = df_15m["close"].iloc[i]
                        df_15m.loc[df_15m.index[i], "Signal_Confidence"] = 0.8
                        in_trade = False
            
            return df_15m
            
        except Exception as e:
            logger.error(f"Error implementing strategy: {str(e)}")
            raise
    
    def backtest_strategy(self, df: pd.DataFrame) -> Dict:
        """Backtest the strategy and calculate performance metrics"""
        try:
            # Market returns
            df["Returns"] = df["close"].pct_change()
            
            # Extract buy & sell prices
            buys = df.loc[df["Signal"] == 1, "close"].reset_index(drop=True)
            sells = df.loc[df["Signal"] == -1, "close"].reset_index(drop=True)
            
            # Align lengths (ignore incomplete last trade)
            n = min(len(buys), len(sells))
            
            if n == 0:
                return {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "total_return": 0.0,
                    "market_return": 0.0,
                    "strategy_return": 0.0,
                    "buy_signals": 0,
                    "sell_signals": 0,
                    "win_rate": 0.0
                }
            
            profits = sells.iloc[:n].values - buys.iloc[:n].values
            trade_returns = profits / buys.iloc[:n].values
            
            # Build a trade return series aligned with sell signals
            strategy_returns = pd.Series(0, index=df.index, dtype=float)
            strategy_returns.loc[df.loc[df["Signal"] == -1].index[:n]] = trade_returns
            
            # Add to df
            df["Strategy_Returns"] = strategy_returns
            df["Cumulative_Market"] = (1 + df["Returns"].fillna(0)).cumprod()
            df["Cumulative_Strategy"] = (1 + df["Strategy_Returns"].fillna(0)).cumprod()
            
            # Calculate performance metrics
            winning_trades = len([p for p in profits if p > 0])
            losing_trades = len([p for p in profits if p <= 0])
            
            market_return = (df["Cumulative_Market"].iloc[-1] - 1) * 100
            strategy_return = (df["Cumulative_Strategy"].iloc[-1] - 1) * 100
            
            return {
                "total_trades": n,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "total_return": strategy_return,
                "market_return": market_return,
                "strategy_return": strategy_return,
                "buy_signals": len(df[df["Signal"] == 1]),
                "sell_signals": len(df[df["Signal"] == -1]),
                "win_rate": (winning_trades / n * 100) if n > 0 else 0.0
            }
            
        except Exception as e:
            logger.error(f"Error in backtesting: {str(e)}")
            raise
    
    def save_signals_to_db(self, df: pd.DataFrame, symbol: str, strategy_name: str):
        """Save trading signals to database"""
        try:
            # Get or create strategy
            strategy, created = TradingStrategy.objects.get_or_create(
                name=strategy_name,
                defaults={
                    'description': 'MACD MA CrossOver Strategy with Multi-Timeframe Analysis',
                    'parameters': {
                        'ma_period': 5,
                        'macd_fast': 12,
                        'macd_slow': 26,
                        'macd_signal': 9
                    }
                }
            )
            
            # Clear existing signals for this symbol and strategy
            TradingSignal.objects.filter(symbol=symbol, strategy=strategy).delete()
            
            # Save new signals
            signals_created = 0
            for index, row in df.iterrows():
                if row["Signal"] != 0:  # Only save actual signals
                    # Ensure all indicator values are JSON serializable
                    indicators_data = {
                        'MA_5': float(row.get("MA_5", 0)) if pd.notna(row.get("MA_5", 0)) else 0.0,
                        'MACD': float(row.get("MACD", 0)) if pd.notna(row.get("MACD", 0)) else 0.0,
                        'MACD_Signal': float(row.get("MACD_Signal", 0)) if pd.notna(row.get("MACD_Signal", 0)) else 0.0,
                        'MACD_Histogram': float(row.get("MACD_Histogram", 0)) if pd.notna(row.get("MACD_Histogram", 0)) else 0.0,
                        'close': float(row["close"]) if pd.notna(row["close"]) else 0.0,
                        'volume': int(row["volume"]) if pd.notna(row["volume"]) else 0,
                        'timestamp': index.isoformat() if hasattr(index, 'isoformat') else str(index)
                    }
                    
                    signal = TradingSignal(
                        symbol=symbol,
                        strategy=strategy,
                        signal_type=row["Signal_Type"],
                        timestamp=index,
                        price=float(row["Signal_Price"]) if pd.notna(row["Signal_Price"]) else 0.0,
                        confidence=float(row["Signal_Confidence"]) if pd.notna(row["Signal_Confidence"]) else 0.0,
                        indicators=indicators_data
                    )
                    signal.save()
                    signals_created += 1
            
            logger.info(f"Saved {signals_created} signals for {symbol}")
            return signals_created
            
        except Exception as e:
            logger.error(f"Error saving signals to database: {str(e)}")
            raise
    
    def save_backtest_results(self, symbol: str, strategy_name: str, backtest_results: Dict, 
                            from_date: datetime, to_date: datetime):
        """Save backtest results to database"""
        try:
            strategy = TradingStrategy.objects.get(name=strategy_name)
            
            # Delete existing backtest results
            StrategyBacktest.objects.filter(
                strategy=strategy,
                symbol=symbol,
                from_date=from_date.date(),
                to_date=to_date.date()
            ).delete()
            
            # Create new backtest record
            backtest = StrategyBacktest(
                strategy=strategy,
                symbol=symbol,
                from_date=from_date.date(),
                to_date=to_date.date(),
                total_trades=int(backtest_results["total_trades"]),
                winning_trades=int(backtest_results["winning_trades"]),
                losing_trades=int(backtest_results["losing_trades"]),
                total_return=float(backtest_results["total_return"]),
                market_return=float(backtest_results["market_return"]),
                strategy_return=float(backtest_results["strategy_return"]),
                buy_signals_count=int(backtest_results["buy_signals"]),
                sell_signals_count=int(backtest_results["sell_signals"]),
                results_data={
                    "total_trades": int(backtest_results["total_trades"]),
                    "winning_trades": int(backtest_results["winning_trades"]),
                    "losing_trades": int(backtest_results["losing_trades"]),
                    "total_return": float(backtest_results["total_return"]),
                    "market_return": float(backtest_results["market_return"]),
                    "strategy_return": float(backtest_results["strategy_return"]),
                    "buy_signals": int(backtest_results["buy_signals"]),
                    "sell_signals": int(backtest_results["sell_signals"]),
                    "win_rate": float(backtest_results["win_rate"])
                }
            )
            backtest.save()
            
            logger.info(f"Saved backtest results for {symbol}")
            return backtest
            
        except Exception as e:
            logger.error(f"Error saving backtest results: {str(e)}")
            raise
    
    def run_strategy_on_file(self, file_path: str, symbol: str) -> Dict:
        """Run complete strategy on a data file"""
        try:
            logger.info(f"Running strategy on file: {file_path}")
            
            # Load data
            df = self.load_data_from_json(file_path)
            
            # Resample data
            resampled_data = self.resample_data(df)
            
            # Calculate indicators for 15-minute data
            df_15m = self.calculate_indicators(resampled_data["15min"])
            df_1h = self.calculate_indicators(resampled_data["1h"])
            df_1d = self.calculate_indicators(resampled_data["1D"])
            
            # Implement strategy
            df_with_signals = self.implement_strategy(df_15m, df_1h, df_1d)
            
            # Backtest strategy
            backtest_results = self.backtest_strategy(df_with_signals)
            
            # Save signals to database
            signals_count = self.save_signals_to_db(df_with_signals, symbol, self.strategy_name)
            
            # Save backtest results
            backtest_record = self.save_backtest_results(
                symbol, 
                self.strategy_name, 
                backtest_results,
                df.index.min(),
                df.index.max()
            )
            
            return {
                "success": True,
                "signals_created": signals_count,
                "backtest_results": backtest_results,
                "backtest_id": backtest_record.id,
                "message": f"Strategy executed successfully. Generated {signals_count} signals."
            }
            
        except Exception as e:
            logger.error(f"Error running strategy: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Strategy execution failed: {str(e)}"
            }
