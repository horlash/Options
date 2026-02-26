import sys
sys.path.insert(0, '/app')
from backend.api.orats import OratsAPI
api = OratsAPI()
chain = api.get_option_chain('EWY')
if not chain:
    print("ERROR: get_option_chain returned None")
    sys.exit(1)

print(f"Symbol: {chain.get('symbol')}")
print(f"Call keys: {list(chain.get('callExpDateMap', {}).keys())[:5]}")
print(f"Put keys: {list(chain.get('putExpDateMap', {}).keys())[:5]}")

# Check a near-money call
for key, strikes in chain.get('callExpDateMap', {}).items():
    if '2026-02-27' in key:
        for sk, opts in strikes.items():
            s = float(sk)
            if abs(s - 153) < 5:
                for o in opts:
                    print(f"\n{key} ${sk} CALL:")
                    print(f"  bid={o.get('bid')} ask={o.get('ask')} last={o.get('last')} mark={o.get('mark')}")
                    print(f"  vol={o.get('totalVolume')} oi={o.get('openInterest')} delta={o.get('delta')}")
                break
        break
