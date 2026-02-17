
import sys
import os

# Add current directory (Project Root) to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.services.reasoning_engine import ReasoningEngine

def test_conviction():
    engine = ReasoningEngine()
    
    # CASE 1: Perfect Setup (AMAT-like)
    ctx1 = {
        'technicals': {
            'score': 80,
            'volume_zscore': 2.1,
            'ma_signal': 'bullish'
        },
        'sentiment': {'score': 100}
    }
    
    # CASE 2: Weak Setup (AVGO-like)
    ctx2 = {
        'technicals': {
            'score': 50,
            'volume_zscore': -0.6,
            'ma_signal': 'pullback_bullish'
        },
        'sentiment': {'score': 50}
    }
    
    # CASE 3: Breakdown (Bearish)
    ctx3 = {
        'technicals': {
            'score': 20,
            'volume_zscore': -1.2,
            'ma_signal': 'breakdown'
        },
        'sentiment': {'score': 20}
    }

    print(f"--- Conviction Score Logic Test ---")
    
    # Test 1
    s1 = engine.calculate_base_score(ctx1['technicals'], ctx1['sentiment'])
    print(f"Case 1 (Perfect): Tech=80, Sent=100, Vol=2.1 (surging), MA=bullish")
    print(f"   -> Expected: ~90 (Max)")
    print(f"   -> Actual:   {s1}")
    
    # Test 2
    s2 = engine.calculate_base_score(ctx2['technicals'], ctx2['sentiment'])
    print(f"\nCase 2 (Weak): Tech=50, Sent=50, Vol=-0.6 (weak), MA=pullback")
    print(f"   -> Expected: 50 + 0 + 0 - 5 + 5 = 50")
    print(f"   -> Actual:   {s2}")
    
    # Test 3
    s3 = engine.calculate_base_score(ctx3['technicals'], ctx3['sentiment'])
    print(f"\nCase 3 (Breakdown): Tech=20, Sent=20, Vol=-1.2 (weak), MA=breakdown")
    print(f"   -> Expected: 50 - 18 - 12 - 5 - 15 = 0 -> Clamped 10")
    print(f"   -> Actual:   {s3}")

if __name__ == "__main__":
    test_conviction()
