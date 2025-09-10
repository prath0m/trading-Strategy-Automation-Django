#!/usr/bin/env python3
"""
Test script to verify that the updated validation allows larger date ranges
and that chunked fetching works properly
"""

import os
import sys
import django
from datetime import datetime

# Add the project directory to the Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_dir)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zerodha_app.settings')
django.setup()

from stock_data.forms import DataFetchForm
from stock_data.services import KiteDataService


def test_form_validation():
    """Test that forms now allow larger date ranges"""
    print("🧪 Testing Form Validation Changes")
    print("=" * 50)
    
    # Test cases with different date ranges
    test_cases = [
        {
            'name': 'Small range (30 days)',
            'data': {
                'symbol': 'RELIANCE',
                'from_date': '2024-01-01',
                'to_date': '2024-01-31',
                'interval': 'minute'
            },
            'should_pass': True
        },
        {
            'name': 'Medium range (90 days) - was blocked, now allowed',
            'data': {
                'symbol': 'RELIANCE', 
                'from_date': '2024-01-01',
                'to_date': '2024-04-01',
                'interval': 'minute'
            },
            'should_pass': True
        },
        {
            'name': 'Large range (180 days) - was blocked, now allowed',
            'data': {
                'symbol': 'RELIANCE',
                'from_date': '2023-07-01', 
                'to_date': '2024-01-01',
                'interval': 'minute'
            },
            'should_pass': True
        },
        {
            'name': 'Very large range (400+ days) - should be blocked',
            'data': {
                'symbol': 'RELIANCE',
                'from_date': '2022-01-01',
                'to_date': '2024-01-01', 
                'interval': 'minute'
            },
            'should_pass': False  # This should still be blocked for performance
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        form = DataFetchForm(data=test_case['data'])
        
        is_valid = form.is_valid()
        
        if is_valid and test_case['should_pass']:
            print("   ✅ PASS - Form validation passed as expected")
        elif not is_valid and not test_case['should_pass']:
            print("   ✅ PASS - Form validation failed as expected")
            print(f"   📝 Errors: {form.errors}")
        elif is_valid and not test_case['should_pass']:
            print("   ❌ FAIL - Form should have failed but passed")
        else:
            print("   ❌ FAIL - Form should have passed but failed")
            print(f"   📝 Errors: {form.errors}")


def test_service_chunking():
    """Test that the service can handle larger date ranges with chunking"""
    print("\n\n🔧 Testing Service Chunking Capabilities")
    print("=" * 50)
    
    service = KiteDataService()
    
    # Test different scenarios
    scenarios = [
        {
            'name': '2 years of minute data (chunked)',
            'symbol': 'RELIANCE',
            'from_date': '2022-01-01',
            'to_date': '2024-01-01',
            'interval': 'minute'
        },
        {
            'name': '6 months of minute data (chunked)', 
            'symbol': 'RELIANCE',
            'from_date': '2023-07-01',
            'to_date': '2024-01-01',
            'interval': 'minute'
        },
        {
            'name': '3 years of daily data (single call)',
            'symbol': 'RELIANCE',
            'from_date': '2021-01-01',
            'to_date': '2024-01-01',
            'interval': 'day'
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📊 Testing: {scenario['name']}")
        
        try:
            # Get fetch information
            info = service.get_fetch_info(
                symbol=scenario['symbol'],
                from_date=scenario['from_date'],
                to_date=scenario['to_date'],
                interval=scenario['interval']
            )
            
            print(f"   📈 Strategy: {info['fetch_strategy']}")
            print(f"   📊 Expected records: {info['expected_records']:,}")
            print(f"   🔄 API calls needed: {info['estimation']['chunks_needed']}")
            print(f"   ⏱️  Estimated time: {info['estimated_time_seconds']} seconds")
            
            # Validate parameters
            validation = service.validate_fetch_parameters(
                symbol=scenario['symbol'],
                from_date=scenario['from_date'],
                to_date=scenario['to_date'],
                interval=scenario['interval']
            )
            
            if validation['valid']:
                print("   ✅ Parameters are valid")
            else:
                print("   ⚠️  Validation warnings:")
                for warning in validation['warnings']:
                    print(f"      • {warning}")
                    
            print("   ✅ Service test completed")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")


def test_data_fetching():
    """Test actual data fetching with chunking (small test)"""
    print("\n\n📡 Testing Actual Data Fetching")
    print("=" * 50)
    
    service = KiteDataService()
    
    # Test a small range that requires chunking for minute data
    print("📊 Testing: 90 days of minute data (should use chunked fetching)")
    
    try:
        # This should now work without the 60-day limit error
        data = service.fetch_historical_data_chunked(
            symbol='RELIANCE',
            from_date='2024-01-01',
            to_date='2024-04-01',  # 90 days
            interval='minute'
        )
        
        print(f"   ✅ Successfully fetched {len(data)} records")
        if data:
            print(f"   📅 Date range: {data[0]['date']} to {data[-1]['date']}")
            print(f"   📊 Sample record: {data[0]}")
            
    except Exception as e:
        print(f"   ❌ Error during fetch: {str(e)}")


if __name__ == "__main__":
    try:
        test_form_validation()
        test_service_chunking()
        test_data_fetching()
        
        print("\n" + "=" * 60)
        print("🎉 VALIDATION UPDATE TESTING COMPLETED")
        print("=" * 60)
        print("\n💡 Summary of Changes:")
        print("   • Forms now allow larger date ranges")
        print("   • Validation focuses on performance rather than API limits")
        print("   • JavaScript validation updated to match")
        print("   • Chunked fetching handles the API limits automatically")
        print("   • Users get helpful warnings instead of hard blocks")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
