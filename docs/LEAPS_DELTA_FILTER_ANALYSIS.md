# LEAPS Delta Filter — Cost Cap Conflict Analysis & Fix

> **Source**: [options_analyzer.py](file:///c:/Users/olasu/.gemini/antigravity/Options/backend/analysis/options_analyzer.py)  
> **Date**: 2026-02-16  
> **Status**: ✅ Implemented

---

## Problem Statement

The LEAPS scanner's delta filter (0.50–0.80) conflicted with the $2,000 max cost cap for stocks priced above ~$100. This created a **dead zone** where no option could pass both filters simultaneously.

### Evidence from Live Scans

| Ticker | Price | LEAPs (Before) | Root Cause |
|--------|-------|----------------|------------|
| **NVDA** | $182 | **0** | Delta 0.50 = ATM ~$2,500+ cost |
| **SNDK** | $625 | **0** | Delta 0.50 = ATM ~$6,000+ cost |
| **GOOGL** | $305 | **2** | Barely works — edge of affordability |

---

## Fix Applied: Foolproof Three-Layer Defense

### Old Logic (Broken)
```python
# Delta 0.50-0.80 hard filter — conflicted with $2000 cost cap
if is_leap and (delta < 0.50 or delta > 0.80):
    continue
```

### New Logic (Foolproof)
```python
# Layer 1: Hard floor 0.15 — blocks true lotto tickets (safety net)
# Layer 2: Hard ceiling 0.80 — blocks deep ITM stock replacement
# Layer 3: 30% profit floor (downstream) — effective delta floor ~0.38
if is_leap and not is_pricing_anomaly:
    if delta > 0.80:
        continue   # Block stock replacement
    if delta < 0.15:
        continue   # Block extreme lotto tickets
# Cost cap ($2000) and profit floor (30%) handle the rest
```

### Why This Works — The Math Proof

The 30% profit floor assumes a 15% stock move. For NVDA at $182 (target = $209.30):

| Strike | Delta | Intrinsic at Target | Premium | Profit % | Passes 30%? |
|--------|-------|---------------------|---------|----------|-------------|
| $230 | ~0.15 | $0 | ~$3 | -100% | ❌ |
| $220 | ~0.22 | $0 | ~$5 | -100% | ❌ |
| $210 | ~0.30 | $0 | ~$8 | -100% | ❌ |
| $200 | ~0.35 | $9.30 | ~$8 | 16% | ❌ |
| $195 | ~0.40 | $14.30 | ~$10 | 43% | ✅ |

**Result**: Profit floor creates effective delta floor of ~0.38-0.42 automatically.

### All Remaining Protections

| Layer | Filter | What It Blocks |
|-------|--------|----------------|
| 1 | Delta > 0.80 | Deep ITM (stock replacement) |
| 2 | Delta < 0.15 | Extreme lotto tickets (hard floor safety net) |
| 3 | Profit ≥ 30% | Low-probability junk (effective delta ~0.38) |
| 4 | Cost ≤ $2,000 | Limits max risk per trade |
| 5 | OI ≥ 10 | Ensures market liquidity |

---

## NewScanner Migration

Apply the same change to `Scanner/NewScanner/analysis/` if a similar delta filter exists.

### Before
```python
# If using delta 0.50-0.80 filter:
if is_leap and (delta < 0.50 or delta > 0.80):
    continue
```

### After
```python
if is_leap:
    if delta > 0.80:
        continue   # Block deep ITM
    if delta < 0.15:
        continue   # Block extreme lotto tickets
# Let cost cap + profit floor handle quality
```

### Checklist for NewScanner
- [ ] Find delta filter in options analyzer
- [ ] Replace 0.50-0.80 with 0.15-0.80
- [ ] Verify 30% profit floor exists downstream
- [ ] Verify cost cap exists downstream
- [ ] Test with NVDA LEAPS scan
