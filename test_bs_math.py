
import math

def calculate_greeks_black_scholes(S, K, T, sigma, r=0.045, opt_type='call'):
    """Test version of the method implemented in HybridScannerService"""
    if T <= 0 or sigma <= 0:
        return {'delta': 0, 'gamma': 0, 'theta': 0}
        
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        # Cumulative Distribution Function (CDF)
        def N(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))
        
        # Probability Density Function (PDF)
        def N_prime(x):
            return (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x ** 2)
        
        if opt_type.lower() == 'call':
            delta = N(d1)
            theta = (- (S * N_prime(d1) * sigma) / (2 * math.sqrt(T)) 
                        - r * K * math.exp(-r * T) * N(d2)) / 365.0
        else: # Put
            delta = N(d1) - 1
            theta = (- (S * N_prime(d1) * sigma) / (2 * math.sqrt(T)) 
                        + r * K * math.exp(-r * T) * N(-d2)) / 365.0
            
        gamma = N_prime(d1) / (S * sigma * math.sqrt(T))
        
        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 4),
            'theta': round(theta, 4)
        }
    except Exception as e:
        print(f"Error: {e}")
        return {}

def test_bs():
    # ATM Call: S=100, K=100, T=1yr, Vol=30%, r=5%
    greeks = calculate_greeks_black_scholes(100, 100, 1.0, 0.30, 0.05, 'call')
    print("ATM Call (S=100, K=100, T=1, Vol=30%):")
    print(f"  Delta: {greeks['delta']} (Expected ~0.59)")
    print(f"  Gamma: {greeks['gamma']} (Expected ~0.013)")
    print(f"  Theta: {greeks['theta']} (Expected ~-0.017 daily)")

    # OTM Put: S=100, K=90
    greeks_put = calculate_greeks_black_scholes(100, 90, 1.0, 0.30, 0.05, 'put')
    print("\nOTM Put (S=100, K=90, T=1, Vol=30%):")
    print(f"  Delta: {greeks_put['delta']} (Expected ~ -0.21)")

if __name__ == "__main__":
    test_bs()
